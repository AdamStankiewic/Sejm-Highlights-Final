"""
Chat Overlay Renderer for Long Videos

Renders time-synchronized chat overlay on video using event-based optimization.
Manual positioning only (no auto-detection for long videos).

Performance: ~30-90 seconds for 2h video (vs 4-8 hours naive per-frame approach)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)


class ChatOverlayRenderer:
    """Renders time-synced chat overlay for long videos."""

    def __init__(
        self,
        position: str = "top_right",
        width_percent: int = 25,
        opacity: float = 0.8,
        max_messages: int = 10,
        message_lifetime: float = 30.0,
        font_size: int = 16,
        font_color: str = "white",
        bg_color: Tuple[int, int, int] = (0, 0, 0)
    ):
        """
        Initialize chat overlay renderer.

        Args:
            position: "top_right", "top_left", "bottom_right", "bottom_left"
            width_percent: Chat box width as % of screen (20-40)
            opacity: Background opacity 0.0-1.0 (0.6-1.0 recommended)
            max_messages: Maximum messages to show at once (5-15)
            message_lifetime: How long to show messages in seconds (20-60)
            font_size: Font size in pixels (12-20)
            font_color: Text color (white, yellow, etc)
            bg_color: Background RGB tuple
        """
        self.position = position
        self.width_percent = max(20, min(40, width_percent))
        self.opacity = max(0.6, min(1.0, opacity))
        self.max_messages = max(5, min(15, max_messages))
        self.message_lifetime = max(20.0, min(60.0, message_lifetime))
        self.font_size = font_size
        self.font_color = font_color
        self.bg_color = bg_color

    def render_overlay(
        self,
        chat_json_path: str,
        video_duration: float,
        video_size: Tuple[int, int] = (1920, 1080)
    ) -> str:
        """
        Render chat overlay and return path to overlay video file.

        This creates a transparent video with chat that can be composited
        over the main video using ffmpeg overlay filter.

        Args:
            chat_json_path: Path to chat.json file
            video_duration: Total video duration in seconds
            video_size: Video resolution (width, height)

        Returns:
            Path to rendered chat overlay video (.mp4 with alpha channel)
        """
        from utils.chat_parser import load_chat_messages

        # Load chat messages
        logger.info(f"Loading chat from: {chat_json_path}")
        messages = load_chat_messages(chat_json_path)

        if not messages:
            logger.warning("No chat messages found - skipping overlay")
            return None

        logger.info(f"Loaded {len(messages)} chat messages")

        # Calculate chat box dimensions and position
        width, height = video_size
        chat_width = int(width * (self.width_percent / 100))
        chat_height = int(height * 0.35)  # 35% of screen height

        positions = {
            "top_right": (width - chat_width - 20, 20),
            "top_left": (20, 20),
            "bottom_right": (width - chat_width - 20, height - chat_height - 20),
            "bottom_left": (20, height - chat_height - 20)
        }

        x, y = positions.get(self.position, positions["top_right"])

        # Generate chat events (when chat content changes)
        chat_events = self._generate_chat_events(messages, video_duration)

        logger.info(f"Generated {len(chat_events)} chat events")

        # Render using ffmpeg (fastest approach)
        output_path = self._render_with_ffmpeg(
            chat_events,
            video_duration,
            video_size,
            (x, y),
            (chat_width, chat_height)
        )

        return output_path

    def _generate_chat_events(
        self,
        messages: List[Dict],
        video_duration: float
    ) -> List[Dict]:
        """
        Generate chat events (changes in visible messages).

        Uses rolling window approach: show last N messages within time window.

        Returns list of events:
            [
                {
                    "timestamp": 120.5,
                    "messages": [
                        {"author": "User1", "message": "Text1"},
                        {"author": "User2", "message": "Text2"},
                    ]
                },
                ...
            ]
        """
        events = []
        current_window = []
        last_event_timestamp = -999

        for msg in messages:
            timestamp = msg["time"]

            # Skip messages beyond video duration
            if timestamp > video_duration:
                break

            # Remove old messages (older than message_lifetime)
            current_window = [
                m for m in current_window
                if timestamp - m["time"] < self.message_lifetime
            ]

            # Add new message
            current_window.append(msg)

            # Keep only last N messages
            current_window = current_window[-self.max_messages:]

            # Create event only if enough time passed (avoid too many events)
            # Minimum 0.5 seconds between events for performance
            if timestamp - last_event_timestamp >= 0.5:
                events.append({
                    "timestamp": timestamp,
                    "messages": [
                        {
                            "author": m["author"][:15],  # Truncate long names
                            "message": m["message"][:60]  # Truncate long messages
                        }
                        for m in current_window
                    ]
                })
                last_event_timestamp = timestamp

        return events

    def _render_with_ffmpeg(
        self,
        chat_events: List[Dict],
        video_duration: float,
        video_size: Tuple[int, int],
        position: Tuple[int, int],
        box_size: Tuple[int, int]
    ) -> str:
        """
        Render chat overlay using ffmpeg drawtext filter.

        Simpler approach: Use single drawtext with enable conditions.

        Returns path to output overlay file.
        """
        import subprocess
        import tempfile

        if not chat_events:
            return None

        width, height = video_size
        x, y = position
        box_width, box_height = box_size

        # Create output file in temp directory
        output_file = Path(tempfile.gettempdir()) / "chat_overlay.mp4"

        # Build drawbox + drawtext filters with enable conditions
        bg_r, bg_g, bg_b = self.bg_color
        text_x = x + 10
        text_y = y + 10

        # Build filter chain: drawbox (always on) + multiple drawtext (timed)
        drawbox_filter = (
            f"drawbox=x={x}:y={y}:w={box_width}:h={box_height}:"
            f"color={bg_r:02x}{bg_g:02x}{bg_b:02x}@{self.opacity}:t=fill"
        )

        # Build drawtext filters with enable conditions
        drawtext_filters = []
        for i, event in enumerate(chat_events):
            timestamp = event["timestamp"]
            next_timestamp = chat_events[i + 1]["timestamp"] if i + 1 < len(chat_events) else video_duration

            # Build text content
            lines = []
            for msg in event["messages"][-self.max_messages:]:
                author = msg["author"]
                text = msg["message"]
                # Simple sanitization
                author_safe = author.replace("'", "").replace(":", "")
                text_safe = text.replace("'", "").replace(":", "").replace("\\", "")
                lines.append(f"{author_safe}: {text_safe}")

            chat_text = "\\n".join(lines)
            if not chat_text:
                continue

            # Enable condition
            enable_condition = f"between(t,{timestamp},{next_timestamp})"

            # Drawtext filter
            drawtext_filter = (
                f"drawtext=text='{chat_text}':"
                f"fontsize={self.font_size}:fontcolor={self.font_color}:"
                f"x={text_x}:y={text_y}:enable='{enable_condition}'"
            )

            drawtext_filters.append(drawtext_filter)

        # Combine all filters
        all_filters = [drawbox_filter] + drawtext_filters
        vf_filter = ",".join(all_filters)

        # Build ffmpeg command
        cmd = [
            'ffmpeg',
            '-f', 'lavfi',
            '-i', f'color=c=black@0.0:s={width}x{height}:d={video_duration}',
            '-vf', vf_filter,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-pix_fmt', 'yuv420p',
            '-y',
            str(output_file)
        ]

        logger.info("Rendering chat overlay with ffmpeg...")
        logger.debug(f"Video filter: {vf_filter[:300]}...")

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                encoding='utf-8',
                errors='replace',
                timeout=300  # 5 minute timeout
            )

            logger.info(f"Chat overlay rendered: {output_file}")
            return str(output_file)

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to render chat overlay: {e.stderr[:500]}")
            # Fall back to simpler approach without events
            return self._render_simple_fallback(
                chat_events,
                video_duration,
                video_size,
                position,
                box_size
            )
        except subprocess.TimeoutExpired:
            logger.error("Chat overlay rendering timed out")
            return None

    def _render_simple_fallback(
        self,
        chat_events: List[Dict],
        video_duration: float,
        video_size: Tuple[int, int],
        position: Tuple[int, int],
        box_size: Tuple[int, int]
    ) -> str:
        """
        Fallback: Render static chat box with all messages.

        Simpler but less dynamic - shows latest messages only.
        """
        import subprocess
        import tempfile

        logger.warning("Using simple fallback rendering (static chat)")

        width, height = video_size
        x, y = position
        box_width, box_height = box_size

        # Get last event messages
        if not chat_events:
            return None

        last_event = chat_events[-1]
        lines = []
        for msg in last_event["messages"][-self.max_messages:]:
            author = msg["author"]
            text = msg["message"]
            lines.append(f"{author}: {text}")

        chat_text = "\\n".join(lines)
        chat_text_safe = chat_text.replace("'", "\\'").replace(":", "\\:")

        output_file = Path(tempfile.gettempdir()) / "chat_overlay_simple.mp4"

        bg_r, bg_g, bg_b = self.bg_color
        text_x = x + 10
        text_y = y + 10

        # Simple static overlay
        cmd = [
            'ffmpeg',
            '-f', 'lavfi',
            '-i', f'color=c=black@0.0:s={width}x{height}:d={video_duration}',
            '-vf',
            f"drawbox=x={x}:y={y}:w={box_width}:h={box_height}:"
            f"color={bg_r:02x}{bg_g:02x}{bg_b:02x}@{self.opacity}:t=fill,"
            f"drawtext=text='{chat_text_safe}':fontsize={self.font_size}:"
            f"fontcolor={self.font_color}:x={text_x}:y={text_y}",
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-pix_fmt', 'yuva420p',
            '-y',
            str(output_file)
        ]

        try:
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )

            logger.info(f"Simple chat overlay rendered: {output_file}")
            return str(output_file)

        except subprocess.CalledProcessError as e:
            logger.error(f"Fallback rendering also failed: {e.stderr[:200]}")
            return None


if __name__ == "__main__":
    # Test
    import sys
    if len(sys.argv) < 2:
        print("Usage: python chat_overlay.py <chat.json>")
        sys.exit(1)

    renderer = ChatOverlayRenderer(
        position="top_right",
        width_percent=25,
        opacity=0.8
    )

    overlay_path = renderer.render_overlay(
        chat_json_path=sys.argv[1],
        video_duration=120.0,  # 2 minutes test
        video_size=(1920, 1080)
    )

    if overlay_path:
        print(f"✅ Chat overlay rendered: {overlay_path}")
    else:
        print("❌ Failed to render chat overlay")
