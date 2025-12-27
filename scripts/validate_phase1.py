#!/usr/bin/env python3
"""
Phase 1 Validation Script
Checks all components are properly installed and working
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def check_directories():
    """Check required directories exist"""
    print("=" * 60)
    print("1. Checking Directory Structure")
    print("=" * 60)

    required_dirs = [
        "pipeline/ai_metadata",
        "pipeline/streamers",
        "pipeline/streamers/profiles",
        "config",
        "database",
        "scripts",
        "data",
    ]

    all_ok = True
    for dir_path in required_dirs:
        path = Path(dir_path)
        if path.exists() and path.is_dir():
            print(f"✅ {dir_path}")
        else:
            print(f"❌ {dir_path} - NOT FOUND")
            all_ok = False

    return all_ok

def check_config_files():
    """Check config files exist"""
    print("\n" + "=" * 60)
    print("2. Checking Configuration Files")
    print("=" * 60)

    required_files = [
        "config/platforms.yaml",
        "config/ai_models.yaml",
        "pipeline/streamers/profiles/_TEMPLATE.yaml",
        "pipeline/streamers/profiles/sejm.yaml",
    ]

    all_ok = True
    for file_path in required_files:
        path = Path(file_path)
        if path.exists() and path.is_file():
            size = path.stat().st_size
            print(f"✅ {file_path} ({size} bytes)")
        else:
            print(f"❌ {file_path} - NOT FOUND")
            all_ok = False

    return all_ok

def check_streamer_manager():
    """Test StreamerManager functionality"""
    print("\n" + "=" * 60)
    print("3. Testing StreamerManager")
    print("=" * 60)

    try:
        # Import directly to avoid pipeline dependencies
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "streamers.manager",
            Path("pipeline/streamers/manager.py")
        )
        manager_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(manager_module)

        StreamerManager = manager_module.StreamerManager
        manager = StreamerManager()

        # Check profiles loaded
        profiles = manager.list_all()
        print(f"✅ Loaded {len(profiles)} profile(s)")

        for profile in profiles:
            print(f"   - {profile.name} ({profile.streamer_id})")
            print(f"     Language: {profile.primary_language}")
            print(f"     Type: {profile.channel_type}")

        # Test Sejm profile detection
        sejm_profile = manager.get("sejm")
        if sejm_profile:
            print(f"✅ Sejm profile loaded: {sejm_profile.name}")

            # Test YouTube detection
            detected = manager.detect_from_youtube("UCSlsIpJrotOvA1wbA4Z46zA")
            if detected:
                print(f"✅ YouTube auto-detection works: {detected.name}")
            else:
                print("❌ YouTube auto-detection failed")
                return False
        else:
            print("❌ Sejm profile not found")
            return False

        return True

    except Exception as e:
        print(f"❌ Error testing StreamerManager: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_database():
    """Check database extension"""
    print("\n" + "=" * 60)
    print("4. Checking Database Extension")
    print("=" * 60)

    try:
        import sqlite3

        db_path = Path("data/uploader.db")
        if not db_path.exists():
            print(f"❌ Database not found at {db_path}")
            return False

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check tables
        expected_tables = [
            'video_generation_cache',
            'streamer_learned_examples',
            'api_cost_tracking'
        ]

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        all_ok = True
        for table in expected_tables:
            if table in tables:
                print(f"✅ Table: {table}")
            else:
                print(f"❌ Table missing: {table}")
                all_ok = False

        # Check indices
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indices = [row[0] for row in cursor.fetchall() if not row[0].startswith('sqlite_')]
        print(f"✅ {len(indices)} custom indices created")

        conn.close()
        return all_ok

    except Exception as e:
        print(f"❌ Error checking database: {e}")
        return False

def check_dependencies():
    """Check Python dependencies"""
    print("\n" + "=" * 60)
    print("5. Checking Python Dependencies")
    print("=" * 60)

    required = [
        ('pydantic', 'StreamerManager models'),
        ('yaml', 'Config file parsing'),
        ('sqlite3', 'Database operations'),
    ]

    all_ok = True
    for module, purpose in required:
        try:
            __import__(module)
            print(f"✅ {module:15s} - {purpose}")
        except ImportError:
            print(f"❌ {module:15s} - NOT INSTALLED ({purpose})")
            all_ok = False

    return all_ok

def main():
    """Run all validation checks"""
    print("\n" + "=" * 60)
    print("PHASE 1 VALIDATION - Core Infrastructure")
    print("=" * 60)

    results = {
        "Directories": check_directories(),
        "Config Files": check_config_files(),
        "StreamerManager": check_streamer_manager(),
        "Database": check_database(),
        "Dependencies": check_dependencies(),
    }

    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    for check, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{check:20s}: {status}")

    all_passed = all(results.values())

    if all_passed:
        print("\n" + "=" * 60)
        print("✅ PHASE 1 COMPLETE - Ready for Phase 2!")
        print("=" * 60)
        print("\nNext steps:")
        print("  1. Git commit: git add -A && git commit -m 'Phase 1: Core infrastructure'")
        print("  2. Proceed to Phase 2: AI Integration")
        return 0
    else:
        print("\n" + "=" * 60)
        print("❌ VALIDATION FAILED - Please fix errors above")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
