"""
Context detection for streaming content.

Auto-detects streamer info, content type, and language context from filenames
and provides flexible content classification for any stream type.
"""

import re
from pathlib import Path
from typing import Dict, Optional, List


class ContentType:
    """Content type constants for flexible stream classification."""
    GAMING = "Gaming"
    IRL = "IRL"
    EVENT = "Event/Special"
    JUST_CHATTING = "Just Chatting"
    VARIETY = "Variety/Mixed"


class Language:
    """Supported languages for transcription and content generation."""
    POLISH = "pl"
    ENGLISH = "en"
    GERMAN = "de"

    @classmethod
    def get_name(cls, code: str) -> str:
        """Get full language name from code."""
        names = {
            "pl": "Polski",
            "en": "English",
            "de": "Deutsch"
        }
        return names.get(code, code.upper())

    @classmethod
    def all_codes(cls) -> List[str]:
        """Get all supported language codes."""
        return ["pl", "en", "de"]


def parse_stream_context(
    vod_path: str,
    stream_title: Optional[str] = None
) -> Dict[str, str]:
    """
    Auto-detect stream context from VOD filename.

    Supports multiple filename formats:
    - [date] STREAMER - title.mp4
    - STREAMER_date_title.mp4
    - STREAMER - title.mp4

    Args:
        vod_path: Path to VOD file
        stream_title: Optional override for stream title

    Returns:
        Dictionary with detected context:
        {
            'streamer': str,
            'content_type': str,  # Gaming/IRL/Event/etc
            'activity': str,      # Specific game/activity or empty
            'stream_title': str,
            'language': str,      # Detected or default 'pl'
            'confidence': str     # 'auto', 'default', 'heuristic'
        }
    """
    filename = Path(vod_path).stem

    # Pattern 1: [date] STREAMER - title
    match = re.search(r'\[[\d-]+\]\s*([^-]+?)\s*-\s*(.+)', filename)

    if match:
        streamer = match.group(1).strip()
        title = match.group(2).strip()
    else:
        # Pattern 2: STREAMER - title (without date)
        match = re.search(r'^([^-]+?)\s*-\s*(.+)', filename)
        if match:
            streamer = match.group(1).strip()
            title = match.group(2).strip()
        else:
            # Pattern 3: STREAMER_date_title
            parts = filename.split('_')
            if len(parts) >= 2:
                streamer = parts[0]
                title = '_'.join(parts[1:])
            else:
                streamer = "Unknown"
                title = filename

    # Override title if provided
    if stream_title:
        title = stream_title

    # Detect content type and activity
    content_type, activity = detect_content_type(title)

    # Detect language
    language = detect_language(title, streamer)

    # Determine confidence
    confidence = 'auto' if activity else 'heuristic' if content_type != ContentType.VARIETY else 'default'

    return {
        'streamer': streamer,
        'content_type': content_type,
        'activity': activity,
        'stream_title': title,
        'language': language,
        'confidence': confidence
    }


def detect_content_type(title: str) -> tuple[str, str]:
    """
    Detect content type and specific activity from stream title.

    Args:
        title: Stream title or description

    Returns:
        Tuple of (content_type, activity)
        - content_type: Gaming/IRL/Event/Just Chatting/Variety
        - activity: Specific game/activity name or empty string
    """
    title_lower = title.lower()

    # Gaming detection - popular games
    games = {
        'tarkov': 'Escape from Tarkov',
        'eft': 'Escape from Tarkov',
        'cs2': 'CS2',
        'cs:go': 'CS:GO',
        'csgo': 'CS:GO',
        'counter-strike': 'Counter-Strike',
        'lol': 'League of Legends',
        'league': 'League of Legends',
        'dota': 'Dota 2',
        'valorant': 'Valorant',
        'fortnite': 'Fortnite',
        'minecraft': 'Minecraft',
        'apex': 'Apex Legends',
        'warzone': 'Warzone',
        'cod': 'Call of Duty',
        'gta': 'GTA',
        'rust': 'Rust',
        'wow': 'World of Warcraft',
        'overwatch': 'Overwatch',
        'pubg': 'PUBG',
    }

    for keyword, game_name in games.items():
        if keyword in title_lower:
            return ContentType.GAMING, game_name

    # IRL detection
    irl_keywords = ['irl', 'miasto', 'city', 'wycieczka', 'trip', 'spacer', 'walk',
                    'shopping', 'zakupy', 'podróż', 'travel']
    if any(kw in title_lower for kw in irl_keywords):
        # Extract location if possible
        location = extract_location(title)
        return ContentType.IRL, location

    # Event detection
    event_keywords = ['event', 'charity', 'maraton', 'marathon', 'special',
                      'konkurs', 'contest', 'tournament', 'turniej', 'celebration']
    if any(kw in title_lower for kw in event_keywords):
        return ContentType.EVENT, ''

    # Just Chatting detection
    chat_keywords = ['q&a', 'chatting', 'pogadanki', 'rozmowa', 'talk',
                     'qa', 'pytania', 'questions']
    if any(kw in title_lower for kw in chat_keywords):
        return ContentType.JUST_CHATTING, ''

    # Mixed/Variety indicators
    variety_keywords = ['mixed', 'variety', 'różne', 'multi', 'several']
    if any(kw in title_lower for kw in variety_keywords):
        return ContentType.VARIETY, 'Mixed content'

    # Default to Variety if nothing detected
    return ContentType.VARIETY, ''


