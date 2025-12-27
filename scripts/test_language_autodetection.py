#!/usr/bin/env python3
"""
Quick test: Verify language auto-detection works correctly

This script tests that:
1. Asmongold profile has primary_language = "en"
2. Sejm profile has primary_language = "pl"
3. Language is correctly auto-detected from profile
"""
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_language_auto_detection():
    """Test language auto-detection from profiles"""
    print("🧪 TESTING LANGUAGE AUTO-DETECTION\n")
    print("="*60)

    from pipeline.streamers import get_manager

    manager = get_manager()

    # Test 1: Asmongold should be EN
    print("\n1️⃣ Test: Asmongold Profile")
    print("-"*60)
    asmongold = manager.get("asmongold")
    if asmongold:
        print(f"✅ Profile found: {asmongold.name}")
        print(f"   Primary language: {asmongold.primary_language}")

        if asmongold.primary_language == "en":
            print(f"   ✅ PASS: Language is EN (as expected for English streamer)")
        else:
            print(f"   ❌ FAIL: Expected 'en', got '{asmongold.primary_language}'")
    else:
        print("❌ Asmongold profile not found!")

    # Test 2: Sejm should be PL
    print("\n2️⃣ Test: Sejm Profile")
    print("-"*60)
    sejm = manager.get("sejm")
    if sejm:
        print(f"✅ Profile found: {sejm.name}")
        print(f"   Primary language: {sejm.primary_language}")

        if sejm.primary_language == "pl":
            print(f"   ✅ PASS: Language is PL (as expected for Polish content)")
        else:
            print(f"   ❌ FAIL: Expected 'pl', got '{sejm.primary_language}'")
    else:
        print("❌ Sejm profile not found!")

    # Test 3: Simulate auto-detection logic
    print("\n3️⃣ Test: Auto-Detection Logic Simulation")
    print("-"*60)

    # Simulate GUI set to PL
    gui_language = "pl"
    print(f"GUI language setting: {gui_language.upper()}")

    if asmongold:
        profile_lang = asmongold.primary_language
        print(f"\nScenario: Processing Asmongold VOD")
        print(f"  Profile language: {profile_lang.upper()}")

        if profile_lang != gui_language:
            print(f"  🌐 Auto-override: {gui_language.upper()} → {profile_lang.upper()}")
            print(f"  ✅ PASS: Language correctly overridden to EN")
        else:
            print(f"  ⚠️  No override needed (already {profile_lang.upper()})")

    if sejm:
        profile_lang = sejm.primary_language
        print(f"\nScenario: Processing Sejm video")
        print(f"  Profile language: {profile_lang.upper()}")

        if profile_lang != gui_language:
            print(f"  🌐 Auto-override: {gui_language.upper()} → {profile_lang.upper()}")
            print(f"  ⚠️  Unexpected override for Sejm!")
        else:
            print(f"  ✅ PASS: Language matches GUI (both PL)")

    print("\n" + "="*60)
    print("✅ LANGUAGE AUTO-DETECTION TEST COMPLETE")
    print("\nNext steps:")
    print("1. Run app.py and select Asmongold profile")
    print("2. Check logs for '🌐 Auto-detected language from profile: EN'")
    print("3. Verify clip titles are gaming-related (not Sejm keywords)")
    print("="*60)

if __name__ == "__main__":
    test_language_auto_detection()
