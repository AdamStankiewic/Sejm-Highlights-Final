"""
Audio extraction from video files using FFmpeg
Part of Highlights AI Platform - Core Engine
"""
import subprocess
import json
from pathlib import Path
from typing import Dict, Any


class AudioExtractor:
    """Extract audio from video files"""

    def __init__(self, sample_rate: int = 16000, channels: int = 1):
        self.sample_rate = sample_rate
        self.channels = channels
        self._check_ffmpeg()

    def _check_ffmpeg(self):
        """Check if ffmpeg is available"""
        try:
            subprocess.run(
                ['ffmpeg', '-version'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError(
                "ffmpeg is not installed!\n"
                "Download from: https://ffmpeg.org/download.html"
            )

    def extract(self, video_path: str, output_path: str) -> Dict[str, Any]:
        """
        Extract audio from video file

        Args:
            video_path: Path to input video
            output_path: Path for output audio (WAV)

        Returns:
            Dict with extraction results
        """
        video_path = Path(video_path)
        output_path = Path(output_path)

        cmd = [
            'ffmpeg',
            '-i', str(video_path),
            '-vn',  # No video
            '-ac', str(self.channels),
            '-ar', str(self.sample_rate),
            '-y',  # Overwrite
            str(output_path)
        ]

        try:
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )

            return {
                'success': True,
                'output_path': str(output_path),
                'sample_rate': self.sample_rate,
                'channels': self.channels
            }

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ffmpeg extraction error: {e.stderr.decode()}")

    def get_metadata(self, video_path: str) -> Dict[str, Any]:
        """
        Get video/audio metadata using ffprobe

        Args:
            video_path: Path to input video

        Returns:
            Dict with metadata (duration, resolution, fps, codecs)
        """
        video_path = Path(video_path)

        if not video_path.exists():
            raise FileNotFoundError(f"File not found: {video_path}")

        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            str(video_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True
            )

            probe_data = json.loads(result.stdout)

        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ffprobe error: {e.stderr}")
        except json.JSONDecodeError:
            raise RuntimeError("Failed to parse ffprobe output")

        # Extract metadata
        format_data = probe_data.get('format', {})
        video_stream = None
        audio_stream = None

        for stream in probe_data.get('streams', []):
            if stream['codec_type'] == 'video' and not video_stream:
                video_stream = stream
            elif stream['codec_type'] == 'audio' and not audio_stream:
                audio_stream = stream

        if not video_stream:
            raise ValueError("No video stream found")

        if not audio_stream:
            raise ValueError("No audio stream found")

        # Parse duration
        duration = float(format_data.get('duration', 0))

        # Parse resolution
        width = int(video_stream.get('width', 0))
        height = int(video_stream.get('height', 0))

        # Parse FPS
        fps_str = video_stream.get('r_frame_rate', '25/1')
        try:
            num, den = map(int, fps_str.split('/'))
            fps = num / den
        except:
            fps = 25.0

        return {
            'duration': duration,
            'width': width,
            'height': height,
            'fps': fps,
            'video_codec': video_stream.get('codec_name', 'unknown'),
            'audio_codec': audio_stream.get('codec_name', 'unknown'),
            'file_size_mb': video_path.stat().st_size / (1024**2)
        }
