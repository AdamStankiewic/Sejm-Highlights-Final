"""
Streaming module configuration
Part of Highlights AI Platform - Streaming Module (Twitch/YouTube)
"""
from dataclasses import dataclass, field
from typing import List
from pathlib import Path

from shared.config_base import BaseModuleConfig


@dataclass
class StreamingConfig(BaseModuleConfig):
    """
    Configuration for streaming content analysis.
    Optimized for Twitch/YouTube VOD highlights.
    """

    # Chat analysis weights
    chat_activity_weight: float = 0.40
    emote_density_weight: float = 0.25
    clip_count_weight: float = 0.20
    audio_energy_weight: float = 0.10
    keyword_weight: float = 0.05

    # Chat spike detection - ADAPTIVE (percentile-based)
    chat_spike_percentile: float = 85.0  # Top 15% activity = spike (adaptive!)
    chat_spike_multiplier: float = 1.5   # Fallback: 1.5x baseline (lowered from 3x)
    chat_window_seconds: float = 10.0    # Window for counting messages
    use_percentile_scoring: bool = True  # Use adaptive percentile instead of fixed multiplier

    # Emote detection
    min_emotes_for_bonus: int = 10
    popular_emotes: List[str] = field(default_factory=lambda: [
        # Twitch emotes
        'KEKW', 'LUL', 'LULW', 'PogChamp', 'Pog', 'PogU',
        'OMEGALUL', 'monkaS', 'monkaW', 'Pepega', 'PepeHands',
        'Sadge', 'FeelsBadMan', 'FeelsGoodMan', 'EZ', 'Clap',
        'PauseChamp', 'POGGERS', 'catJAM', 'PepeLaugh',
        # BTTV/FFZ
        'KEKW', 'Pepega', 'FeelsStrongMan', 'widepeepoHappy',
        'peepoClap', 'pepeD', 'HYPERS'
    ])

    # Reaction keywords (streamer or chat reactions)
    reaction_keywords: List[str] = field(default_factory=lambda: [
        'oh my god', 'omg', 'what', 'no way', 'holy', 'wow',
        'bruh', 'dude', 'insane', 'crazy', 'clip it', 'clip that',
        'did you see that', 'lets go', "let's go", 'poggers'
    ])

    # Streamer-specific (optional)
    streamer_name: str = ""
    isolate_streamer_voice: bool = False

    # Selection
    target_duration: float = 600.0  # 10 minutes for streaming highlights
    min_clip_duration: float = 15.0  # Shorter clips for streaming
    max_clip_duration: float = 120.0
    max_clips: int = 20

    # Language (usually English for streaming)
    language: str = "en"
    whisper_model: str = "small"
