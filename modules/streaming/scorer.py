"""
Streaming content scoring based on chat activity
Part of Highlights AI Platform - Streaming Module
"""
from typing import List, Dict, Optional
from .chat_parser import ChatParser
from .config import StreamingConfig


class StreamingScorer:
    """
    Score streaming segments based on chat activity and reactions.

    Scoring components:
    - Chat activity spike (40%): Messages/sec relative to baseline
    - Emote density (25%): Popular emotes (KEKW, Pog, etc.)
    - Audio energy (10%): Loud moments
    - Keywords (5%): Reaction words
    """

    def __init__(self, config: StreamingConfig, chat_data: List[Dict]):
        self.config = config
        self.chat_parser = ChatParser(config.popular_emotes)
        self.chat_data = chat_data
        self.baseline_rate = self.chat_parser.get_baseline_rate(chat_data)

    def score_segments(self, segments: List[Dict]) -> List[Dict]:
        """
        Score segments based on chat activity and reactions

        Args:
            segments: List of segment dicts with features

        Returns:
            Segments with added 'score' field
        """
        for segment in segments:
            score = self._compute_segment_score(segment)
            segment['final_score'] = score
            segment['score_breakdown'] = self._get_score_breakdown(segment)

        return segments

    def _compute_segment_score(self, segment: Dict) -> float:
        """Compute composite score for segment"""
        score = 0.0
        timestamp = segment.get('t0', 0)

        # 1. Chat activity spike (40%)
        chat_score = self._score_chat_activity(timestamp)
        score += chat_score * self.config.chat_activity_weight

        # 2. Emote density (25%)
        emote_score = self._score_emote_density(timestamp)
        score += emote_score * self.config.emote_density_weight

        # 3. Audio energy (10%)
        audio_score = self._score_audio_energy(segment)
        score += audio_score * self.config.audio_energy_weight

        # 4. Keywords (5%)
        keyword_score = self._score_keywords(segment)
        score += keyword_score * self.config.keyword_weight

        return min(score, 1.0)

    def _score_chat_activity(self, timestamp: float) -> float:
        """Score based on chat activity spike"""
        if self.baseline_rate <= 0:
            return 0.0

        activity = self.chat_parser.get_activity_at_time(
            self.chat_data,
            timestamp,
            self.config.chat_window_seconds
        )

        expected = self.baseline_rate * self.config.chat_window_seconds
        if expected <= 0:
            return 0.0

        ratio = activity / expected

        # Score: 0 if ratio < 1, scaling up to 1.0 at spike_multiplier
        if ratio < 1.0:
            return 0.0
        elif ratio >= self.config.chat_spike_multiplier:
            return 1.0
        else:
            return (ratio - 1.0) / (self.config.chat_spike_multiplier - 1.0)

    def _score_emote_density(self, timestamp: float) -> float:
        """Score based on emote spam"""
        emotes = self.chat_parser.count_emotes(
            self.chat_data,
            timestamp,
            self.config.chat_window_seconds
        )

        # Normalize: 0-1 scale with max at 50 emotes
        return min(emotes / 50.0, 1.0)

    def _score_audio_energy(self, segment: Dict) -> float:
        """Score based on audio energy (RMS)"""
        acoustic = segment.get('acoustic_features', {})
        rms = acoustic.get('rms', 0)

        # Normalize RMS (typical range 0.01-0.1)
        return min(rms * 10, 1.0)

    def _score_keywords(self, segment: Dict) -> float:
        """Score based on reaction keywords in transcript"""
        transcript = segment.get('transcript', '').lower()

        if not transcript:
            return 0.0

        matches = 0
        for keyword in self.config.reaction_keywords:
            if keyword in transcript:
                matches += 1

        # Max score at 3+ keyword matches
        return min(matches / 3.0, 1.0)

    def _get_score_breakdown(self, segment: Dict) -> Dict[str, float]:
        """Get detailed score breakdown for debugging"""
        timestamp = segment.get('t0', 0)

        return {
            'chat_activity': self._score_chat_activity(timestamp),
            'emote_density': self._score_emote_density(timestamp),
            'audio_energy': self._score_audio_energy(segment),
            'keywords': self._score_keywords(segment)
        }
