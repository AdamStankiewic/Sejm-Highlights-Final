"""Shorts generator orchestrating templates and selection."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

from shorts.templates.gaming import GamingTemplate
from shorts.templates.universal import UniversalTemplate
from shorts.templates.base import TemplateBase

logger = logging.getLogger(__name__)


@dataclass
class Segment:
    start: float
    end: float
    score: float
    subtitles: List[tuple] | None = None

    @property
    def duration(self) -> float:
        return max(0.1, self.end - self.start)


class ShortsGenerator:
    """Generuje shortsy z najlepszych segmentów."""

    def __init__(self, output_dir: Path = Path("outputs/shorts"), face_regions: Sequence[str] | None = None):
        self.output_dir = output_dir
        self.face_regions = list(face_regions) if face_regions else None

    def _template_for_name(self, name: str) -> TemplateBase:
        if name == "gaming":
            return GamingTemplate(face_regions=self.face_regions)
        return UniversalTemplate()

    def generate(
        self,
        video_path: Path,
        segments: Sequence[Segment],
        template: str = "gaming",
        count: int = 6,
        speedup: float = 1.0,
        add_subtitles: bool = False,
        subtitle_lang: str = "pl",
        copyright_processor=None,
    ) -> List[Path]:
        if not segments:
            logger.warning("No segments supplied for shorts generation")
            return []
        sorted_segments = sorted(segments, key=lambda s: s.score, reverse=True)
        selected = [s for s in sorted_segments if s.duration <= 60][: count or 6]
        results: List[Path] = []
        template_impl = self._template_for_name(template)
        for idx, segment in enumerate(selected):
            out = self.output_dir / f"short_{idx+1:02d}.mp4"
            try:
                rendered = template_impl.apply(
                    Path(video_path),
                    segment.start,
                    min(segment.end, segment.start + 60),
                    out,
                    speedup=speedup,
                    add_subtitles=add_subtitles,
                    subtitles=segment.subtitles,
                    subtitle_lang=subtitle_lang,
                    copyright_processor=copyright_processor,
                )
                if rendered is None:
                    logger.warning("[Shorts] Template returned None — skipping segment %s", segment)
                    continue
                if copyright_processor:
                    fixed_path, status = copyright_processor.scan_and_fix(str(rendered))
                    logger.info("Copyright scan status for %s: %s", rendered, status)
                    rendered = Path(fixed_path)
                results.append(rendered)
            except Exception:  # pragma: no cover - defensive
                logger.exception("Short generation failed for segment %s", segment)
                continue
        return results
