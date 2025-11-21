"""Politics Module - Polish Parliamentary Debates (Sejm)"""
from .config import PoliticsConfig
from .scorer import PoliticsScorer
from .pipeline import PoliticsPipeline

__all__ = ['PoliticsConfig', 'PoliticsScorer', 'PoliticsPipeline']
