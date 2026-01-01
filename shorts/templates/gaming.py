"""Gaming template with MediaPipe facecam detection and stable 9:16 layout."""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Tuple, Optional

# Support both MoviePy 1.x and 2.x
try:
    # MoviePy 2.x - try different import paths
    from moviepy import ColorClip, VideoClip, VideoFileClip
    from moviepy.video.fx import MultiplySpeed

    # Try lowercase crop function first
    try:
        from moviepy.video.fx.crop import crop
    except (ImportError, ModuleNotFoundError):
        # Try uppercase Crop class
        try:
            from moviepy.video.fx.Crop import Crop as crop
        except (ImportError, ModuleNotFoundError):
            # Try vfx module
            from moviepy import vfx
            crop = vfx.crop

    MOVIEPY_V2 = True
except ImportError:
    # MoviePy 1.x
    from moviepy.editor import ColorClip, VideoClip, VideoFileClip
    from moviepy.video.fx.all import speedx as vfx_speedx, crop as vfx_crop
    MultiplySpeed = None
    crop = None
    MOVIEPY_V2 = False

from shorts.face_detection import FaceDetector, FaceRegion
from utils import video as video_utils
from utils.video import (
    apply_speedup,
    burn_subtitles_ffmpeg,
    center_crop_9_16,
    ensure_fps,
    ensure_output_path,
    load_subclip,
    write_srt,
    FpsFixedCompositeVideoClip,
)
from .base import TemplateBase

logger = logging.getLogger(__name__)


def render_with_ffmpeg(clip: VideoClip, output_path: Path, fps: int = 30) -> None:
    """Bypass MoviePy's broken write_videofile() and call ffmpeg directly.

    MoviePy's use_clip_fps_by_default decorator ignores explicit fps parameters,
    so we need to render frames and audio separately, then combine with ffmpeg.
    """
    import numpy as np
    from moviepy.video.io.ffmpeg_writer import FFMPEG_VideoWriter

    logger.info("Direct ffmpeg render: %s at %d fps", output_path, fps)

    # Create temporary files for video and audio
    temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
    temp_audio = tempfile.NamedTemporaryFile(suffix='.mp3', delete=False)
    temp_video_path = temp_video.name
    temp_audio_path = temp_audio.name
    temp_video.close()
    temp_audio.close()

    try:
        # Write video with explicit fps using FFMPEG_VideoWriter directly
        writer = FFMPEG_VideoWriter(
            temp_video_path,
            clip.size,
            fps,  # EXPLICIT FPS - not from clip.fps!
            codec='libx264',
            preset='medium',
            bitrate=None,
            audiofile=None,  # No audio yet
            threads=2,
            ffmpeg_params=None
        )

        # Write frames
        logger.debug("Writing %d frames at %d fps", int(clip.duration * fps), fps)
        for t in np.arange(0, clip.duration, 1.0 / fps):
            frame = clip.get_frame(t)
            writer.write_frame(frame)

        writer.close()
        logger.debug("Video frames written to %s", temp_video_path)

        # Write audio if present
        if clip.audio is not None:
            logger.debug("Writing audio to %s", temp_audio_path)
            clip.audio.write_audiofile(
                temp_audio_path,
                codec='mp3',
                bitrate='192k',
                verbose=False,
                logger=None
            )

            # Combine video and audio using ffmpeg subprocess
            logger.debug("Combining video and audio with ffmpeg")
            subprocess.run([
                'ffmpeg',
                '-y',  # Overwrite output
                '-i', temp_video_path,
                '-i', temp_audio_path,
                '-c:v', 'copy',  # Copy video stream
                '-c:a', 'aac',  # Re-encode audio to AAC
                '-b:a', '192k',
                '-shortest',  # Match shortest stream duration
                str(output_path)
            ], check=True, capture_output=True)
        else:
            # No audio, just copy video
            logger.debug("No audio, copying video file")
            Path(temp_video_path).rename(output_path)

        logger.info("✓ Rendered successfully: %s", output_path)

    finally:
        # Cleanup temp files
        try:
            Path(temp_video_path).unlink(missing_ok=True)
        except:
            pass
        try:
            Path(temp_audio_path).unlink(missing_ok=True)
        except:
            pass




