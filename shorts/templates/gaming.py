"""Gaming template with MediaPipe facecam detection and stable 9:16 layout."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Tuple, Optional
import functools

from moviepy.editor import ColorClip, CompositeVideoClip, VideoClip, VideoFileClip
from moviepy.video.fx.all import speedx as vfx_speedx
import moviepy.decorators
from moviepy.video.io.ffmpeg_writer import ffmpeg_write_video

from shorts.face_detection import FaceDetector, FaceRegion
from utils.video import (
    add_subtitles,
    apply_speedup,
    center_crop_9_16,
    ensure_fps,
    ensure_output_path,
    load_subclip,
)
from .base import TemplateBase

logger = logging.getLogger(__name__)


# MONKEY PATCH: Fix MoviePy's use_clip_fps_by_default to handle None fps
_original_use_clip_fps_by_default = moviepy.decorators.use_clip_fps_by_default


def _patched_use_clip_fps_by_default(func):
    """Patched version that injects fps=30 if clip.fps is None."""
    @functools.wraps(func)
    def wrapper(clip, *args, **kwargs):
        # If fps not explicitly provided and clip.fps is None, inject fps=30
        if 'fps' not in kwargs:
            clip_fps = getattr(clip, 'fps', None)
            if clip_fps is None:
                logger.warning(
                    "Clip has fps=None, injecting fps=30 via monkey-patch"
                )
                kwargs['fps'] = 30
            else:
                kwargs['fps'] = clip_fps
        return func(clip, *args, **kwargs)
    return wrapper


# Apply the monkey patch globally
moviepy.decorators.use_clip_fps_by_default = _patched_use_clip_fps_by_default
logger.info("Applied MoviePy fps monkey-patch")


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
            confidence_threshold=0.5,
            consensus_threshold=0.3,
            num_samples=6
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
                final = self._build_layout_gameplay_only(gameplay_clip)

            final = final.set_duration(segment_duration)

            # CRITICAL: Ensure fps before and after audio operations
            final = ensure_fps(final, fallback=30)

            if gameplay_clip.audio is not None:
                final = final.set_audio(gameplay_clip.audio)
                # set_audio might clear fps, restore it
                final = ensure_fps(final, fallback=30)

            render_fps = 30  # Always use 30fps for Shorts

            # NUCLEAR FPS FIX: MoviePy's use_clip_fps_by_default decorator
            # ignores fps= argument if clip.fps is None.
            # Use object.__setattr__ to bypass read-only property setters.
            try:
                object.__setattr__(final, 'fps', render_fps)
                logger.debug("Forced clip.fps via __setattr__ = %s", render_fps)
            except Exception as e:
                logger.error("Cannot force fps via __setattr__: %s", e)
                # Last resort: try regular assignment
                try:
                    final.fps = render_fps
                except:
                    pass

            actual_fps = getattr(final, "fps", None)
            logger.debug(
                "Clip FPS before render: %s (target=%s)",
                actual_fps,
                render_fps,
            )

            if actual_fps is None:
                logger.error("CRITICAL: clip.fps is still None - using direct ffmpeg_write_video")
                # ULTIMATE FIX: Bypass write_videofile() entirely, call ffmpeg_write_video directly
                ffmpeg_write_video(
                    final,
                    str(output_path),
                    fps=render_fps,  # Force fps here
                    codec="libx264",
                    audiofile=None,  # Will extract from clip
                    preset="medium",
                    bitrate=None,
                    audio_codec="aac",
                    threads=2,
                    ffmpeg_params=[],
                    verbose=False,
                    logger=None,
                )
            else:
                # Normal path when fps is valid
                final.write_videofile(
                    str(output_path),
                    codec="libx264",
                    audio_codec="aac",
                    fps=render_fps,
                    threads=2,
                    verbose=False,
                    logger=None,
                )
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
                if clip and getattr(clip, "audio", None):
                    fallback_clip = fallback_clip.set_audio(clip.audio)

                fallback_clip = ensure_fps(fallback_clip, fallback=30)
                render_fps = 30

                # NUCLEAR FPS FIX for fallback clip
                try:
                    object.__setattr__(fallback_clip, 'fps', render_fps)
                    logger.debug("Forced fallback_clip.fps via __setattr__ = %s", render_fps)
                except Exception as e:
                    logger.error("Cannot force fallback fps via __setattr__: %s", e)
                    try:
                        fallback_clip.fps = render_fps
                    except:
                        pass

                actual_fps = getattr(fallback_clip, "fps", None)
                if actual_fps is None:
                    logger.error("CRITICAL: fallback_clip.fps is still None - using direct ffmpeg_write_video")
                    # ULTIMATE FIX: Bypass write_videofile(), call ffmpeg_write_video directly
                    ffmpeg_write_video(
                        fallback_clip,
                        str(output_path),
                        fps=render_fps,  # Force fps here
                        codec="libx264",
                        audiofile=None,  # Will extract from clip
                        preset="medium",
                        bitrate=None,
                        audio_codec="aac",
                        threads=2,
                        ffmpeg_params=[],
                        verbose=False,
                        logger=None,
                    )
                else:
                    fallback_clip.write_videofile(
                        str(output_path),
                        codec="libx264",
                        audio_codec="aac",
                        fps=render_fps,
                        threads=2,
                        verbose=False,
                        logger=None,
                    )
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
        """Build PIP layout with gameplay background and facecam overlay

        Args:
            source_clip: Original video clip (full frame)
            gameplay_clip: Already processed gameplay clip
            face_region: Detected face region with bbox and zone info

        Returns:
            Composite video clip with PIP layout
        """
        target_w, target_h = 1080, 1920
        x, y, w, h = face_region.bbox

        # Expand bbox by 20% margin for context around face
        margin = 1.2
        x1 = max(0, int(x - (margin - 1) * w / 2))
        y1 = max(0, int(y - (margin - 1) * h / 2))
        x2 = int(min(source_clip.w, x + w * margin))
        y2 = int(min(source_clip.h, y + h * margin))

        # Crop and resize face clip to 45% of target width
        face_clip = source_clip.crop(x1=x1, y1=y1, x2=x2, y2=y2)
        face_clip = ensure_fps(face_clip.set_duration(source_clip.duration))
        face_clip = face_clip.resize(width=int(target_w * 0.45))
        logger.debug("Clip FPS after face crop: %s", face_clip.fps)

        # Prepare full-frame gameplay background
        gameplay_full = center_crop_9_16(gameplay_clip)
        gameplay_full = ensure_fps(gameplay_full.resize((target_w, target_h)).set_duration(source_clip.duration))
        logger.debug("Clip FPS after gameplay resize: %s", gameplay_full.fps)

        # Position facecam PIP based on detected zone
        side = "left" if face_region.zone.startswith("left_") else "right"
        if face_region.zone.endswith("top"):
            vertical = "top"
        elif face_region.zone.endswith("middle"):
            vertical = "middle"
        else:
            vertical = "bottom"

        # Calculate PIP position (40px margin from edges)
        margin_px = 40
        face_x = margin_px if side == "left" else target_w - face_clip.w - margin_px
        if vertical == "top":
            face_y = margin_px
        elif vertical == "middle":
            face_y = (target_h - face_clip.h) // 2
        else:
            face_y = target_h - face_clip.h - margin_px

        face_clip = face_clip.set_position((face_x, face_y))
        face_clip = ensure_fps(face_clip.set_duration(source_clip.duration))
        logger.debug("Clip FPS after face positioning: %s", face_clip.fps)

        # Composite gameplay + facecam
        final = CompositeVideoClip(
            [gameplay_full, face_clip],
            size=(target_w, target_h),
            fps=30,  # CRITICAL: CompositeVideoClip needs explicit fps
        ).set_duration(source_clip.duration)
        logger.debug("Clip FPS after composite (with face): %s", final.fps)
        logger.info("[GamingTemplate] Using gameplay+face PIP layout (%s, %s)", side, vertical)
        return final

    def _build_layout_gameplay_only(self, gameplay_clip: VideoFileClip) -> VideoClip:
        target_w, target_h = 1080, 1920
        gameplay_full = center_crop_9_16(gameplay_clip, scale=1.05)
        gameplay_full = ensure_fps(gameplay_full.resize((target_w, target_h)).set_duration(gameplay_clip.duration))
        logger.debug("Clip FPS after gameplay-only layout: %s", gameplay_full.fps)
        return gameplay_full

