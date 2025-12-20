"""
Learning Loop - Automated improvement from YouTube metrics.

Components:
- YouTubeMetricsAPI: Fetch video metrics from YouTube Data API v3
- PerformanceAnalyzer: Calculate performance scores (coming in Task 3.2)
- LearningLoop: Automated learning system (coming in Task 3.3)
"""

from .youtube_api import YouTubeMetricsAPI, get_youtube_api

__all__ = ['YouTubeMetricsAPI', 'get_youtube_api']
