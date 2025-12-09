"""
Input Validation Utilities
- Video file validation
- Configuration validation
- Safety checks
"""
import os
from pathlib import Path
from typing import Dict, Tuple, Optional
import subprocess
import json
from ..logger import get_logger

logger = get_logger()


class VideoValidator:
    """
    Validates video files before processing

    Checks:
    - File existence and readability
    - Video format and codec
    - Duration limits
    - Audio track presence
    - File size limits
    """

    # Supported formats
    SUPPORTED_FORMATS = {'.mp4', '.mkv', '.avi', '.mov', '.webm', '.flv', '.wmv'}

    # Limits
    MAX_DURATION_HOURS = 8
    MAX_FILE_SIZE_GB = 50
    MIN_DURATION_SECONDS = 10

    def __init__(self):
        self._check_ffmpeg()

    def _check_ffmpeg(self):
        """Check if ffmpeg is available"""
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                logger.debug("✓ ffmpeg is available")
            else:
                logger.warning("⚠️ ffmpeg check failed")

        except FileNotFoundError:
            logger.error("❌ ffmpeg not found! Please install ffmpeg")
            raise RuntimeError("ffmpeg is required but not installed")
        except Exception as e:
            logger.warning(f"ffmpeg check failed: {e}")

    def validate(self, video_path: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Validate video file

        Args:
            video_path: Path to video file

        Returns:
            (is_valid, error_message, metadata)
        """
        video_path = Path(video_path)

        # Check 1: File exists
        if not video_path.exists():
            return False, f"File does not exist: {video_path}", None

        # Check 2: File is readable
        if not os.access(video_path, os.R_OK):
            return False, f"File is not readable: {video_path}", None

        # Check 3: File extension
        if video_path.suffix.lower() not in self.SUPPORTED_FORMATS:
            return False, f"Unsupported format: {video_path.suffix}. Supported: {self.SUPPORTED_FORMATS}", None

        # Check 4: File size
        file_size_gb = video_path.stat().st_size / (1024**3)
        if file_size_gb > self.MAX_FILE_SIZE_GB:
            return False, f"File too large: {file_size_gb:.1f} GB (max: {self.MAX_FILE_SIZE_GB} GB)", None

        if file_size_gb == 0:
            return False, "File is empty", None

        # Check 5: Probe with ffprobe
        metadata = self._probe_video(video_path)
        if not metadata:
            return False, "Failed to read video metadata (file may be corrupted)", None

        # Check 6: Has video stream
        if not metadata.get('has_video'):
            return False, "No video stream found", None

        # Check 7: Has audio stream
        if not metadata.get('has_audio'):
            return False, "No audio stream found (required for transcription)", None

        # Check 8: Duration limits
        duration_seconds = metadata.get('duration_seconds', 0)

        if duration_seconds < self.MIN_DURATION_SECONDS:
            return False, f"Video too short: {duration_seconds:.1f}s (min: {self.MIN_DURATION_SECONDS}s)", None

        max_duration_seconds = self.MAX_DURATION_HOURS * 3600
        if duration_seconds > max_duration_seconds:
            logger.warning(
                f"⚠️ Long video detected: {duration_seconds/3600:.1f}h "
                f"(processing may take several hours)"
            )

        # All checks passed
        logger.success("✓ Video validation passed")
        logger.info(f"   Format: {metadata.get('format')}")
        logger.info(f"   Duration: {duration_seconds/60:.1f} min")
        logger.info(f"   Resolution: {metadata.get('width')}x{metadata.get('height')}")
        logger.info(f"   Audio: {metadata.get('audio_codec')} @ {metadata.get('audio_sample_rate')} Hz")

        return True, None, metadata

    def _probe_video(self, video_path: Path) -> Optional[Dict]:
        """
        Probe video file with ffprobe

        Returns:
            Metadata dict or None
        """
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                str(video_path)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                logger.error(f"ffprobe failed: {result.stderr}")
                return None

            probe_data = json.loads(result.stdout)

            # Extract metadata
            metadata = {
                'format': probe_data.get('format', {}).get('format_name', 'unknown'),
                'duration_seconds': float(probe_data.get('format', {}).get('duration', 0)),
                'size_bytes': int(probe_data.get('format', {}).get('size', 0)),
                'bit_rate': int(probe_data.get('format', {}).get('bit_rate', 0)),
                'has_video': False,
                'has_audio': False
            }

            # Find video and audio streams
            for stream in probe_data.get('streams', []):
                codec_type = stream.get('codec_type')

                if codec_type == 'video':
                    metadata['has_video'] = True
                    metadata['video_codec'] = stream.get('codec_name', 'unknown')
                    metadata['width'] = stream.get('width', 0)
                    metadata['height'] = stream.get('height', 0)
                    metadata['fps'] = eval(stream.get('r_frame_rate', '0/1'))  # Fraction to float

                elif codec_type == 'audio':
                    metadata['has_audio'] = True
                    metadata['audio_codec'] = stream.get('codec_name', 'unknown')
                    metadata['audio_sample_rate'] = int(stream.get('sample_rate', 0))
                    metadata['audio_channels'] = stream.get('channels', 0)

            return metadata

        except subprocess.TimeoutExpired:
            logger.error("ffprobe timeout (file may be very large or corrupted)")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse ffprobe output: {e}")
            return None
        except Exception as e:
            logger.error(f"ffprobe error: {e}")
            return None

    def get_safe_duration_warning(self, duration_hours: float) -> Optional[str]:
        """
        Get warning message for long videos

        Args:
            duration_hours: Video duration in hours

        Returns:
            Warning message or None
        """
        if duration_hours < 1:
            return None
        elif duration_hours < 2:
            return "⏱️  Processing time: ~30-60 minutes"
        elif duration_hours < 4:
            return "⏱️  Processing time: 1-2 hours (consider Smart Splitter)"
        else:
            return "⏱️  Processing time: 2+ hours (Smart Splitter recommended)"


class ConfigValidator:
    """Validates configuration parameters"""

    @staticmethod
    def validate_asr_config(config) -> Tuple[bool, Optional[str]]:
        """Validate ASR configuration"""
        valid_models = ['tiny', 'base', 'small', 'medium', 'large', 'large-v2', 'large-v3']

        if config.asr.model_size not in valid_models:
            return False, f"Invalid Whisper model: {config.asr.model_size}. Valid: {valid_models}"

        if config.asr.beam_size < 1:
            return False, "Beam size must be >= 1"

        return True, None

    @staticmethod
    def validate_scoring_config(config) -> Tuple[bool, Optional[str]]:
        """Validate scoring configuration"""
        weights_sum = (
            config.scoring.semantic_weight +
            config.scoring.acoustic_weight +
            config.scoring.keyword_weight +
            config.scoring.speaker_change_weight
        )

        if abs(weights_sum - 1.0) > 0.01:
            return False, f"Scoring weights must sum to 1.0 (got {weights_sum:.3f})"

        return True, None

    @staticmethod
    def validate_selection_config(config) -> Tuple[bool, Optional[str]]:
        """Validate selection configuration"""
        if config.selection.min_clip_duration >= config.selection.max_clip_duration:
            return False, "min_clip_duration must be < max_clip_duration"

        if config.selection.num_clips < 1:
            return False, "num_clips must be >= 1"

        return True, None


def validate_video_file(video_path: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
    """
    Convenience function to validate video file

    Returns:
        (is_valid, error_message, metadata)
    """
    validator = VideoValidator()
    return validator.validate(video_path)
