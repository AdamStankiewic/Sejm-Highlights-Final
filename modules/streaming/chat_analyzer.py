"""
Multi-platform Chat Analyzer
Supports: YouTube, Kick, Twitch

Parses chat JSON files and performs:
- Baseline normalization
- Spike detection
- Viewer count normalization (if available)
- Activity timeline generation
"""

import json
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from datetime import datetime
import statistics


class ChatMessage:
    """Unified chat message format across all platforms"""

    def __init__(
        self,
        timestamp: float,
        username: str,
        message: str,
        emotes: List[str] = None,
        is_subscriber: bool = False,
        is_vip: bool = False,
        is_moderator: bool = False,
        platform: str = "unknown"
    ):
        self.timestamp = timestamp
        self.username = username
        self.message = message
        self.emotes = emotes or []
        self.is_subscriber = is_subscriber
        self.is_vip = is_vip
        self.is_moderator = is_moderator
        self.platform = platform

    def __repr__(self):
        return f"ChatMessage({self.timestamp:.1f}s, {self.username}: {self.message[:30]}...)"


class ChatAnalyzer:
    """
    Multi-platform chat analyzer with spike detection
    """

    def __init__(
        self,
        chat_json_path: Optional[str] = None,
        vod_duration: float = 0,
        platform: Optional[str] = None
    ):
        """
        Initialize chat analyzer

        Args:
            chat_json_path: Path to chat JSON file
            vod_duration: Total VOD duration in seconds
            platform: 'youtube', 'kick', or 'twitch' (auto-detected if None)
        """
        self.chat_json_path = chat_json_path
        self.vod_duration = vod_duration
        self.platform = platform
        self.messages: List[ChatMessage] = []
        self.baseline_msg_rate = 0.0
        self.viewer_count_available = False

        if chat_json_path:
            self.load_and_parse()

    def load_and_parse(self) -> List[ChatMessage]:
        """Load and parse chat JSON file"""
        if not self.chat_json_path or not Path(self.chat_json_path).exists():
            raise FileNotFoundError(f"Chat file not found: {self.chat_json_path}")

        with open(self.chat_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Auto-detect platform if not specified
        if not self.platform:
            self.platform = self._detect_platform(data)

        # Parse based on platform
        if self.platform == 'twitch':
            self.messages = self._parse_twitch(data)
        elif self.platform == 'youtube':
            self.messages = self._parse_youtube(data)
        elif self.platform == 'kick':
            self.messages = self._parse_kick(data)
        else:
            raise ValueError(f"Unknown platform: {self.platform}")

        print(f"✅ Parsed {len(self.messages)} messages from {self.platform.upper()}")

        # Calculate baseline
        if self.messages:
            self.baseline_msg_rate = self._calculate_baseline()
            print(f"📊 Baseline: {self.baseline_msg_rate:.2f} msg/s")

        return self.messages

    def _detect_platform(self, data: dict) -> str:
        """Auto-detect platform from JSON structure"""

        # Twitch Downloader format
        if isinstance(data, dict) and 'comments' in data:
            if any('commenter' in c for c in data.get('comments', [])[:5]):
                return 'twitch'

        # YouTube format (yt-dlp or chat-downloader)
        if isinstance(data, list) and len(data) > 0:
            first = data[0]
            if 'author' in first or 'author_name' in first:
                return 'youtube'
            if 'sender' in first or 'content' in first:
                return 'kick'

        # Fallback: check for platform-specific fields
        data_str = json.dumps(data)[:1000].lower()
        if 'twitch' in data_str or 'commenter' in data_str:
            return 'twitch'
        if 'youtube' in data_str or 'yt-dlp' in data_str:
            return 'youtube'
        if 'kick' in data_str or 'sender' in data_str:
            return 'kick'

        return 'unknown'

    def _parse_twitch(self, data: dict) -> List[ChatMessage]:
        """
        Parse Twitch Downloader JSON format

        Format:
        {
          "comments": [
            {
              "content_offset_seconds": 123.45,
              "commenter": {
                "display_name": "Viewer123",
                "_id": "12345"
              },
              "message": {
                "body": "KEKW message",
                "fragments": [
                  {"text": "KEKW", "emoticon": {"emoticon_id": "..."}}
                ],
                "user_badges": [
                  {"_id": "subscriber", "version": "1"},
                  {"_id": "vip"}
                ]
              }
            }
          ],
          "video": {
            "title": "Stream title",
            "viewCount": 12345  // May contain viewer count
          }
        }
        """
        messages = []
        comments = data.get('comments', [])

        # Check if viewer count available
        video_info = data.get('video', {})
        if 'viewCount' in video_info:
            self.viewer_count_available = True

        for comment in comments:
            try:
                timestamp = comment.get('content_offset_seconds', 0)

                commenter = comment.get('commenter', {})
                username = commenter.get('display_name', 'Anonymous')

                message_data = comment.get('message', {})
                text = message_data.get('body', '')

                # Extract emotes from fragments
                emotes = []
                for fragment in message_data.get('fragments', []):
                    if 'emoticon' in fragment:
                        emote_text = fragment.get('text', '')
                        if emote_text:
                            emotes.append(emote_text)

                # Parse badges
                badges = message_data.get('user_badges', [])
                is_sub = any(b.get('_id') == 'subscriber' for b in badges)
                is_vip = any(b.get('_id') == 'vip' for b in badges)
                is_mod = any(b.get('_id') == 'moderator' for b in badges)

                msg = ChatMessage(
                    timestamp=timestamp,
                    username=username,
                    message=text,
                    emotes=emotes,
                    is_subscriber=is_sub,
                    is_vip=is_vip,
                    is_moderator=is_mod,
                    platform='twitch'
                )
                messages.append(msg)

            except Exception as e:
                # Skip malformed messages
                continue

        return sorted(messages, key=lambda m: m.timestamp)

    def _parse_youtube(self, data: list) -> List[ChatMessage]:
        """
        Parse YouTube chat JSON format (from yt-dlp or chat-downloader)

        Format 1 (yt-dlp --write-comments):
        [
          {
            "id": "...",
            "text": "Great stream!",
            "timestamp": 123,  // seconds
            "time_text": "2:03",
            "author": "Viewer Name",
            "author_id": "UC...",
            "is_favorited": false
          }
        ]

        Format 2 (chat-downloader):
        [
          {
            "time_in_seconds": 123.45,
            "message": "LOL",
            "author": {"name": "Viewer"},
            "message_type": "text_message"
          }
        ]
        """
        messages = []

        for item in data:
            try:
                # Handle different timestamp fields
                timestamp = (
                    item.get('time_in_seconds') or
                    item.get('timestamp') or
                    item.get('time') or
                    0
                )

                # Handle different message fields
                text = (
                    item.get('message') or
                    item.get('text') or
                    item.get('snippet', {}).get('displayMessage', '') or
                    ''
                )

                # Handle different author fields
                author_data = item.get('author', {})
                if isinstance(author_data, dict):
                    username = author_data.get('name', 'Anonymous')
                else:
                    username = item.get('author', 'Anonymous')

                # YouTube emotes detection (basic)
                # YouTube uses different emote system (reactions, not text-based)
                emotes = self._extract_youtube_emotes(text, item)

                # YouTube membership = subscriber
                is_sub = item.get('is_member', False) or item.get('is_sponsor', False)
                is_mod = item.get('is_moderator', False)
                is_owner = item.get('is_owner', False)

                msg = ChatMessage(
                    timestamp=float(timestamp),
                    username=username,
                    message=text,
                    emotes=emotes,
                    is_subscriber=is_sub,
                    is_vip=is_owner,  # Channel owner = VIP equivalent
                    is_moderator=is_mod,
                    platform='youtube'
                )
                messages.append(msg)

            except Exception as e:
                continue

        return sorted(messages, key=lambda m: m.timestamp)

    def _parse_kick(self, data: list) -> List[ChatMessage]:
        """
        Parse Kick chat JSON format

        Format (from Kick chat export or API):
        [
          {
            "id": "...",
            "chatroom_id": 123,
            "content": "PogChamp awesome",
            "created_at": "2025-01-15T20:02:03.000000Z",
            "sender": {
              "id": 456,
              "username": "kickviewer",
              "slug": "kickviewer",
              "identity": {
                "badges": [
                  {"type": "subscriber", "count": 3},
                  {"type": "vip"}
                ]
              }
            }
          }
        ]
        """
        messages = []

        # Need VOD start time to calculate relative timestamps
        vod_start = None

        for item in data:
            try:
                # Parse timestamp
                created_at = item.get('created_at', '')
                if created_at:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))

                    # Calculate relative timestamp
                    if vod_start is None:
                        vod_start = dt
                        timestamp = 0.0
                    else:
                        timestamp = (dt - vod_start).total_seconds()
                else:
                    timestamp = 0.0

                # Message content
                text = item.get('content', '')

                # Sender info
                sender = item.get('sender', {})
                username = sender.get('username', 'Anonymous')

                # Extract emotes (Kick uses text-based emotes like Twitch)
                emotes = self._extract_kick_emotes(text)

                # Badges
                identity = sender.get('identity', {})
                badges = identity.get('badges', [])
                is_sub = any(b.get('type') == 'subscriber' for b in badges)
                is_vip = any(b.get('type') == 'vip' for b in badges)
                is_mod = any(b.get('type') == 'moderator' for b in badges)

                msg = ChatMessage(
                    timestamp=timestamp,
                    username=username,
                    message=text,
                    emotes=emotes,
                    is_subscriber=is_sub,
                    is_vip=is_vip,
                    is_moderator=is_mod,
                    platform='kick'
                )
                messages.append(msg)

            except Exception as e:
                continue

        return sorted(messages, key=lambda m: m.timestamp)

    def _extract_youtube_emotes(self, text: str, item: dict) -> List[str]:
        """Extract YouTube emotes (reactions, custom emojis)"""
        emotes = []

        # YouTube custom emotes (for members)
        if 'emotes' in item:
            emotes.extend([e.get('id', '') for e in item.get('emotes', [])])

        # Common YouTube reactions (as text)
        youtube_reactions = ['😂', '🤣', '💀', '🔥', '❤️', '👏', '😭', '💯']
        for reaction in youtube_reactions:
            if reaction in text:
                emotes.append(reaction)

        return emotes

    def _extract_kick_emotes(self, text: str) -> List[str]:
        """Extract Kick emotes from message text"""
        # Kick uses colon-wrapped emotes like :PogChamp:
        # And also supports some global emotes as text
        import re

        emotes = []

        # :emotename: format
        colon_emotes = re.findall(r':(\w+):', text)
        emotes.extend(colon_emotes)

        # Common global emotes as text
        kick_emotes = ['PogChamp', 'KEKW', 'LUL', 'Pog', 'Sadge', 'monkaS']
        for emote in kick_emotes:
            if emote in text:
                emotes.append(emote)

        return emotes

    def _calculate_baseline(self, window_size: int = 60) -> float:
        """
        Calculate baseline message rate (median across stream)

        Args:
            window_size: Seconds per window (default 60s)

        Returns:
            Baseline messages per second
        """
        if not self.messages:
            return 0.0

        # Get max timestamp
        max_time = max(m.timestamp for m in self.messages)
        if max_time == 0:
            return 0.0

        # Calculate msg rate for each window
        rates = []
        for t in range(0, int(max_time), window_size):
            window_msgs = [
                m for m in self.messages
                if t <= m.timestamp < t + window_size
            ]
            rate = len(window_msgs) / window_size
            if rate > 0:  # Only count non-zero windows
                rates.append(rate)

        # Use median (more robust than mean)
        if rates:
            return statistics.median(rates)
        return 0.0

    def detect_spikes(
        self,
        window_size: int = 30,
        spike_threshold: float = 3.0,
        min_messages: int = 10
    ) -> List[Tuple[float, float, int]]:
        """
        Detect chat activity spikes

        Args:
            window_size: Seconds per window (default 30s)
            spike_threshold: Multiplier vs baseline (default 3.0x)
            min_messages: Minimum messages in window to consider

        Returns:
            List of (timestamp, spike_intensity, message_count) tuples
        """
        if not self.messages or self.baseline_msg_rate == 0:
            return []

        spikes = []
        max_time = max(m.timestamp for m in self.messages)

        # Slide window with 50% overlap
        step = window_size // 2

        for t in range(0, int(max_time), step):
            window_start = t
            window_end = t + window_size

            # Get messages in window
            window_msgs = [
                m for m in self.messages
                if window_start <= m.timestamp < window_end
            ]

            msg_count = len(window_msgs)

            # Skip if too few messages
            if msg_count < min_messages:
                continue

            # Calculate rate
            msg_rate = msg_count / window_size

            # Check if spike
            spike_ratio = msg_rate / self.baseline_msg_rate

            if spike_ratio >= spike_threshold:
                # Use middle of window as timestamp
                spike_time = window_start + (window_size / 2)
                spikes.append((spike_time, spike_ratio, msg_count))

        # Sort by intensity (highest first)
        spikes.sort(key=lambda x: x[1], reverse=True)

        return spikes

    def get_messages_in_window(
        self,
        start_time: float,
        end_time: float
    ) -> List[ChatMessage]:
        """Get all messages in time window"""
        return [
            m for m in self.messages
            if start_time <= m.timestamp < end_time
        ]

    def calculate_local_baseline(
        self,
        timestamp: float,
        lookback: int = 300
    ) -> float:
        """
        Calculate baseline for local context (previous 5 minutes)

        Better for streams with varying activity levels
        """
        start = max(0, timestamp - lookback)
        window_msgs = self.get_messages_in_window(start, timestamp)

        if not window_msgs:
            return self.baseline_msg_rate

        return len(window_msgs) / lookback

    def get_statistics(self) -> Dict:
        """Get overall chat statistics"""
        if not self.messages:
            return {
                'total_messages': 0,
                'duration': 0,
                'avg_msg_rate': 0,
                'baseline_msg_rate': 0,
                'unique_chatters': 0,
                'platform': self.platform
            }

        max_time = max(m.timestamp for m in self.messages)
        unique_users = len(set(m.username for m in self.messages))

        return {
            'total_messages': len(self.messages),
            'duration': max_time,
            'avg_msg_rate': len(self.messages) / max_time if max_time > 0 else 0,
            'baseline_msg_rate': self.baseline_msg_rate,
            'unique_chatters': unique_users,
            'platform': self.platform,
            'viewer_count_available': self.viewer_count_available
        }


if __name__ == "__main__":
    # Test with sample file
    import sys

    if len(sys.argv) > 1:
        analyzer = ChatAnalyzer(sys.argv[1])

        print("\n📊 Chat Statistics:")
        stats = analyzer.get_statistics()
        for key, value in stats.items():
            print(f"  {key}: {value}")

        print("\n🔥 Top Spikes:")
        spikes = analyzer.detect_spikes(window_size=30, spike_threshold=2.5)
        for i, (time, intensity, count) in enumerate(spikes[:10], 1):
            mins = int(time // 60)
            secs = int(time % 60)
            print(f"  {i}. {mins}:{secs:02d} - {intensity:.2f}x baseline ({count} msgs)")
