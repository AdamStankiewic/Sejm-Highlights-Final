"""
Composite Streaming Scorer
Combines all signals for final highlight selection

Signal sources:
1. Chat activity spikes (baseline normalization)
2. Emote quality and density
3. Engagement metrics (diversity, quality)
4. Audio features (from existing pipeline)
5. Viewer count normalization (if available)

Final score: 0.0 - 10.0
"""

from typing import List, Dict, Optional, Tuple
from pathlib import Path
import statistics

from .chat_analyzer import ChatAnalyzer, ChatMessage
from .emote_scorer import EmoteScorer
from .engagement_scorer import EngagementScorer


class StreamingScorer:
    """
    Main scoring system for streaming highlights
    Combines chat, emotes, engagement, and audio
    """

    def __init__(
        self,
        chat_analyzer: Optional[ChatAnalyzer] = None,
        platform: str = 'twitch',
        weights: Optional[Dict[str, float]] = None
    ):
        """
        Initialize streaming scorer

        Args:
            chat_analyzer: ChatAnalyzer instance (optional)
            platform: 'twitch', 'youtube', or 'kick'
            weights: Custom weights for scoring components
        """
        self.chat_analyzer = chat_analyzer
        self.platform = platform.lower()

        # Initialize sub-scorers
        self.emote_scorer = EmoteScorer(platform=self.platform)
        self.engagement_scorer = EngagementScorer()

        # Default weights (configurable)
        self.weights = weights or {
            'chat_spike': 0.30,      # Chat activity vs baseline
            'emote_quality': 0.25,   # Emote types (PogChamp > Kappa)
            'engagement': 0.20,      # Diversity, message quality
            'audio': 0.15,           # Audio features (loudness, energy)
            'viewer_normalized': 0.10,  # MPVS (if available)
        }

        # Validate weights sum to 1.0
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total}")

        # Cache for scored segments
        self._score_cache = {}

    def score_segment(
        self,
        start_time: float,
        end_time: float,
        audio_features: Optional[Dict] = None,
        viewer_count: Optional[int] = None
    ) -> Tuple[float, Dict]:
        """
        Score a video segment for highlight worthiness

        Args:
            start_time: Segment start (seconds)
            end_time: Segment end (seconds)
            audio_features: Optional dict with audio metrics
            viewer_count: Optional viewer count for normalization

        Returns:
            (score, breakdown) tuple
            - score: 0.0 - 10.0
            - breakdown: dict with component scores
        """
        # Check cache
        cache_key = f"{start_time}-{end_time}"
        if cache_key in self._score_cache:
            return self._score_cache[cache_key]

        # Get messages in this window
        messages = []
        if self.chat_analyzer:
            messages = self.chat_analyzer.get_messages_in_window(start_time, end_time)

        # Initialize scores
        scores = {
            'chat_spike': 0.0,
            'emote_quality': 0.0,
            'engagement': 0.0,
            'audio': 0.0,
            'viewer_normalized': 0.0,
        }

        # 1. Chat spike score
        if self.chat_analyzer and messages:
            scores['chat_spike'] = self._score_chat_spike(
                messages,
                start_time,
                end_time
            )
        else:
            scores['chat_spike'] = 5.0  # Neutral if no chat

        # 2. Emote quality score
        if messages:
            scores['emote_quality'] = self.emote_scorer.score_composite(messages)
        else:
            scores['emote_quality'] = 5.0  # Neutral if no chat

        # 3. Engagement score
        if messages:
            scores['engagement'] = self.engagement_scorer.score_composite_engagement(messages)
        else:
            scores['engagement'] = 5.0  # Neutral if no chat

        # 4. Audio score
        if audio_features:
            scores['audio'] = self._score_audio(audio_features)
        else:
            scores['audio'] = 5.0  # Neutral if no audio features

        # 5. Viewer normalized score
        if self.chat_analyzer and viewer_count and messages:
            scores['viewer_normalized'] = self._score_viewer_normalized(
                messages,
                viewer_count,
                end_time - start_time
            )
        else:
            # No viewer count available - redistribute weight
            scores['viewer_normalized'] = 5.0

        # Calculate composite score
        final_score = sum(
            scores[key] * self.weights[key]
            for key in scores
        )

        # Prepare detailed breakdown
        breakdown = {
            'final_score': final_score,
            'components': scores,
            'weights': self.weights,
            'message_count': len(messages),
            'has_chat': len(messages) > 0,
            'has_audio': audio_features is not None,
            'has_viewer_count': viewer_count is not None,
        }

        # Cache result
        self._score_cache[cache_key] = (final_score, breakdown)

        return final_score, breakdown

    def _score_chat_spike(
        self,
        messages: List[ChatMessage],
        start_time: float,
        end_time: float
    ) -> float:
        """
        Score based on chat spike vs baseline

        Returns:
            Spike score (0.0 - 10.0)
        """
        if not self.chat_analyzer or not messages:
            return 5.0

        window_duration = end_time - start_time
        msg_rate = len(messages) / window_duration

        # Compare to baseline
        baseline = self.chat_analyzer.baseline_msg_rate

        if baseline == 0:
            return 5.0  # Can't determine spike

        spike_ratio = msg_rate / baseline

        # Scale spike ratio to 0-10
        # 1x baseline = 5.0 (normal)
        # 2x baseline = 6.5
        # 3x baseline = 8.0
        # 5x+ baseline = 10.0

        if spike_ratio < 1.0:
            # Below baseline (quiet moment)
            return max(0.0, 5.0 * spike_ratio)  # 0.5x→2.5, 0.8x→4.0
        elif spike_ratio < 2.0:
            return 5.0 + ((spike_ratio - 1.0) * 1.5)  # 1x→5.0, 2x→6.5
        elif spike_ratio < 3.0:
            return 6.5 + ((spike_ratio - 2.0) * 1.5)  # 2x→6.5, 3x→8.0
        elif spike_ratio < 5.0:
            return 8.0 + ((spike_ratio - 3.0) * 1.0)  # 3x→8.0, 5x→10.0
        else:
            return 10.0  # Massive spike

    def _score_audio(self, audio_features: Dict) -> float:
        """
        Score based on audio features

        Expected audio_features:
        {
            'loudness': 85.0,      # dB
            'energy': 0.8,         # 0-1
            'spectral_flux': 0.6,  # 0-1
        }

        Returns:
            Audio score (0.0 - 10.0)
        """
        # Extract features with defaults
        loudness = audio_features.get('loudness', 70.0)
        energy = audio_features.get('energy', 0.5)
        spectral_flux = audio_features.get('spectral_flux', 0.5)

        # Loudness score (dB)
        # 60-70 dB = quiet → 3-5
        # 70-80 dB = normal → 5-7
        # 80-90 dB = loud → 7-9
        # 90+ dB = very loud/shouting → 9-10
        if loudness < 70:
            loudness_score = 3.0 + ((loudness - 60) / 10) * 2.0
        elif loudness < 80:
            loudness_score = 5.0 + ((loudness - 70) / 10) * 2.0
        elif loudness < 90:
            loudness_score = 7.0 + ((loudness - 80) / 10) * 2.0
        else:
            loudness_score = min(9.0 + ((loudness - 90) / 10), 10.0)

        # Energy score (0-1)
        # High energy = excitement
        energy_score = 2.0 + (energy * 8.0)  # 0→2.0, 1→10.0

        # Spectral flux (0-1)
        # High flux = dynamic/changing audio (exciting)
        flux_score = 3.0 + (spectral_flux * 7.0)  # 0→3.0, 1→10.0

        # Composite audio score
        audio_score = (
            loudness_score * 0.5 +    # 50% - loudness most important
            energy_score * 0.3 +      # 30% - energy
            flux_score * 0.2          # 20% - dynamics
        )

        return min(max(audio_score, 0.0), 10.0)

    def _score_viewer_normalized(
        self,
        messages: List[ChatMessage],
        viewer_count: int,
        window_duration: float
    ) -> float:
        """
        Score based on Messages Per Viewer Per Second (MPVS)

        Normalizes chat activity by viewer count

        Returns:
            Normalized score (0.0 - 10.0)
        """
        if viewer_count == 0 or window_duration == 0:
            return 5.0

        msg_rate = len(messages) / window_duration
        mpvs = msg_rate / viewer_count

        # Typical MPVS ranges (empirical):
        # 0.0001-0.001 = quiet chat → 3-5
        # 0.001-0.005 = normal → 5-7
        # 0.005-0.02 = active → 7-9
        # 0.02+ = very active → 9-10

        if mpvs < 0.001:
            return 3.0 + (mpvs / 0.001) * 2.0
        elif mpvs < 0.005:
            return 5.0 + ((mpvs - 0.001) / 0.004) * 2.0
        elif mpvs < 0.02:
            return 7.0 + ((mpvs - 0.005) / 0.015) * 2.0
        else:
            return min(9.0 + ((mpvs - 0.02) / 0.02), 10.0)

    def score_all_segments(
        self,
        segments: List[Dict],
        audio_features_list: Optional[List[Dict]] = None
    ) -> List[Tuple[Dict, float, Dict]]:
        """
        Score multiple segments

        Args:
            segments: List of segment dicts with 't0' and 't1'
            audio_features_list: Optional list of audio features per segment

        Returns:
            List of (segment, score, breakdown) tuples, sorted by score
        """
        results = []

        for i, segment in enumerate(segments):
            start = segment.get('t0', 0)
            end = segment.get('t1', start + 60)

            audio = None
            if audio_features_list and i < len(audio_features_list):
                audio = audio_features_list[i]

            score, breakdown = self.score_segment(start, end, audio)

            results.append((segment, score, breakdown))

        # Sort by score (highest first)
        results.sort(key=lambda x: x[1], reverse=True)

        return results

    def get_top_highlights(
        self,
        segments: List[Dict],
        top_n: int = 10,
        min_score: float = 6.0,
        audio_features_list: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """
        Get top N highlights from segments

        Args:
            segments: List of segment dicts
            top_n: Number of highlights to return
            min_score: Minimum score threshold
            audio_features_list: Optional audio features

        Returns:
            List of segment dicts with added 'final_score' field
        """
        scored = self.score_all_segments(segments, audio_features_list)

        # Filter by min_score and take top N
        highlights = []
        for segment, score, breakdown in scored:
            if score >= min_score:
                segment['final_score'] = score
                segment['score_breakdown'] = breakdown
                highlights.append(segment)

                if len(highlights) >= top_n:
                    break

        return highlights

    def print_score_report(
        self,
        start_time: float,
        end_time: float,
        audio_features: Optional[Dict] = None
    ):
        """
        Print detailed scoring report for a segment (debugging)
        """
        score, breakdown = self.score_segment(start_time, end_time, audio_features)

        mins = int(start_time // 60)
        secs = int(start_time % 60)

        print(f"\n{'='*60}")
        print(f"Segment: {mins}:{secs:02d} - {int(end_time//60)}:{int(end_time%60):02d}")
        print(f"{'='*60}")
        print(f"FINAL SCORE: {score:.2f}/10.0\n")

        print("Component Scores:")
        for key, value in breakdown['components'].items():
            weight = self.weights[key]
            contribution = value * weight
            print(f"  {key:20s}: {value:5.2f}/10 (weight: {weight:.2f}) → {contribution:.2f}")

        print(f"\nMetadata:")
        print(f"  Messages: {breakdown['message_count']}")
        print(f"  Has chat: {breakdown['has_chat']}")
        print(f"  Has audio: {breakdown['has_audio']}")
        print(f"  Has viewer count: {breakdown['has_viewer_count']}")


# Helper function to create scorer from chat file
def create_scorer_from_chat(
    chat_json_path: str,
    vod_duration: float = 0,
    platform: Optional[str] = None,
    weights: Optional[Dict[str, float]] = None
) -> StreamingScorer:
    """
    Convenience function to create scorer from chat file

    Args:
        chat_json_path: Path to chat JSON file
        vod_duration: Total VOD duration in seconds
        platform: Platform name (auto-detected if None)
        weights: Custom scoring weights

    Returns:
        Configured StreamingScorer instance
    """
    # Load and parse chat
    chat_analyzer = ChatAnalyzer(
        chat_json_path=chat_json_path,
        vod_duration=vod_duration,
        platform=platform
    )

    # Create scorer
    scorer = StreamingScorer(
        chat_analyzer=chat_analyzer,
        platform=chat_analyzer.platform,
        weights=weights
    )

    print(f"✅ Scorer created for {chat_analyzer.platform.upper()}")
    print(f"   Messages: {len(chat_analyzer.messages)}")
    print(f"   Baseline: {chat_analyzer.baseline_msg_rate:.2f} msg/s")

    return scorer


if __name__ == "__main__":
    # Test composite scorer
    import sys

    if len(sys.argv) > 1:
        chat_file = sys.argv[1]
        scorer = create_scorer_from_chat(chat_file)

        # Find spikes
        spikes = scorer.chat_analyzer.detect_spikes(window_size=30, spike_threshold=2.5)

        print(f"\n🔥 Top 5 Highlights:")
        for i, (time, intensity, count) in enumerate(spikes[:5], 1):
            # Mock audio features for testing
            audio_features = {
                'loudness': 75 + (intensity * 5),  # Higher spike = louder
                'energy': min(0.5 + (intensity * 0.1), 1.0),
                'spectral_flux': 0.6
            }

            scorer.print_score_report(
                time - 15,  # 15s before spike
                time + 15,  # 15s after spike
                audio_features
            )
