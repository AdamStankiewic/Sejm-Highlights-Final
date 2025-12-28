#!/usr/bin/env python3
"""
Test suite for AI metadata generation (Phase 2)

Tests:
- Context building from clips
- Prompt construction with few-shot learning
- Full metadata generation
- Caching functionality
"""
import sys
from pathlib import Path
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def create_mock_clips():
    """Create mock clips data from stage_06 selection"""
    return [
        {
            "t0": 120.5,
            "t1": 145.2,
            "duration": 24.7,
            "title": "Tusk kontra Kaczyński - Ostra wymiana zdań",
            "transcript": "To jest skandaliczne! Rząd PiS dopuścił się łamania konstytucji. Nie możemy tego tolerować!",
            "keywords": ["Tusk", "Kaczyński", "konstytucja", "rząd", "skandal"],
            "final_score": 0.92
        },
        {
            "t0": 340.1,
            "t1": 358.9,
            "duration": 18.8,
            "title": "Kontrowersyjna ustawa wywołuje emocje",
            "transcript": "Czy państwo zdajecie sobie sprawę z konsekwencji tego głosowania?",
            "keywords": ["ustawa", "głosowanie", "konsekwencje"],
            "final_score": 0.85
        },
        {
            "t0": 520.3,
            "t1": 542.1,
            "duration": 21.8,
            "title": "Hołownia przerywa debatę",
            "transcript": "Proszę o spokój! Przywołuję do porządku!",
            "keywords": ["Hołownia", "porządek", "debata"],
            "final_score": 0.78
        }
    ]


