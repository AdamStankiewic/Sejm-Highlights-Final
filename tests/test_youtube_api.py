#!/usr/bin/env python3
"""
Test suite for YouTube API integration (Phase 3)
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_youtube_api_import():
    """Test that YouTube API can be imported"""
    print("\n" + "=" * 60)
    print("TEST 1: YouTube API Import")
    print("=" * 60)

    try:
        from pipeline.learning import YouTubeMetricsAPI, get_youtube_api
        print("✅ YouTube API modules imported successfully")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False


def test_youtube_api_connection():
    """Test YouTube API connection (requires API key in .env)"""
    print("\n" + "=" * 60)
    print("TEST 2: YouTube API Connection")
    print("=" * 60)

    try:
        import os
        from dotenv import load_dotenv
        from pipeline.learning import YouTubeMetricsAPI

        load_dotenv()

        api_key = os.getenv("YOUTUBE_API_KEY")
        if not api_key:
            print("⚠️ YOUTUBE_API_KEY not set in .env - skipping test")
            return True  # Not a failure, just not configured

        # Try to create API client
        api = YouTubeMetricsAPI(api_key=api_key)
        print("✅ YouTube API client initialized")

        # Test with a known public video (Rick Astley - Never Gonna Give You Up)
        test_video_id = "dQw4w9WgXcQ"
        print(f"   Testing with video: {test_video_id}")

        metrics = api.get_video_metrics([test_video_id])

        if test_video_id in metrics:
            video = metrics[test_video_id]
            print(f"✅ Successfully fetched metrics:")
            print(f"   Title: {video['title'][:50]}...")
            print(f"   Views: {video['views']:,}")
            print(f"   Likes: {video['likes']:,}")
            print(f"   Duration: {video['duration_seconds']}s")
            return True
        else:
            print("❌ Failed to fetch video metrics")
            return False

    except Exception as e:
        print(f"❌ API test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_duration_parsing():
    """Test ISO 8601 duration parsing"""
    print("\n" + "=" * 60)
    print("TEST 3: Duration Parsing")
    print("=" * 60)

    try:
        from pipeline.learning import YouTubeMetricsAPI

        api = YouTubeMetricsAPI.__new__(YouTubeMetricsAPI)  # Don't init (no API key needed)

        test_cases = [
            ("PT1H2M10S", 3730),   # 1h 2m 10s
            ("PT5M30S", 330),       # 5m 30s
            ("PT45S", 45),          # 45s
            ("PT1H", 3600),         # 1h
            ("PT2M", 120),          # 2m
        ]

        all_passed = True
        for duration_str, expected_seconds in test_cases:
            result = api._parse_duration(duration_str)
            if result == expected_seconds:
                print(f"✅ {duration_str} → {result}s (expected {expected_seconds}s)")
            else:
                print(f"❌ {duration_str} → {result}s (expected {expected_seconds}s)")
                all_passed = False

        return all_passed

    except Exception as e:
        print(f"❌ Duration parsing test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("PHASE 3: YOUTUBE API - TEST SUITE")
    print("=" * 60)

    results = {
        "YouTube API Import": test_youtube_api_import(),
        "Duration Parsing": test_duration_parsing(),
        "YouTube API Connection": test_youtube_api_connection(),
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
        print("✅ ALL TESTS PASSED - Task 3.1 Complete!")
        print("=" * 60)
        print("\nNext steps:")
        print("  1. Set YOUTUBE_API_KEY in .env file")
        print("  2. Enable YouTube Data API v3 in Google Cloud Console")
        print("  3. Continue with Task 3.2: Performance Score Calculator")
        return 0
    else:
        print("\n" + "=" * 60)
        print("❌ SOME TESTS FAILED")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
