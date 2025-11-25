"""
Platform-specific Emote Scorer
Supports: Twitch, YouTube, Kick

Different emotes have different "values" for highlight detection:
- High-value: KEKW, PogChamp (clip-worthy moments)
- Medium-value: Standard reactions
- Low-value: Common spam emotes
"""

from typing import List, Dict
from .chat_analyzer import ChatMessage


# ===== TWITCH EMOTES =====
TWITCH_EMOTE_WEIGHTS = {
    # Top-tier (clip-worthy moments)
    'KEKW': 2.5,
    'LULW': 2.5,
    'OMEGALUL': 3.0,      # Maximum laughter
    'PogChamp': 2.8,      # Peak excitement
    'Pog': 2.5,
    'PogU': 2.5,
    'poggers': 2.3,
    'MonkaS': 2.2,        # Intense tension
    'monkaW': 2.2,
    'MonkaGIGA': 2.5,
    'Jebaited': 2.0,      # Troll moment
    'Kreygasm': 2.0,      # Hype

    # High-value
    'LUL': 2.0,
    'EZ': 1.8,            # Easy win (exciting)
    'POGGERS': 1.8,
    'PauseChamp': 1.7,    # Suspense
    'WidePeepoHappy': 1.6,
    'gachiHYPER': 1.8,
    'Clap': 1.7,
    'Pepega': 1.5,        # Funny fail

    # Medium-value
    'Sadge': 1.3,
    'PepeHands': 1.3,
    'BibleThump': 1.4,    # Emotional
    'FeelsStrongMan': 1.4,
    'FeelsBadMan': 1.2,
    'FeelsGoodMan': 1.3,
    'NotLikeThis': 1.3,
    'ResidentSleeper': 0.6,  # Boring (negative value)
    'MingLee': 1.2,
    'CoolStoryBob': 1.0,

    # Common/Low-value (spam)
    'Kappa': 0.8,
    'KappaHD': 0.8,
    '4Head': 0.9,
    'SeemsGood': 1.0,
    'DansGame': 0.9,
    'TriHard': 0.8,
    'BabyRage': 0.8,
    'PJSalt': 0.8,
    'SwiftRage': 0.9,

    # BTTV/FFZ popular emotes
    'monkaHmm': 1.5,
    'Okayge': 1.2,
    'LULW': 2.3,
    'OMEGADANCE': 1.8,
    'YEP': 1.3,
    'Copege': 1.4,
    'Aware': 1.5,
    'Clueless': 1.6,
}

# ===== YOUTUBE EMOTES (Emoji-based) =====
YOUTUBE_EMOTE_WEIGHTS = {
    # Laughter (high-value)
    '😂': 2.5,
    '🤣': 2.8,
    '💀': 2.3,            # "I'm dead" (funny)

    # Excitement
    '🔥': 2.0,            # Fire/hype
    '⚡': 1.8,
    '💯': 1.9,
    '🎉': 1.7,
    '🎊': 1.7,

    # Love/Support
    '❤️': 1.5,
    '💖': 1.5,
    '💙': 1.4,
    '💚': 1.4,
    '🧡': 1.4,

    # Reactions
    '👏': 1.6,            # Applause
    '🙌': 1.6,
    '👍': 1.2,
    '👌': 1.2,
    '😭': 1.4,            # Crying (funny or emotional)
    '😱': 1.8,            # Shock
    '🤯': 2.0,            # Mind blown
    '😮': 1.7,
    '😲': 1.7,

    # Negative/Low-value
    '😴': 0.5,            # Sleeping (boring)
    '🥱': 0.6,            # Yawning
    '👎': 0.7,
    '😐': 0.8,

    # Meme reactions
    '🗿': 1.3,            # Moai (meme)
    '💩': 0.9,
    '🤡': 1.4,
    '👀': 1.5,            # Eyes (suspense)
}

# ===== KICK EMOTES =====
# Kick uses similar emotes to Twitch, plus some unique ones
KICK_EMOTE_WEIGHTS = {
    # Shared with Twitch (inherit weights)
    **TWITCH_EMOTE_WEIGHTS,

    # Kick-specific emotes
    'kickPog': 2.5,
    'kickLUL': 2.3,
    'kickW': 2.0,
    'kickL': 1.2,
    'kickHype': 2.2,
    'kickClap': 1.7,
    'kickSadge': 1.3,
    'kickDance': 1.8,
}


