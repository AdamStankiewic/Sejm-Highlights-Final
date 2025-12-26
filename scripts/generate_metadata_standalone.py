#!/usr/bin/env python3
"""
Standalone AI Metadata Generation - Generate titles/descriptions WITHOUT YouTube upload.

This script allows you to:
1. Generate AI titles/descriptions for your clips
2. Cache results in database
3. Test streamer detection
4. View generated metadata

Usage:
    # Auto-detect streamer from filename/directory
    python scripts/generate_metadata_standalone.py --input output/session_123/selected_clips.json

    # Explicit streamer
    python scripts/generate_metadata_standalone.py --input selected_clips.json --streamer asmongold

    # Test with sample clips
    python scripts/generate_metadata_standalone.py --test
"""
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict
import os

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        print(f"✅ Loaded environment variables from: {env_path}")
except ImportError:
    print("⚠️  python-dotenv not installed - using system environment variables only")
    print("   Install with: pip install python-dotenv")


def load_clips(clips_path: str) -> List[Dict]:
    """Load clips from selected_clips.json"""
    path = Path(clips_path)

    if not path.exists():
        print(f"❌ File not found: {clips_path}")
        sys.exit(1)

    with open(path) as f:
        data = json.load(f)

    # Handle different formats
    if isinstance(data, dict):
        clips = data.get('clips', [])
    elif isinstance(data, list):
        clips = data
    else:
        print(f"❌ Invalid clips format")
        sys.exit(1)

    if not clips:
        print(f"❌ No clips found in {clips_path}")
        sys.exit(1)

    print(f"✅ Loaded {len(clips)} clips from {clips_path}")
    return clips


def create_sample_clips() -> List[Dict]:
    """Create sample clips for testing"""
    return [
        {
            "id": 1,
            "t0": 120.5,
            "t1": 185.2,
            "duration": 64.7,
            "title": "Insane Gaming Drama Reaction",
            "transcript": "Oh my god, I can't believe they actually did this. This is the most insane thing I've ever seen in gaming. The community is going to lose their minds over this announcement...",
            "keywords": ["drama", "reaction", "gaming", "announcement"],
            "final_score": 0.92,
            "features": {
                "matched_keywords": [
                    {"token": "insane", "category": "intensity"},
                    {"token": "drama", "category": "content_type"}
                ],
                "emotion": "excited"
            }
        },
        {
            "id": 2,
            "t0": 450.1,
            "t1": 523.8,
            "duration": 73.7,
            "title": "Epic Boss Fight Attempt",
            "transcript": "Alright chat, here we go. This boss is actually impossible. No way I'm beating this on first try. Wait... wait... WAIT! OH MY GOD I ACTUALLY GOT IT!",
            "keywords": ["boss", "fight", "epic", "victory"],
            "final_score": 0.88,
            "features": {
                "matched_keywords": [
                    {"token": "boss", "category": "gameplay"},
                    {"token": "epic", "category": "intensity"}
                ],
                "emotion": "triumphant"
            }
        },
        {
            "id": 3,
            "t0": 892.3,
            "t1": 967.5,
            "duration": 75.2,
            "title": "Hilarious Community Meme Review",
            "transcript": "Okay, let's check out what you guys posted on the subreddit. Oh no... oh NO. This is so bad. Why would you make this? Chat, why is our community like this?",
            "keywords": ["meme", "community", "reddit", "hilarious"],
            "final_score": 0.85,
            "features": {
                "matched_keywords": [
                    {"token": "meme", "category": "content_type"},
                    {"token": "hilarious", "category": "emotion"}
                ],
                "emotion": "humorous"
            }
        }
    ]


