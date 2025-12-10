"""Universal fallback template: zoom out + center crop 9:16."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Tuple

from moviepy.editor import ColorClip, CompositeAudioClip

from utils.video import (
    apply_speedup,
    center_crop_9_16,
    add_subtitles,
    ensure_fps,
    ensure_output_path,
    load_subclip,
)
from .base import TemplateBase

logger = logging.getLogger(__name__)


class UniversalTemplate(TemplateBase):
    name = "universal"

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
        logger.info("[UniversalTemplate] Rendering segment %.2f-%.2f", start, end)
        output_path = ensure_output_path(Path(output_path))
        clip = load_subclip(video_path, start, end)
        segment_duration = max(0.1, end - start)

        try:
            if clip is None or clip.duration is None or clip.duration <= 0:
                logger.warning("[UniversalTemplate] Invalid or empty clip — using fallback")
                clip = ensure_fps(
                    ColorClip(
                        size=(1080, 1920), color=(0, 0, 0), duration=segment_duration
                    )
                )
                clip.audio = CompositeAudioClip([])
            clip = center_crop_9_16(clip, scale=0.9)
            clip = clip.set_duration(segment_duration)
            logger.debug("Clip FPS after center crop: %s", clip.fps)
            if clip.audio is None:
                logger.warning("[UniversalTemplate] No audio — subtitles and speedup skipped")
            if add_subtitles and subtitles and clip.audio is not None:
                clip = add_subtitles(clip, subtitles)
                logger.debug("Clip FPS after subtitles: %s", clip.fps)
            if speedup > 1.0 and clip.audio is not None:
                try:
                    clip = apply_speedup(clip, speedup)
                    clip = ensure_fps(clip)
                    logger.debug("Clip FPS after speedup: %s", clip.fps)
                except Exception as exc:  # pragma: no cover - defensywnie
                    logger.exception("Speedup failed, keeping original speed: %s", exc)
            if copyright_processor:
                clip = copyright_processor.clean_clip_audio(
                    clip, video_path, start, end, output_path.stem
                )
            clip = ensure_fps(clip)
            if clip.audio is None:
                clip.audio = CompositeAudioClip([])
            if clip.fps is None:
                logger.warning("Final clip had no fps – forcing 30fps")
                clip = clip.set_fps(30)
            logger.debug("Clip FPS before render: %s", clip.fps)
            clip.write_videofile(
                str(output_path),
                codec="libx264",
                audio_codec="aac",
                threads=2,
                verbose=False,
                logger=None,
            )
            clip.close()
            return output_path
        except Exception:
            logger.exception("[UniversalTemplate] Failed to render segment %.2f-%.2f", start, end)
            try:
                fallback = ensure_fps(
                    ColorClip(
                        size=(1080, 1920), color=(0, 0, 0), duration=segment_duration
                    )
                )
                fallback.audio = CompositeAudioClip([])
                fallback.write_videofile(
                    str(output_path),
                    codec="libx264",
                    audio_codec="aac",
                    threads=2,
                    verbose=False,
                    logger=None,
                )
                fallback.close()
            except Exception:
                logger.exception("[UniversalTemplate] Fallback clip rendering failed")
            return output_path
