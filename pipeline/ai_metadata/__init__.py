"""
AI Metadata Generation Module

This module provides AI-powered metadata generation for video content.

Components:
- ContextBuilder: Extracts context from clips
- PromptBuilder: Constructs AI prompts with few-shot learning
- MetadataGenerator: Main orchestration for title/description generation
"""

from .context_builder import ContextBuilder, StreamingBrief
from .prompt_builder import PromptBuilder
from .generator import MetadataGenerator

__all__ = [
    "ContextBuilder",
    "StreamingBrief",
    "PromptBuilder",
    "MetadataGenerator"
]
