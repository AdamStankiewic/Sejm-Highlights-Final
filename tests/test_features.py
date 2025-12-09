"""
Tests for feature extraction (Stage 4)
"""
import pytest
import numpy as np
from pipeline.stage_04_features import FeaturesStage


def test_acoustic_features_extraction(sample_config, sample_audio):
    """Test acoustic feature extraction"""
    audio, sr = sample_audio

    stage = FeaturesStage(sample_config)

    # Create a mock segment
    segment = {
        't0': 0.0,
        't1': 1.0,
        'duration': 1.0,
        'transcript': 'Test',
        'words': []
    }

    features = stage._extract_acoustic_features(segment, audio, sr)

    # Check required features
    assert 'rms' in features
    assert 'spectral_centroid' in features
    assert 'spectral_flux' in features
    assert 'zcr' in features

    # Check value ranges
    assert features['rms'] >= 0
    assert features['spectral_centroid'] >= 0
    assert features['zcr'] >= 0


def test_prosodic_features_extraction(sample_config):
    """Test prosodic feature extraction (speech rate, pauses)"""
    stage = FeaturesStage(sample_config)

    segment = {
        'duration': 3.5,
        'words': [
            {'start': 0.0, 'end': 0.5, 'word': 'To'},
            {'start': 0.5, 'end': 1.0, 'word': 'jest'},
            {'start': 1.5, 'end': 2.0, 'word': 'test'},  # Gap before this
            {'start': 2.0, 'end': 2.5, 'word': 'pauz'}
        ]
    }

    features = stage._extract_prosodic_features(segment)

    assert 'speech_rate_wpm' in features
    assert 'num_pauses' in features
    assert 'avg_pause_duration' in features
    assert 'dramatic_pauses' in features

    # Should detect pause before 'test'
    assert features['num_pauses'] >= 1
    assert features['speech_rate_wpm'] > 0


def test_acoustic_features_with_silence(sample_config):
    """Test acoustic features with silent audio"""
    sr = 16000
    duration = 1
    silence = np.zeros(sr * duration, dtype=np.float32)

    stage = FeaturesStage(sample_config)
    segment = {'t0': 0.0, 't1': 1.0, 'duration': 1.0, 'transcript': '', 'words': []}

    features = stage._extract_acoustic_features(segment, silence, sr)

    # Silent audio should have low RMS
    assert features['rms'] < 0.01


def test_prosodic_features_empty_words(sample_config):
    """Test prosodic features with no words"""
    stage = FeaturesStage(sample_config)

    segment = {
        'duration': 1.0,
        'words': []
    }

    features = stage._extract_prosodic_features(segment)

    # Should handle empty gracefully
    assert features['speech_rate_wpm'] == 0.0
    assert features['num_pauses'] == 0
