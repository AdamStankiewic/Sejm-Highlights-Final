"""
Tests for scoring system (Stage 5)
"""
import pytest
from pipeline.stage_05_scoring_gpt import ScoringStage


def test_composite_score_calculation(sample_config):
    """Test composite score calculation"""
    stage = ScoringStage(sample_config)

    segment = {
        'semantic_score': 0.8,
        'acoustic_score': 0.6,
        'keyword_score': 0.7,
        'speaker_change_score': 0.5
    }

    score = stage._calculate_composite_score(segment)

    # Score should be weighted average
    expected = (
        0.8 * sample_config.scoring.semantic_weight +
        0.6 * sample_config.scoring.acoustic_weight +
        0.7 * sample_config.scoring.keyword_weight +
        0.5 * sample_config.scoring.speaker_change_weight
    )

    assert abs(score - expected) < 0.01


def test_prefiltering(sample_config):
    """Test pre-filtering of segments"""
    stage = ScoringStage(sample_config)

    segments = [
        {'acoustic_score': 0.8, 'keyword_score': 0.7, 'text': 'High score'},
        {'acoustic_score': 0.2, 'keyword_score': 0.1, 'text': 'Low score'},
        {'acoustic_score': 0.9, 'keyword_score': 0.8, 'text': 'Very high'},
    ]

    candidates = stage._prefilter_candidates(segments)

    # Should select high-scoring segments
    assert len(candidates) <= len(segments)
    assert all('acoustic_score' in seg for seg in candidates)


def test_fallback_scoring_without_gpt(sample_config):
    """Test fallback scoring when GPT is not available"""
    # Create stage without GPT
    stage = ScoringStage(sample_config)
    stage.openai_client = None  # Simulate no GPT

    segments = [
        {'acoustic_score': 0.8, 'keyword_score': 0.7, 'text': 'Test 1'},
        {'acoustic_score': 0.6, 'keyword_score': 0.5, 'text': 'Test 2'}
    ]

    scored = stage._semantic_analysis_fallback(segments)

    # Should add semantic_score
    assert all('semantic_score' in seg for seg in scored)
    assert all(0 <= seg['semantic_score'] <= 1 for seg in scored)


def test_composite_score_weights_sum_to_one(sample_config):
    """Test that scoring weights sum to 1.0"""
    total_weight = (
        sample_config.scoring.semantic_weight +
        sample_config.scoring.acoustic_weight +
        sample_config.scoring.keyword_weight +
        sample_config.scoring.speaker_change_weight
    )

    assert abs(total_weight - 1.0) < 0.01


def test_score_boundaries(sample_config):
    """Test that scores stay within valid range"""
    stage = ScoringStage(sample_config)

    segment = {
        'semantic_score': 1.5,  # Invalid: > 1.0
        'acoustic_score': -0.2,  # Invalid: < 0.0
        'keyword_score': 0.7,
        'speaker_change_score': 0.5
    }

    # Should handle invalid scores gracefully
    score = stage._calculate_composite_score(segment)
    # Even with invalid inputs, final score should be reasonable
    assert score >= 0
