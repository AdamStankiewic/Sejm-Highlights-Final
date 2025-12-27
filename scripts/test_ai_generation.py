#!/usr/bin/env python3
"""
Quick test script for AI metadata generation

Usage:
    python scripts/test_ai_generation.py --streamer sejm
    python scripts/test_ai_generation.py --streamer sejm --content-type sejm_meeting_pl
    python scripts/test_ai_generation.py --streamer asmongold --content-type asmongold_gaming
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import os
import yaml

def test_generation(streamer_id, content_type=None):
    """Test AI generation with mock data"""

    print("=" * 60)
    print(f"AI METADATA GENERATION TEST")
    print("=" * 60)
    print(f"  Streamer: {streamer_id}")
    print(f"  Content Type: {content_type or 'auto-detect'}")
    print("=" * 60)

    # Load streamer
    try:
        from pipeline.streamers import get_manager
        manager = get_manager()
        streamer = manager.get(streamer_id)

        if not streamer:
            print(f"\n❌ Streamer '{streamer_id}' not found")
            print(f"\nAvailable streamers:")
            for s in manager.list_all():
                print(f"  - {s.streamer_id} ({s.name})")
            return

        print(f"\n✅ Loaded: {streamer.name}")
        print(f"   Language: {streamer.primary_language}")
        print(f"   Type: {streamer.channel_type}")

    except Exception as e:
        print(f"\n❌ Failed to load streamer: {e}")
        return

    # Mock clips data (sejm-specific)
    if streamer_id == "sejm":
        mock_clips = [
            {
                "title": "Debata o budżecie",
                "transcript": "Minister przedstawia projekt budżetu państwa na rok 2025. "
                              "Opozycja podnosi wątpliwości dotyczące wydatków na obronność.",
                "keywords": ["budżet", "minister", "finanse", "2025"],
                "t0": 120.0,
                "final_score": 0.85
            },
            {
                "title": "Pytanie posła",
                "transcript": "Poseł Kowalski pyta ministra o plany dotyczące reformy systemu podatkowego.",
                "keywords": ["poseł", "pytanie", "podatki", "reforma"],
                "t0": 450.0,
                "final_score": 0.78
            },
            {
                "title": "Odpowiedź ministra",
                "transcript": "Minister odnosi się do zarzutów opozycji i przedstawia szczegółowy plan reform.",
                "keywords": ["minister", "odpowiedź", "reformy"],
                "t0": 680.0,
                "final_score": 0.72
            }
        ]
    else:
        # Generic gaming stream clips
        mock_clips = [
            {
                "title": "Epic play",
                "transcript": "Oh my god, that was insane! Did you see that play?",
                "keywords": ["epic", "play", "gaming"],
                "t0": 120.0,
                "final_score": 0.88
            },
            {
                "title": "Funny moment",
                "transcript": "Chat, this is so dumb. I can't believe this just happened.",
                "keywords": ["funny", "chat", "reaction"],
                "t0": 350.0,
                "final_score": 0.82
            }
        ]

    # Load platform config
    try:
        config_path = Path("config/platforms.yaml")
        if not config_path.exists():
            print(f"\n⚠️ Platform config not found: {config_path}")
            print("   Creating default config...")
            config_path.parent.mkdir(exist_ok=True)
            default_config = {
                "youtube": {
                    "title_max_length": 100,
                    "description_max_length": 5000
                },
                "twitch": {
                    "title_max_length": 140
                }
            }
            with open(config_path, 'w') as f:
                yaml.dump(default_config, f)

        with open(config_path, 'r') as f:
            platform_config = yaml.safe_load(f)

    except Exception as e:
        print(f"\n⚠️ Failed to load platform config: {e}")
        platform_config = {"youtube": {"title_max_length": 100}}

    # Initialize generator
    try:
        from pipeline.ai_metadata import MetadataGenerator
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("\n❌ OPENAI_API_KEY not set in environment")
            print("   Set it in .env file or export OPENAI_API_KEY=sk-...")
            return

        client = OpenAI(api_key=api_key)
        generator = MetadataGenerator(
            openai_client=client,
            streamer_manager=manager,
            platform_config=platform_config,
            db_path="data/uploader.db"
        )

        print("\n✅ Initialized MetadataGenerator")

    except Exception as e:
        print(f"\n❌ Failed to initialize generator: {e}")
        import traceback
        traceback.print_exc()
        return

    # Generate metadata
    print(f"\n🤖 Generating metadata...")
    print(f"   Platform: youtube")
    print(f"   Video type: long")
    print(f"   Content type: {content_type or 'auto-detect'}")

    try:
        result = generator.generate_metadata(
            clips=mock_clips,
            streamer_id=streamer_id,
            platform="youtube",
            video_type="long",
            language=streamer.primary_language,
            content_type=content_type,
            force_regenerate=True  # Always regenerate for testing
        )

        # Display results
        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)

        print(f"\n📝 TITLE:")
        print(f"  {result['title']}")
        print(f"  Length: {len(result['title'])} chars")

        print(f"\n📄 DESCRIPTION:")
        desc = result['description']
        if len(desc) > 200:
            print(f"  {desc[:200]}...")
            print(f"  [truncated - full length: {len(desc)} chars]")
        else:
            print(f"  {desc}")

        if result.get('hashtags'):
            print(f"\n🏷️ HASHTAGS:")
            print(f"  {', '.join(result['hashtags'])}")

        print(f"\n💰 COST: ${result.get('cost', 0):.4f}")
        print(f"🎯 MODEL: {result.get('model', 'unknown')}")
        print(f"📊 EXAMPLES USED: {result.get('examples_used', 0)}")
        print(f"📁 CONTENT TYPE: {result.get('content_type', 'unknown')}")
        print(f"💾 CACHED: {'Yes' if result.get('cached') else 'No'}")

        # Brief summary
        if result.get('brief'):
            brief = result['brief']
            print(f"\n📋 BRIEF SUMMARY:")
            print(f"  Key topics: {len(brief.get('key_topics', []))}")
            print(f"  Top speakers: {len(brief.get('top_speakers', []))}")
            if brief.get('key_topics'):
                print(f"  Topics: {', '.join(brief['key_topics'][:3])}")

        print("\n✅ Test complete!")

        # Show cache location
        print(f"\n📍 Results cached in: data/uploader.db")
        print(f"   Table: video_generation_cache")

    except Exception as e:
        print(f"\n❌ Generation failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test AI metadata generation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/test_ai_generation.py --streamer sejm
  python scripts/test_ai_generation.py --streamer sejm --content-type sejm_meeting_pl
  python scripts/test_ai_generation.py --streamer asmongold --content-type asmongold_gaming
        """
    )

    parser.add_argument(
        '--streamer',
        required=True,
        help='Streamer ID (e.g., sejm, asmongold)'
    )

    parser.add_argument(
        '--content-type',
        help='Content type (e.g., sejm_meeting_pl, asmongold_gaming). Auto-detected if not specified.'
    )

    args = parser.parse_args()

    test_generation(args.streamer, args.content_type)