def extract_location(text: str) -> str:
    """
    Extract location from IRL stream title.

    Args:
        text: Stream title

    Returns:
        Location name or empty string
    """
    # Common city patterns
    cities = ['warszawa', 'warsaw', 'kraków', 'krakow', 'wrocław', 'wroclaw',
              'gdańsk', 'gdansk', 'poznań', 'poznan', 'łódź', 'lodz',
              'berlin', 'london', 'paris', 'new york', 'tokyo']

    text_lower = text.lower()
    for city in cities:
        if city in text_lower:
            return city.title()

    return ''


def detect_language(title: str, streamer: str = "") -> str:
    """
    Auto-detect likely stream language from title and streamer name.

    Args:
        title: Stream title
        streamer: Streamer name

    Returns:
        Language code ('pl', 'en', 'de') - defaults to 'pl'
    """
    text = f"{title} {streamer}".lower()

    # Polish indicators
    polish_chars = ['ą', 'ć', 'ę', 'ł', 'ń', 'ó', 'ś', 'ź', 'ż']
    if any(char in text for char in polish_chars):
        return Language.POLISH

    polish_words = ['heja', 'cześć', 'gramy', 'stream', 'dzień', 'dobry']
    if any(word in text for word in polish_words):
        return Language.POLISH

    # German indicators
    german_chars = ['ä', 'ö', 'ü', 'ß']
    if any(char in text for char in german_chars):
        return Language.GERMAN

    german_words = ['deutsch', 'german', 'spielen', 'hallo', 'guten']
    if any(word in text for word in german_words):
        return Language.GERMAN

    # English indicators (less specific, so check last)
    english_words = ['playing', 'gaming', 'stream', 'live', 'hello']
    if any(word in text for word in english_words):
        # Only return EN if no Polish indicators
        if not any(word in text for word in polish_words):
            return Language.ENGLISH

    # Default to Polish
    return Language.POLISH


def format_context_summary(context: Dict[str, str]) -> str:
    """
    Format context dictionary as readable summary.

    Args:
        context: Context dictionary from parse_stream_context()

    Returns:
        Formatted string summary
    """
    lines = [
        f"Streamer: {context['streamer']}",
        f"Content Type: {context['content_type']}",
    ]

    if context['activity']:
        lines.append(f"Activity: {context['activity']}")

    lines.extend([
        f"Stream Title: {context['stream_title']}",
        f"Language: {Language.get_name(context['language'])} ({context['language']})",
        f"Detection: {context['confidence']}"
    ])

    return "\n".join(lines)


# Example usage and testing
if __name__ == "__main__":
    # Test cases
    test_files = [
        "[11-24-25] H2P_Gucio - heja.mp4",
        "LVNDMARK - Tarkov Raids Today.mp4",
        "Streamer - IRL Warszawa Shopping.mp4",
        "xQc - Variety Gaming Marathon.mp4",
        "MontanaBlack - CS2 Ranked Grind.mp4",
    ]

    print("🧪 Testing Context Detector\n")

    for filename in test_files:
        print(f"File: {filename}")
        context = parse_stream_context(filename)
        print(format_context_summary(context))
        print("-" * 50)
