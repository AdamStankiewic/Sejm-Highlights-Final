"""
Chat Overlay Renderer for Long Videos - Chat Render MP4 Based

Extracts time-synchronized segments from pre-rendered chat video (e.g., from TwitchDownloaderCLI)
and overlays them onto highlight videos.

Performance: Very fast - just cutting and scaling, no rendering from scratch.
"""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class ChatRenderOverlay:
    """Handles Chat Render MP4 extraction and overlay preparation."""

    def __init__(
        self,
        chat_render_path: str,
        x_percent: int = 64,
        y_percent: int = 10,
        scale_percent: int = 80
    ):
        """
        Initialize chat render overlay handler.

        Args:
            chat_render_path: Path to Chat Render MP4 (e.g., 700x1200 portrait video)
            x_percent: Horizontal position 0-100% (0=left, 100=right)
            y_percent: Vertical position 0-100% (0=top, 100=bottom)
            scale_percent: Scale 50-100% of original size
        """
        self.chat_render_path = Path(chat_render_path)
        self.x_percent = max(0, min(100, x_percent))
        self.y_percent = max(0, min(100, y_percent))
        self.scale_percent = max(50, min(100, scale_percent))

        if not self.chat_render_path.exists():
            raise FileNotFoundError(f"Chat render not found: {chat_render_path}")

        # Get chat render dimensions
        self.chat_width, self.chat_height = self._get_video_dimensions(
            str(self.chat_render_path)
        )

        logger.info(
            f"Chat render loaded: {self.chat_width}x{self.chat_height}, "
            f"pos=({x_percent}%, {y_percent}%), scale={scale_percent}%"
        )

    def extract_segment(
        self,
        start_time: float,
        end_time: float,
        video_width: int = 1920,
        video_height: int = 1080
    ) -> Optional[str]:
        """
        Extract and prepare chat segment for overlay.

        Args:
            start_time: Start time in seconds
            end_time: End time in seconds
            video_width: Target video width (for positioning)
            video_height: Target video height (for positioning)

        Returns:
            Path to processed chat segment ready for overlay, or None if failed
        """
        duration = end_time - start_time

        if duration <= 0:
            logger.warning(f"Invalid duration: {duration}s")
            return None

        try:
            # Calculate scaled dimensions
            scaled_width = int(self.chat_width * (self.scale_percent / 100.0))
            scaled_height = int(self.chat_height * (self.scale_percent / 100.0))

            # Ensure dimensions are even (required by libx264 encoder)
            # If odd, add 1 to make even
            scaled_width = scaled_width + (scaled_width % 2)
            scaled_height = scaled_height + (scaled_height % 2)

            # Calculate position in pixels
            x_pos = int((video_width - scaled_width) * (self.x_percent / 100.0))
            y_pos = int((video_height - scaled_height) * (self.y_percent / 100.0))

            # Create temp output file
            temp_output = Path(tempfile.gettempdir()) / f"chat_segment_{int(start_time)}_{int(end_time)}.mp4"

            # Extract segment with scaling
            cmd = [
                'ffmpeg',
                '-ss', str(start_time),
                '-t', str(duration),
                '-i', str(self.chat_render_path),
                '-vf', f'scale={scaled_width}:{scaled_height}',
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-crf', '23',
                '-an',  # No audio needed for chat overlay
                '-y',
                str(temp_output)
            ]

            logger.info(f"Extracting chat segment: {start_time:.1f}s - {end_time:.1f}s")
            logger.debug(f"Chat source: {self.chat_render_path}")
            logger.debug(f"Scaled to {scaled_width}x{scaled_height}, position ({x_pos}, {y_pos})")
            logger.debug(f"Duration: {duration:.1f}s, Output: {temp_output}")

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                encoding='utf-8',
                errors='replace',
                timeout=60
            )

            logger.info(f"Chat segment extracted: {temp_output}")
            return str(temp_output)

        except subprocess.CalledProcessError as e:
            # Log full stderr to see actual error (not just banner)
            stderr_lines = e.stderr.split('\n') if e.stderr else []
            # Get last 20 lines which contain actual errors
            relevant_errors = '\n'.join(stderr_lines[-20:])
            logger.error(f"Failed to extract chat segment (exit code {e.returncode}):")
            logger.error(f"Command: {' '.join(cmd[:10])}")  # Log command (first 10 args)
            logger.error(f"Error details:\n{relevant_errors}")
            return None
        except subprocess.TimeoutExpired:
            logger.error("Chat segment extraction timed out")
            return None
        except Exception as e:
            logger.error(f"Unexpected error extracting chat: {e}")
            return None

    def get_overlay_position(
        self,
        video_width: int = 1920,
        video_height: int = 1080
    ) -> Tuple[int, int]:
        """
        Get overlay position in pixels for ffmpeg overlay filter.

        Args:
            video_width: Target video width
            video_height: Target video height

        Returns:
            Tuple of (x, y) position in pixels
        """
        scaled_width = int(self.chat_width * (self.scale_percent / 100.0))
        scaled_height = int(self.chat_height * (self.scale_percent / 100.0))

        x_pos = int((video_width - scaled_width) * (self.x_percent / 100.0))
        y_pos = int((video_height - scaled_height) * (self.y_percent / 100.0))

        return (x_pos, y_pos)

    @staticmethod
    def _get_video_dimensions(video_path: str) -> Tuple[int, int]:
        """Get video dimensions using ffprobe."""
        try:
            # Get width
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                 '-show_entries', 'stream=width', '-of', 'default=noprint_wrappers=1:nokey=1',
                 video_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding='utf-8'
            )
            width = int(result.stdout.strip())

            # Get height
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                 '-show_entries', 'stream=height', '-of', 'default=noprint_wrappers=1:nokey=1',
                 video_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding='utf-8'
            )
            height = int(result.stdout.strip())

            return (width, height)

        except Exception as e:
            logger.error(f"Failed to get video dimensions: {e}")
            # Default to common chat render size (portrait)
            return (700, 1200)