class GamingTemplate(TemplateBase):
    """Gaming template with automatic facecam detection and PIP overlay.

    Uses MediaPipe Face Detection to automatically locate and crop the
    streamer's facecam, then creates a picture-in-picture layout.

    If no face is detected, falls back to gameplay-only 9:16 crop.
    """

    name = "gaming"

    def __init__(
        self,
        face_regions: Iterable[str] | None = None,
        face_detector: Optional[FaceDetector] = None
    ):
        """Initialize gaming template

        Args:
            face_regions: Allowed face detection zones (for backward compat, unused)
            face_detector: Optional pre-configured FaceDetector instance
        """
        self.face_detector = face_detector or FaceDetector(
            confidence_threshold=0.1,  # Very low threshold to catch all faces
            consensus_threshold=0.1,   # Very low consensus (1 out of 20 samples)
            num_samples=20             # Many samples for thorough detection
        )

    def apply(
        self,
        video_path: Path,
        start: float,
        end: float,
        output_path: Path,
        speedup: float = 1.0,
        enable_subtitles: bool = False,
        subtitles: Iterable[Tuple[str, float, float]] | None = None,
        subtitle_lang: str = "pl",
        copyright_processor=None,
        idx: int | None = None,
    ) -> Path | None:
        logger.info("[GamingTemplate][%02d] Rendering segment %.2f-%.2f", idx or 0, start, end)
        output_path = ensure_output_path(Path(output_path))
        segment_duration = max(0.1, end - start)

        clip = load_subclip(video_path, start, end)
        if clip is None or clip.duration is None or clip.duration <= 0:
            logger.warning("[GamingTemplate] Hard failure loading clip — using black fallback")
            clip = ensure_fps(
                ColorClip(size=(1080, 1920), color=(0, 0, 0), duration=segment_duration)
            )
        else:
            # ✅ FIX: Only set_duration if clip has the method (ColorClip doesn't)
            if hasattr(clip, 'set_duration') and callable(getattr(clip, 'set_duration')):
                clip = ensure_fps(clip.set_duration(segment_duration))
            else:
                clip = ensure_fps(clip)

        logger.debug("Clip FPS after load and duration set: %s", clip.fps)

        subtitles_data = list(subtitles or [])

        # Detect facecam region using MediaPipe
        face_region = self.face_detector.detect(Path(video_path), start, end)
        if face_region:
            logger.info(
                "[GamingTemplate] Facecam detected in zone: %s (confidence: %.2f)",
                face_region.zone,
                face_region.confidence
            )
        else:
            logger.info("[GamingTemplate] No facecam detected, using gameplay-only layout")

        try:
            gameplay_clip = center_crop_9_16(clip)
            logger.debug("Clip FPS after gameplay crop: %s", gameplay_clip.fps)
            if speedup and speedup > 1.0:
                try:
                    if MOVIEPY_V2:
                        gameplay_clip = ensure_fps(gameplay_clip.fx(MultiplySpeed, factor=speedup))
                    else:
                        gameplay_clip = ensure_fps(gameplay_clip.fx(vfx_speedx, speedup))
                    logger.debug("Clip FPS after video speedup: %s", gameplay_clip.fps)
                    if gameplay_clip.audio:
                        new_audio = apply_speedup(gameplay_clip.audio, speedup)
                        gameplay_clip = gameplay_clip.set_audio(new_audio)
                except Exception:
                    logger.exception("[GamingTemplate] Speedup failed — using original speed")

            if copyright_processor:
                gameplay_clip = copyright_processor.clean_clip_audio(
                    gameplay_clip, video_path, start, end, output_path.stem
                )

            # ✅ FIX: Only set_duration if clip has the method (ColorClip doesn't)
            if hasattr(gameplay_clip, 'set_duration') and callable(getattr(gameplay_clip, 'set_duration')):
                gameplay_clip = ensure_fps(gameplay_clip.set_duration(segment_duration))
            else:
                gameplay_clip = ensure_fps(gameplay_clip)
            logger.debug("Clip FPS before layout: %s", gameplay_clip.fps)

            if face_region:
                final = self._build_layout_with_face(
                    clip, gameplay_clip, face_region
                )
            else:
                # No face detected - use fixed facecam position (left bottom)
                logger.info("[GamingTemplate] Using fixed facecam fallback (left bottom)")
                final = self._build_layout_with_fixed_facecam(
                    clip, gameplay_clip
                )

            # Get fps from layout BEFORE transformations
            target_fps = getattr(final, "fps", None) or 30
            logger.debug("Clip FPS from layout: %s", target_fps)

            # set_duration returns a NEW clip, restore fps
            final = final.set_duration(segment_duration)
            final = ensure_fps(final, fallback=target_fps)

            # Set audio from gameplay clip
            if gameplay_clip.audio is not None:
                final = final.set_audio(gameplay_clip.audio)
                # set_audio also returns a new clip, restore fps again
                final = ensure_fps(final, fallback=target_fps)

            render_target = output_path
            if enable_subtitles and subtitles_data:
                render_target = output_path.with_name(f"{output_path.stem}_nosub{output_path.suffix}")

            logger.info(
                "Rendering video with direct ffmpeg (fps=30) → %s", render_target.name
            )
            render_with_ffmpeg(final, render_target, fps=30)
            final.close()
            clip.close()

            if enable_subtitles and subtitles_data:
                srt_path = render_target.with_suffix(".srt")
                write_srt(subtitles_data, srt_path)
                burn_subtitles_ffmpeg(str(render_target), str(srt_path), str(output_path))
                try:
                    Path(render_target).unlink(missing_ok=True)
                    Path(srt_path).unlink(missing_ok=True)
                except Exception:
                    logger.debug("Cleanup of temporary subtitle artifacts failed", exc_info=True)
            return output_path
        except Exception:
            logger.exception("[GamingTemplate] Hard failure during render")
            try:
                duration = segment_duration
                fallback_clip = ColorClip(
                    size=(1080, 1920), color=(0, 0, 0), duration=duration
                )
                fallback_clip = ensure_fps(fallback_clip, fallback=30)

                # ✅ FIX: ColorClip doesn't support set_audio, skip audio in fallback
                # (Fallback is black screen anyway, audio not critical)

                # BYPASS MoviePy's broken write_videofile() - use direct ffmpeg
                render_target = output_path
                if enable_subtitles and subtitles_data:
                    render_target = output_path.with_name(f"{output_path.stem}_nosub{output_path.suffix}")

                logger.info("Rendering fallback video with direct ffmpeg (fps=30) → %s", render_target.name)
                render_with_ffmpeg(fallback_clip, render_target, fps=30)
                fallback_clip.close()
                if enable_subtitles and subtitles_data:
                    srt_path = render_target.with_suffix(".srt")
                    write_srt(subtitles_data, srt_path)
                    burn_subtitles_ffmpeg(str(render_target), str(srt_path), str(output_path))
                    try:
                        Path(render_target).unlink(missing_ok=True)
                        Path(srt_path).unlink(missing_ok=True)
                    except Exception:
                        logger.debug("Cleanup of temporary subtitle artifacts failed", exc_info=True)
            except Exception:
                logger.exception("[GamingTemplate] Fallback clip rendering failed")
            try:
                clip.close()
            except Exception:
                pass
            return output_path

    def _build_layout_with_face(
        self,
        source_clip: VideoFileClip,
        gameplay_clip: VideoFileClip,
        face_region: FaceRegion,
    ) -> VideoClip:
        """Build split layout with gameplay on top and detected facecam bar at bottom.

        Layout:
        - Top 80%: Gameplay (centered, zoomed out more) ✅ User requested
        - Bottom 20%: Facecam (full width bar from detected region) ✅ User requested

        Args:
            source_clip: Original video clip (full frame)
            gameplay_clip: Already processed gameplay clip
            face_region: Detected face region with bbox and zone info

        Returns:
            Composite video clip with split layout
        """
        target_w, target_h = 1080, 1920

        # Split layout: 80% gameplay top, 20% facecam bottom (user requested)
        gameplay_h = int(target_h * 0.80)  # ✅ Changed from 70% to 80%
        facecam_h = int(target_h * 0.20)   # ✅ Changed from 30% to 20%

        # Prepare gameplay for top section (centered, zoomed out more)
        gameplay_full = center_crop_9_16(gameplay_clip, scale=0.80)  # ✅ More zoom out (was 0.85)

        # ✅ FIX: Check if ColorClip (no resize/set_duration methods)
        if hasattr(gameplay_full, 'resize') and hasattr(gameplay_full, 'set_duration'):
            gameplay_full = ensure_fps(gameplay_full.resize((target_w, gameplay_h)).set_duration(source_clip.duration))
            gameplay_full = gameplay_full.set_position((0, 0))  # Top
        else:
            # ColorClip fallback - recreate with correct size
            # Position will be set automatically by CompositeVideoClip (defaults to 0,0)
            from moviepy.video.VideoClip import ColorClip
            gameplay_full = ColorClip(size=(target_w, gameplay_h), color=(0, 0, 0), duration=source_clip.duration)
            gameplay_full = ensure_fps(gameplay_full)

        logger.debug("Clip FPS after gameplay resize: %s", gameplay_full.fps)

        # Use actual detected face bbox with padding for tight, centered framing
        src_w, src_h = source_clip.size

        # Extract face bbox (x, y, w, h) from detection
        face_x, face_y, face_w, face_h = face_region.bbox

        # Calculate face center
        face_center_x = face_x + face_w // 2
        face_center_y = face_y + face_h // 2

        # Create rectangular crop (tighter zoom on face for better fit in smaller bar)
        # Bottom bar is now 1080×384 (2.8:1 ratio), so crop wider
        face_size = max(face_w, face_h)
        crop_width = int(face_size * 4.0)   # ✅ Tighter zoom (was 5.5) - closer face
        crop_height = int(face_size * 2.2)  # ✅ Tighter zoom (was 3.0) - closer face
        # Aspect ratio: ~1.82 (fits better in narrower bottom bar)

        # Create rectangular crop centered on face
        x1 = face_center_x - crop_width // 2
        y1 = face_center_y - crop_height // 2
        x2 = x1 + crop_width
        y2 = y1 + crop_height

        # Ensure crop stays within frame boundaries
        if x1 < 0:
            x2 -= x1
            x1 = 0
        if y1 < 0:
            y2 -= y1
            y1 = 0
        if x2 > src_w:
            x1 -= (x2 - src_w)
            x2 = src_w
        if y2 > src_h:
            y1 -= (y2 - src_h)
            y2 = src_h

        # Clamp to valid range
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(src_w, x2)
        y2 = min(src_h, y2)

        facecam_w_actual = x2 - x1
        facecam_h_actual = y2 - y1
        aspect_ratio = facecam_w_actual / facecam_h_actual

        logger.info(
            "[GamingTemplate] Face detected in zone '%s' → using bbox-based crop %dx%d (AR: %.2f) at (%d,%d)",
            face_region.zone, facecam_w_actual, facecam_h_actual, aspect_ratio, x1, y1
        )
        logger.info(
            "[GamingTemplate] Original face bbox: %dx%d at (%d,%d), crop: 5.5x wide × 3.0x tall",
            face_w, face_h, face_x, face_y
        )

        # Crop facecam region (MoviePy crop)
        if MOVIEPY_V2:
            # MoviePy 2.x: crop is a function (no .fx() method exists in v2)
            face_clip = crop(source_clip, x1=x1, y1=y1, x2=x2, y2=y2)
        else:
            # MoviePy 1.x: Use fx API
            face_clip = source_clip.fx(vfx_crop, x1=x1, y1=y1, x2=x2, y2=y2)
        face_clip = ensure_fps(face_clip.set_duration(source_clip.duration))

        # Scale to fill bottom bar height while preserving aspect ratio
        # With wider crop (1.83:1), this should fill most of the width naturally
        new_facecam_h = facecam_h  # Full bottom bar height (576px)
        new_facecam_w = int(new_facecam_h * aspect_ratio)  # Scale width proportionally

        # If width exceeds target, scale down to fit width instead
        if new_facecam_w > target_w:
            new_facecam_w = target_w
            new_facecam_h = int(new_facecam_w / aspect_ratio)

        face_clip = face_clip.resize((new_facecam_w, new_facecam_h))

        # Center horizontally in bottom bar, align to top
        facecam_x = (target_w - new_facecam_w) // 2  # Center horizontally
        facecam_y = gameplay_h  # Align to top of bottom section (no padding)

        face_clip = face_clip.set_position((facecam_x, facecam_y))
        logger.debug("Clip FPS after facecam crop: %s", face_clip.fps)
        logger.info(
            "[GamingTemplate] Facecam positioned: %dx%d at (%d, %d) - natural aspect ratio %.2f",
            new_facecam_w, new_facecam_h, facecam_x, facecam_y, aspect_ratio
        )

        # Create black background for bottom bar (for padding around facecam)
        black_bg = ColorClip(
            size=(target_w, facecam_h),
            color=(0, 0, 0),
            duration=source_clip.duration
        )
        black_bg = ensure_fps(black_bg)
        black_bg = black_bg.set_position((0, gameplay_h))  # Bottom bar

        # Composite: gameplay (top) + black background (bottom) + facecam (centered on black)
        final = FpsFixedCompositeVideoClip(
            [gameplay_full, black_bg, face_clip],
            size=(target_w, target_h),
            fps=30,
        ).set_duration(source_clip.duration)
        logger.debug("Clip FPS after composite (split layout): %s", final.fps)
        logger.info("[GamingTemplate] Using split layout with detected face: gameplay top (80%), facecam bar bottom (20%)")  # ✅ Updated percentages
        return final

    def _build_layout_with_fixed_facecam(
        self,
        source_clip: VideoFileClip,
        gameplay_clip: VideoFileClip,
    ) -> VideoClip:
        """Build split layout with gameplay on top and facecam bar at bottom.

        Tries to detect facecam in all 4 corners and uses the one with a face.
        Falls back to left bottom if no face found anywhere.

        Layout:
        - Top 80%: Gameplay (centered, zoomed out more) ✅ User requested
        - Bottom 20%: Facecam (full width bar) ✅ User requested

        Args:
            source_clip: Original video clip (full frame)
            gameplay_clip: Already processed gameplay clip

        Returns:
            Composite video clip with split layout
        """
        target_w, target_h = 1080, 1920

        # Split layout: 80% gameplay top, 20% facecam bottom (user requested)
        gameplay_h = int(target_h * 0.80)  # ✅ Changed from 70% to 80%
        facecam_h = int(target_h * 0.20)   # ✅ Changed from 30% to 20%

        # Prepare gameplay for top section (centered, zoomed out more)
        gameplay_full = center_crop_9_16(gameplay_clip, scale=0.80)  # ✅ More zoom out (was 0.85)

        # ✅ FIX: Check if ColorClip (no resize/set_duration methods)
        if hasattr(gameplay_full, 'resize') and hasattr(gameplay_full, 'set_duration'):
            gameplay_full = ensure_fps(gameplay_full.resize((target_w, gameplay_h)).set_duration(source_clip.duration))
            gameplay_full = gameplay_full.set_position((0, 0))  # Top
        else:
            # ColorClip fallback - recreate with correct size
            # Position will be set automatically by CompositeVideoClip (defaults to 0,0)
            from moviepy.video.VideoClip import ColorClip
            gameplay_full = ColorClip(size=(target_w, gameplay_h), color=(0, 0, 0), duration=source_clip.duration)
            gameplay_full = ensure_fps(gameplay_full)

        logger.debug("Clip FPS after gameplay resize: %s", gameplay_full.fps)

        # Try to find facecam in multiple regions (smaller regions to match actual facecam size)
        src_w, src_h = source_clip.size

        # Square regions (35% width x 35% height) for each zone
        facecam_h_percent = 0.35  # 35% of height
        facecam_w_percent = 0.35  # 35% of width
        facecam_w = int(src_w * facecam_w_percent)
        facecam_h_src = int(src_h * facecam_h_percent)

        # Since face detection is unreliable, just use right_top directly
        # This is where the facecam is in your VOD based on the screenshot
        logger.info("[GamingTemplate] Using fixed right_top region (35%x35%) for facecam")

        best_region = "right_top"
        center_x = (src_w - facecam_w) // 2  # Center horizontally
        regions = {
            # Left edge
            "left_top": (0, 0, facecam_w, facecam_h_src),
            "left_middle": (0, (src_h - facecam_h_src) // 2, facecam_w, (src_h + facecam_h_src) // 2),
            "left_bottom": (0, src_h - facecam_h_src, facecam_w, src_h),
            # Center column
            "center_top": (center_x, 0, center_x + facecam_w, facecam_h_src),
            "center_bottom": (center_x, src_h - facecam_h_src, center_x + facecam_w, src_h),
            # Right edge
            "right_top": (src_w - facecam_w, 0, src_w, facecam_h_src),
            "right_middle": (src_w - facecam_w, (src_h - facecam_h_src) // 2, src_w, (src_h + facecam_h_src) // 2),
            "right_bottom": (src_w - facecam_w, src_h - facecam_h_src, src_w, src_h),
        }

        x1, y1, x2, y2 = regions[best_region]
        logger.info(
            "[GamingTemplate] Using facecam region: %s (%dx%d at %d,%d)",
            best_region, x2-x1, y2-y1, x1, y1
        )

        # Crop facecam region (MoviePy crop)
        if MOVIEPY_V2:
            # MoviePy 2.x: crop is a function (no .fx() method exists in v2)
            face_clip = crop(source_clip, x1=x1, y1=y1, x2=x2, y2=y2)
        else:
            # MoviePy 1.x: Use fx API
            face_clip = source_clip.fx(vfx_crop, x1=x1, y1=y1, x2=x2, y2=y2)
        face_clip = ensure_fps(face_clip.set_duration(source_clip.duration))

        # Calculate aspect ratio and resize preserving it
        facecam_w_actual = x2 - x1
        facecam_h_actual = y2 - y1
        aspect_ratio = facecam_w_actual / facecam_h_actual

        # Resize to fill 100% of bottom bar width, preserving aspect ratio
        target_facecam_w = int(target_w * 1.0)  # 100% of 1080px = full width
        new_facecam_w = target_facecam_w
        new_facecam_h = int(target_facecam_w / aspect_ratio)

        # If height exceeds bottom bar, scale down to fit
        if new_facecam_h > facecam_h:
            new_facecam_h = facecam_h
            new_facecam_w = int(facecam_h * aspect_ratio)

        face_clip = face_clip.resize((new_facecam_w, new_facecam_h))

        # Center facecam horizontally in the bottom bar
        facecam_x = (target_w - new_facecam_w) // 2
        facecam_y = gameplay_h + (facecam_h - new_facecam_h) // 2  # Center vertically too

        face_clip = face_clip.set_position((facecam_x, facecam_y))
        logger.debug("Clip FPS after fixed facecam crop: %s", face_clip.fps)
        logger.info(
            "[GamingTemplate] Fixed facecam positioned: %dx%d at (%d, %d) - aspect ratio preserved!",
            new_facecam_w, new_facecam_h, facecam_x, facecam_y
        )

        # Create black background for bottom bar (for padding around facecam)
        black_bg = ColorClip(
            size=(target_w, facecam_h),
            color=(0, 0, 0),
            duration=source_clip.duration
        )
        black_bg = ensure_fps(black_bg)
        black_bg = black_bg.set_position((0, gameplay_h))  # Bottom bar

        # Composite: gameplay (top) + black background (bottom) + facecam (centered on black)
        final = FpsFixedCompositeVideoClip(
            [gameplay_full, black_bg, face_clip],
            size=(target_w, target_h),
            fps=30,
        ).set_duration(source_clip.duration)
        logger.debug("Clip FPS after composite (split layout): %s", final.fps)
        logger.info("[GamingTemplate] Using split layout: gameplay top (80%), facecam bar bottom (20%)")  # ✅ Updated percentages
        return final

    def _build_layout_gameplay_only(self, gameplay_clip: VideoFileClip) -> VideoClip:
        """Build gameplay-only layout (no facecam) - zoomed out to see more."""
        target_w, target_h = 1080, 1920
        gameplay_full = center_crop_9_16(gameplay_clip, scale=0.80)  # ✅ More zoom out for consistency (was 0.85)

        # ✅ FIX: Check if ColorClip (no resize/set_duration methods)
        if hasattr(gameplay_full, 'resize') and hasattr(gameplay_full, 'set_duration'):
            gameplay_full = ensure_fps(gameplay_full.resize((target_w, target_h)).set_duration(gameplay_clip.duration))
        else:
            # ColorClip fallback - recreate with correct size
            from moviepy.video.VideoClip import ColorClip
            gameplay_full = ColorClip(size=(target_w, target_h), color=(0, 0, 0), duration=gameplay_clip.duration)
            gameplay_full = ensure_fps(gameplay_full)

        logger.debug("Clip FPS after gameplay-only layout: %s", gameplay_full.fps)
        return gameplay_full

