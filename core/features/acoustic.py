"""
Acoustic feature extraction (RMS, spectral features)
Part of Highlights AI Platform - Core Engine
"""
import numpy as np
import librosa
from typing import Dict, List, Any
from pathlib import Path


class AcousticFeatureExtractor:
    """Extract acoustic features from audio"""

    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate

    def extract_for_segments(
        self,
        audio_path: str,
        segments: List[Dict]
    ) -> List[Dict]:
        """
        Extract acoustic features for all segments

        Args:
            audio_path: Path to audio file
            segments: List of segment dicts with t0, t1

        Returns:
            Segments with added acoustic features
        """
        # Load audio once
        y, sr = librosa.load(str(audio_path), sr=None)

        enriched = []
        for seg in segments:
            features = self._extract_segment_features(seg, y, sr)
            enriched.append({**seg, 'acoustic_features': features})

        return enriched

    def _extract_segment_features(
        self,
        segment: Dict,
        audio: np.ndarray,
        sr: int
    ) -> Dict[str, float]:
        """Extract acoustic features for single segment"""

        # Extract segment audio
        t0 = int(segment['t0'] * sr)
        t1 = int(segment['t1'] * sr)
        seg_audio = audio[t0:t1]

        if len(seg_audio) == 0:
            return {
                'rms': 0.0,
                'spectral_centroid': 0.0,
                'spectral_flux': 0.0,
                'zcr': 0.0
            }

        # RMS Energy (loudness)
        rms = float(np.sqrt(np.mean(seg_audio**2)))

        # Spectral Centroid
        centroid = librosa.feature.spectral_centroid(y=seg_audio, sr=sr)
        spectral_centroid = float(np.mean(centroid))

        # Spectral Flux
        spec = np.abs(librosa.stft(seg_audio))
        flux = np.sqrt(np.sum(np.diff(spec, axis=1)**2, axis=0))
        spectral_flux = float(np.mean(flux)) if len(flux) > 0 else 0.0

        # Zero Crossing Rate
        zcr = librosa.feature.zero_crossing_rate(seg_audio)
        zcr_mean = float(np.mean(zcr))

        return {
            'rms': rms,
            'spectral_centroid': spectral_centroid,
            'spectral_flux': spectral_flux,
            'zcr': zcr_mean
        }

    def extract_from_audio(self, audio: np.ndarray, sr: int) -> Dict[str, float]:
        """Extract features from raw audio array"""
        if len(audio) == 0:
            return {'rms': 0.0, 'spectral_centroid': 0.0, 'spectral_flux': 0.0, 'zcr': 0.0}

        rms = float(np.sqrt(np.mean(audio**2)))
        centroid = librosa.feature.spectral_centroid(y=audio, sr=sr)
        spectral_centroid = float(np.mean(centroid))

        return {
            'rms': rms,
            'spectral_centroid': spectral_centroid
        }
