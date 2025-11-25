"""
Stage 5: Streaming Chat-Based Scoring
- Chat activity spike detection (replaces GPT semantic analysis)
- Multi-platform emote analysis (Twitch/YouTube/Kick)
- Engagement metrics (diversity, message quality)
- Audio correlation (streamer reaction)
- Viewer count normalization (if available)

For streaming content (Twitch/YouTube/Kick) with chat data.
Falls back to audio-only if no chat provided.
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
import numpy as np

from .config import Config


class StreamingScoringStage:
    """Stage 5: Chat-Based Scoring for Streaming Content"""

    def __init__(self, config: Config, chat_scorer=None):
        """
        Initialize streaming scoring stage

        Args:
            config: Pipeline config
            chat_scorer: StreamingScorer instance (optional)
                         If None, falls back to audio-only scoring
        """
        self.config = config
        self.chat_scorer = chat_scorer
        self.has_chat = chat_scorer is not None

        if self.has_chat:
            print("✓ Chat-based scoring enabled")
            stats = self.chat_scorer.chat_analyzer.get_statistics()
            print(f"  Platform: {stats['platform'].upper()}")
            print(f"  Messages: {stats['total_messages']}")
            print(f"  Baseline: {stats['baseline_msg_rate']:.2f} msg/s")
            print(f"  Delay offset: {self.chat_scorer.chat_delay_offset:.1f}s")
        else:
            print("⚠️ No chat data - using audio-only scoring")

    def process(
        self,
        segments: List[Dict],
        output_dir: Path,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Main processing method

        Returns:
            Dict containing segments with final scoring
        """
        print(f"🎮 Streaming Scoring for {len(segments)} segments...")

        if self.has_chat:
            # Chat-based scoring
            scored_segments = self._score_with_chat(segments, progress_callback)
        else:
            # Audio-only fallback
            scored_segments = self._score_audio_only(segments, progress_callback)

        # Sort by score
        scored_segments.sort(key=lambda x: x['final_score'], reverse=True)

        # Save
        output_file = output_dir / "scored_segments.json"
        self._save_segments(scored_segments, output_file)

        # Stats
        avg_score = np.mean([s['final_score'] for s in scored_segments])
        max_score = scored_segments[0]['final_score'] if scored_segments else 0

        print(f"   Average score: {avg_score:.3f}")
        print(f"   Top score: {max_score:.3f}")
        print("✅ Stage 5 completed")

        return {
            'segments': scored_segments,
            'num_segments': len(scored_segments),
            'scoring_method': 'chat_based' if self.has_chat else 'audio_only',
            'output_file': str(output_file)
        }

    def _score_with_chat(
        self,
        segments: List[Dict],
        progress_callback: Optional[Callable] = None
    ) -> List[Dict]:
        """Score segments using chat analysis"""
        print("📊 Chat-based scoring...")

        scored = []
        total = len(segments)

        for i, segment in enumerate(segments):
            # Extract audio features
            audio_features = self._extract_audio_features(segment)

            # Score with StreamingScorer
            score, breakdown = self.chat_scorer.score_segment(
                start_time=segment['t0'],
                end_time=segment['t1'],
                audio_features=audio_features
            )

            # Add to segment
            segment['final_score'] = score
            segment['score_breakdown'] = breakdown
            segment['scoring_method'] = 'chat_based'

            scored.append(segment)

            # Progress
            if progress_callback and i % 10 == 0:
                percent = int((i / total) * 100)
                progress_callback(
                    "Stage 5",
                    percent,
                    f"Scoring segment {i}/{total} (chat-based)"
                )

        return scored

    def _score_audio_only(
        self,
        segments: List[Dict],
        progress_callback: Optional[Callable] = None
    ) -> List[Dict]:
        """Fallback: Score segments using audio features only"""
        print("🔊 Audio-only scoring (no chat data)...")

        scored = []
        total = len(segments)

        for i, segment in enumerate(segments):
            features = segment.get('features', {})

            # Audio-based score (similar to pre-filter in GPT stage)
            acoustic_score = (
                0.35 * features.get('rms_z', 0) +
                0.25 * features.get('spectral_centroid_z', 0) +
                0.20 * min(features.get('speech_rate_wpm', 0) / 200, 1.0) +
                0.15 * features.get('spectral_flux', 0) +
                0.05 * features.get('dramatic_pauses', 0)
            )

            # Keyword boost
            keyword_score = features.get('keyword_score', 0)
            keyword_boost = min(keyword_score / 10, 1.0)

            # Final score (0-10 scale)
            final_score = (
                (acoustic_score * 0.7 + keyword_boost * 0.3) * 10
            )

            segment['final_score'] = max(0.0, min(10.0, final_score))
            segment['scoring_method'] = 'audio_only'
            segment['score_breakdown'] = {
                'acoustic': acoustic_score * 10,
                'keyword': keyword_boost * 10
            }

            scored.append(segment)

            # Progress
            if progress_callback and i % 10 == 0:
                percent = int((i / total) * 100)
                progress_callback(
                    "Stage 5",
                    percent,
                    f"Scoring segment {i}/{total} (audio-only)"
                )

        return scored

    def _extract_audio_features(self, segment: Dict) -> Dict:
        """Extract audio features for StreamingScorer"""
        features = segment.get('features', {})

        # Convert to format expected by StreamingScorer
        # RMS energy (dB scale)
        rms = features.get('rms_mean', 0.01)
        loudness_db = 20 * np.log10(max(rms, 1e-10)) + 70  # Normalize to ~70 dB baseline

        # Energy (0-1 normalized)
        energy = min(features.get('rms_z', 0) / 3.0, 1.0)  # Z-score to 0-1

        # Spectral flux (0-1)
        spectral_flux = features.get('spectral_flux', 0.5)

        return {
            'loudness': loudness_db,
            'energy': max(0.0, min(1.0, energy)),
            'spectral_flux': max(0.0, min(1.0, spectral_flux))
        }

    def _save_segments(self, segments: List[Dict], output_file: Path):
        """Save scored segments to JSON"""
        # Convert numpy types to native Python
        def convert_types(obj):
            if isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, dict):
                return {k: convert_types(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_types(item) for item in obj]
            return obj

        segments_converted = convert_types(segments)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(segments_converted, f, indent=2, ensure_ascii=False)

        print(f"   Saved: {output_file}")


# Factory function for backward compatibility
def create_scoring_stage(config: Config, chat_scorer=None):
    """
    Create appropriate scoring stage

    Args:
        config: Pipeline config
        chat_scorer: StreamingScorer instance (None = use GPT/audio-only)

    Returns:
        StreamingScoringStage or ScoringStage (GPT)
    """
    if chat_scorer is not None:
        # Use streaming scorer
        return StreamingScoringStage(config, chat_scorer)
    else:
        # Fall back to GPT scorer
        from .stage_05_scoring_gpt import ScoringStage
        return ScoringStage(config)