def generate_metadata(
    clips: List[Dict],
    streamer_id: str,
    platform: str = "youtube",
    video_type: str = "long",
    force_regenerate: bool = False
):
    """Generate AI metadata for clips"""
    try:
        # Check for OpenAI API key
        if not os.getenv("OPENAI_API_KEY"):
            print("\n❌ ERROR: OPENAI_API_KEY not found in environment")
            print("\nSet it in .env file:")
            print("  OPENAI_API_KEY=sk-proj-...")
            print("\nOr export as environment variable:")
            print("  export OPENAI_API_KEY=sk-proj-...")
            return None

        # Import dependencies
        print("📦 Loading AI metadata components...")
        from pipeline.ai_metadata import MetadataGenerator
        from pipeline.streamers import get_manager
        from openai import OpenAI
        import yaml

        # Initialize OpenAI client
        print("🔑 Initializing OpenAI client...")
        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Load platform config
        platform_config_path = Path("config/platforms.yaml")
        if not platform_config_path.exists():
            print(f"⚠️  Platform config not found: {platform_config_path}")
            print("   Using defaults...")
            platform_config = {}
        else:
            with open(platform_config_path) as f:
                platform_config = yaml.safe_load(f)

        # Initialize streamer manager
        print("👤 Loading streamer profiles...")
        manager = get_manager()

        # Verify streamer profile exists
        profile = manager.get(streamer_id)
        if not profile:
            print(f"\n❌ Streamer profile not found: {streamer_id}")
            print("\nAvailable profiles:")
            for p in manager.list_all():
                print(f"  - {p.streamer_id} ({p.display_name})")
            return None

        print(f"✅ Using streamer: {profile.display_name} ({streamer_id})")

        # Initialize metadata generator
        print("🤖 Initializing MetadataGenerator...")
        generator = MetadataGenerator(
            openai_client=openai_client,
            streamer_manager=manager,
            platform_config=platform_config
        )

        # Generate metadata
        print(f"\n{'='*60}")
        print(f"🎬 GENERATING AI METADATA")
        print(f"{'='*60}")
        print(f"  Streamer: {profile.display_name}")
        print(f"  Platform: {platform}")
        print(f"  Video type: {video_type}")
        print(f"  Clips: {len(clips)}")
        print(f"  Force regenerate: {force_regenerate}")
        print(f"{'='*60}\n")

        metadata = generator.generate_metadata(
            clips=clips,
            streamer_id=streamer_id,
            platform=platform,
            video_type=video_type,
            force_regenerate=force_regenerate
        )

        # Display results
        print(f"\n{'='*60}")
        print(f"✅ METADATA GENERATED")
        print(f"{'='*60}")
        print(f"\n📝 TITLE:")
        print(f"  {metadata['title']}\n")
        print(f"📄 DESCRIPTION:")
        print(f"  {metadata['description'][:200]}...")
        print(f"\n{'='*60}")
        print(f"💰 COST: ${metadata.get('cost', 0):.4f}")
        print(f"💾 CACHED: {metadata.get('cached', False)}")
        print(f"🎯 CONTENT TYPE: {metadata.get('content_type', 'N/A')}")
        print(f"🤖 MODEL: {metadata.get('model', 'N/A')}")
        print(f"📚 EXAMPLES USED: {metadata.get('examples_used', 0)}")
        print(f"{'='*60}\n")

        return metadata

    except ModuleNotFoundError as e:
        print(f"\n❌ Missing dependency: {e}")
        print("\nTry installing missing packages:")
        print("  pip install openai pyyaml")
        return None
    except Exception as e:
        print(f"\n❌ Error generating metadata: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Generate AI metadata (titles/descriptions) for video clips"
    )
    parser.add_argument(
        "--input", "-i",
        help="Path to selected_clips.json"
    )
    parser.add_argument(
        "--streamer", "-s",
        help="Streamer ID (e.g., asmongold, sejm). Auto-detected if not provided."
    )
    parser.add_argument(
        "--platform", "-p",
        default="youtube",
        choices=["youtube", "twitch", "kick"],
        help="Target platform (default: youtube)"
    )
    parser.add_argument(
        "--video-type", "-t",
        default="long",
        choices=["long", "shorts"],
        help="Video type (default: long)"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Force regenerate (skip cache)"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test with sample clips (no input file needed)"
    )

    args = parser.parse_args()

    print("\n🎯 STANDALONE AI METADATA GENERATION\n")

    # Load or create clips
    if args.test:
        print("🧪 Using sample test clips...")
        clips = create_sample_clips()
        streamer_id = args.streamer or "asmongold"
    elif args.input:
        clips = load_clips(args.input)

        # Auto-detect streamer if not provided
        if not args.streamer:
            print("\n🔍 Auto-detecting streamer from path...")
            from pipeline.streamers.detector import detect_streamer
            streamer_id = detect_streamer(args.input)
        else:
            streamer_id = args.streamer
    else:
        print("❌ Error: Either --input or --test is required")
        parser.print_help()
        sys.exit(1)

    # Generate metadata
    metadata = generate_metadata(
        clips=clips,
        streamer_id=streamer_id,
        platform=args.platform,
        video_type=args.video_type,
        force_regenerate=args.force
    )

    if metadata:
        # Save to file
        output_file = Path("generated_metadata.json")
        with open(output_file, 'w') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        print(f"💾 Metadata saved to: {output_file}\n")

        return 0
    else:
        print("\n❌ Failed to generate metadata\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
