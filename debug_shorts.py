#!/usr/bin/env python3
"""
Debug script for testing Shorts generation with refactored pipeline.
Compatible with previous debug_shorts.py interface.
"""

import argparse
import json
import logging
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Configure logging to see DEBUG messages from gaming.py
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)

from shorts.generator import ShortsGenerator
from shorts.face_detection import FaceDetector
from dataclasses import dataclass


@dataclass
class Segment:
    """Simple segment representation."""
    start: float
    end: float
    score: float = 0.0
    subtitles: str | None = None

    @property
    def duration(self) -> float:
        """Calculate segment duration from start and end times."""
        return self.end - self.start


def load_candidates(json_path: Path) -> list[Segment]:
    """Load segments from shorts_candidates.json."""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    segments = []
    for raw in data:
        start = float(raw.get("t0", raw.get("start", 0.0)))
        end = float(raw.get("t1", raw.get("end", start)))
        score = float(raw.get("final_score", raw.get("score", 0.0)))
        subtitles = raw.get("subtitles")

        segments.append(Segment(
            start=start,
            end=end,
            score=score,
            subtitles=subtitles
        ))

    return segments


def main():
    parser = argparse.ArgumentParser(
        description="Debug Shorts generation with refactored pipeline"
    )
    parser.add_argument(
        "--vod",
        required=True,
        help="Path to VOD file (e.g., C:/Users/.../video.mp4)"
    )
    parser.add_argument(
        "--json",
        required=True,
        help="Path to shorts_candidates.json"
    )
    parser.add_argument(
        "--outdir",
        default="temp/debug_shorts",
        help="Output directory for generated shorts"
    )
    parser.add_argument(
        "--speedup",
        type=float,
        default=1.0,
        help="Playback speedup (e.g., 1.1 for 10%% faster)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum number of shorts to generate"
    )
    parser.add_argument(
        "--template",
        default="gaming",
        choices=["gaming", "universal"],
        help="Template to use (gaming=facecam, universal=crop)"
    )
    parser.add_argument(
        "--no-face-detection",
        action="store_true",
        help="Disable face detection (force universal template)"
    )

    args = parser.parse_args()

    # Validate paths
    vod_path = Path(args.vod)
    if not vod_path.exists():
        print(f"❌ ERROR: VOD file not found: {vod_path}")
        return 1

    json_path = Path(args.json)
    if not json_path.exists():
        print(f"❌ ERROR: JSON file not found: {json_path}")
        return 1

    output_dir = Path(args.outdir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("🎬 DEBUG SHORTS GENERATION (Refactored Pipeline)")
    print("=" * 60)
    print(f"📹 VOD: {vod_path}")
    print(f"📄 Candidates: {json_path}")
    print(f"📁 Output: {output_dir}")
    print(f"⚡ Speedup: {args.speedup}x")
    print(f"🎯 Template: {args.template}")
    print(f"🔢 Limit: {args.limit}")
    print()

    # Load segments
    print("📥 Loading candidates...")
    segments = load_candidates(json_path)
    print(f"   ✓ Loaded {len(segments)} segments")

    # Limit segments
    if args.limit:
        segments = segments[:args.limit]
        print(f"   ✓ Limited to {len(segments)} segments")

    # Initialize face detector - let gaming.py create it with proper settings
    # (Don't override with hardcoded values here)
    face_detector = None
    if args.template == "gaming" and not args.no_face_detection:
        print("\n🔍 Face detection enabled")
        print("   ✓ Template will auto-configure MediaPipe detector")
        print("   ✓ 9-zone grid (all zones except center_middle)")
        print("   ✓ Low thresholds for maximum detection")
        # face_detector stays None - gaming.py will create its own with optimal settings

    # Initialize generator
    print("\n🎨 Initializing ShortsGenerator...")
    generator = ShortsGenerator(
        output_dir=output_dir,
        face_detector=face_detector
    )

    # Generate shorts
    print(f"\n🚀 Generating {len(segments)} shorts...")
    print("-" * 60)

    try:
        results = generator.generate(
            video_path=vod_path,
            segments=segments,
            template=args.template,
            speedup=args.speedup,
            count=args.limit or len(segments)
        )

        print("\n" + "=" * 60)
        print("✅ GENERATION COMPLETE")
        print("=" * 60)
        print(f"📊 Generated: {len(results)} shorts")

        for i, path in enumerate(results, 1):
            size_mb = path.stat().st_size / 1024 / 1024
            print(f"   {i}. {path.name} ({size_mb:.1f} MB)")

        print(f"\n📁 Output directory: {output_dir.absolute()}")
        return 0

    except Exception as e:
        print("\n" + "=" * 60)
        print("❌ GENERATION FAILED")
        print("=" * 60)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
