"""
Learning Loop - Automated improvement from YouTube metrics.

Components:
- YouTubeMetricsAPI: Fetch video metrics from YouTube Data API v3
- PerformanceAnalyzer: Calculate performance scores
- LearningLoop: Automated learning system (coming in Task 3.3)
"""

from .youtube_api import YouTubeMetricsAPI, get_youtube_api
from .performance import PerformanceAnalyzer, analyze_and_update

__all__ = [
    'YouTubeMetricsAPI',
    'get_youtube_api',
    'PerformanceAnalyzer',
    'analyze_and_update'
]
