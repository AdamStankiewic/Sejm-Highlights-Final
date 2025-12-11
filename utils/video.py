"""Utility helpers for shorts processing (speedup, subtitles, crops).

Funkcje współdzielone przez szablony shortsów i generator.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Tuple

from moviepy.audio.AudioClip import AudioClip
from moviepy.audio.fx import all as afx
from moviepy.editor import CompositeVideoClip, TextClip, VideoFileClip
from moviepy.video.fx import resize
from moviepy.video.fx.crop import crop

logger = logging.getLogger(__name__)


class FpsFixedCompositeVideoClip(CompositeVideoClip):
    """CompositeVideoClip with forced fps property.

    MoviePy's CompositeVideoClip.fps property can return None even when
    fps is explicitly provided to the constructor. This subclass overrides
    the fps property to always return our forced fps value.
    """
    def __init__(self, clips, size=None, bg_color=None, use_bgclip=False, fps=30, **kwargs):
        """Initialize with forced fps value.

        Args:
            clips: List of clips to compose
            size: Output size (width, height)
            bg_color: Background color
            use_bgclip: Whether to use first clip as background
            fps: Forced fps value (default: 30)
            **kwargs: Additional arguments for CompositeVideoClip
        """
        super().__init__(clips, size=size, bg_color=bg_color, use_bgclip=use_bgclip, **kwargs)
        self._forced_fps = fps
        logger.debug("FpsFixedCompositeVideoClip initialized with forced fps=%s", fps)

    @property
    def fps(self):
        """Always return forced fps value."""
        return self._forced_fps

    @fps.setter
    def fps(self, value):
        """Update forced fps value."""
        self._forced_fps = value
        logger.debug("FpsFixedCompositeVideoClip fps set to %s", value)


def ensure_fps(clip: VideoFileClip, fallback: int = 30) -> VideoFileClip:
    """THE ONLY fps enforcement function - ensures clip has valid, non-None fps.

    This function handles MoviePy's unreliable fps metadata by:
    1. Checking if current fps is valid (numeric, positive)
    2. Setting to fallback if invalid
    3. Force-assigning the attribute (MoviePy sometimes ignores set_fps)
    4. Logging for debugging

    Args:
        clip: VideoFileClip or any clip object
        fallback: FPS to use if current is invalid (default: 30)

    Returns:
        Clip with guaranteed valid fps attribute
    """
    # Determine target fps
    current_fps = getattr(clip, "fps", None)
    if not isinstance(current_fps, (int, float)) or current_fps <= 0:
        target_fps = fallback
        logger.debug("ensure_fps: Invalid fps=%s, using fallback=%s", current_fps, fallback)
    else:
        target_fps = current_fps
        logger.debug("ensure_fps: Current fps=%s is valid", current_fps)

    # Set fps using MoviePy API
    clip = clip.set_fps(target_fps)

    # Force attribute assignment (MoviePy workaround for some clip types)
    try:
        clip.fps = target_fps
        logger.debug("ensure_fps: Direct fps attribute assignment successful")
    except (AttributeError, TypeError) as e:
        logger.warning("ensure_fps: Unable to assign fps attribute directly: %s", e)

    # Verify fps was actually set
    final_fps = getattr(clip, "fps", None)
    if final_fps is None or final_fps != target_fps:
        logger.error(
            "ensure_fps: FAILED to set fps! target=%s, final=%s, clip_type=%s",
            target_fps, final_fps, type(clip).__name__
        )
    else:
        logger.debug("ensure_fps: SUCCESS - fps=%s", final_fps)

    return clip


def center_crop_9_16(clip: VideoFileClip, scale: float = 1.0) -> VideoFileClip:
    """Crop clip to 9:16 keeping center, optional scale (zoom out)."""
    target_ratio = 9 / 16
    clip = ensure_fps(clip.fx(resize.resize, scale))
    logger.debug("Clip FPS after resize: %s", clip.fps)
    w, h = clip.size
    current_ratio = w / h
    if abs(current_ratio - target_ratio) < 0.01:
        return ensure_fps(clip)
    if current_ratio > target_ratio:
        new_w = int(h * target_ratio)
        x1 = int((w - new_w) / 2)
        cropped = crop(clip, x1=x1, y1=0, width=new_w, height=h)
        cropped = ensure_fps(cropped)
        logger.debug("Clip FPS after center_crop_9_16 width crop: %s", cropped.fps)
        return cropped
    new_h = int(w / target_ratio)
    y1 = int((h - new_h) / 2)
    cropped = crop(clip, x1=0, y1=y1, width=w, height=new_h)
    cropped = ensure_fps(cropped)
    logger.debug("Clip FPS after center_crop_9_16 height crop: %s", cropped.fps)
    return cropped


def apply_speedup(clip: AudioClip | None, factor: float | None) -> AudioClip | None:
    """Przyspiesz klip audio w sposób defensywny."""

    if clip is None:
        return None

    if factor is None or factor == 1.0:
        return clip

    original_clip = clip
    try:
        if hasattr(afx, "audio_speedx"):
            return clip.fx(afx.audio_speedx, factor)
        if hasattr(afx, "speedx"):
            return clip.fx(afx.speedx, factor)
        logger.warning(
            "Audio speedup unavailable – no audio_speedx/speedx in moviepy.afx, using original audio"
        )
        return clip
    except Exception:
        logger.error("Audio speedup failed — using original audio", exc_info=True)
        return clip


def add_subtitles(
    clip: VideoFileClip,
    subtitles: Iterable[Tuple[str, float, float]],
    fontsize: int = 42,
    color: str = "yellow",
) -> VideoFileClip:
    """Overlay simple hard subtitles. subtitles = [(text, start, end), ...]"""
    text_clips = []
    for text, start, end in subtitles:
        try:
            txt = TextClip(
                text,
                fontsize=fontsize,
                color=color,
                stroke_color="black",
                stroke_width=2,
                font="Arial",
                method="caption",
                size=(clip.w - 80, None),
            )
            txt = txt.set_position(("center", "bottom")).set_start(start).set_end(end)
            text_clips.append(txt)
        except Exception as exc:  # pragma: no cover
            logger.exception("Failed to render subtitle '%s': %s", text, exc)
    if not text_clips:
        return clip
    # Get fps from source clip before creating composite
    source_fps = getattr(clip, "fps", None) or 30
    composed = FpsFixedCompositeVideoClip(
        [clip, *text_clips],
        fps=source_fps  # Forced fps via custom subclass
    ).set_duration(clip.duration)
    logger.debug("Clip FPS after subtitles composite: %s", composed.fps)
    return composed


def ensure_output_path(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_subclip(video_path: Path, start: float, end: float) -> VideoFileClip | None:
    """Load a subclip with basic sanity checks, returning None if unusable."""

    try:
        clip = VideoFileClip(str(video_path)).subclip(start, end)
        clip = ensure_fps(clip)
        logger.debug("Clip FPS after load_subclip: %s", clip.fps)
    except Exception:
        logger.exception("[Shorts] Failed to load subclip %s %.2f-%.2f", video_path, start, end)
        return None

    if clip.duration is None or clip.duration <= 0:
        logger.warning(f"[Shorts] Skipping invalid clip: duration={clip.duration}, segment {start}-{end}")
        clip.close()
        return None

    if clip.audio is None:
        logger.warning(f"[Shorts] Clip {start}-{end} has no audio – speedup disabled")

    logger.debug("Clip FPS after load_subclip validation: %s", clip.fps)

    return clip
