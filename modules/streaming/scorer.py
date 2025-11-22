"""
Streaming content scoring based on chat activity
Part of Highlights AI Platform - Streaming Module

SLIDING WINDOW APPROACH:
- Instead of global average, compare with LOCAL activity (±30 min window)
- This handles varying viewer counts throughout the stream
- Early stream (500 viewers): spike = 2x local baseline
- Peak time (5000 viewers): spike = 2x local baseline
- Late stream (1000 viewers): spike = 2x local baseline
"""
import numpy as np
from typing import List, Dict, Optional, Tuple
from .chat_parser import ChatParser
from .config import StreamingConfig


class StreamingScorer:
    """
    Score streaming segments based on chat activity and reactions.

    INTELLIGENT ADAPTIVE SCORING:
    - Uses SLIDING WINDOW to compare with local activity (not global!)
    - Handles varying viewer counts throughout stream
    - Works for quiet AND busy parts of the same stream

    Scoring components:
    - Chat activity spike (40%): Relative to LOCAL baseline (±30 min window)
    - Emote density (25%): Popular emotes relative to local emote rate
    - Audio energy (10%): Loud moments
    - Keywords (5%): Reaction words
    """

    # Sliding window size (seconds) - ±30 minutes = 1 hour total context
    LOCAL_WINDOW_SIZE = 30 * 60  # 30 minutes each side

    def __init__(self, config: StreamingConfig, chat_data: List[Dict]):
        print(f"   [DEBUG] StreamingScorer created with {len(chat_data) if chat_data else 0} messages")

        self.config = config
        self.chat_parser = ChatParser(config.popular_emotes)
        self.chat_data = chat_data
        self.baseline_rate = self.chat_parser.get_baseline_rate(chat_data)

        # Pre-compute activity at each timestamp
        self.timestamps = []
        self.activity_at_time = {}  # timestamp -> activity
        self.emotes_at_time = {}    # timestamp -> emote count
        self.local_baseline = {}    # timestamp -> local average (sliding window)
        self.local_emote_baseline = {}

        self._compute_activity_map()

    def _compute_activity_map(self):
        """Pre-compute chat activity and LOCAL baselines using sliding window"""
        if not self.chat_data or len(self.chat_data) < 10:
            print("   [Chat Stats] Not enough chat data for analysis")
            return

        first_time = self.chat_data[0]['timestamp']
        last_time = self.chat_data[-1]['timestamp']
        duration = last_time - first_time

        print(f"\n   === CHAT ANALYSIS (Sliding Window) ===")
        print(f"   Total messages: {len(self.chat_data):,}")
        print(f"   Duration: {duration/3600:.1f} hours")
        print(f"   Global avg: {self.baseline_rate:.2f} msg/sec ({self.baseline_rate*60:.0f} msg/min)")

        # Step 1: Sample activity every 5 seconds
        activities = []
        emotes_list = []
        timestamps = []

        for t in range(int(first_time), int(last_time), 5):
            activity = self.chat_parser.get_activity_at_time(
                self.chat_data, t, self.config.chat_window_seconds
            )
            emote_count = self.chat_parser.count_emotes(
                self.chat_data, t, self.config.chat_window_seconds
            )

            timestamps.append(t)
            activities.append(activity)
            emotes_list.append(emote_count)

            self.activity_at_time[t] = activity
            self.emotes_at_time[t] = emote_count

        self.timestamps = timestamps

        if not activities:
            return

        # Step 2: Compute LOCAL baseline for each timestamp (sliding window)
        print(f"   Computing local baselines (±{self.LOCAL_WINDOW_SIZE//60} min window)...")

        for i, t in enumerate(timestamps):
            # Find indices within ±LOCAL_WINDOW_SIZE
            window_activities = []
            window_emotes = []

            for j, t2 in enumerate(timestamps):
                if abs(t2 - t) <= self.LOCAL_WINDOW_SIZE:
                    window_activities.append(activities[j])
                    window_emotes.append(emotes_list[j])

            # Local baseline = median of window (more robust than mean)
            if window_activities:
                self.local_baseline[t] = np.median(window_activities)
                self.local_emote_baseline[t] = np.median(window_emotes)
            else:
                self.local_baseline[t] = np.median(activities)
                self.local_emote_baseline[t] = np.median(emotes_list)

        # Step 3: Analyze phases of the stream
        # Divide into chunks and show stats
        chunk_size = len(timestamps) // 4 if len(timestamps) >= 4 else 1
        phases = ['Start', 'Early', 'Peak', 'End']

        print(f"\n   Stream phases:")
        for i, phase in enumerate(phases):
            start_idx = i * chunk_size
            end_idx = min((i + 1) * chunk_size, len(activities))
            chunk = activities[start_idx:end_idx]

            if chunk:
                avg = np.mean(chunk)
                peak = max(chunk)
                print(f"   - {phase}: avg={avg:.1f}, peak={peak:.0f} msg/window")

        # Step 4: Count relative spikes (2x local baseline)
        spikes = 0
        for t in timestamps:
            activity = self.activity_at_time[t]
            local_base = self.local_baseline[t]

            if local_base > 0 and activity >= local_base * 2:
                spikes += 1

        print(f"\n   Relative spikes (2x local): {spikes} ({spikes/len(timestamps)*100:.1f}%)")
        print(f"   Activity range: {min(activities)}-{max(activities)} msg/window")
        print(f"   ======================\n")

    def score_segments(self, segments: List[Dict]) -> List[Dict]:
        """Score segments based on chat activity and reactions"""
        print(f"   Scoring {len(segments)} segments (sliding window method)...")

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
            print(f"   {i}. t={t0:.0f}s ({int(t0//3600)}:{int((t0%3600)//60):02d}:{int(t0%60):02d}) | "
                  f"score={score:.3f} | "
                  f"chat={breakdown.get('chat_activity', 0):.2f} "
                  f"emote={breakdown.get('emote_density', 0):.2f} "
                  f"local_ratio={breakdown.get('local_ratio', 0):.1f}x")

        return segments

    def _compute_segment_score(self, segment: Dict) -> float:
        """Compute composite score for segment"""
        score = 0.0
        timestamp = segment.get('t0', 0)

        # 1. Chat activity spike (40%) - RELATIVE TO LOCAL BASELINE
        chat_score = self._score_chat_activity_local(timestamp)
        score += chat_score * self.config.chat_activity_weight

        # 2. Emote density (25%) - relative to local emote rate
        emote_score = self._score_emote_density_local(timestamp)
        score += emote_score * self.config.emote_density_weight

        # 3. Audio energy (10%)
        audio_score = self._score_audio_energy(segment)
        score += audio_score * self.config.audio_energy_weight

        # 4. Keywords (5%)
        keyword_score = self._score_keywords(segment)
        score += keyword_score * self.config.keyword_weight

        return min(score, 1.0)

    def _get_closest_timestamp(self, target: float) -> int:
        """Find closest pre-computed timestamp"""
        if not self.timestamps:
            return int(target)

        # Binary search for closest
        closest = min(self.timestamps, key=lambda t: abs(t - target))
        return closest

    def _score_chat_activity_local(self, timestamp: float) -> float:
        """
        Score based on chat activity RELATIVE TO LOCAL BASELINE

        - ratio < 1.0: below local average -> 0
        - ratio = 1.5: 50% above local -> 0.3
        - ratio = 2.0: 2x local baseline -> 0.7
        - ratio >= 3.0: 3x or more -> 1.0
        """
        if not self.chat_data:
            return 0.0

        # Get activity at this timestamp
        closest_t = self._get_closest_timestamp(timestamp)
        activity = self.activity_at_time.get(closest_t, 0)
        local_base = self.local_baseline.get(closest_t, 1)

        if local_base <= 0:
            local_base = 1  # Prevent division by zero

        ratio = activity / local_base

        # Store ratio for debugging
        self._last_local_ratio = ratio

        # Scoring curve
        if ratio < 1.0:
            return 0.0
        elif ratio < 1.5:
            # 1.0-1.5x: score 0-0.3
            return 0.3 * (ratio - 1.0) / 0.5
        elif ratio < 2.0:
            # 1.5-2.0x: score 0.3-0.7
            return 0.3 + 0.4 * (ratio - 1.5) / 0.5
        elif ratio < 3.0:
            # 2.0-3.0x: score 0.7-1.0
            return 0.7 + 0.3 * (ratio - 2.0) / 1.0
        else:
            return 1.0

    def _score_emote_density_local(self, timestamp: float) -> float:
        """Score emotes relative to local emote baseline"""
        closest_t = self._get_closest_timestamp(timestamp)
        emotes = self.emotes_at_time.get(closest_t, 0)
        local_base = self.local_emote_baseline.get(closest_t, 1)

        if local_base <= 0:
            local_base = 1

        ratio = emotes / local_base

        # Similar curve to chat activity
        if ratio < 1.5:
            return ratio / 3.0  # Gradual increase
        elif ratio >= 3.0:
            return 1.0
        else:
            return 0.3 + 0.7 * (ratio - 1.5) / 1.5

    def _score_audio_energy(self, segment: Dict) -> float:
        """Score based on audio energy (RMS)"""
        acoustic = segment.get('acoustic_features', {})
        rms = acoustic.get('rms', 0)
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

        return min(matches / 3.0, 1.0)

    def _get_score_breakdown(self, segment: Dict) -> Dict[str, float]:
        """Get detailed score breakdown for debugging"""
        timestamp = segment.get('t0', 0)
        closest_t = self._get_closest_timestamp(timestamp)

        activity = self.activity_at_time.get(closest_t, 0)
        local_base = self.local_baseline.get(closest_t, 1)
        ratio = activity / local_base if local_base > 0 else 0

        return {
            'chat_activity': self._score_chat_activity_local(timestamp),
            'emote_density': self._score_emote_density_local(timestamp),
            'audio_energy': self._score_audio_energy(segment),
            'keywords': self._score_keywords(segment),
            'local_ratio': ratio,
            'activity': activity,
            'local_baseline': local_base
        }

    def get_top_chat_spikes(self, top_n: int = 20) -> List[Dict]:
        """Get timestamps with highest RELATIVE chat activity - for preview"""
        if not self.timestamps:
            return []

        # Calculate relative spikes
        spikes = []
        for t in self.timestamps:
            activity = self.activity_at_time.get(t, 0)
            local_base = self.local_baseline.get(t, 1)
            ratio = activity / local_base if local_base > 0 else 0

            if ratio >= 1.5:  # At least 1.5x local baseline
                emotes = self.emotes_at_time.get(t, 0)
                spikes.append({
                    'timestamp': t,
                    'timestamp_str': f"{int(t//3600)}:{int((t%3600)//60):02d}:{int(t%60):02d}",
                    'activity': activity,
                    'local_baseline': local_base,
                    'ratio': ratio,
                    'emotes': emotes
                })

        # Sort by ratio (relative spike strength)
        spikes.sort(key=lambda x: x['ratio'], reverse=True)
        return spikes[:top_n]