class EmoteScorer:
    """
    Score chat messages based on emote quality and density
    """

    def __init__(self, platform: str = 'twitch'):
        """
        Initialize emote scorer

        Args:
            platform: 'twitch', 'youtube', or 'kick'
        """
        self.platform = platform.lower()

        # Select appropriate emote weights
        if self.platform == 'youtube':
            self.emote_weights = YOUTUBE_EMOTE_WEIGHTS
        elif self.platform == 'kick':
            self.emote_weights = KICK_EMOTE_WEIGHTS
        else:  # twitch or default
            self.emote_weights = TWITCH_EMOTE_WEIGHTS

    def score_messages(self, messages: List[ChatMessage]) -> float:
        """
        Score a list of messages based on emote quality

        Args:
            messages: List of ChatMessage objects

        Returns:
            Emote quality score (0.0 - 10.0)
        """
        if not messages:
            return 0.0

        total_weight = 0.0
        emote_count = 0

        for msg in messages:
            for emote in msg.emotes:
                weight = self.emote_weights.get(emote, 1.0)
                total_weight += weight
                emote_count += 1

        # No emotes = neutral score (5.0)
        if emote_count == 0:
            return 5.0

        # Calculate average emote weight
        avg_weight = total_weight / emote_count

        # Scale to 0-10
        # avg_weight ranges typically:
        # 0.6-0.9 = spam/low-value → 2-4
        # 1.0-1.5 = normal → 5-6
        # 1.6-2.5 = high-value → 7-9
        # 2.5+ = peak moments → 9-10

        score = 3.0 + (avg_weight * 2.5)  # Maps 0.8→5.0, 2.0→8.0, 3.0→10.5

        # Clamp to 0-10
        return max(0.0, min(10.0, score))

    def score_emote_density(self, messages: List[ChatMessage]) -> float:
        """
        Score based on emote density (how many messages contain emotes)

        Returns:
            Density score (0.0 - 10.0)
        """
        if not messages:
            return 0.0

        messages_with_emotes = sum(1 for m in messages if m.emotes)
        density = messages_with_emotes / len(messages)

        # Scale density:
        # 0.0-0.2 = low emote usage (boring) → 3-5
        # 0.3-0.6 = normal → 5-7
        # 0.7-1.0 = high emote spam (exciting) → 8-10

        if density < 0.2:
            return 3.0 + (density * 10)  # 0→3, 0.2→5
        elif density < 0.6:
            return 5.0 + ((density - 0.2) * 5)  # 0.2→5, 0.6→7
        else:
            return 7.0 + ((density - 0.6) * 7.5)  # 0.6→7, 1.0→10

    def detect_emote_spam(
        self,
        messages: List[ChatMessage],
        threshold: float = 0.7
    ) -> bool:
        """
        Detect if this is an emote spam moment

        Args:
            messages: List of messages
            threshold: Minimum density to consider spam (default 0.7 = 70%)

        Returns:
            True if emote spam detected
        """
        if not messages:
            return False

        messages_with_emotes = sum(1 for m in messages if m.emotes)
        density = messages_with_emotes / len(messages)

        return density >= threshold

    def get_top_emotes(
        self,
        messages: List[ChatMessage],
        top_n: int = 5
    ) -> List[tuple]:
        """
        Get most common emotes in message list

        Returns:
            List of (emote, count, weight) tuples
        """
        emote_counts = {}

        for msg in messages:
            for emote in msg.emotes:
                emote_counts[emote] = emote_counts.get(emote, 0) + 1

        # Sort by count
        sorted_emotes = sorted(
            emote_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # Add weights
        result = [
            (emote, count, self.emote_weights.get(emote, 1.0))
            for emote, count in sorted_emotes[:top_n]
        ]

        return result

    def score_composite(self, messages: List[ChatMessage]) -> float:
        """
        Composite score combining quality and density

        Returns:
            Combined score (0.0 - 10.0)
        """
        quality = self.score_messages(messages)
        density = self.score_emote_density(messages)

        # Weight: 60% quality, 40% density
        return (quality * 0.6) + (density * 0.4)


def get_emote_weight(emote: str, platform: str = 'twitch') -> float:
    """
    Get weight for a specific emote

    Args:
        emote: Emote text/emoji
        platform: Platform name

    Returns:
        Weight value (default 1.0)
    """
    if platform == 'youtube':
        return YOUTUBE_EMOTE_WEIGHTS.get(emote, 1.0)
    elif platform == 'kick':
        return KICK_EMOTE_WEIGHTS.get(emote, 1.0)
    else:
        return TWITCH_EMOTE_WEIGHTS.get(emote, 1.0)


if __name__ == "__main__":
    # Test emote scorer
    from chat_analyzer import ChatMessage

    # Test Twitch
    test_messages = [
        ChatMessage(10.0, "user1", "KEKW KEKW KEKW", ["KEKW", "KEKW", "KEKW"], platform='twitch'),
        ChatMessage(11.0, "user2", "PogChamp moment!", ["PogChamp"], platform='twitch'),
        ChatMessage(12.0, "user3", "OMEGALUL", ["OMEGALUL"], platform='twitch'),
        ChatMessage(13.0, "user4", "Kappa", ["Kappa"], platform='twitch'),
        ChatMessage(14.0, "user5", "normal message", [], platform='twitch'),
    ]

    scorer = EmoteScorer('twitch')
    quality = scorer.score_messages(test_messages)
    density = scorer.score_emote_density(test_messages)
    composite = scorer.score_composite(test_messages)

    print(f"Emote Quality: {quality:.2f}/10")
    print(f"Emote Density: {density:.2f}/10")
    print(f"Composite: {composite:.2f}/10")
    print(f"Is spam? {scorer.detect_emote_spam(test_messages)}")
    print(f"\nTop emotes: {scorer.get_top_emotes(test_messages)}")
