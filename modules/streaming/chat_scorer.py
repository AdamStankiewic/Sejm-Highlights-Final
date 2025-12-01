"""
Chat-based Scorer - Scores video segments based on chat activity
Alternative to GPT scoring for streaming content
"""

from typing import Dict, List, Any
import json
from pathlib import Path

from .chat_analyzer import ChatAnalyzer


class ChatScorer:
    """Scores video segments based on chat activity"""

    def __init__(self, chat_analyzer: ChatAnalyzer, chat_delay_offset: float = 10.0):
        """
        Initialize chat scorer

        Args:
            chat_analyzer: ChatAnalyzer instance with parsed chat
            chat_delay_offset: Seconds between action and chat reaction (default: 10s)
                              Chat reactions come AFTER the action happens due to stream delay
        """
        self.chat_analyzer = chat_analyzer
        self.chat_delay_offset = chat_delay_offset

    def score_segment(self, start_time: float, end_time: float) -> Dict[str, Any]:
        """
        Score a video segment based on chat activity

        IMPORTANT: Due to stream delay, chat reactions come ~10s AFTER the action.
        We offset the chat analysis window to account for this.

        Args:
            start_time: Segment start (seconds)
            end_time: Segment end (seconds)

        Returns:
            Dict with score and breakdown
        """
        # Offset chat window to account for stream delay
        # If action happens at 100s, chat reacts at ~110s
        chat_start = start_time + self.chat_delay_offset
        chat_end = end_time + self.chat_delay_offset

        # Get chat score for the offset window
        chat_score = self.chat_analyzer.get_chat_score(chat_start, chat_end)

        # Get breakdown for debugging
        activity_mult = self.chat_analyzer.get_activity_multiplier(chat_start, chat_end)
        emote_score = self.chat_analyzer.get_emote_spam_score(chat_start, chat_end)
        msg_rate = self.chat_analyzer.get_message_rate(chat_start, chat_end)

        return {
            'score': chat_score,  # 0-100
            'breakdown': {
                'activity_multiplier': activity_mult,
                'emote_spam_score': emote_score,
                'message_rate': msg_rate,
                'baseline_rate': self.chat_analyzer.baseline_msg_rate,
                'chat_offset_applied': self.chat_delay_offset
            }
        }


def create_scorer_from_chat(chat_json_path: str,
                            vod_duration: float = 0,
                            chat_delay_offset: float = 10.0) -> ChatScorer:
    """
    Factory function to create ChatScorer from chat JSON file

    Args:
        chat_json_path: Path to chat JSON file (Twitch Downloader format)
        vod_duration: VOD duration in seconds (0 = auto-detect from chat)
        chat_delay_offset: Stream delay in seconds (default: 10s)

    Returns:
        ChatScorer instance

    Raises:
        FileNotFoundError: If chat file doesn't exist
        json.JSONDecodeError: If chat file is invalid JSON
    """
    chat_path = Path(chat_json_path)

    if not chat_path.exists():
        raise FileNotFoundError(f"Chat file not found: {chat_json_path}")

    # Load chat data
    with open(chat_path, 'r', encoding='utf-8') as f:
        chat_data = json.load(f)

    # Create analyzer
    analyzer = ChatAnalyzer(chat_data, vod_duration)

    # Create scorer
    scorer = ChatScorer(analyzer, chat_delay_offset)

    return scorer
