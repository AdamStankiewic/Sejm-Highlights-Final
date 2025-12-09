"""
Pytest configuration and shared fixtures
"""
import pytest
import tempfile
import shutil
from pathlib import Path
import yaml
import numpy as np
from pipeline.config import load_config


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files"""
    tmp = tempfile.mkdtemp()
    yield Path(tmp)
    shutil.rmtree(tmp)


@pytest.fixture
def sample_config(temp_dir):
    """Create a sample configuration for testing"""
    config_data = {
        'audio': {
            'sample_rate': 16000,
            'normalize_loudness': True,
            'target_loudness': -23.0
        },
        'vad': {
            'threshold': 0.5,
            'min_speech_duration_ms': 250,
            'min_silence_duration_ms': 100
        },
        'asr': {
            'model_size': 'small',
            'language': 'pl',
            'beam_size': 5,
            'use_gpu': False
        },
        'features': {
            'acoustic_weight': 0.3,
            'prosodic_weight': 0.2,
            'lexical_weight': 0.5
        },
        'scoring': {
            'use_gpt': False,
            'gpt_model': 'gpt-4o-mini',
            'semantic_weight': 0.7,
            'acoustic_weight': 0.1,
            'keyword_weight': 0.1,
            'speaker_change_weight': 0.1
        },
        'selection': {
            'target_duration_seconds': 300,
            'num_clips': 5,
            'min_clip_duration': 15,
            'max_clip_duration': 90
        },
        'export': {
            'video_codec': 'h264',
            'crf': 21,
            'preset': 'medium'
        }
    }

    config_path = temp_dir / 'test_config.yml'
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config_data, f)

    return load_config(str(config_path))


@pytest.fixture
def sample_audio(temp_dir):
    """Generate a sample audio array for testing"""
    # Generate 5 seconds of audio at 16kHz
    sample_rate = 16000
    duration = 5
    t = np.linspace(0, duration, sample_rate * duration)
    # Create a simple sine wave
    audio = np.sin(2 * np.pi * 440 * t).astype(np.float32)

    return audio, sample_rate


@pytest.fixture
def sample_transcript():
    """Sample transcript data for testing"""
    return [
        {
            'start': 0.0,
            'end': 3.5,
            'text': 'To jest test transkrypcji.',
            'words': [
                {'start': 0.0, 'end': 0.5, 'word': 'To'},
                {'start': 0.5, 'end': 1.0, 'word': 'jest'},
                {'start': 1.0, 'end': 1.5, 'word': 'test'},
                {'start': 1.5, 'end': 2.5, 'word': 'transkrypcji'}
            ]
        },
        {
            'start': 3.5,
            'end': 7.0,
            'text': 'Sztuczna inteligencja analizuje debatę.',
            'words': [
                {'start': 3.5, 'end': 4.0, 'word': 'Sztuczna'},
                {'start': 4.0, 'end': 4.8, 'word': 'inteligencja'},
                {'start': 4.8, 'end': 5.5, 'word': 'analizuje'},
                {'start': 5.5, 'end': 6.5, 'word': 'debatę'}
            ]
        }
    ]


@pytest.fixture
def sample_features():
    """Sample feature data for testing"""
    return {
        'acoustic': {
            'rms_energy': 0.35,
            'spectral_centroid': 1500.0,
            'spectral_flux': 0.2,
            'zcr': 0.15
        },
        'prosodic': {
            'speech_rate': 5.5,
            'pitch_variance': 0.3,
            'pause_ratio': 0.1
        },
        'lexical': {
            'keyword_score': 0.6,
            'entity_density': 0.25
        }
    }


@pytest.fixture
def sample_segments():
    """Sample scored segments for selection testing"""
    return [
        {'start': 0.0, 'end': 30.0, 'score': 0.8, 'text': 'Segment 1'},
        {'start': 35.0, 'end': 60.0, 'score': 0.9, 'text': 'Segment 2'},
        {'start': 90.0, 'end': 120.0, 'score': 0.7, 'text': 'Segment 3'},
        {'start': 150.0, 'end': 180.0, 'score': 0.85, 'text': 'Segment 4'},
        {'start': 200.0, 'end': 230.0, 'score': 0.75, 'text': 'Segment 5'}
    ]
