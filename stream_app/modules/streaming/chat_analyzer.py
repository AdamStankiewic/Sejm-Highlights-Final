"""
Chat Analyzer - Parses and analyzes Twitch/YouTube chat data
Detects emote spam, message rate spikes, and highlight moments
"""

import json
from typing import Dict, List, Any
from pathlib import Path
from collections import defaultdict
import statistics


class ChatAnalyzer:
    """Analyzes chat activity to detect highlight moments"""

    # Common emotes that indicate reactions
    REACTION_EMOTES = {
        'KEKW', 'LULW', 'LUL', 'OMEGALUL', 'LMAO',  # Laughing
        'PogChamp', 'POG', 'POGGERS', 'PogU', 'POGGIES',  # Exciting
        'monkaS', 'monkaW', 'monkaHmm',  # Tense
        'Pog', 'Sadge', 'PepeHands', 'FeelsBadMan',  # Sad
        'Pepega', 'BRAIN', '5Head',  # Smart/dumb plays
        'WTF', 'WHAT', 'HUH',  # Confusion
        'HYPERS', 'EZ', 'GG'  # Victory
    }

    def __init__(self, chat_data: Dict[str, Any], vod_duration: float = 0):
        """
        Initialize chat analyzer

        Args:
            chat_data: Parsed chat JSON (Twitch Downloader or YouTube format)
            vod_duration: Total VOD duration in seconds
        """
        self.chat_data = chat_data
        self.vod_duration = vod_duration
        self.messages = []
        self.platform = "unknown"

        # Parse messages based on format
        self._parse_messages()

        # Calculate baseline metrics
        self.baseline_msg_rate = self._calculate_baseline_message_rate()

    def _parse_messages(self):
        """Parse messages from various chat formats"""
        # Twitch Downloader format
        if isinstance(self.chat_data, dict) and 'comments' in self.chat_data:
            self.platform = "twitch"
            for comment in self.chat_data['comments']:
                timestamp = comment.get('content_offset_seconds', 0)
                message_body = comment.get('message', {}).get('body', '')
                username = comment.get('commenter', {}).get('display_name', 'Unknown')

                self.messages.append({
                    'timestamp': float(timestamp),
                    'text': message_body,
                    'username': username
                })

        # Simple list format (custom)
        elif isinstance(self.chat_data, list):
            self.platform = "custom"
            for msg in self.chat_data:
                self.messages.append({
                    'timestamp': float(msg.get('timestamp', 0)),
                    'text': msg.get('text', ''),
                    'username': msg.get('username', 'Unknown')
                })

        # Sort by timestamp
        self.messages.sort(key=lambda x: x['timestamp'])

        # Update VOD duration if not provided
        if self.vod_duration == 0 and self.messages:
            self.vod_duration = max(msg['timestamp'] for msg in self.messages)

    def _calculate_baseline_message_rate(self) -> float:
        """Calculate baseline (median) message rate"""
        if not self.messages or self.vod_duration == 0:
            return 0.0

        # Split VOD into 30-second windows
        window_size = 30
        num_windows = int(self.vod_duration / window_size) + 1
        window_counts = [0] * num_windows

        for msg in self.messages:
            window_idx = int(msg['timestamp'] / window_size)
            if window_idx < len(window_counts):
                window_counts[window_idx] += 1

        # Calculate messages per second for each window
        rates = [count / window_size for count in window_counts if count > 0]

        if not rates:
            return 0.0

        # Use median as baseline (resistant to spikes)
        return statistics.median(rates)

    def get_statistics(self) -> Dict[str, Any]:
        """Get overall chat statistics"""
        unique_chatters = len(set(msg['username'] for msg in self.messages))

        return {
            'total_messages': len(self.messages),
            'unique_chatters': unique_chatters,
            'baseline_msg_rate': self.baseline_msg_rate,
            'platform': self.platform,
            'vod_duration': self.vod_duration
        }

    def get_message_rate(self, start_time: float, end_time: float) -> float:
        """
        Get message rate (msg/s) in a time window

        Args:
            start_time: Window start (seconds)
            end_time: Window end (seconds)

        Returns:
            Messages per second
        """
        duration = end_time - start_time
        if duration <= 0:
            return 0.0

        count = sum(1 for msg in self.messages
                   if start_time <= msg['timestamp'] < end_time)

        return count / duration

    def get_emote_spam_score(self, start_time: float, end_time: float) -> float:
        """
        Calculate emote spam score (0-1) in a time window

        Higher score = more emote spam = more exciting moment

        Args:
            start_time: Window start (seconds)
            end_time: Window end (seconds)

        Returns:
            Score from 0 (no spam) to 1 (heavy spam)
        """
        window_messages = [msg for msg in self.messages
                          if start_time <= msg['timestamp'] < end_time]

        if not window_messages:
            return 0.0

        # Count emote occurrences
        emote_count = 0
        total_words = 0

        for msg in window_messages:
            words = msg['text'].split()
            total_words += len(words)

            for word in words:
                # Check if word is a reaction emote
                if word in self.REACTION_EMOTES:
                    emote_count += 1

        if total_words == 0:
            return 0.0

        # Emote ratio (0-1)
        emote_ratio = min(emote_count / total_words, 1.0)

        return emote_ratio

    def get_activity_multiplier(self, start_time: float, end_time: float) -> float:
        """
        Get activity multiplier relative to baseline

        Args:
            start_time: Window start (seconds)
            end_time: Window end (seconds)

        Returns:
            Multiplier (1.0 = baseline, >1.0 = more active)
        """
        if self.baseline_msg_rate == 0:
            return 1.0

        current_rate = self.get_message_rate(start_time, end_time)
        multiplier = current_rate / self.baseline_msg_rate

        return max(multiplier, 1.0)  # At least 1x

    def get_chat_score(self, start_time: float, end_time: float) -> float:
        """
        Get comprehensive chat score for a segment (0-100)

        Combines:
        - Message rate spike (relative to baseline)
        - Emote spam intensity

        Args:
            start_time: Window start (seconds)
            end_time: Window end (seconds)

        Returns:
            Chat score (0-100)
        """
        # Get components
        activity_mult = self.get_activity_multiplier(start_time, end_time)
        emote_score = self.get_emote_spam_score(start_time, end_time)

        # Combine scores
        # Activity: 0-50 points (capped at 5x baseline = 50 points)
        activity_points = min((activity_mult - 1) * 12.5, 50)

        # Emote spam: 0-50 points
        emote_points = emote_score * 50

        total_score = activity_points + emote_points

        return min(total_score, 100)
