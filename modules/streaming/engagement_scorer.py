"""
Engagement Scorer
Analyzes chat engagement quality beyond just volume

Metrics:
- Chatter diversity (unique users vs spam)
- Message quality (length, complexity)
- Conversation detection (reply chains)
- VIP/Subscriber participation
"""

from typing import List, Dict, Set
from .chat_analyzer import ChatMessage
import statistics


class EngagementScorer:
    """
    Score chat engagement quality
    """

    def __init__(self):
        """Initialize engagement scorer"""
        pass

    def score_chatter_diversity(self, messages: List[ChatMessage]) -> float:
        """
        Score based on unique chatters vs total messages

        High diversity = many different people engaging (good)
        Low diversity = few people spamming (less valuable)

        Returns:
            Diversity score (0.0 - 10.0)
        """
        if not messages:
            return 0.0

        unique_users = len(set(m.username for m in messages))
        total_messages = len(messages)

        diversity_ratio = unique_users / total_messages

        # Interpretation:
        # 1.0 = every message from different person (perfect, rare)
        # 0.5-0.8 = healthy conversation
        # 0.2-0.4 = some spam
        # <0.2 = heavy spam from few users

        if diversity_ratio >= 0.8:
            return 10.0  # Exceptional diversity
        elif diversity_ratio >= 0.5:
            return 7.0 + ((diversity_ratio - 0.5) / 0.3) * 3.0  # 7-10
        elif diversity_ratio >= 0.2:
            return 4.0 + ((diversity_ratio - 0.2) / 0.3) * 3.0  # 4-7
        else:
            return diversity_ratio * 20  # 0-4 (spam zone)

    def score_message_quality(self, messages: List[ChatMessage]) -> float:
        """
        Score based on message length and complexity

        Longer messages = more engaged viewers (usually)
        Very short = spam/emotes only

        Returns:
            Quality score (0.0 - 10.0)
        """
        if not messages:
            return 0.0

        lengths = [len(m.message) for m in messages if m.message.strip()]

        if not lengths:
            return 3.0  # Only emotes, no text

        avg_length = statistics.mean(lengths)
        median_length = statistics.median(lengths)

        # Use median (more robust against outliers)
        typical_length = median_length

        # Interpretation:
        # <10 chars: Emotes/spam → 3-5
        # 10-30: Normal chat → 5-7
        # 30-100: Engaged discussion → 7-9
        # 100+: Very engaged (questions, long reactions) → 9-10

        if typical_length < 10:
            return 3.0 + (typical_length / 10) * 2.0  # 3-5
        elif typical_length < 30:
            return 5.0 + ((typical_length - 10) / 20) * 2.0  # 5-7
        elif typical_length < 100:
            return 7.0 + ((typical_length - 30) / 70) * 2.0  # 7-9
        else:
            return min(9.0 + ((typical_length - 100) / 100), 10.0)  # 9-10

    def detect_conversation_bursts(self, messages: List[ChatMessage]) -> float:
        """
        Detect if messages form a conversation (back-and-forth)

        Indicators:
        - @ mentions
        - Quick replies (<2s between messages)
        - Multiple people responding to same topic

        Returns:
            Conversation score (0.0 - 10.0)
        """
        if len(messages) < 3:
            return 0.0

        # Count @ mentions
        mention_count = sum(1 for m in messages if '@' in m.message)
        mention_ratio = mention_count / len(messages)

        # Count quick replies (<2s between messages)
        quick_replies = 0
        for i in range(1, len(messages)):
            time_diff = messages[i].timestamp - messages[i-1].timestamp
            if time_diff < 2.0:
                quick_replies += 1

        quick_reply_ratio = quick_replies / (len(messages) - 1)

        # Conversation score
        # High @ mentions + quick replies = active conversation
        score = 0.0

        # @ mentions contribute 50%
        if mention_ratio >= 0.3:
            score += 5.0
        elif mention_ratio >= 0.1:
            score += 2.0 + (mention_ratio - 0.1) * 15  # Scale 2-5

        # Quick replies contribute 50%
        if quick_reply_ratio >= 0.5:
            score += 5.0
        elif quick_reply_ratio >= 0.2:
            score += 2.0 + (quick_reply_ratio - 0.2) * 10  # Scale 2-5

        return min(score, 10.0)

    def score_vip_participation(self, messages: List[ChatMessage]) -> float:
        """
        Score based on VIP/Subscriber/Moderator participation

        These are more engaged community members
        Their reactions = higher signal value

        Returns:
            VIP participation score (0.0 - 10.0)
        """
        if not messages:
            return 0.0

        # Calculate weighted message count
        weighted_count = 0.0
        for msg in messages:
            weight = 1.0

            if msg.is_moderator:
                weight = 1.8  # Mods are very engaged
            elif msg.is_vip:
                weight = 1.6
            elif msg.is_subscriber:
                weight = 1.3

            weighted_count += weight

        # Compare weighted vs raw count
        raw_count = len(messages)
        weight_ratio = weighted_count / raw_count

        # Interpretation:
        # 1.0 = no VIPs (all regular users) → 5.0
        # 1.2 = some subs → 6.5
        # 1.4 = many subs/VIPs → 8.0
        # 1.6+ = high VIP engagement → 9-10

        if weight_ratio >= 1.6:
            return 9.0 + min((weight_ratio - 1.6) * 10, 1.0)  # 9-10
        elif weight_ratio >= 1.4:
            return 8.0 + ((weight_ratio - 1.4) / 0.2) * 1.0  # 8-9
        elif weight_ratio >= 1.2:
            return 6.5 + ((weight_ratio - 1.2) / 0.2) * 1.5  # 6.5-8
        elif weight_ratio >= 1.0:
            return 5.0 + ((weight_ratio - 1.0) / 0.2) * 1.5  # 5-6.5
        else:
            return 5.0

    def detect_spam_patterns(self, messages: List[ChatMessage]) -> bool:
        """
        Detect if messages are spam (low engagement value)

        Spam indicators:
        - Same user repeating same message
        - Very short messages (<5 chars)
        - Low diversity (<0.2)

        Returns:
            True if spam detected
        """
        if not messages:
            return False

        # Check diversity
        unique_users = len(set(m.username for m in messages))
        diversity = unique_users / len(messages)

        if diversity < 0.2:
            return True  # Heavy spam from few users

        # Check for repeated messages
        message_texts = [m.message.lower().strip() for m in messages]
        unique_texts = len(set(message_texts))
        text_diversity = unique_texts / len(messages)

        if text_diversity < 0.3:
            return True  # Same messages repeated

        # Check average length
        avg_length = statistics.mean([len(m.message) for m in messages])
        if avg_length < 5:
            return True  # Very short spam

        return False

    def score_composite_engagement(self, messages: List[ChatMessage]) -> float:
        """
        Composite engagement score combining all metrics

        Returns:
            Combined score (0.0 - 10.0)
        """
        if not messages:
            return 0.0

        # Check for spam first
        if self.detect_spam_patterns(messages):
            return 2.0  # Spam = low value

        # Calculate individual scores
        diversity = self.score_chatter_diversity(messages)
        quality = self.score_message_quality(messages)
        conversation = self.detect_conversation_bursts(messages)
        vip_participation = self.score_vip_participation(messages)

        # Weighted combination
        composite = (
            diversity * 0.30 +           # 30% - unique users important
            quality * 0.25 +             # 25% - message length/quality
            conversation * 0.25 +        # 25% - conversation dynamics
            vip_participation * 0.20     # 20% - VIP engagement
        )

        return composite

    def get_engagement_breakdown(self, messages: List[ChatMessage]) -> Dict:
        """
        Get detailed breakdown of engagement metrics

        Returns:
            Dictionary with all scores and stats
        """
        if not messages:
            return {
                'composite': 0.0,
                'diversity': 0.0,
                'quality': 0.0,
                'conversation': 0.0,
                'vip_participation': 0.0,
                'is_spam': False,
                'unique_chatters': 0,
                'total_messages': 0,
                'avg_message_length': 0.0,
            }

        unique_users = len(set(m.username for m in messages))
        avg_length = statistics.mean([len(m.message) for m in messages])

        return {
            'composite': self.score_composite_engagement(messages),
            'diversity': self.score_chatter_diversity(messages),
            'quality': self.score_message_quality(messages),
            'conversation': self.detect_conversation_bursts(messages),
            'vip_participation': self.score_vip_participation(messages),
            'is_spam': self.detect_spam_patterns(messages),
            'unique_chatters': unique_users,
            'total_messages': len(messages),
            'avg_message_length': avg_length,
        }


