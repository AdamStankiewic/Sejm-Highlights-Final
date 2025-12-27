#!/usr/bin/env python3
"""
Test suite for Performance Analyzer (Phase 3 Task 3.2)
"""
import sys
from pathlib import Path
import importlib.util

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def import_module_from_path(module_name, file_path):
    """Import a module from a file path"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_performance_import():
    """Test that PerformanceAnalyzer can be imported"""
    print("\n" + "=" * 60)
    print("TEST 1: Performance Analyzer Import")
    print("=" * 60)

    try:
        perf_path = project_root / "pipeline/learning/performance.py"
        perf_module = import_module_from_path("performance", perf_path)
        print("✅ PerformanceAnalyzer imported successfully")
        print(f"   Classes: PerformanceAnalyzer, analyze_and_update")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_score_calculation():
    """Test performance score calculation"""
    print("\n" + "=" * 60)
    print("TEST 2: Performance Score Calculation")
    print("=" * 60)

    try:
        perf_path = project_root / "pipeline/learning/performance.py"
        perf_module = import_module_from_path("performance", perf_path)

        PerformanceAnalyzer = perf_module.PerformanceAnalyzer

        analyzer = PerformanceAnalyzer()

        # Mock video metrics (high-performing video)
        video_metrics = {
            'views': 10000,
            'likes': 500,
            'duration_seconds': 600,
            'published_at': '2024-01-15T10:00:00Z'
        }

        # Mock channel averages
        channel_avg = {
            'engagement_rate': 0.02,   # 2% average
            'ctr': 0.05,                # 5% average
            'watch_time': 240,          # 4 minutes average
            'views': 5000
        }

        score = analyzer.calculate_performance_score(video_metrics, channel_avg)

        print(f"✅ Video metrics:")
        print(f"   Views: {video_metrics['views']:,}")
        print(f"   Likes: {video_metrics['likes']:,}")
        print(f"   Engagement: {video_metrics['likes']/video_metrics['views']:.2%}")
        print(f"\n✅ Channel averages:")
        print(f"   Avg engagement: {channel_avg['engagement_rate']:.2%}")
        print(f"\n✅ Performance score: {score:.2f}/10.0")

        if 0 <= score <= 10:
            print(f"✅ Score in valid range (0-10)")
            return True
        else:
            print(f"❌ Score out of range: {score}")
            return False

    except Exception as e:
        print(f"❌ Score calculation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_channel_analysis():
    """Test analyzing multiple videos"""
    print("\n" + "=" * 60)
    print("TEST 3: Channel Video Analysis")
    print("=" * 60)

    try:
        perf_path = project_root / "pipeline/learning/performance.py"
        perf_module = import_module_from_path("performance", perf_path)

        PerformanceAnalyzer = perf_module.PerformanceAnalyzer

        analyzer = PerformanceAnalyzer()

        # Mock video metrics for multiple videos
        video_metrics = {
            'video_1': {
                'title': 'High Performer',
                'views': 15000,
                'likes': 750,
                'duration_seconds': 600,
                'published_at': '2024-01-20T10:00:00Z'
            },
            'video_2': {
                'title': 'Average Video',
                'views': 5000,
                'likes': 100,
                'duration_seconds': 600,
                'published_at': '2024-01-15T10:00:00Z'
            },
            'video_3': {
                'title': 'Low Performer',
                'views': 2000,
                'likes': 20,
                'duration_seconds': 600,
                'published_at': '2024-01-10T10:00:00Z'
            }
        }

        performances = analyzer.analyze_channel_videos('test_streamer', video_metrics)

        print(f"✅ Analyzed {len(performances)} videos")
        print(f"\n   Rankings:")
        for i, perf in enumerate(performances, 1):
            print(f"   {i}. {perf['title']}: {perf['performance_score']:.2f}/10")
            print(f"      Views: {perf['views']:,}, Likes: {perf['likes']:,}")

        # Check if sorted correctly
        if performances[0]['performance_score'] >= performances[1]['performance_score']:
            print(f"\n✅ Videos correctly sorted by performance")
            return True
        else:
            print(f"\n❌ Videos not sorted correctly")
            return False

    except Exception as e:
        print(f"❌ Channel analysis test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_top_performers():
    """Test filtering top performers"""
    print("\n" + "=" * 60)
    print("TEST 4: Top Performers Selection")
    print("=" * 60)

    try:
        perf_path = project_root / "pipeline/learning/performance.py"
        perf_module = import_module_from_path("performance", perf_path)

        PerformanceAnalyzer = perf_module.PerformanceAnalyzer

        analyzer = PerformanceAnalyzer()

        # Mock performances
        performances = [
            {'video_id': 'v1', 'performance_score': 8.5, 'title': 'Great'},
            {'video_id': 'v2', 'performance_score': 7.2, 'title': 'Good'},
            {'video_id': 'v3', 'performance_score': 4.8, 'title': 'Average'},
            {'video_id': 'v4', 'performance_score': 3.1, 'title': 'Poor'},
        ]

        # Get top 2 with min score 5.0
        top = analyzer.get_top_performers(performances, top_n=2, min_score=5.0)

        print(f"✅ Selected {len(top)} top performers (min_score=5.0)")
        for perf in top:
            print(f"   - {perf['title']}: {perf['performance_score']:.1f}")

        if len(top) == 2 and all(p['performance_score'] >= 5.0 for p in top):
            print(f"✅ Correctly filtered top performers")
            return True
        else:
            print(f"❌ Top performers filtering failed")
            return False

    except Exception as e:
        print(f"❌ Top performers test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_recency_bonus():
    """Test recency bonus calculation"""
    print("\n" + "=" * 60)
    print("TEST 5: Recency Bonus")
    print("=" * 60)

    try:
        perf_path = project_root / "pipeline/learning/performance.py"
        perf_module = import_module_from_path("performance", perf_path)

        PerformanceAnalyzer = perf_module.PerformanceAnalyzer

        analyzer = PerformanceAnalyzer()

        from datetime import datetime, timedelta

        test_cases = [
            (datetime.now().isoformat() + 'Z', "Today", 2.0),
            ((datetime.now() - timedelta(days=3)).isoformat() + 'Z', "3 days ago", 2.0),
            ((datetime.now() - timedelta(days=15)).isoformat() + 'Z', "15 days ago", 1.5),
            ((datetime.now() - timedelta(days=60)).isoformat() + 'Z', "60 days ago", 1.2),
            ((datetime.now() - timedelta(days=180)).isoformat() + 'Z', "180 days ago", 1.0),
        ]

        all_passed = True
        for published_at, label, expected_min in test_cases:
            bonus = analyzer._calculate_recency_bonus(published_at)
            status = "✅" if bonus >= expected_min else "❌"
            print(f"{status} {label}: bonus={bonus:.1f} (expected >={expected_min})")
            if bonus < expected_min:
                all_passed = False

        return all_passed

    except Exception as e:
        print(f"❌ Recency bonus test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("PHASE 3: PERFORMANCE ANALYZER - TEST SUITE")
    print("=" * 60)

    results = {
        "Performance Import": test_performance_import(),
        "Score Calculation": test_score_calculation(),
        "Channel Analysis": test_channel_analysis(),
        "Top Performers": test_top_performers(),
        "Recency Bonus": test_recency_bonus(),
    }

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:25s}: {status}")

    all_passed = all(results.values())

    if all_passed:
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED - Task 3.2 Complete!")
        print("=" * 60)
        print("\nPhase 3 Task 3.2 completed:")
        print("  • Performance scoring: CTR, watch time, engagement")
        print("  • Channel analysis: Compare vs averages")
        print("  • Top performers: Filter top 20 videos")
        print("  • Recency bonus: Recent videos get higher scores")
        print("\nNext: Task 3.3 - Automated Learning System")
        return 0
    else:
        print("\n" + "=" * 60)
        print("❌ SOME TESTS FAILED")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
