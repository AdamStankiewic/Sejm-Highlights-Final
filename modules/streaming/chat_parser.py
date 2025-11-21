"""
Parse Twitch/YouTube chat logs
Part of Highlights AI Platform - Streaming Module
"""
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime


class ChatParser:
    """
    Parse chat activity from VOD chat logs.

    Supports formats:
    - Twitch chat JSON (from tools like TwitchDownloader)
    - YouTube live chat JSON
    - Generic timestamped chat format
    """

    def __init__(self, emotes: Optional[List[str]] = None):
        self.popular_emotes = emotes or [
            'KEKW', 'LUL', 'PogChamp', 'Pog', 'OMEGALUL',
            'monkaS', 'Pepega', 'Sadge', 'PepeHands', 'EZ'
        ]

    def parse_twitch_chat(self, chat_file: str) -> List[Dict]:
        """
        Parse Twitch chat JSON format

        Expected format (TwitchDownloader output):
        {
            "comments": [
                {
                    "content_offset_seconds": 123.45,
                    "commenter": {"display_name": "user1"},
                    "message": {"body": "KEKW"}
                }
            ]
        }
        """
        with open(chat_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        chat_data = []

        # Handle different formats
        if 'comments' in data:
            # TwitchDownloader format
            for comment in data['comments']:
                chat_data.append({
                    'timestamp': comment.get('content_offset_seconds', 0),
                    'user': comment.get('commenter', {}).get('display_name', 'unknown'),
                    'message': comment.get('message', {}).get('body', '')
                })
        elif isinstance(data, list):
            # Simple list format
            for item in data:
                chat_data.append({
                    'timestamp': item.get('timestamp', item.get('time', 0)),
                    'user': item.get('user', item.get('author', 'unknown')),
                    'message': item.get('message', item.get('text', ''))
                })

        # Sort by timestamp
        chat_data.sort(key=lambda x: x['timestamp'])

        return chat_data

    def parse_youtube_chat(self, chat_file: str) -> List[Dict]:
        """
        Parse YouTube live chat JSON

        Expected format (yt-dlp live chat):
        Lines of JSON with:
        {
            "replayChatItemAction": {
                "videoOffsetTimeMsec": "123000",
                "actions": [{"addChatItemAction": {"item": {"liveChatTextMessageRenderer": {...}}}}]
            }
        }
        """
        chat_data = []

        with open(chat_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    item = json.loads(line)

                    if 'replayChatItemAction' in item:
                        action = item['replayChatItemAction']
                        offset_ms = int(action.get('videoOffsetTimeMsec', 0))
                        timestamp = offset_ms / 1000.0

                        for sub_action in action.get('actions', []):
                            if 'addChatItemAction' in sub_action:
                                chat_item = sub_action['addChatItemAction'].get('item', {})
                                renderer = chat_item.get('liveChatTextMessageRenderer', {})

                                if renderer:
                                    author = renderer.get('authorName', {}).get('simpleText', 'unknown')
                                    message_runs = renderer.get('message', {}).get('runs', [])
                                    message = ''.join(run.get('text', '') for run in message_runs)

                                    chat_data.append({
                                        'timestamp': timestamp,
                                        'user': author,
                                        'message': message
                                    })

                except json.JSONDecodeError:
                    continue

        chat_data.sort(key=lambda x: x['timestamp'])
        return chat_data

    def get_activity_at_time(
        self,
        chat_data: List[Dict],
        timestamp: float,
        window: float = 10.0
    ) -> int:
        """
        Count messages in time window around timestamp

        Args:
            chat_data: Parsed chat data
            timestamp: Center timestamp in seconds
            window: Window size in seconds

        Returns:
            Number of messages in window
        """
        count = 0
        half_window = window / 2

        for msg in chat_data:
            msg_time = msg['timestamp']
            if timestamp - half_window <= msg_time <= timestamp + half_window:
                count += 1

        return count

    def get_baseline_rate(self, chat_data: List[Dict]) -> float:
        """
        Calculate baseline messages/second for entire stream

        Returns:
            Average messages per second
        """
        if not chat_data or len(chat_data) < 2:
            return 0.0

        first_time = chat_data[0]['timestamp']
        last_time = chat_data[-1]['timestamp']
        duration = last_time - first_time

        if duration <= 0:
            return 0.0

        return len(chat_data) / duration

    def count_emotes(
        self,
        chat_data: List[Dict],
        timestamp: float,
        window: float = 10.0
    ) -> int:
        """
        Count emote occurrences in time window

        Args:
            chat_data: Parsed chat data
            timestamp: Center timestamp
            window: Window size in seconds

        Returns:
            Total emote count
        """
        count = 0
        half_window = window / 2

        for msg in chat_data:
            msg_time = msg['timestamp']
            if timestamp - half_window <= msg_time <= timestamp + half_window:
                message = msg.get('message', '')
                for emote in self.popular_emotes:
                    count += message.count(emote)

        return count

    def find_chat_spikes(
        self,
        chat_data: List[Dict],
        multiplier: float = 3.0,
        window: float = 10.0
    ) -> List[Dict]:
        """
        Find timestamps where chat activity spikes above baseline

        Args:
            chat_data: Parsed chat data
            multiplier: How many times above baseline counts as spike
            window: Window size for activity counting

        Returns:
            List of spike dicts with timestamp and intensity
        """
        if not chat_data:
            return []

        baseline = self.get_baseline_rate(chat_data)
        if baseline <= 0:
            return []

        spikes = []
        threshold = baseline * window * multiplier

        # Sample every 5 seconds
        first_time = chat_data[0]['timestamp']
        last_time = chat_data[-1]['timestamp']

        for t in range(int(first_time), int(last_time), 5):
            activity = self.get_activity_at_time(chat_data, t, window)

            if activity > threshold:
                intensity = activity / threshold
                spikes.append({
                    'timestamp': t,
                    'activity': activity,
                    'intensity': intensity
                })

        return spikes

    def get_chat_stats(self, chat_data: List[Dict]) -> Dict[str, Any]:
        """Get overall chat statistics"""
        if not chat_data:
            return {
                'total_messages': 0,
                'unique_users': 0,
                'duration_seconds': 0,
                'messages_per_minute': 0.0
            }

        first_time = chat_data[0]['timestamp']
        last_time = chat_data[-1]['timestamp']
        duration = last_time - first_time

        users = set(msg['user'] for msg in chat_data)

        return {
            'total_messages': len(chat_data),
            'unique_users': len(users),
            'duration_seconds': duration,
            'messages_per_minute': (len(chat_data) / duration * 60) if duration > 0 else 0.0
        }
