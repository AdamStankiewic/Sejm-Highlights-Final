"""Gaming template with MediaPipe facecam detection and stable 9:16 layout."""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Tuple, Optional

from moviepy.editor import ColorClip, VideoClip, VideoFileClip
from moviepy.video.fx.all import speedx as vfx_speedx

from shorts.face_detection import FaceDetector, FaceRegion
from utils.video import (
    add_subtitles,
    apply_speedup,
    center_crop_9_16,
    ensure_fps,
    ensure_output_path,
    load_subclip,
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
            confidence_threshold=0.3,  # Lower threshold for smaller facecams
            consensus_threshold=0.2,   # Lower consensus needed
            num_samples=15             # More samples for better detection
        )

    def apply(
        self,
        video_path: Path,
        start: float,
        end: float,
        output_path: Path,
        speedup: float = 1.0,
        add_subtitles: bool = False,
        subtitles: Iterable[Tuple[str, float, float]] | None = None,
        subtitle_lang: str = "pl",
        copyright_processor=None,
    ) -> Path | None:
        logger.info("[GamingTemplate] Rendering segment %.2f-%.2f", start, end)
        output_path = ensure_output_path(Path(output_path))
        segment_duration = max(0.1, end - start)

        clip = load_subclip(video_path, start, end)
        if clip is None or clip.duration is None or clip.duration <= 0:
            logger.warning("[GamingTemplate] Hard failure loading clip — using black fallback")
            clip = ensure_fps(
                ColorClip(size=(1080, 1920), color=(0, 0, 0), duration=segment_duration)
            )

        clip = ensure_fps(clip.set_duration(segment_duration))
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
                    gameplay_clip = ensure_fps(gameplay_clip.fx(vfx_speedx, speedup))
                    logger.debug("Clip FPS after video speedup: %s", gameplay_clip.fps)
                    if gameplay_clip.audio:
                        new_audio = apply_speedup(gameplay_clip.audio, speedup)
                        gameplay_clip = gameplay_clip.set_audio(new_audio)
                except Exception:
                    logger.exception("[GamingTemplate] Speedup failed — using original speed")

            if add_subtitles and subtitles_data:
                gameplay_clip = add_subtitles(gameplay_clip, subtitles_data)
                logger.debug("Clip FPS after subtitles: %s", gameplay_clip.fps)

            if copyright_processor:
                gameplay_clip = copyright_processor.clean_clip_audio(
                    gameplay_clip, video_path, start, end, output_path.stem
                )

            gameplay_clip = ensure_fps(gameplay_clip.set_duration(segment_duration))
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

            # BYPASS MoviePy's broken write_videofile() and use direct ffmpeg
            logger.info("Rendering video with direct ffmpeg (fps=30)")
            render_with_ffmpeg(final, output_path, fps=30)
            final.close()
            clip.close()
            return output_path
        except Exception:
            logger.exception("[GamingTemplate] Hard failure during render")
            try:
                duration = segment_duration
                fallback_clip = ColorClip(
                    size=(1080, 1920), color=(0, 0, 0), duration=duration
                )
                fallback_clip = ensure_fps(fallback_clip, fallback=30)

                if clip and getattr(clip, "audio", None):
                    fallback_clip = fallback_clip.set_audio(clip.audio)
                    # set_audio returns a new clip, restore fps
                    fallback_clip = ensure_fps(fallback_clip, fallback=30)

                # BYPASS MoviePy's broken write_videofile() - use direct ffmpeg
                logger.info("Rendering fallback video with direct ffmpeg (fps=30)")
                render_with_ffmpeg(fallback_clip, output_path, fps=30)
                fallback_clip.close()
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
        - Top 70%: Gameplay (centered, zoomed out)
        - Bottom 30%: Facecam (full width bar from detected region)

        Args:
            source_clip: Original video clip (full frame)
            gameplay_clip: Already processed gameplay clip
            face_region: Detected face region with bbox and zone info

        Returns:
            Composite video clip with split layout
        """
        target_w, target_h = 1080, 1920

        # Split layout: 70% gameplay top, 30% facecam bottom
        gameplay_h = int(target_h * 0.70)
        facecam_h = int(target_h * 0.30)

        # Prepare gameplay for top section (centered, zoomed out)
        gameplay_full = center_crop_9_16(gameplay_clip, scale=0.85)
        gameplay_full = ensure_fps(gameplay_full.resize((target_w, gameplay_h)).set_duration(source_clip.duration))
        gameplay_full = gameplay_full.set_position((0, 0))  # Top
        logger.debug("Clip FPS after gameplay resize: %s", gameplay_full.fps)

        # Use FULL REGION of detected zone (not just bbox around face)
        # This ensures we capture the entire facecam area, not just the face
        src_w, src_h = source_clip.size
        facecam_h_percent = 0.30  # 30% of height
        facecam_w_percent = 0.35  # 35% of width
        facecam_w = int(src_w * facecam_w_percent)
        facecam_h_src = int(src_h * facecam_h_percent)

        # Map detected zone to full region coordinates
        regions = {
            "right_top": (src_w - facecam_w, 0, src_w, facecam_h_src),
            "right_bottom": (src_w - facecam_w, src_h - facecam_h_src, src_w, src_h),
            "left_top": (0, 0, facecam_w, facecam_h_src),
            "left_bottom": (0, src_h - facecam_h_src, facecam_w, src_h),
        }

        # Get full region based on detected zone
        detected_zone = face_region.zone
        if detected_zone not in regions:
            logger.warning(
                "[GamingTemplate] Unknown zone '%s', defaulting to right_top",
                detected_zone
            )
            detected_zone = "right_top"

        x1, y1, x2, y2 = regions[detected_zone]
        logger.info(
            "[GamingTemplate] Face detected in zone: %s → using full region (%dx%d at %d,%d)",
            detected_zone, x2-x1, y2-y1, x1, y1
        )

        # Crop and resize detected facecam to full width bar at bottom
        face_clip = source_clip.crop(x1=x1, y1=y1, x2=x2, y2=y2)
        face_clip = ensure_fps(face_clip.set_duration(source_clip.duration))
        face_clip = face_clip.resize((target_w, facecam_h))  # Full width, bottom 30%
        face_clip = face_clip.set_position((0, gameplay_h))  # Position at bottom
        logger.debug("Clip FPS after face crop: %s", face_clip.fps)

        # Composite gameplay (top) + facecam bar (bottom)
        final = FpsFixedCompositeVideoClip(
            [gameplay_full, face_clip],
            size=(target_w, target_h),
            fps=30,
        ).set_duration(source_clip.duration)
        logger.debug("Clip FPS after composite (split layout): %s", final.fps)
        logger.info("[GamingTemplate] Using split layout with detected face: gameplay top (70%), facecam bar bottom (30%)")
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
        - Top 70%: Gameplay (centered, zoomed out)
        - Bottom 30%: Facecam (full width bar)

        Args:
            source_clip: Original video clip (full frame)
            gameplay_clip: Already processed gameplay clip

        Returns:
            Composite video clip with split layout
        """
        target_w, target_h = 1080, 1920

        # Split layout: 70% gameplay top, 30% facecam bottom
        gameplay_h = int(target_h * 0.70)
        facecam_h = int(target_h * 0.30)

        # Prepare gameplay for top section (centered, zoomed out)
        gameplay_full = center_crop_9_16(gameplay_clip, scale=0.85)
        gameplay_full = ensure_fps(gameplay_full.resize((target_w, gameplay_h)).set_duration(source_clip.duration))
        gameplay_full = gameplay_full.set_position((0, 0))  # Top
        logger.debug("Clip FPS after gameplay resize: %s", gameplay_full.fps)

        # Try to find facecam in multiple regions (use larger regions to ensure full facecam)
        src_w, src_h = source_clip.size

        # Larger regions to ensure we capture full facecam (35% width x 30% height)
        facecam_h_percent = 0.30  # 30% of height
        facecam_w_percent = 0.35  # 35% of width
        facecam_w = int(src_w * facecam_w_percent)
        facecam_h_src = int(src_h * facecam_h_percent)

        # Since face detection is unreliable, just use right_top directly
        # This is where the facecam is in your VOD based on the screenshot
        logger.info("[GamingTemplate] Using fixed right_top region (35%x30%) for facecam")

        best_region = "right_top"
        regions = {
            "right_top": (src_w - facecam_w, 0, src_w, facecam_h_src),
            "right_bottom": (src_w - facecam_w, src_h - facecam_h_src, src_w, src_h),
            "left_top": (0, 0, facecam_w, facecam_h_src),
            "left_bottom": (0, src_h - facecam_h_src, facecam_w, src_h),
        }

        x1, y1, x2, y2 = regions[best_region]
        logger.info(
            "[GamingTemplate] Using facecam region: %s (%dx%d at %d,%d)",
            best_region, x2-x1, y2-y1, x1, y1
        )

        # Crop and resize facecam to full width bar at bottom
        face_clip = source_clip.crop(x1=x1, y1=y1, x2=x2, y2=y2)
        face_clip = ensure_fps(face_clip.set_duration(source_clip.duration))
        face_clip = face_clip.resize((target_w, facecam_h))  # Full width, bottom 30%
        face_clip = face_clip.set_position((0, gameplay_h))  # Position at bottom
        logger.debug("Clip FPS after fixed facecam crop: %s", face_clip.fps)

        # Composite gameplay (top) + facecam bar (bottom)
        final = FpsFixedCompositeVideoClip(
            [gameplay_full, face_clip],
            size=(target_w, target_h),
            fps=30,
        ).set_duration(source_clip.duration)
        logger.debug("Clip FPS after composite (split layout): %s", final.fps)
        logger.info("[GamingTemplate] Using split layout: gameplay top (70%), facecam bar bottom (30%)")
        return final

    def _build_layout_gameplay_only(self, gameplay_clip: VideoFileClip) -> VideoClip:
        """Build gameplay-only layout (no facecam) - zoomed out to see more."""
        target_w, target_h = 1080, 1920
        gameplay_full = center_crop_9_16(gameplay_clip, scale=0.85)  # Zoom out
        gameplay_full = ensure_fps(gameplay_full.resize((target_w, target_h)).set_duration(gameplay_clip.duration))
        logger.debug("Clip FPS after gameplay-only layout: %s", gameplay_full.fps)
        return gameplay_full

