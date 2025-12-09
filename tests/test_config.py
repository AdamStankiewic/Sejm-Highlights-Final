"""
Tests for configuration management
"""
import pytest
from pathlib import Path
from pipeline.config import load_config, Config


def test_load_config(sample_config):
    """Test configuration loading"""
    assert isinstance(sample_config, Config)
    assert sample_config.asr.model_size == 'small'
    assert sample_config.asr.language == 'pl'
    assert sample_config.audio.sample_rate == 16000


def test_config_audio_settings(sample_config):
    """Test audio configuration"""
    assert sample_config.audio.normalize_loudness is True
    assert sample_config.audio.target_loudness == -23.0


def test_config_vad_settings(sample_config):
    """Test VAD configuration"""
    assert sample_config.vad.threshold == 0.5
    assert sample_config.vad.min_speech_duration_ms == 250


def test_config_asr_settings(sample_config):
    """Test ASR configuration"""
    assert sample_config.asr.model_size in ['tiny', 'base', 'small', 'medium', 'large', 'large-v2', 'large-v3']
    assert sample_config.asr.beam_size > 0


def test_config_scoring_weights(sample_config):
    """Test scoring weight configuration"""
    weights_sum = (
        sample_config.scoring.semantic_weight +
        sample_config.scoring.acoustic_weight +
        sample_config.scoring.keyword_weight +
        sample_config.scoring.speaker_change_weight
    )
    assert abs(weights_sum - 1.0) < 0.01  # Should sum to 1.0


def test_config_selection_constraints(sample_config):
    """Test selection configuration constraints"""
    assert sample_config.selection.min_clip_duration < sample_config.selection.max_clip_duration
    assert sample_config.selection.num_clips > 0
    assert sample_config.selection.target_duration_seconds > 0
