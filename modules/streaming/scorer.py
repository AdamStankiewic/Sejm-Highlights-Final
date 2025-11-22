"""
Streaming content scoring based on chat activity
Part of Highlights AI Platform - Streaming Module
"""
import numpy as np
from typing import List, Dict, Optional
from .chat_parser import ChatParser
from .config import StreamingConfig


class StreamingScorer:
    """
    Score streaming segments based on chat activity and reactions.

    ADAPTIVE SCORING - works with any stream size:
    - Uses percentiles instead of fixed thresholds
    - Top 15% chat activity = high score (configurable)
    - Works for quiet streams AND busy streams

    Scoring components:
    - Chat activity spike (40%): Percentile-based scoring
    - Emote density (25%): Popular emotes (KEKW, Pog, etc.)
    - Audio energy (10%): Loud moments
    - Keywords (5%): Reaction words
    """

    def __init__(self, config: StreamingConfig, chat_data: List[Dict]):
        self.config = config
        self.chat_parser = ChatParser(config.popular_emotes)
        self.chat_data = chat_data
        self.baseline_rate = self.chat_parser.get_baseline_rate(chat_data)

        # Pre-compute activity distribution for adaptive scoring
        self.activity_threshold = 0
        self.activity_distribution = []
        self.emote_threshold = 0
        self._compute_activity_distribution()

    def _compute_activity_distribution(self):
        """Pre-compute chat activity at regular intervals for percentile scoring"""
        if not self.chat_data or len(self.chat_data) < 10:
            print("   [Chat Stats] Not enough chat data for analysis")
            return

        first_time = self.chat_data[0]['timestamp']
        last_time = self.chat_data[-1]['timestamp']
        duration = last_time - first_time

        # Sample every 5 seconds
        activities = []
        emotes = []
        for t in range(int(first_time), int(last_time), 5):
            activity = self.chat_parser.get_activity_at_time(
                self.chat_data, t, self.config.chat_window_seconds
            )
            emote_count = self.chat_parser.count_emotes(
                self.chat_data, t, self.config.chat_window_seconds
            )
            activities.append(activity)
            emotes.append(emote_count)

        if activities:
            self.activity_distribution = activities

            # Compute thresholds at configured percentile
            if getattr(self.config, 'use_percentile_scoring', True):
                self.activity_threshold = np.percentile(
                    activities,
                    self.config.chat_spike_percentile
                )
                self.emote_threshold = np.percentile(emotes, 80) if max(emotes) > 0 else 5
            else:
                # Fallback to multiplier-based
                expected = self.baseline_rate * self.config.chat_window_seconds
                self.activity_threshold = expected * self.config.chat_spike_multiplier

            # Log comprehensive stats
            print(f"\n   === CHAT ANALYSIS ===")
            print(f"   Total messages: {len(self.chat_data):,}")
            print(f"   Duration: {duration/3600:.1f} hours")
            print(f"   Avg rate: {self.baseline_rate:.2f} msg/sec ({self.baseline_rate*60:.0f} msg/min)")
            print(f"   Activity range: {min(activities)}-{max(activities)} msg/10s window")
            print(f"   Median activity: {np.median(activities):.1f}")
            print(f"   Spike threshold (p{int(self.config.chat_spike_percentile)}): {self.activity_threshold:.1f}")
            print(f"   Emote threshold (p80): {self.emote_threshold:.1f}")

            # Find how many spikes we have
            spikes = sum(1 for a in activities if a >= self.activity_threshold)
            print(f"   Potential spike moments: {spikes} ({spikes/len(activities)*100:.1f}%)")
            print(f"   ======================\n")

    def score_segments(self, segments: List[Dict]) -> List[Dict]:
        """
        Score segments based on chat activity and reactions
        """
        print(f"   Scoring {len(segments)} segments...")

        scored_above_threshold = 0

        for segment in segments:
            score = self._compute_segment_score(segment)
            segment['final_score'] = score
            segment['score_breakdown'] = self._get_score_breakdown(segment)

            if score >= 0.2:
                scored_above_threshold += 1

        print(f"   Segments with score >= 0.2: {scored_above_threshold}")

        # Sort by score and show top 10
        sorted_segs = sorted(segments, key=lambda x: x['final_score'], reverse=True)[:10]
        print(f"\n   TOP 10 SEGMENTS:")
        for i, seg in enumerate(sorted_segs, 1):
            t0 = seg.get('t0', 0)
            score = seg.get('final_score', 0)
            breakdown = seg.get('score_breakdown', {})
            print(f"   {i}. t={t0:.0f}s ({t0//60:.0f}m{t0%60:.0f}s) | score={score:.3f} | "
                  f"chat={breakdown.get('chat_activity', 0):.2f} "
                  f"emote={breakdown.get('emote_density', 0):.2f}")

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
        """Score based on chat activity - ADAPTIVE percentile-based"""
        if not self.chat_data:
            return 0.0

        activity = self.chat_parser.get_activity_at_time(
            self.chat_data,
            timestamp,
            self.config.chat_window_seconds
        )

        if self.activity_threshold <= 0:
            return 0.0

        # Percentile-based scoring:
        # - Below median: 0
        # - At threshold (p85): 0.7
        # - Above threshold: up to 1.0

        if not self.activity_distribution:
            return 0.0

        median = np.median(self.activity_distribution)

        if activity < median:
            return 0.0
        elif activity >= self.activity_threshold:
            # Above threshold - scale from 0.7 to 1.0
            max_activity = max(self.activity_distribution)
            if max_activity > self.activity_threshold:
                extra = (activity - self.activity_threshold) / (max_activity - self.activity_threshold)
                return 0.7 + 0.3 * min(extra, 1.0)
            return 1.0
        else:
            # Between median and threshold - scale from 0 to 0.7
            return 0.7 * (activity - median) / (self.activity_threshold - median)

    def _score_emote_density(self, timestamp: float) -> float:
        """Score based on emote spam - adaptive"""
        emotes = self.chat_parser.count_emotes(
            self.chat_data,
            timestamp,
            self.config.chat_window_seconds
        )

        if self.emote_threshold <= 0:
            # Fallback: normalize to 50 emotes max
            return min(emotes / 50.0, 1.0)

        # Adaptive: score based on stream's own emote distribution
        if emotes >= self.emote_threshold:
            return 1.0
        else:
            return emotes / self.emote_threshold

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

    def get_top_chat_spikes(self, top_n: int = 20) -> List[Dict]:
        """Get timestamps with highest chat activity - for preview"""
        if not self.activity_distribution:
            return []

        first_time = self.chat_data[0]['timestamp']

        # Create list of (timestamp, activity)
        spikes = []
        for i, activity in enumerate(self.activity_distribution):
            t = first_time + i * 5  # 5-second intervals
            if activity >= self.activity_threshold:
                emotes = self.chat_parser.count_emotes(self.chat_data, t, 10)
                spikes.append({
                    'timestamp': t,
                    'timestamp_str': f"{int(t//3600)}:{int((t%3600)//60):02d}:{int(t%60):02d}",
                    'activity': activity,
                    'emotes': emotes
                })

        # Sort by activity and return top N
        spikes.sort(key=lambda x: x['activity'], reverse=True)
        return spikes[:top_n]