def overlay_chat_on_video(
    video_path: str,
    chat_segment_path: str,
    output_path: str,
    x_pos: int,
    y_pos: int
) -> bool:
    """
    Overlay chat segment onto video.

    Args:
        video_path: Path to main video
        chat_segment_path: Path to chat segment (already scaled)
        output_path: Path for output video
        x_pos: X position in pixels
        y_pos: Y position in pixels

    Returns:
        True if successful, False otherwise
    """
    try:
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-i', chat_segment_path,
            '-filter_complex', f'[0:v][1:v]overlay={x_pos}:{y_pos}[outv]',
            '-map', '[outv]',  # Use overlayed video
            '-map', '0:a?',     # Copy audio from main video only (? = optional)
            '-c:v', 'libx264',
            '-preset', 'ultrafast',  # Faster encoding for overlay (was 'fast')
            '-crf', '23',  # Slightly lower quality for speed (was 21)
            '-c:a', 'copy',
            '-y',
            output_path
        ]

        logger.info(f"Overlaying chat at position ({x_pos}, {y_pos})")

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            encoding='utf-8',
            errors='replace',
            timeout=3600  # 1 hour timeout (was 300s/5min)
        )

        logger.info(f"Chat overlay complete: {output_path}")
        return True

    except subprocess.CalledProcessError as e:
        # Log full stderr to see actual error (not just banner)
        stderr_lines = e.stderr.split('\n') if e.stderr else []
        # Get last 20 lines which contain actual errors
        relevant_errors = '\n'.join(stderr_lines[-20:])
        logger.error(f"Failed to overlay chat (exit code {e.returncode}):")
        logger.error(f"Error details:\n{relevant_errors}")
        return False
    except subprocess.TimeoutExpired:
        logger.error("Chat overlay timed out")
        return False
    except Exception as e:
        logger.error(f"Unexpected error overlaying chat: {e}")
        return False


if __name__ == "__main__":
    # Test
    import sys
    if len(sys.argv) < 2:
        print("Usage: python chat_overlay.py <chat_render.mp4>")
        sys.exit(1)

    try:
        overlay = ChatRenderOverlay(
            chat_render_path=sys.argv[1],
            x_percent=64,
            y_percent=10,
            scale_percent=80
        )

        # Test extraction
        segment = overlay.extract_segment(
            start_time=120.0,
            end_time=180.0
        )

        if segment:
            print(f"✅ Test segment extracted: {segment}")
            pos = overlay.get_overlay_position()
            print(f"✅ Overlay position: {pos}")
        else:
            print("❌ Failed to extract segment")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