if __name__ == "__main__":
    # Test engagement scorer
    from chat_analyzer import ChatMessage

    # Test case 1: High engagement conversation
    high_engagement = [
        ChatMessage(10.0, "user1", "Wow that was insane! Did you see that play?", [], platform='twitch'),
        ChatMessage(10.5, "user2", "@user1 Yeah absolutely crazy!", [], platform='twitch'),
        ChatMessage(11.0, "user3", "Best moment of the stream so far", [], platform='twitch'),
        ChatMessage(11.2, "user4", "I can't believe that just happened", [], platform='twitch'),
        ChatMessage(11.8, "user5", "@user1 replay please!", [], is_subscriber=True, platform='twitch'),
    ]

    # Test case 2: Spam
    spam = [
        ChatMessage(20.0, "spammer1", "F", [], platform='twitch'),
        ChatMessage(20.1, "spammer1", "F", [], platform='twitch'),
        ChatMessage(20.2, "spammer2", "F", [], platform='twitch'),
        ChatMessage(20.3, "spammer1", "F", [], platform='twitch'),
        ChatMessage(20.4, "spammer2", "F", [], platform='twitch'),
    ]

    scorer = EngagementScorer()

    print("=== High Engagement Test ===")
    breakdown = scorer.get_engagement_breakdown(high_engagement)
    for key, value in breakdown.items():
        print(f"  {key}: {value}")

    print("\n=== Spam Test ===")
    breakdown = scorer.get_engagement_breakdown(spam)
    for key, value in breakdown.items():
        print(f"  {key}: {value}")