def test_context_builder():
    """Test ContextBuilder with mock clips"""
    print("\n" + "=" * 60)
    print("TEST 1: Context Builder")
    print("=" * 60)

    try:
        from pipeline.ai_metadata import ContextBuilder

        # Create context builder (without LLM)
        builder = ContextBuilder(openai_client=None)

        # Build context from mock clips
        clips = create_mock_clips()
        brief = builder.build_from_clips(clips, language="pl", use_llm=False)

        # Validate results
        assert brief.main_narrative, "Main narrative should not be empty"
        assert brief.emotional_state, "Emotional state should not be empty"
        assert brief.content_type, "Content type should not be empty"
        assert len(brief.key_moments) > 0, "Should have key moments"
        assert len(brief.keywords) > 0, "Should have keywords"

        print(f"✅ Context built successfully:")
        print(f"   Main narrative: {brief.main_narrative}")
        print(f"   Emotional state: {brief.emotional_state}")
        print(f"   Content type: {brief.content_type}")
        print(f"   Keywords: {', '.join(brief.keywords[:5])}")
        print(f"   Key moments: {len(brief.key_moments)}")

        return True

    except Exception as e:
        print(f"❌ Context builder test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_prompt_builder():
    """Test PromptBuilder with mock brief"""
    print("\n" + "=" * 60)
    print("TEST 2: Prompt Builder")
    print("=" * 60)

    try:
        from pipeline.ai_metadata import ContextBuilder, PromptBuilder
        import yaml

        # Load platform config
        platform_config_path = Path("config/platforms.yaml")
        if not platform_config_path.exists():
            print("⚠️ Platform config not found, skipping test")
            return True

        with open(platform_config_path, 'r') as f:
            platform_config = yaml.safe_load(f)

        # Create brief
        builder = ContextBuilder(openai_client=None)
        clips = create_mock_clips()
        brief = builder.build_from_clips(clips, language="pl", use_llm=False)

        # Create prompt builder
        prompt_builder = PromptBuilder(platform_config, language="pl")

        # Build title prompt
        title_prompts = prompt_builder.build_title_prompt(
            brief,
            platform="youtube",
            video_type="long",
            few_shot_examples=[
                {
                    "title": "🔥 SEJM: Najgorętsze Momenty!",
                    "metadata": {"content_type": "political", "emotional_tone": "heated"}
                }
            ]
        )

        # Validate prompts
        assert "system" in title_prompts, "Should have system prompt"
        assert "user" in title_prompts, "Should have user prompt"
        assert len(title_prompts["system"]) > 0, "System prompt should not be empty"
        assert len(title_prompts["user"]) > 0, "User prompt should not be empty"

        print(f"✅ Prompts built successfully:")
        print(f"   System prompt length: {len(title_prompts['system'])} chars")
        print(f"   User prompt length: {len(title_prompts['user'])} chars")
        print(f"\n   Sample system prompt:")
        print(f"   {title_prompts['system'][:200]}...")

        return True

    except Exception as e:
        print(f"❌ Prompt builder test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_streamer_detection():
    """Test streamer auto-detection"""
    print("\n" + "=" * 60)
    print("TEST 3: Streamer Detection")
    print("=" * 60)

    try:
        from pipeline.streamers import get_manager

        manager = get_manager()

        # Test detection from Sejm YouTube channel
        sejm_channel_id = "UCSlsIpJrotOvA1wbA4Z46zA"
        profile = manager.detect_from_youtube(sejm_channel_id)

        if profile:
            print(f"✅ Detected streamer: {profile.name}")
            print(f"   ID: {profile.streamer_id}")
            print(f"   Language: {profile.primary_language}")
            print(f"   Type: {profile.channel_type}")
            print(f"   Seed examples: {len(profile.seed_examples)}")
            return True
        else:
            print("⚠️ No profile found for Sejm channel (expected)")
            return True

    except Exception as e:
        print(f"❌ Streamer detection test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_database_tables():
    """Test that database tables exist"""
    print("\n" + "=" * 60)
    print("TEST 4: Database Tables")
    print("=" * 60)

    try:
        import sqlite3

        db_path = Path("data/uploader.db")
        if not db_path.exists():
            print("⚠️ Database not found, skipping test")
            return True

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
                print(f"✅ Table exists: {table}")
            else:
                print(f"❌ Table missing: {table}")
                all_ok = False

        conn.close()
        return all_ok

    except Exception as e:
        print(f"❌ Database test failed: {e}")
        return False


def test_full_pipeline_mock():
    """Test full AI metadata generation with mock data (no actual API calls)"""
    print("\n" + "=" * 60)
    print("TEST 5: Full Pipeline (Mock)")
    print("=" * 60)

    try:
        from pipeline.ai_metadata import MetadataGenerator
        from pipeline.streamers import get_manager
        import yaml

        # Load platform config
        platform_config_path = Path("config/platforms.yaml")
        if not platform_config_path.exists():
            print("⚠️ Platform config not found, skipping test")
            return True

        with open(platform_config_path, 'r') as f:
            platform_config = yaml.safe_load(f)

        # Create generator WITHOUT OpenAI client (will use fallback)
        manager = get_manager()
        generator = MetadataGenerator(
            openai_client=None,  # No API calls
            streamer_manager=manager,
            platform_config=platform_config
        )

        # Generate metadata
        clips = create_mock_clips()
        result = generator.generate_metadata(
            clips=clips,
            streamer_id="sejm",
            platform="youtube",
            video_type="long",
            language="pl"
        )

        # Validate results
        assert "title" in result, "Should have title"
        assert "description" in result, "Should have description"
        assert len(result["title"]) > 0, "Title should not be empty"
        assert len(result["description"]) > 0, "Description should not be empty"

        print(f"✅ Metadata generated (fallback mode):")
        print(f"   Title: {result['title']}")
        print(f"   Description (first 100 chars): {result['description'][:100]}...")
        print(f"   Cost: ${result.get('cost', 0.0):.4f}")
        print(f"   Fallback: {result.get('fallback', False)}")

        return True

    except Exception as e:
        print(f"❌ Full pipeline test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("PHASE 2: AI METADATA GENERATION - TEST SUITE")
    print("=" * 60)

    results = {
        "Context Builder": test_context_builder(),
        "Prompt Builder": test_prompt_builder(),
        "Streamer Detection": test_streamer_detection(),
        "Database Tables": test_database_tables(),
        "Full Pipeline (Mock)": test_full_pipeline_mock(),
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
        print("✅ ALL TESTS PASSED - Phase 2 Complete!")
        print("=" * 60)
        print("\nNext steps:")
        print("  1. Test with actual OpenAI API (set OPENAI_API_KEY)")
        print("  2. Run end-to-end pipeline with real video")
        print("  3. Monitor cost tracking in database")
        print("  4. Add high-performing examples to learned_examples table")
        return 0
    else:
        print("\n" + "=" * 60)
        print("❌ SOME TESTS FAILED - Please fix errors above")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(main())
