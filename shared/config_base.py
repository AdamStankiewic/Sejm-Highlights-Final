"""
Base configuration that all modules extend
Part of Highlights AI Platform - Shared
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class BaseModuleConfig:
    """
    Base configuration with common settings for all modules.

    All domain-specific configs (PoliticsConfig, StreamingConfig)
    should extend this base class.
    """

    # Audio processing
    sample_rate: int = 16000
    channels: int = 1
    target_loudness: float = -16.0

    # VAD
    vad_threshold: float = 0.5
    min_speech_duration: float = 0.5
    min_silence_duration: float = 0.3
    max_segment_duration: float = 180.0

    # ASR (Whisper)
    whisper_model: str = "small"
    language: str = "pl"
    beam_size: int = 5
    temperature: float = 0.0
    initial_prompt: str = ""

    # Selection
    target_duration: float = 900.0  # 15 minutes
    min_clip_duration: float = 90.0
    max_clip_duration: float = 180.0
    max_clips: int = 15

    # Export
    video_codec: str = "libx264"
    crf: int = 21
    audio_bitrate: str = "128k"

    # Hardware
    use_gpu: bool = True

    # Directories
    output_dir: Path = field(default_factory=lambda: Path("output"))
    temp_dir: Path = field(default_factory=lambda: Path("temp"))

    def __post_init__(self):
        """Ensure paths are Path objects"""
        if isinstance(self.output_dir, str):
            self.output_dir = Path(self.output_dir)
        if isinstance(self.temp_dir, str):
            self.temp_dir = Path(self.temp_dir)


@dataclass
class SelectionConfig:
    """Configuration for clip selection"""
    target_duration: float = 900.0
    min_clip_duration: float = 90.0
    max_clip_duration: float = 180.0
    max_clips: int = 15
    score_threshold: float = 0.3


@dataclass
class ExportConfig:
    """Configuration for video export"""
    video_codec: str = "libx264"
    crf: int = 21
    audio_bitrate: str = "128k"
    subtitle_style: str = "yellow"
    add_intro: bool = False
    add_outro: bool = False
