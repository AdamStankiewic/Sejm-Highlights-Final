"""Shorts generator orchestrating templates and selection."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Optional

from shorts.templates import get_template, list_templates
from shorts.face_detection import FaceDetector

logger = logging.getLogger(__name__)


@dataclass
class Segment:
    """Segment to be rendered as a Short"""
    start: float
    end: float
    score: float
    subtitles: List[tuple] | None = None

    @property
    def duration(self) -> float:
        return max(0.1, self.end - self.start)


class ShortsGenerator:
    """Orchestrates Shorts generation using registered templates.

    This class handles:
    - Segment selection and filtering
    - Template instantiation
    - Copyright processing integration
    - Batch rendering coordination
    """

    def __init__(
        self,
        output_dir: Path = Path("outputs/shorts"),
        face_regions: Sequence[str] | None = None,
        face_detector: Optional[FaceDetector] = None
    ):
        """Initialize generator

        Args:
            output_dir: Output directory for rendered Shorts
            face_regions: Allowed face detection zones (legacy, unused)
            face_detector: Optional pre-configured FaceDetector for templates
        """
        self.output_dir = output_dir
        self.face_detector = face_detector

    def generate(
        self,
        video_path: Path,
        segments: Sequence[Segment],
        template: str = "gaming",
        count: int = 6,
        speedup: float = 1.0,
        enable_subtitles: bool = False,
        subtitle_lang: str = "pl",
        copyright_processor=None,
        start_index: int = 1,
    ) -> List[Path]:
        """Generate Shorts from segments using specified template

        Args:
            video_path: Source video file
            segments: List of Segment objects to render
            template: Template name (must be registered)
            count: Maximum number of Shorts to generate
            speedup: Speed multiplier (1.0 = normal, 1.5 = 50% faster)
            enable_subtitles: Whether to burn-in subtitles
            subtitle_lang: Subtitle language code
            copyright_processor: Optional copyright checker/processor

        Returns:
            List of paths to generated Short files

        Raises:
            ValueError: If template not found
        """
        if not segments:
            logger.warning("No segments supplied for shorts generation")
            return []

        # Log available templates
        available = list_templates()
        logger.info(
            "Available templates: %s",
            ', '.join(f"{t.name} ({t.display_name})" for t in available.values())
        )
        logger.info("Using template: %s", template)

        # Sort and filter segments
        sorted_segments = sorted(segments, key=lambda s: s.score, reverse=True)
        selected = [s for s in sorted_segments if s.duration <= 60][:count or 6]

        logger.info("Selected %d/%d segments for rendering", len(selected), len(segments))

        # Get template instance (will raise ValueError if not found)
        template_kwargs = {}
        if self.face_detector:
            template_kwargs['face_detector'] = self.face_detector

        template_impl = get_template(template, **template_kwargs)
        logger.info("Template instance created: %s", template_impl.__class__.__name__)

        # Render each segment
        results: List[Path] = []
        for idx, segment in enumerate(selected, start_index):
            out = self.output_dir / f"short_{idx:02d}.mp4"
            logger.info(
                "Rendering short %d/%d → %s (%.1f-%.1fs, score=%.2f)",
                idx, len(selected), out.name, segment.start, segment.end, segment.score
            )

            try:
                rendered = template_impl.apply(
                    Path(video_path),
                    segment.start,
                    min(segment.end, segment.start + 60),
                    out,
                    speedup=speedup,
                    enable_subtitles=enable_subtitles,
                    subtitles=segment.subtitles,
                    subtitle_lang=subtitle_lang,
                    copyright_processor=copyright_processor,
                    idx=idx,
                )

                if rendered is None:
                    logger.warning("Template returned None — skipping segment %s", segment)
                    continue

                # Copyright post-processing
                if copyright_processor:
                    fixed_path, status = copyright_processor.scan_and_fix(str(rendered))
                    logger.info("Copyright scan status for %s: %s", rendered, status)
                    rendered = Path(fixed_path)

                results.append(rendered)
                logger.info("✓ Short %d rendered successfully: %s", idx, rendered.name)

            except Exception:
                logger.exception("Short generation failed for segment %s", segment)
                continue

        logger.info("Shorts generation complete: %d/%d successful", len(results), len(selected))
        return results
