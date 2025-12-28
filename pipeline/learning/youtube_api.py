"""
YouTube API Integration - Fetch video metrics for learning loop.
"""
from typing import List, Dict, Optional
import logging
from datetime import datetime, timedelta
import os

try:
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    YOUTUBE_API_AVAILABLE = True
except ImportError:
    YOUTUBE_API_AVAILABLE = False
    logging.warning("google-api-python-client not installed. Run: pip install google-api-python-client")

logger = logging.getLogger(__name__)


class YouTubeMetricsAPI:
    """
    YouTube Data API v3 wrapper for fetching video metrics.

    API Quota Usage (per call):
    - videos.list: 1 unit per request
    - Can batch 50 videos per request
    - Free tier: 10,000 units/day = ~10,000 requests

    Required Scopes: None (public data only)
    """

    def __init__(self, api_key: str = None):
        """
        Args:
            api_key: YouTube Data API v3 key (or set YOUTUBE_API_KEY env var)
        """
        if not YOUTUBE_API_AVAILABLE:
            raise ImportError("google-api-python-client required. Install: pip install google-api-python-client")

        self.api_key = api_key or os.getenv("YOUTUBE_API_KEY")

        if not self.api_key:
            raise ValueError(
                "YouTube API key required. Set YOUTUBE_API_KEY env var or pass api_key.\n"
                "Get key: https://console.cloud.google.com/apis/credentials"
            )

        self.youtube = build('youtube', 'v3', developerKey=self.api_key)
        logger.info("YouTube API client initialized")

    def get_video_metrics(self, video_ids: List[str]) -> Dict[str, Dict]:
        """
        Fetch metrics for multiple videos (batch).

        Args:
            video_ids: List of YouTube video IDs (e.g., ['dQw4w9WgXcQ', ...])
                       Max 50 per request (API limit)

        Returns:
            Dict mapping video_id -> metrics:
            {
                'video_id': {
                    'views': 12345,
                    'likes': 567,
                    'comments': 89,
                    'duration_seconds': 600,
                    'published_at': '2024-01-15T10:00:00Z',
                    'title': 'Video Title',
                    'description': 'Video description...'
                }
            }
        """
        if not video_ids:
            return {}

        # YouTube API limit: 50 videos per request
        if len(video_ids) > 50:
            logger.warning(f"Batching {len(video_ids)} videos into multiple requests")
            results = {}
            for i in range(0, len(video_ids), 50):
                batch = video_ids[i:i+50]
                results.update(self.get_video_metrics(batch))
            return results

        try:
            # Fetch video data
            request = self.youtube.videos().list(
                part='statistics,contentDetails,snippet',
                id=','.join(video_ids)
            )
            response = request.execute()

            metrics = {}

            for item in response.get('items', []):
                video_id = item['id']
                stats = item.get('statistics', {})
                details = item.get('contentDetails', {})
                snippet = item.get('snippet', {})

                # Parse duration (ISO 8601 format: PT1H2M10S)
                duration = self._parse_duration(details.get('duration', 'PT0S'))

                metrics[video_id] = {
                    'views': int(stats.get('viewCount', 0)),
                    'likes': int(stats.get('likeCount', 0)),
                    'comments': int(stats.get('commentCount', 0)),
                    'duration_seconds': duration,
                    'published_at': snippet.get('publishedAt', ''),
                    'title': snippet.get('title', ''),
                    'description': snippet.get('description', '')
                }

            logger.info(f"Fetched metrics for {len(metrics)} videos")
            return metrics

        except HttpError as e:
            logger.error(f"YouTube API error: {e}")
            return {}

    def get_channel_videos(
        self,
        channel_id: str,
        max_results: int = 50,
        published_after: datetime = None
    ) -> List[str]:
        """
        Get recent video IDs from a channel.

        Args:
            channel_id: YouTube channel ID (e.g., 'UCxxxxxx')
            max_results: Max videos to return (1-50)
            published_after: Only videos after this date

        Returns:
            List of video IDs
        """
        try:
            params = {
                'part': 'id',
                'channelId': channel_id,
                'maxResults': min(max_results, 50),
                'order': 'date',
                'type': 'video'
            }

            if published_after:
                params['publishedAfter'] = published_after.isoformat() + 'Z'

            request = self.youtube.search().list(**params)
            response = request.execute()

            video_ids = [
                item['id']['videoId']
                for item in response.get('items', [])
                if item['id']['kind'] == 'youtube#video'
            ]

            logger.info(f"Found {len(video_ids)} videos for channel {channel_id}")
            return video_ids

        except HttpError as e:
            logger.error(f"YouTube API error: {e}")
            return []

    def _parse_duration(self, duration_str: str) -> int:
        """
        Parse ISO 8601 duration to seconds.

        Examples:
            PT1H2M10S → 3730 seconds
            PT5M30S → 330 seconds
            PT45S → 45 seconds
        """
        import re

        pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
        match = re.match(pattern, duration_str)

        if not match:
            return 0

        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)

        return hours * 3600 + minutes * 60 + seconds

    def estimate_ctr(
        self,
        views: int,
        impressions: int = None,
        fallback_rate: float = 0.05
    ) -> float:
        """
        Estimate CTR (Click-Through Rate).

        Note: YouTube Analytics API required for actual CTR.
        This estimates based on typical rates.

        Args:
            views: View count
            impressions: Impression count (if available from Analytics API)
            fallback_rate: Typical CTR for content type

        Returns:
            Estimated CTR (0.0-1.0)
        """
        if impressions and impressions > 0:
            return views / impressions

        # Fallback estimation based on view velocity
        # This is a ROUGH estimate - real CTR requires Analytics API
        return fallback_rate

    def estimate_watch_time(
        self,
        views: int,
        duration_seconds: int,
        retention_rate: float = 0.45
    ) -> int:
        """
        Estimate average watch time.

        Note: YouTube Analytics API required for actual watch time.

        Args:
            views: View count
            duration_seconds: Video duration
            retention_rate: Typical retention (0.4-0.5 for highlights)

        Returns:
            Estimated avg watch time in seconds
        """
        # Typical retention for highlight videos: 40-50%
        return int(duration_seconds * retention_rate)


def get_youtube_api() -> YouTubeMetricsAPI:
    """Get YouTube API client instance"""
    return YouTubeMetricsAPI()
