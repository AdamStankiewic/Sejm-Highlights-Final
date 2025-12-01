"""
Music Detection using AudD API
Detects copyrighted music in audio segments for DMCA-safe clip generation
"""

import subprocess
import requests
import time
from pathlib import Path
from typing import Dict, List, Optional


class MusicDetector:
    """
    Detect copyrighted music using AudD API

    Free tier: 300 requests/day
    API docs: https://docs.audd.io/
    """

    def __init__(self, api_key: str, base_url: str = "https://api.audd.io/"):
        """
        Initialize music detector

        Args:
            api_key: AudD API key (get from https://audd.io)
            base_url: AudD API base URL
        """
        self.api_key = api_key
        self.base_url = base_url
        self.requests_made = 0

    def extract_audio_segment(self, video_file: str, start_time: float, duration: float, output_file: str) -> bool:
        """
        Extract audio segment from video using ffmpeg

        Args:
            video_file: Path to video file
            start_time: Start time in seconds
            duration: Duration in seconds
            output_file: Output audio file path

        Returns:
            True if successful, False otherwise
        """
        try:
            subprocess.run([
                'ffmpeg', '-y',  # Overwrite
                '-i', video_file,
                '-ss', str(start_time),
                '-t', str(duration),
                '-q:a', '0',  # Best quality
                '-map', 'a',  # Audio only
                output_file
            ], capture_output=True, check=True, timeout=30)

            return True

        except Exception as e:
            print(f"⚠️ Audio extraction failed: {e}")
            return False

    def detect_music_in_segment(self, audio_file: str, return_timecode: bool = True) -> Optional[Dict]:
        """
        Detect music in audio segment using AudD API

        Args:
            audio_file: Path to audio file (MP3, WAV, etc.)
            return_timecode: Return timecode info

        Returns:
            Dict with detection results or None if no music detected
            {
                'artist': str,
                'title': str,
                'album': str,
                'release_date': str,
                'label': str,
                'timecode': float,  # Where in the segment music starts
                'score': int  # Confidence (0-100)
            }
        """
        if not Path(audio_file).exists():
            print(f"⚠️ Audio file not found: {audio_file}")
            return None

        try:
            # Send to AudD API
            with open(audio_file, 'rb') as f:
                data = {
                    'api_token': self.api_key,
                    'return': 'timecode' if return_timecode else 'apple_music,spotify'
                }

                files = {'file': f}

                response = requests.post(
                    self.base_url,
                    data=data,
                    files=files,
                    timeout=30
                )

                self.requests_made += 1

                result = response.json()

                # Check status
                if result.get('status') != 'success':
                    error = result.get('error', {}).get('error_message', 'Unknown error')
                    print(f"⚠️ AudD API error: {error}")
                    return None

                # Check if music detected
                if not result.get('result'):
                    # No music detected
                    return None

                track = result['result']

                return {
                    'artist': track.get('artist', 'Unknown'),
                    'title': track.get('title', 'Unknown'),
                    'album': track.get('album', 'Unknown'),
                    'release_date': track.get('release_date', 'Unknown'),
                    'label': track.get('label', 'Unknown'),
                    'timecode': track.get('timecode', 0.0),
                    'score': track.get('score', 0)  # Confidence 0-100
                }

        except requests.exceptions.Timeout:
            print("⚠️ AudD API timeout")
            return None

        except Exception as e:
            print(f"⚠️ Music detection failed: {e}")
            return None

    def scan_clip(
        self,
        video_file: str,
        clip_start: float,
        clip_end: float,
        scan_interval: int = 10,
        temp_dir: str = "temp"
    ) -> List[Dict]:
        """
        Scan entire clip for copyrighted music by sampling every N seconds

        Args:
            video_file: Path to video file
            clip_start: Clip start time in seconds
            clip_end: Clip end time in seconds
            scan_interval: Scan every N seconds (default: 10)
            temp_dir: Directory for temporary audio files

        Returns:
            List of detected music segments with metadata
        """
        clip_duration = clip_end - clip_start
        detected_music = []

        # Create temp directory
        temp_path = Path(temp_dir)
        temp_path.mkdir(parents=True, exist_ok=True)

        print(f"🎵 Scanning clip ({clip_duration:.1f}s) for copyrighted music...")

        # Sample clip every scan_interval seconds
        num_samples = max(1, int(clip_duration / scan_interval))

        for i in range(num_samples):
            sample_start = clip_start + (i * scan_interval)

            # Don't go beyond clip end
            if sample_start >= clip_end:
                break

            # Extract 10s audio sample
            sample_duration = min(10.0, clip_end - sample_start)
            audio_file = temp_path / f"sample_{i}_{sample_start:.0f}.mp3"

            print(f"   Scanning {i+1}/{num_samples} ({sample_start:.1f}s)...", end=' ')

            # Extract audio
            if not self.extract_audio_segment(
                video_file,
                sample_start,
                sample_duration,
                str(audio_file)
            ):
                print("❌ Extraction failed")
                continue

            # Detect music
            detection = self.detect_music_in_segment(str(audio_file))

            # Cleanup
            audio_file.unlink(missing_ok=True)

            if detection:
                # Music detected!
                detection['clip_timestamp'] = sample_start
                detection['sample_index'] = i
                detected_music.append(detection)

                print(f"🎵 FOUND: {detection['artist']} - {detection['title']} (score: {detection['score']})")
            else:
                print("✅ Clean")

            # Rate limiting (free tier: ~1 request/second)
            time.sleep(1.0)

        return detected_music

    def analyze_clip_music_coverage(self, detected_music: List[Dict], clip_duration: float) -> Dict:
        """
        Analyze how much of the clip contains copyrighted music

        Args:
            detected_music: List of detected music segments
            clip_duration: Total clip duration in seconds

        Returns:
            Dict with analysis:
            {
                'has_music': bool,
                'music_count': int,  # Number of detected segments
                'coverage_percentage': float,  # Estimated % of clip with music
                'unique_tracks': int,  # Number of different songs
                'tracks': List[str]  # List of "Artist - Title"
            }
        """
        if not detected_music:
            return {
                'has_music': False,
                'music_count': 0,
                'coverage_percentage': 0.0,
                'unique_tracks': 0,
                'tracks': []
            }

        # Estimate coverage (each detection covers ~10s)
        estimated_coverage = len(detected_music) * 10.0
        coverage_percentage = min(100.0, (estimated_coverage / clip_duration) * 100.0)

        # Find unique tracks
        tracks_set = set()
        for detection in detected_music:
            track_id = f"{detection['artist']} - {detection['title']}"
            tracks_set.add(track_id)

        return {
            'has_music': True,
            'music_count': len(detected_music),
            'coverage_percentage': coverage_percentage,
            'unique_tracks': len(tracks_set),
            'tracks': sorted(list(tracks_set))
        }

    def should_skip_clip(
        self,
        analysis: Dict,
        max_music_percentage: float = 30.0,
        min_confidence: int = 70
    ) -> bool:
        """
        Determine if clip should be skipped based on music coverage

        Args:
            analysis: Result from analyze_clip_music_coverage()
            max_music_percentage: Skip if >X% is music
            min_confidence: Only count detections with score >= X

        Returns:
            True if clip should be skipped
        """
        if not analysis['has_music']:
            return False

        # Check coverage
        if analysis['coverage_percentage'] > max_music_percentage:
            print(f"   ⚠️ {analysis['coverage_percentage']:.1f}% music (threshold: {max_music_percentage}%)")
            return True

        return False

    def get_stats(self) -> Dict:
        """Get detector statistics"""
        return {
            'requests_made': self.requests_made,
            'requests_remaining': max(0, 300 - self.requests_made)  # Free tier limit
        }
