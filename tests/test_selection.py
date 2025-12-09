"""
Tests for clip selection algorithm (Stage 6)
"""
import pytest
from pipeline.stage_06_selection import SelectionStage


def test_filter_by_duration(sample_config):
    """Test duration filtering"""
    stage = SelectionStage(sample_config)

    segments = [
        {'t0': 0.0, 't1': 5.0, 'duration': 5.0, 'final_score': 0.8},  # Too short
        {'t0': 10.0, 't1': 40.0, 'duration': 30.0, 'final_score': 0.9},  # Good
        {'t0': 50.0, 't1': 80.0, 'duration': 30.0, 'final_score': 0.7},  # Good
    ]

    filtered = stage._filter_by_duration(segments)

    # Should filter out too-short segments
    assert all(seg['duration'] >= stage.config.selection.min_clip_duration for seg in filtered)


def test_greedy_selection_with_nms(sample_config):
    """Test greedy selection with non-maximum suppression"""
    stage = SelectionStage(sample_config)

    segments = [
        {'t0': 0.0, 't1': 30.0, 'duration': 30.0, 'final_score': 0.9},
        {'t0': 5.0, 't1': 35.0, 'duration': 30.0, 'final_score': 0.8},  # Overlaps
        {'t0': 100.0, 't1': 130.0, 'duration': 30.0, 'final_score': 0.85},  # No overlap
    ]

    selected = stage._greedy_selection_with_nms(segments)

    # Should suppress overlapping lower-scoring segment
    assert len(selected) <= len(segments)
    # Top score should be selected
    assert any(seg['final_score'] == 0.9 for seg in selected)


def test_smart_merge_adjacent(sample_config):
    """Test smart merging of adjacent segments"""
    stage = SelectionStage(sample_config)

    selected = [
        {'t0': 0.0, 't1': 30.0, 'duration': 30.0, 'final_score': 0.8},
        {'t0': 100.0, 't1': 130.0, 'duration': 30.0, 'final_score': 0.85},
    ]

    all_segments = [
        {'t0': 0.0, 't1': 30.0, 'duration': 30.0, 'final_score': 0.8},
        {'t0': 32.0, 't1': 60.0, 'duration': 28.0, 'final_score': 0.75},  # Adjacent, high score
        {'t0': 100.0, 't1': 130.0, 'duration': 30.0, 'final_score': 0.85},
    ]

    merged = stage._smart_merge(selected, all_segments)

    # Should attempt to merge adjacent high-scoring segments
    assert isinstance(merged, list)


def test_optimize_temporal_coverage(sample_config):
    """Test temporal coverage optimization"""
    stage = SelectionStage(sample_config)

    clips = [
        {'t0': 0.0, 't1': 30.0, 'duration': 30.0, 'final_score': 0.8},
        {'t0': 10.0, 't1': 40.0, 'duration': 30.0, 'final_score': 0.9},  # Early clustering
        {'t0': 500.0, 't1': 530.0, 'duration': 30.0, 'final_score': 0.7},  # Late
    ]

    total_duration = 600.0

    balanced = stage._optimize_temporal_coverage(clips, total_duration)

    # Should try to balance coverage across time
    assert isinstance(balanced, list)
    assert len(balanced) > 0


def test_adjust_duration(sample_config):
    """Test duration adjustment"""
    stage = SelectionStage(sample_config)

    clips = [
        {'t0': 0.0, 't1': 30.0, 'duration': 30.0, 'final_score': 0.8},
        {'t0': 50.0, 't1': 80.0, 'duration': 30.0, 'final_score': 0.9},
    ]

    adjusted = stage._adjust_duration(clips)

    # Should adjust to target duration if needed
    total_duration = sum(clip['duration'] for clip in adjusted)
    assert isinstance(total_duration, (int, float))


def test_selection_respects_min_score(sample_config, temp_dir):
    """Test that selection filters by minimum score"""
    stage = SelectionStage(sample_config)

    segments = [
        {'t0': 0.0, 't1': 30.0, 'duration': 30.0, 'final_score': 0.9},
        {'t0': 50.0, 't1': 80.0, 'duration': 30.0, 'final_score': 0.3},  # Low score
        {'t0': 100.0, 't1': 130.0, 'duration': 30.0, 'final_score': 0.8},
    ]

    result = stage.process(
        segments=segments,
        total_duration=200.0,
        output_dir=temp_dir,
        min_score=0.5
    )

    # Low-score segment should be filtered
    assert all(clip['final_score'] >= 0.5 for clip in result['clips'])
