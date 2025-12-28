#!/usr/bin/env python3
"""
Test script to verify AI metadata generation and streamer learning system.

Usage:
    python scripts/test_metadata_generation.py
"""
import sys
import sqlite3
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_database_status():
    """Check database tables and content"""
    print("="*60)
    print("1. DATABASE STATUS CHECK")
    print("="*60)

    db_path = "data/uploader.db"

    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        return False

    print(f"✅ Database found: {db_path}\n")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    tables = [row[0] for row in cursor.fetchall()]

    required_tables = [
        'streamer_learned_examples',
        'video_generation_cache',
        'api_cost_tracking'
    ]

    print("Tables:")
    for table in required_tables:
        exists = table in tables
        status = "✅" if exists else "❌"
        print(f"  {status} {table}")

    print("\nTable Counts:")

    # Count rows
    for table in required_tables:
        if table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            count = cursor.fetchone()[0]
            print(f"  {table}: {count} rows")

            # Show details if rows exist
            if table == 'streamer_learned_examples' and count > 0:
                cursor.execute("""
                    SELECT streamer_id, COUNT(*), AVG(performance_score)
                    FROM streamer_learned_examples
                    WHERE is_active=1
                    GROUP BY streamer_id
                """)
                print("\n  Learned Examples by Streamer:")
                for row in cursor.fetchall():
                    print(f"    - {row[0]}: {row[1]} examples (avg score: {row[2]:.2f})")

            if table == 'video_generation_cache' and count > 0:
                cursor.execute("""
                    SELECT streamer_id, COUNT(*), SUM(metadata_cost)
                    FROM video_generation_cache
                    GROUP BY streamer_id
                """)
                print("\n  Cached Metadata by Streamer:")
                for row in cursor.fetchall():
                    cost = row[2] if row[2] else 0.0
                    print(f"    - {row[0]}: {row[1]} cached entries (${cost:.4f} saved)")

            if table == 'api_cost_tracking' and count > 0:
                cursor.execute("""
                    SELECT operation, COUNT(*), SUM(cost_usd)
                    FROM api_cost_tracking
                    GROUP BY operation
                """)
                print("\n  API Costs by Operation:")
                for row in cursor.fetchall():
                    cost = row[2] if row[2] else 0.0
                    print(f"    - {row[0]}: {row[1]} calls (${cost:.4f})")

    conn.close()

    print("\n" + "="*60)
    return True


