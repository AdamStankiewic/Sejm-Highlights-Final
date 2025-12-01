"""
Stage 6b: Copyright Detection
Scans selected clips for copyrighted music BEFORE export
"""

from pathlib import Path
from typing import Dict, List, Any

from modules.streaming.music_detector import MusicDetector


class CopyrightDetectionStage:
    """
    Stage 6b: Scan selected clips for copyrighted music

    Workflow:
    1. Takes clips selected by Stage 6
    2. Scans each clip using AudD API
    3. Marks clips with music for post-processing (vocal isolation)
    4. Optionally skips clips with too much music
    """

    def __init__(self, config):
        self.config = config
        self.music_detector = None

        # Initialize detector if API key provided
        if hasattr(config.streaming, 'audd_api_key') and config.streaming.audd_api_key:
            self.music_detector = MusicDetector(
                api_key=config.streaming.audd_api_key
            )
        else:
            print("⚠️ No AudD API key - copyright detection disabled")

    def process(
        self,
        input_file: str,
        clips: List[Dict[str, Any]],
        output_dir: Path
    ) -> Dict[str, Any]:
        """
        Scan selected clips for copyrighted music

        Args:
            input_file: Original video file path
            clips: List of selected clips from Stage 6
            output_dir: Output directory

        Returns:
            Dict with:
                - clips: Updated clips with copyright info
                - copyright_report: Summary of detections
        """
        print("\n" + "="*60)
        print("STAGE 6b: Copyright Detection (DMCA Safety)")
        print("="*60)

        # Check if enabled
        if not hasattr(self.config.streaming, 'enable_copyright_detection') or \
           not self.config.streaming.enable_copyright_detection:
            print("⚠️ Copyright detection disabled in config")
            return {
                'clips': clips,
                'copyright_report': {'enabled': False}
            }

        if not self.music_detector:
            print("⚠️ No API key - skipping copyright detection")
            return {
                'clips': clips,
                'copyright_report': {'enabled': False, 'reason': 'no_api_key'}
            }

        print(f"🎵 Scanning {len(clips)} clips for copyrighted music...")
        print(f"   API Key: {'*' * 20}{self.music_detector.api_key[-4:]}")

        confidence_threshold = getattr(self.config.streaming, 'music_confidence_threshold', 0.7)
        max_music_pct = getattr(self.config.streaming, 'max_music_percentage', 0.3)

        print(f"   Confidence threshold: {int(confidence_threshold * 100)}%")
        print(f"   Max music %: {int(max_music_pct * 100)}%")

        # Scan each clip
        clips_to_keep = []
        clips_skipped = []
        total_music_found = 0

        for i, clip in enumerate(clips, 1):
            print(f"\n🎬 Clip {i}/{len(clips)}: {clip['t0']:.1f}s - {clip['t1']:.1f}s ({clip['duration']:.1f}s)")

            # Scan clip
            detections = self.music_detector.scan_clip(
                video_file=input_file,
                clip_start=clip['t0'],
                clip_end=clip['t1'],
                scan_interval=10,  # Scan every 10s
                temp_dir=str(output_dir / "temp_audio")
            )

            # Analyze coverage
            analysis = self.music_detector.analyze_clip_music_coverage(
                detections,
                clip_duration=clip['duration']
            )

            # Add copyright info to clip
            clip['copyright'] = {
                'scanned': True,
                'has_music': analysis['has_music'],
                'music_count': analysis['music_count'],
                'coverage_percentage': analysis['coverage_percentage'],
                'unique_tracks': analysis['unique_tracks'],
                'tracks': analysis['tracks'],
                'detections': detections,
                'requires_vocal_isolation': False,
                'skip_clip': False
            }

            if analysis['has_music']:
                total_music_found += 1

                print(f"   🎵 Music detected: {analysis['unique_tracks']} track(s)")
                print(f"   📊 Coverage: {analysis['coverage_percentage']:.1f}%")

                for track in analysis['tracks']:
                    print(f"      - {track}")

                # Should we skip this clip?
                should_skip = self.music_detector.should_skip_clip(
                    analysis,
                    max_music_percentage=max_music_pct * 100,
                    min_confidence=int(confidence_threshold * 100)
                )

                auto_vocal_isolation = getattr(self.config.streaming, 'auto_vocal_isolation', False)

                if should_skip:
                    print(f"   ❌ SKIPPING - Too much copyrighted music ({analysis['coverage_percentage']:.1f}%)")
                    clip['copyright']['skip_clip'] = True
                    clips_skipped.append(clip)
                    continue
                else:
                    print(f"   ⚠️ FLAGGED for vocal isolation")
                    clip['copyright']['requires_vocal_isolation'] = auto_vocal_isolation

            else:
                print(f"   ✅ Clean - no copyrighted music detected")

            clips_to_keep.append(clip)

        # Report
        print(f"\n" + "="*60)
        print(f"📊 COPYRIGHT DETECTION SUMMARY")
        print(f"="*60)
        print(f"   Total clips scanned: {len(clips)}")
        print(f"   Clips with music: {total_music_found}")
        print(f"   Clips flagged for vocal isolation: {sum(1 for c in clips_to_keep if c.get('copyright', {}).get('requires_vocal_isolation'))}")
        print(f"   Clips skipped: {len(clips_skipped)}")
        print(f"   Clips kept: {len(clips_to_keep)}")
        print(f"   API requests made: {self.music_detector.requests_made}")

        detector_stats = self.music_detector.get_stats()
        print(f"   API requests remaining: {detector_stats['requests_remaining']}/300")

        # Create report
        copyright_report = {
            'enabled': True,
            'total_scanned': len(clips),
            'music_found': total_music_found,
            'clips_flagged': sum(1 for c in clips_to_keep if c.get('copyright', {}).get('requires_vocal_isolation')),
            'clips_skipped': len(clips_skipped),
            'clips_kept': len(clips_to_keep),
            'api_requests': self.music_detector.requests_made,
            'api_remaining': detector_stats['requests_remaining'],
            'skipped_clips': [
                {
                    'start': c['t0'],
                    'end': c['t1'],
                    'tracks': c['copyright']['tracks'],
                    'coverage': c['copyright']['coverage_percentage']
                }
                for c in clips_skipped
            ]
        }

        # Warn if too many clips skipped
        if len(clips_skipped) > len(clips) * 0.5:
            print(f"\n⚠️ WARNING: {len(clips_skipped)}/{len(clips)} clips skipped due to music!")
            print(f"   Consider:")
            print(f"   - Increasing max_music_percentage (currently {int(max_music_pct * 100)}%)")
            print(f"   - Using vocal isolation instead of skipping")

        return {
            'clips': clips_to_keep,
            'copyright_report': copyright_report
        }
