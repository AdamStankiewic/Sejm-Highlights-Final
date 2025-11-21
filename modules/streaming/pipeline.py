"""
Complete pipeline for streaming content (Twitch/YouTube)
Part of Highlights AI Platform - Streaming Module
"""
from typing import List, Dict, Any, Optional
from pathlib import Path

from core.pipeline_base import BasePipeline
from .config import StreamingConfig
from .scorer import StreamingScorer
from .chat_parser import ChatParser


class StreamingPipeline(BasePipeline):
    """
    Pipeline for streaming content (Twitch/YouTube VODs).

    Extends BasePipeline with:
    - Chat activity-based scoring
    - Emote density analysis
    - Twitch clip integration (optional)
    """

    def __init__(
        self,
        config: Optional[StreamingConfig] = None,
        chat_data: Optional[List[Dict]] = None
    ):
        if config is None:
            config = StreamingConfig()

        super().__init__(config)

        self.chat_data = chat_data or []
        self.chat_parser = ChatParser(config.popular_emotes)
        self.scorer = None

        if chat_data:
            self.scorer = StreamingScorer(config, chat_data)

    def load_chat_from_file(self, chat_file: str, format: str = "twitch") -> int:
        """
        Load chat data from file

        Args:
            chat_file: Path to chat JSON file
            format: "twitch" or "youtube"

        Returns:
            Number of messages loaded
        """
        if format == "twitch":
            self.chat_data = self.chat_parser.parse_twitch_chat(chat_file)
        elif format == "youtube":
            self.chat_data = self.chat_parser.parse_youtube_chat(chat_file)
        else:
            raise ValueError(f"Unknown format: {format}")

        # Reinitialize scorer with new chat data
        self.scorer = StreamingScorer(self.config, self.chat_data)

        return len(self.chat_data)

    def score_segments(self, segments: List[Dict]) -> List[Dict]:
        """
        Score streaming segments based on chat activity.

        Requires chat_data to be loaded first.
        """
        if not self.scorer:
            # No chat data - use audio-only scoring
            return self._score_audio_only(segments)

        return self.scorer.score_segments(segments)

    def _score_audio_only(self, segments: List[Dict]) -> List[Dict]:
        """Fallback scoring when no chat data available"""
        for seg in segments:
            acoustic = seg.get('acoustic_features', {})
            rms = acoustic.get('rms', 0)

            # Simple audio-based score
            seg['final_score'] = min(rms * 10, 1.0)
            seg['score_breakdown'] = {'audio_only': True}

        return segments

    def select_clips(self, segments: List[Dict]) -> List[Dict]:
        """
        Select top streaming moments for highlights.

        Optimized for streaming:
        - Shorter clips (15-120s)
        - More clips (up to 20)
        - Focus on chat spike moments
        """
        # Sort by score
        sorted_segments = sorted(
            segments,
            key=lambda x: x.get('final_score', 0),
            reverse=True
        )

        selected = []
        total_duration = 0.0
        used_ranges = []

        for seg in sorted_segments:
            score = seg.get('final_score', 0)
            duration = seg.get('duration', 0)
            t0 = seg.get('t0', 0)
            t1 = seg.get('t1', 0)

            # Score threshold (lower for streaming - more content)
            if score < 0.2:
                continue

            # Duration constraints
            if duration < self.config.min_clip_duration:
                continue
            if duration > self.config.max_clip_duration:
                # Truncate long segments
                duration = self.config.max_clip_duration
                t1 = t0 + duration

            # Check overlap
            is_overlap = False
            for (used_t0, used_t1) in used_ranges:
                # Allow 30s gap between clips
                if not (t1 < used_t0 - 30 or t0 > used_t1 + 30):
                    is_overlap = True
                    break

            if is_overlap:
                continue

            # Check total duration
            if total_duration + duration > self.config.target_duration:
                if self.config.target_duration - total_duration < self.config.min_clip_duration:
                    break
                continue

            # Add clip
            clip = {**seg, 't1': t1, 'duration': duration}
            selected.append(clip)
            total_duration += duration
            used_ranges.append((t0, t1))

            if len(selected) >= self.config.max_clips:
                break

        # Sort chronologically
        selected.sort(key=lambda x: x.get('t0', 0))

        return selected

    def get_chat_stats(self) -> Dict[str, Any]:
        """Get chat statistics for display"""
        if not self.chat_data:
            return {'loaded': False}

        stats = self.chat_parser.get_chat_stats(self.chat_data)
        stats['loaded'] = True
        return stats

    def find_chat_spikes(self) -> List[Dict]:
        """Find chat activity spikes for preview"""
        if not self.chat_data:
            return []

        return self.chat_parser.find_chat_spikes(
            self.chat_data,
            self.config.chat_spike_multiplier,
            self.config.chat_window_seconds
        )

    def get_module_name(self) -> str:
        return "Stream Highlights"