def test_streamer_profiles():
    """Check if streamer profiles exist and are valid"""
    print("\n2. STREAMER PROFILES CHECK")
    print("="*60)

    try:
        from pipeline.streamers import get_manager

        # This will fail if moviepy is missing, but we can work around it
        try:
            manager = get_manager()
        except Exception as e:
            print(f"⚠️  Cannot load StreamerManager due to missing dependency:")
            print(f"   {str(e)}")
            print("\n   Falling back to manual profile check...")

            # Manual check
            profiles_dir = Path("pipeline/streamers/profiles")
            if not profiles_dir.exists():
                print(f"❌ Profiles directory not found: {profiles_dir}")
                return False

            profiles = list(profiles_dir.glob("*.yaml"))
            profiles = [p for p in profiles if not p.name.startswith("_")]

            print(f"\n✅ Found {len(profiles)} profile(s):\n")
            for profile_path in profiles:
                print(f"  📄 {profile_path.name}")

                # Try to read YAML
                try:
                    import yaml
                    with open(profile_path) as f:
                        data = yaml.safe_load(f)

                    print(f"     Streamer ID: {data.get('streamer_id', 'N/A')}")
                    print(f"     Name: {data.get('name', 'N/A')}")
                    print(f"     Language: {data.get('content', {}).get('primary_language', 'N/A')}")

                    # Check seed examples
                    seed_count = len(data.get('seed_examples', []))
                    print(f"     Seed examples: {seed_count}")

                    # Check generation config
                    gen_config = data.get('generation', {})
                    if gen_config:
                        print(f"     Title model: {gen_config.get('title_model', 'N/A')}")
                        print(f"     Description model: {gen_config.get('description_model', 'N/A')}")

                    print()
                except Exception as e:
                    print(f"     ⚠️  Error reading profile: {e}\n")

            return len(profiles) > 0

    except Exception as e:
        print(f"❌ Error checking profiles: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "="*60)
    return True


def test_config():
    """Check if YouTube upload and AI metadata are configured"""
    print("\n3. CONFIGURATION CHECK")
    print("="*60)

    config_path = Path("config.yml")

    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        return False

    try:
        import yaml
        with open(config_path) as f:
            config = yaml.safe_load(f)

        print("✅ Config file loaded\n")

        # Check YouTube settings
        youtube_config = config.get('youtube', {})
        youtube_enabled = youtube_config.get('enabled', False)

        print(f"YouTube Upload:")
        print(f"  enabled: {youtube_enabled} {'✅' if youtube_enabled else '⚠️ (AI generation only runs with YouTube upload)'}")

        if youtube_enabled:
            print(f"  schedule_as_premiere: {youtube_config.get('schedule_as_premiere', False)}")
            print(f"  privacy_status: {youtube_config.get('privacy_status', 'N/A')}")

        print()

    except Exception as e:
        print(f"❌ Error reading config: {e}")
        return False

    print("="*60)
    return True


def test_ai_metadata_availability():
    """Check if AI metadata components can be imported"""
    print("\n4. AI METADATA COMPONENTS CHECK")
    print("="*60)

    try:
        print("Importing AI metadata components...")

        # Try importing MetadataGenerator
        try:
            from pipeline.ai_metadata import MetadataGenerator
            print("  ✅ MetadataGenerator")
        except ImportError as e:
            print(f"  ❌ MetadataGenerator: {e}")
            return False

        # Try importing ContextBuilder
        try:
            from pipeline.ai_metadata.context_builder import ContextBuilder
            print("  ✅ ContextBuilder")
        except ImportError as e:
            print(f"  ❌ ContextBuilder: {e}")
            return False

        # Try importing PromptBuilder
        try:
            from pipeline.ai_metadata.prompt_builder import PromptBuilder
            print("  ✅ PromptBuilder")
        except ImportError as e:
            print(f"  ❌ PromptBuilder: {e}")
            return False

        # Try importing LearningLoop
        try:
            from pipeline.learning.learning_loop import LearningLoop
            print("  ✅ LearningLoop")
        except ImportError as e:
            print(f"  ❌ LearningLoop: {e}")
            return False

        print("\n✅ All AI metadata components available!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

    print("\n" + "="*60)
    return True


def print_summary():
    """Print summary and next steps"""
    print("\n" + "="*60)
    print("SUMMARY & NEXT STEPS")
    print("="*60)

    db_path = Path("data/uploader.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if database has content
    cursor.execute("SELECT COUNT(*) FROM streamer_learned_examples;")
    learned_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM video_generation_cache;")
    cache_count = cursor.fetchone()[0]

    conn.close()

    if learned_count == 0 and cache_count == 0:
        print("\n⚠️  STATUS: AI Metadata system is READY but NOT YET USED\n")
        print("📋 To start using AI metadata generation:\n")
        print("Option 1: Run Learning Loop (recommended first)")
        print("  → Populates database with learned examples from YouTube")
        print("  → Requires YouTube Data API key")
        print("  → Command:")
        print("     python scripts/run_learning_loop.py --streamer sejm --api-key YOUR_KEY\n")

        print("Option 2: Run Pipeline with YouTube Upload")
        print("  → Set youtube.enabled = true in config.yml")
        print("  → Run: python app.py or python processor.py --input video.mp4")
        print("  → AI generation will trigger during YouTube upload stage\n")

        print("Option 3: Test AI Generation without YouTube")
        print("  → TODO: Create standalone test script")
        print("  → Would generate title/description for sample clips\n")

    elif learned_count > 0:
        print("\n✅ STATUS: AI Metadata system is ACTIVE and LEARNING\n")
        print(f"  📊 Learned examples: {learned_count}")
        print(f"  💾 Cached metadata: {cache_count}")
        print("\n  System is ready to generate titles/descriptions!")
        print("  Future generations will use learned examples for better results.\n")

    print("="*60)
    print("\n📖 For detailed documentation, see:")
    print("   METADATA_SYSTEM_REPORT.md")
    print("\n")


def main():
    """Run all tests"""
    print("\n🔍 AI METADATA GENERATION & STREAMER LEARNING - SYSTEM TEST\n")

    # Run tests
    tests = [
        test_database_status,
        test_streamer_profiles,
        test_config,
        test_ai_metadata_availability
    ]

    results = []
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"\n❌ Test failed: {test_func.__name__}")
            print(f"   Error: {e}")
            import traceback
            traceback.print_exc()
            results.append(False)

    # Print summary
    print_summary()

    # Overall result
    if all(results):
        print("✅ All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed - check output above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
