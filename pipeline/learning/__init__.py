"""
Learning Loop - Automated improvement from YouTube metrics.

Components:
- YouTubeMetricsAPI: Fetch video metrics from YouTube Data API v3
- PerformanceAnalyzer: Calculate performance scores
- LearningLoop: Automated learning system
"""

from .youtube_api import YouTubeMetricsAPI, get_youtube_api
from .performance import PerformanceAnalyzer, analyze_and_update
from .learning_loop import LearningLoop, run_learning_loop

__all__ = [
    'YouTubeMetricsAPI',
    'get_youtube_api',
    'PerformanceAnalyzer',
    'analyze_and_update',
    'LearningLoop',
    'run_learning_loop'
]
