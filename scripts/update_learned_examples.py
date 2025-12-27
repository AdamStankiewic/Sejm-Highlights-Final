#!/usr/bin/env python3
"""
CLI Tool: Update Learned Examples

Manually trigger the learning loop to update learned examples from YouTube metrics.

Usage:
    python scripts/update_learned_examples.py              # Update all streamers
    python scripts/update_learned_examples.py sejm         # Update specific streamer
    python scripts/update_learned_examples.py --stats sejm # Show stats only
"""
import sys
import argparse
from pathlib import Path
import logging

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from pipeline.learning import LearningLoop, run_learning_loop
from pipeline.streamers import get_manager

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def show_stats(streamer_id: str = None):
    """Show learning statistics"""
    print("\n" + "=" * 60)
    print("LEARNED EXAMPLES STATISTICS")
    print("=" * 60)

    manager = get_manager()

    try:
        from pipeline.learning import LearningLoop
        loop = LearningLoop(manager)

        if streamer_id:
            streamers = [streamer_id]
        else:
            streamers = [p.streamer_id for p in manager.list_all()]

        for sid in streamers:
            stats = loop.get_learning_stats(sid)

            print(f"\n📊 {sid.upper()}")
            print(f"  Total examples: {stats['total_learned_examples']}")
            print(f"  Avg score: {stats['avg_performance_score']:.2f}/10")
            print(f"  Last updated: {stats['last_updated']}")

            if 'top_example' in stats:
                top = stats['top_example']
                print(f"  🏆 Top example:")
                print(f"     Title: {top['title'][:50]}...")
                print(f"     Score: {top['score']:.2f}/10")
                print(f"     Views: {top['views']:,}")

    except Exception as e:
        print(f"❌ Failed to get stats: {e}")
        sys.exit(1)


def run_update(streamer_id: str = None, args=None):
    """Run learning loop update"""
    print("\n" + "=" * 60)
    print("LEARNING LOOP: Update Learned Examples")
    print("=" * 60)

    # Configuration
    top_n = args.top_n if args else 20
    min_score = args.min_score if args else 5.0

    print(f"\nConfig:")
    print(f"  Top N videos: {top_n}")
    print(f"  Min score threshold: {min_score}")
    print(f"  Streamer: {streamer_id or 'ALL'}")

    try:
        # Run learning loop
        results = run_learning_loop(
            streamer_id=streamer_id,
            top_n=top_n,
            min_score=min_score
        )

        # Display results
        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)

        for result in results:
            if result['success']:
                print(f"\n✅ {result['streamer_id'].upper()}")
                print(f"  Videos analyzed: {result['videos_analyzed']}")
                print(f"  Top performers: {result['top_performers']}")
                print(f"  Examples updated: {result['examples_updated']}")
                print(f"  Time: {result['elapsed_seconds']}s")
            else:
                print(f"\n❌ {result['streamer_id'].upper()}")
                print(f"  Error: {result['error']}")

        # Summary
        successful = sum(1 for r in results if r['success'])
        total_examples = sum(r.get('examples_updated', 0) for r in results)

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"  Successful: {successful}/{len(results)}")
        print(f"  Total examples updated: {total_examples}")

    except Exception as e:
        print(f"\n❌ Update failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Update learned examples from YouTube metrics',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Update all streamers
  python scripts/update_learned_examples.py

  # Update specific streamer
  python scripts/update_learned_examples.py sejm

  # Custom config
  python scripts/update_learned_examples.py --top-n 30 --min-score 6.0

  # Show stats only
  python scripts/update_learned_examples.py --stats
  python scripts/update_learned_examples.py --stats sejm
        """
    )

    parser.add_argument(
        'streamer_id',
        nargs='?',
        help='Streamer ID (or omit for all streamers)'
    )

    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show statistics only (no update)'
    )

    parser.add_argument(
        '--top-n',
        type=int,
        default=20,
        help='Number of top videos to keep (default: 20)'
    )

    parser.add_argument(
        '--min-score',
        type=float,
        default=5.0,
        help='Minimum performance score threshold (default: 5.0)'
    )

    args = parser.parse_args()

    # Show stats or run update
    if args.stats:
        show_stats(args.streamer_id)
    else:
        run_update(args.streamer_id, args)


if __name__ == "__main__":
    main()
