"""
Sejm Highlights Pipeline
"""

from .config import Config
from .processor import PipelineProcessor
from .stage_01_ingest import IngestStage
from .stage_02_vad import VADStage
from .stage_03_transcribe import TranscribeStage
from .stage_04_features import FeaturesStage
from .stage_05_scoring_gpt import ScoringStage  # ← POPRAWIONE z stage_05_scoring
from .stage_06_selection import SelectionStage
from .stage_07_export import ExportStage
from .stage_09_youtube import YouTubeStage

__version__ = "1.0.0"

__all__ = [
    'Config',
    'PipelineProcessor',
    'IngestStage',
    'VADStage',
    'TranscribeStage',
    'FeaturesStage',
    'ScoringStage',
    'SelectionStage',
    'ExportStage',
    'YouTubeStage',
]