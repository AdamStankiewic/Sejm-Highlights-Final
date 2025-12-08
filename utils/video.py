"""Utility helpers for shorts processing (speedup, subtitles, crops).

Funkcje współdzielone przez szablony shortsów i generator.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Tuple

from moviepy.editor import CompositeVideoClip, TextClip, VideoFileClip
from moviepy.video.fx import resize
from moviepy.video.fx.crop import crop
from moviepy.video.fx.all import speedx as vfx_speedx
from moviepy.audio.fx import all as afx

logger = logging.getLogger(__name__)


def center_crop_9_16(clip: VideoFileClip, scale: float = 1.0) -> VideoFileClip:
    """Crop clip to 9:16 keeping center, optional scale (zoom out)."""
    target_ratio = 9 / 16
    clip = clip.fx(resize.resize, scale)
    w, h = clip.size
    current_ratio = w / h
    if abs(current_ratio - target_ratio) < 0.01:
        return clip
    if current_ratio > target_ratio:
        new_w = int(h * target_ratio)
        x1 = int((w - new_w) / 2)
        return crop(clip, x1=x1, y1=0, width=new_w, height=h)
    new_h = int(w / target_ratio)
    y1 = int((h - new_h) / 2)
    return crop(clip, x1=0, y1=y1, width=w, height=new_h)


def apply_speedup(clip: VideoFileClip, factor: float) -> VideoFileClip:
    """Przyspiesz klip wideo, zachowując możliwie naturalny głos."""
    if factor <= 1.0:
        return clip
    try:
        sped = clip.fx(vfx_speedx, factor)
    except Exception as exc:  # pragma: no cover - kompatybilność ze starszym MoviePy
        logger.warning("Video speedup fallback (bez speedx): %s", exc)
        sped = clip

    audio = sped.audio or clip.audio
    if audio:
        sped_audio = None
        # Najpierw spróbuj time_stretch (lepsza jakość), potem speedx, w ostateczności brak zmiany audio
        for fx in (getattr(afx, "time_stretch", None), getattr(afx, "speedx", None)):
            if fx is None:
                continue
            try:
                sped_audio = audio.fx(fx, factor)
                break
            except Exception as exc:  # pragma: no cover
                logger.warning("Audio speedup fallback failed (%s): %s", fx.__name__, exc)
                continue

        if sped_audio is None:
            logger.warning("Audio speedup unavailable – keeping original audio")
            sped_audio = audio

        try:
            sped = sped.set_audio(sped_audio)
        except Exception as exc:  # pragma: no cover
            logger.error("Setting sped-up audio failed, keeping original: %s", exc)
            sped = sped.set_audio(audio)

    return sped


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
            logger.error("Failed to render subtitle '%s': %s", text, exc)
    if not text_clips:
        return clip
    return CompositeVideoClip([clip, *text_clips]).set_duration(clip.duration)


def ensure_output_path(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
