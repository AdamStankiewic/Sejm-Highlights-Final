"""
Complete pipeline for political content (Sejm)
Part of Highlights AI Platform - Politics Module
"""
from typing import List, Dict, Any, Optional
from pathlib import Path

from core.pipeline_base import BasePipeline
from core.features.lexical import LexicalFeatureExtractor
from .config import PoliticsConfig
from .scorer import PoliticsScorer


class PoliticsPipeline(BasePipeline):
    """
    Pipeline for Polish political content (Sejm debates).

    Extends BasePipeline with:
    - GPT-based semantic scoring for political controversy
    - Keyword matching for political terms
    - Polish language optimization
    """

    def __init__(self, config: Optional[PoliticsConfig] = None):
        if config is None:
            config = PoliticsConfig()

        super().__init__(config)

        # Politics-specific components
        self.scorer = PoliticsScorer(config)
        self.lexical_extractor = LexicalFeatureExtractor(
            keywords_file=config.keywords_file,
            spacy_model=config.spacy_model,
            use_spacy=True
        )

    def score_segments(self, segments: List[Dict]) -> List[Dict]:
        """
        Score political segments using GPT semantic analysis.

        Scoring components:
        - Acoustic (15%): RMS energy, spectral features
        - Lexical (25%): Keyword matches, entity density
        - Semantic (60%): GPT analysis of political controversy
        """
        # Add lexical features
        segments = self.lexical_extractor.extract_for_segments(segments)

        # Score with politics scorer
        scored = self.scorer.score_segments(
            segments,
            progress_callback=lambda p, m: self._update_progress(0.7 + p * 0.1, m)
        )

        return scored

    def select_clips(self, segments: List[Dict]) -> List[Dict]:
        """
        Select top political moments for highlights video.

        Selection criteria:
        - Score threshold
        - Duration constraints
        - Gap between clips (avoid overlap)
        - Total duration target
        """
        # Sort by score
        sorted_segments = sorted(
            segments,
            key=lambda x: x.get('final_score', 0),
            reverse=True
        )

        selected = []
        total_duration = 0.0
        used_timestamps = set()

        for seg in sorted_segments:
            score = seg.get('final_score', 0)
            duration = seg.get('duration', 0)
            t0 = seg.get('t0', 0)

            # Score threshold
            if score < 0.3:
                continue

            # Duration constraints
            if duration < self.config.min_clip_duration:
                continue
            if duration > self.config.max_clip_duration:
                continue

            # Check overlap with already selected
            is_overlap = False
            for used_t0 in used_timestamps:
                if abs(t0 - used_t0) < self.config.clip_gap_min:
                    is_overlap = True
                    break

            if is_overlap:
                continue

            # Check total duration
            if total_duration + duration > self.config.target_duration:
                # Try to fit remaining time
                if self.config.target_duration - total_duration < self.config.min_clip_duration:
                    break
                continue

            # Add clip
            selected.append(seg)
            total_duration += duration
            used_timestamps.add(t0)

            # Max clips limit
            if len(selected) >= self.config.max_clips:
                break

        # Sort by timestamp for chronological order
        selected.sort(key=lambda x: x.get('t0', 0))

        return selected

    def get_module_name(self) -> str:
        return "Sejm Politics"
