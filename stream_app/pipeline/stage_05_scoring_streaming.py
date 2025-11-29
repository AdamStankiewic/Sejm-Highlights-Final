"""
Stage 5: Streaming Scoring
Chat-based scoring for Twitch/YouTube/Kick streams
Alternative to GPT scoring - uses chat activity patterns
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
import numpy as np

from .config import Config


class StreamingScoringStage:
    """Stage 5: Chat-based Scoring for Streaming Content"""

    def __init__(self, config: Config, chat_scorer=None):
        """
        Initialize streaming scoring stage

        Args:
            config: Pipeline configuration
            chat_scorer: Optional ChatScorer instance (from modules.streaming.chat_scorer)
                        If None, falls back to audio-only scoring
        """
        self.config = config
        self.chat_scorer = chat_scorer

    def process(
        self,
        segments: List[Dict],
        output_dir: Path,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Score segments based on chat activity (or audio fallback)

        Returns:
            Dict containing segments with final scoring
        """
        print(f"🎮 Streaming Scoring for {len(segments)} segments...")

        if self.chat_scorer:
            print("💬 Using chat-based scoring")
            scored_segments = self._score_with_chat(segments, progress_callback)
        else:
            print("🔊 Chat not available - using audio-only fallback")
            scored_segments = self._score_audio_only(segments)

        # Sort by score
        scored_segments.sort(key=lambda x: x['final_score'], reverse=True)

        # Save
        output_file = output_dir / "scored_segments.json"
        self._save_segments(scored_segments, output_file)

        # Stats
        avg_score = np.mean([s['final_score'] for s in scored_segments])
        print(f"   Average score: {avg_score:.3f}")
        print(f"   Top score: {scored_segments[0]['final_score']:.3f}")

        print("✅ Stage 5 complete")

        return {
            'segments': scored_segments,
            'num_segments': len(scored_segments),
            'output_file': str(output_file),
            'scoring_method': 'chat' if self.chat_scorer else 'audio_only'
        }

    def _score_with_chat(
        self,
        segments: List[Dict],
        progress_callback: Optional[Callable] = None
    ) -> List[Dict]:
        """Score segments using chat activity"""

        scored = []
        total = len(segments)

        for i, seg in enumerate(segments):
            # Progress update
            if progress_callback and i % 10 == 0:
                progress = i / total
                progress_callback(progress, f"Scoring {i}/{total} segments")

            # Get segment time range
            start_time = seg.get('start', 0)
            end_time = seg.get('end', start_time + 60)

            # Get chat score (0-100)
            chat_result = self.chat_scorer.score_segment(start_time, end_time)
            chat_score = chat_result['score'] / 100.0  # Normalize to 0-1

            # Get audio features for hybrid scoring
            features = seg.get('features', {})
            acoustic_score = self._calculate_acoustic_score(features)

            # Hybrid scoring: 70% chat, 30% audio
            # Chat activity is primary indicator for streams
            final_score = (
                0.70 * chat_score +
                0.30 * acoustic_score
            )

            # Position diversity bonus (same as GPT scoring)
            position = features.get('position_in_video', 0.5)
            position_bonus = 1.0 + self.config.scoring.position_diversity_bonus * (1 - abs(position - 0.5))
            final_score *= position_bonus

            # Clamp to [0, 1]
            final_score = float(np.clip(final_score, 0, 1))

            # Store scores
            seg['final_score'] = final_score
            seg['chat_score'] = chat_score
            seg['subscores'] = {
                'chat': float(chat_score),
                'acoustic': float(acoustic_score),
                'activity_multiplier': chat_result['breakdown']['activity_multiplier'],
                'emote_spam': chat_result['breakdown']['emote_spam_score'],
                'message_rate': chat_result['breakdown']['message_rate']
            }

            scored.append(seg)

        return scored

    def _score_audio_only(self, segments: List[Dict]) -> List[Dict]:
        """Fallback scoring using only audio features (no chat)"""

        scored = []

        for seg in segments:
            features = seg.get('features', {})

            # Calculate acoustic score
            acoustic_score = self._calculate_acoustic_score(features)

            # For audio-only, also consider speech characteristics
            speech_score = min(features.get('speech_rate_wpm', 0) / 200, 1.0)

            # Combine: 60% acoustic, 40% speech
            final_score = 0.6 * acoustic_score + 0.4 * speech_score

            # Position diversity bonus
            position = features.get('position_in_video', 0.5)
            position_bonus = 1.0 + self.config.scoring.position_diversity_bonus * (1 - abs(position - 0.5))
            final_score *= position_bonus

            # Clamp
            final_score = float(np.clip(final_score, 0, 1))

            seg['final_score'] = final_score
            seg['subscores'] = {
                'acoustic': float(acoustic_score),
                'speech_rate': float(speech_score)
            }

            scored.append(seg)

        return scored

    def _calculate_acoustic_score(self, features: Dict) -> float:
        """
        Calculate acoustic score from audio features

        For streams: Focus on excitement indicators
        - Loud moments (yelling, excitement)
        - High spectral energy (intense sounds)
        - Fast speech (rapid commentary)
        - Spectral flux (audio changes)
        """
        acoustic_score = (
            0.35 * features.get('rms_z', 0) +          # Loudness
            0.25 * features.get('spectral_centroid_z', 0) +  # Brightness
            0.20 * min(features.get('speech_rate_wpm', 0) / 200, 1.0) +  # Speech rate
            0.15 * features.get('spectral_flux', 0) +  # Audio dynamics
            0.05 * features.get('dramatic_pauses', 0)  # Pauses
        )

        return max(min(acoustic_score, 1.0), 0.0)

    def _save_segments(self, segments: List[Dict], output_file: Path):
        """Save scored segments to JSON"""
        serializable = []
        for seg in segments:
            seg_copy = seg.copy()
            if 'final_score' in seg_copy:
                seg_copy['final_score'] = float(seg_copy['final_score'])
            serializable.append(seg_copy)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)

        print(f"   💾 Scored segments saved: {output_file.name}")

    def cancel(self):
        """Cancel operation"""
        pass
