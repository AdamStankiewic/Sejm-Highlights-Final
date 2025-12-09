"""Universal fallback template: zoom out + center crop 9:16."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Tuple

from moviepy.editor import VideoFileClip

from utils.video import center_crop_9_16, apply_speedup, add_subtitles, ensure_output_path
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
    ) -> Path:
        logger.info("[UniversalTemplate] Rendering segment %.2f-%.2f", start, end)
        output_path = ensure_output_path(Path(output_path))
        clip = VideoFileClip(str(video_path)).subclip(start, end)
        clip = center_crop_9_16(clip, scale=0.9)
        if add_subtitles and subtitles:
            clip = add_subtitles(clip, subtitles)
        if speedup > 1.0:
            try:
                clip = apply_speedup(clip, speedup)
            except Exception as exc:  # pragma: no cover - defensywnie
                logger.error("Speedup failed, keeping original speed: %s", exc)
        if copyright_processor:
            clip = copyright_processor.clean_clip_audio(clip, video_path, start, end, output_path.stem)
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
