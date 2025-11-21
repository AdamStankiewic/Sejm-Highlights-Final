"""
Prosodic feature extraction (speech rate, pauses)
Part of Highlights AI Platform - Core Engine
"""
import numpy as np
from typing import Dict, List


class ProsodicFeatureExtractor:
    """Extract prosodic features from transcribed segments"""

    def __init__(self, pause_threshold: float = 0.3, dramatic_pause: float = 2.0):
        self.pause_threshold = pause_threshold
        self.dramatic_pause = dramatic_pause

    def extract_for_segments(self, segments: List[Dict]) -> List[Dict]:
        """
        Extract prosodic features for all segments

        Args:
            segments: List of segment dicts with words (word timings)

        Returns:
            Segments with added prosodic features
        """
        enriched = []
        for seg in segments:
            features = self._extract_segment_features(seg)
            enriched.append({**seg, 'prosodic_features': features})

        return enriched

    def _extract_segment_features(self, segment: Dict) -> Dict[str, float]:
        """Extract prosodic features for single segment"""

        words = segment.get('words', [])
        duration = segment.get('duration', 0)

        if not words or duration == 0:
            return {
                'speech_rate_wpm': 0.0,
                'num_pauses': 0,
                'avg_pause_duration': 0.0,
                'dramatic_pauses': 0
            }

        # Speech rate (words per minute)
        speech_rate_wpm = (len(words) / duration) * 60

        # Pause analysis
        pauses = []
        for i in range(len(words) - 1):
            gap = words[i+1]['start'] - words[i]['end']
            if gap > self.pause_threshold:
                pauses.append(gap)

        num_pauses = len(pauses)
        avg_pause = float(np.mean(pauses)) if pauses else 0.0
        dramatic_pauses = sum(1 for p in pauses if p > self.dramatic_pause)

        return {
            'speech_rate_wpm': float(speech_rate_wpm),
            'num_pauses': num_pauses,
            'avg_pause_duration': avg_pause,
            'dramatic_pauses': dramatic_pauses
        }
