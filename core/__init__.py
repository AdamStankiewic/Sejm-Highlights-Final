"""
Highlights AI Platform - Core Engine

Shared components used by all domain modules:
- Audio processing (extraction, normalization, VAD)
- Transcription (Whisper ASR)
- Feature extraction (acoustic, prosodic, lexical)
- Base pipeline interface
"""

from .pipeline_base import BasePipeline

__all__ = ['BasePipeline']
