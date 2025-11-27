#!/usr/bin/env python3
"""
Copyright Checker - Standalone tool
Sprawdza filmy pod kątem muzyki i ryzyka copyright PRZED uploadem na YouTube

Usage:
    python check_copyright.py video.mp4
    python check_copyright.py video.mp4 --protect pitch_shift
    python check_copyright.py output/*.mp4 --protect auto
"""

import sys
import argparse
from pathlib import Path
from pipeline.stage_11_copyright_protection import CopyrightProtectionStage
from pipeline.config import Config


def main():
    parser = argparse.ArgumentParser(description='YouTube Copyright Protection Tool')
    parser.add_argument('videos', nargs='+', help='Video files to check')
    parser.add_argument('--protect', choices=['report_only', 'pitch_shift', 'speed_change', 'mute_music', 'auto'],
                       default='report_only',
                       help='Protection mode (default: report_only)')
    parser.add_argument('--output', default='protected_videos',
                       help='Output directory for protected videos')
    parser.add_argument('--pitch', type=float, default=0.5,
                       help='Pitch shift in semitones (default: 0.5)')
    parser.add_argument('--speed', type=float, default=1.02,
                       help='Speed change factor (default: 1.02 = 2% faster)')

    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load config (minimal)
    config = Config.load_default()

    # Create protection stage
    protection = CopyrightProtectionStage(config)
    protection.pitch_shift_semitones = args.pitch
    protection.speed_change_factor = args.speed

    # Process videos
    print("=" * 80)
    print("🛡️  YouTube COPYRIGHT PROTECTION TOOL")
    print("=" * 80)

    results = protection.process(
        video_files=args.videos,
        output_dir=output_dir,
        protection_mode=args.protect
    )

    # Summary
    print("\n" + "=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    print(f"Videos checked: {len(results['reports'])}")
    print(f"Overall risk: {results['total_risk']}")

    if results['protected_files']:
        print(f"\n✅ Protected videos created:")
        for f in results['protected_files']:
            print(f"   {f}")
    elif args.protect != 'report_only':
        print(f"\n✅ No protection needed (low/no risk)")

    # Risk breakdown
    risk_counts = {'NONE': 0, 'LOW': 0, 'MEDIUM': 0, 'HIGH': 0}
    for report in results['reports']:
        risk_counts[report['risk_level']] += 1

    print(f"\nRisk breakdown:")
    print(f"   🔴 HIGH: {risk_counts['HIGH']}")
    print(f"   🟡 MEDIUM: {risk_counts['MEDIUM']}")
    print(f"   🟢 LOW: {risk_counts['LOW']}")
    print(f"   ✅ NONE: {risk_counts['NONE']}")

    # Next steps
    print(f"\n💡 Next steps:")
    if results['total_risk'] in ['HIGH', 'MEDIUM']:
        print(f"   ⚠️  Some videos have copyright risk!")
        print(f"   🔧 Run with --protect auto to apply automatic protection")
        print(f"   📤 Upload protected files instead of originals")
    else:
        print(f"   ✅ All videos are safe to upload!")

    print("=" * 80)


if __name__ == "__main__":
    main()
