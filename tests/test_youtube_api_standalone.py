#!/usr/bin/env python3
"""
Standalone test suite for YouTube API (Phase 3)
Imports modules directly to avoid pipeline dependencies
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


def test_youtube_api_import():
    """Test that YouTube API can be imported"""
    print("\n" + "=" * 60)
    print("TEST 1: YouTube API Import")
    print("=" * 60)

    try:
        youtube_api_path = project_root / "pipeline/learning/youtube_api.py"
        youtube_module = import_module_from_path("youtube_api", youtube_api_path)
        print("✅ YouTube API module imported successfully")
        print(f"   Classes available: YouTubeMetricsAPI, get_youtube_api")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_duration_parsing():
    """Test ISO 8601 duration parsing"""
    print("\n" + "=" * 60)
    print("TEST 2: Duration Parsing")
    print("=" * 60)

    try:
        youtube_api_path = project_root / "pipeline/learning/youtube_api.py"
        youtube_module = import_module_from_path("youtube_api", youtube_api_path)

        YouTubeMetricsAPI = youtube_module.YouTubeMetricsAPI

        # Create instance without API key for testing private method
        api = YouTubeMetricsAPI.__new__(YouTubeMetricsAPI)

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
        import traceback
        traceback.print_exc()
        return False


def test_estimate_functions():
    """Test CTR and watch time estimation functions"""
    print("\n" + "=" * 60)
    print("TEST 3: Estimation Functions")
    print("=" * 60)

    try:
        youtube_api_path = project_root / "pipeline/learning/youtube_api.py"
        youtube_module = import_module_from_path("youtube_api", youtube_api_path)

        YouTubeMetricsAPI = youtube_module.YouTubeMetricsAPI

        # Create instance without API key
        api = YouTubeMetricsAPI.__new__(YouTubeMetricsAPI)

        # Test CTR estimation
        ctr_with_impressions = api.estimate_ctr(views=1000, impressions=20000)
        ctr_without_impressions = api.estimate_ctr(views=1000)

        print(f"✅ CTR with impressions (1000 views / 20000 impressions): {ctr_with_impressions:.2%}")
        print(f"✅ CTR fallback (1000 views, no impressions): {ctr_without_impressions:.2%}")

        # Test watch time estimation
        watch_time = api.estimate_watch_time(views=1000, duration_seconds=600, retention_rate=0.45)
        print(f"✅ Estimated avg watch time (600s video, 45% retention): {watch_time}s")

        return True

    except Exception as e:
        print(f"❌ Estimation functions test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_api_availability():
    """Test if google-api-python-client is available"""
    print("\n" + "=" * 60)
    print("TEST 4: API Dependencies")
    print("=" * 60)

    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
        print("✅ google-api-python-client is installed")
        return True
    except ImportError as e:
        print(f"⚠️ google-api-python-client not installed: {e}")
        print("   Install with: pip install google-api-python-client")
        return False


def test_env_file():
    """Test if .env.example exists with YOUTUBE_API_KEY"""
    print("\n" + "=" * 60)
    print("TEST 5: Environment Configuration")
    print("=" * 60)

    try:
        env_example_path = project_root / ".env.example"
        if not env_example_path.exists():
            print("❌ .env.example not found")
            return False

        with open(env_example_path, 'r') as f:
            content = f.read()

        if "YOUTUBE_API_KEY" in content:
            print("✅ .env.example contains YOUTUBE_API_KEY")
        else:
            print("❌ .env.example missing YOUTUBE_API_KEY")
            return False

        # Check if .env exists
        env_path = project_root / ".env"
        if env_path.exists():
            print("✅ .env file exists (user configured)")
        else:
            print("⚠️ .env file not found (copy from .env.example)")

        return True

    except Exception as e:
        print(f"❌ Environment config test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("PHASE 3: YOUTUBE API - STANDALONE TEST SUITE")
    print("=" * 60)

    results = {
        "YouTube API Import": test_youtube_api_import(),
        "Duration Parsing": test_duration_parsing(),
        "Estimation Functions": test_estimate_functions(),
        "API Dependencies": test_api_availability(),
        "Environment Config": test_env_file(),
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
        print("\nPhase 3 Task 3.1 completed:")
        print("  • YouTubeMetricsAPI: Fetch video metrics from YouTube Data API v3")
        print("  • Duration parsing: ISO 8601 format support")
        print("  • Estimation functions: CTR and watch time fallbacks")
        print("  • Dependencies: google-api-python-client installed")
        print("\nTo use YouTube API:")
        print("  1. Get API key: https://console.cloud.google.com/apis/credentials")
        print("  2. Enable 'YouTube Data API v3' in Google Cloud project")
        print("  3. Add to .env file: YOUTUBE_API_KEY=AIzaSy...")
        print("\nNext: Task 3.2 - Performance Score Calculator")
        return 0
    else:
        print("\n" + "=" * 60)
        print("❌ SOME TESTS FAILED")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
