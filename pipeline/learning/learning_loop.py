"""
Learning Loop - Automated system for continuous improvement from YouTube metrics.
"""
from typing import Dict, List, Optional
import logging
from datetime import datetime, timedelta
from pathlib import Path
import time

from .youtube_api import YouTubeMetricsAPI
from .performance import PerformanceAnalyzer

logger = logging.getLogger(__name__)


class LearningLoop:
    """
    Automated learning system that continuously improves AI metadata generation.

    Flow:
    1. Fetch recent videos from YouTube channel
    2. Get metrics (views, likes, comments, etc.)
    3. Calculate performance scores
    4. Update learned_examples with top performers
    5. Future AI generations use these proven examples

    Usage:
        loop = LearningLoop(streamer_manager, youtube_api_key)
        loop.run('sejm')  # Update learned examples for Sejm
        loop.run_all()    # Update all streamers
    """

    def __init__(
        self,
        streamer_manager,
        youtube_api_key: str = None,
        db_path: str = "data/uploader.db",
        config: Dict = None
    ):
        """
        Args:
            streamer_manager: StreamerManager instance
            youtube_api_key: YouTube Data API key (or use YOUTUBE_API_KEY env var)
            db_path: Database path
            config: Optional configuration dict
        """
        self.streamer_manager = streamer_manager
        self.db_path = Path(db_path)

        # Initialize components
        self.youtube_api = YouTubeMetricsAPI(api_key=youtube_api_key)
        self.analyzer = PerformanceAnalyzer(db_path=str(db_path))

        # Configuration
        self.config = config or {}
        self.top_n = self.config.get('top_n', 20)
        self.min_score = self.config.get('min_score', 5.0)
        self.max_videos_to_fetch = self.config.get('max_videos', 50)
        self.days_lookback = self.config.get('days_lookback', 30)

        logger.info("LearningLoop initialized")
        logger.info(f"  Config: top_n={self.top_n}, min_score={self.min_score}")

    def run(
        self,
        streamer_id: str,
        platform: str = "youtube",
        force_refresh: bool = False
    ) -> Dict:
        """
        Run learning loop for a single streamer.

        Args:
            streamer_id: Streamer identifier
            platform: Platform (youtube/twitch/kick)
            force_refresh: Force re-fetch even if recently updated

        Returns:
            Dict with results:
            {
                'success': bool,
                'streamer_id': str,
                'videos_analyzed': int,
                'top_performers': int,
                'examples_updated': int,
                'elapsed_seconds': float
            }
        """
        start_time = time.time()

        logger.info(f"\n{'='*60}")
        logger.info(f"LEARNING LOOP: {streamer_id} ({platform})")
        logger.info(f"{'='*60}")

        try:
            # Get streamer profile
            profile = self.streamer_manager.get(streamer_id)
            if not profile:
                logger.error(f"Streamer profile not found: {streamer_id}")
                return self._error_result(streamer_id, "Profile not found")

            # Get channel ID for YouTube
            if platform == "youtube":
                channel_id = profile.platforms.get('youtube', {}).channel_id
                if not channel_id:
                    logger.error(f"No YouTube channel_id for {streamer_id}")
                    return self._error_result(streamer_id, "No YouTube channel")
            else:
                logger.warning(f"Platform {platform} not yet supported, using YouTube")
                channel_id = profile.platforms.get('youtube', {}).channel_id

            # Fetch recent videos
            logger.info(f"📥 Fetching recent videos from channel: {channel_id}")
            published_after = datetime.now() - timedelta(days=self.days_lookback)

            video_ids = self.youtube_api.get_channel_videos(
                channel_id,
                max_results=self.max_videos_to_fetch,
                published_after=published_after
            )

            if not video_ids:
                logger.warning(f"No recent videos found for {streamer_id}")
                return self._success_result(streamer_id, 0, 0, 0, time.time() - start_time)

            logger.info(f"Found {len(video_ids)} recent videos")

            # Fetch metrics for videos
            logger.info(f"📊 Fetching metrics for {len(video_ids)} videos...")
            video_metrics = self.youtube_api.get_video_metrics(video_ids)

            if not video_metrics:
                logger.error(f"Failed to fetch video metrics")
                return self._error_result(streamer_id, "Metrics fetch failed")

            logger.info(f"Got metrics for {len(video_metrics)} videos")

            # Analyze performance
            logger.info(f"🔍 Analyzing video performance...")
            performances = self.analyzer.analyze_channel_videos(
                streamer_id,
                video_metrics
            )

            # Get top performers
            top_videos = self.analyzer.get_top_performers(
                performances,
                top_n=self.top_n,
                min_score=self.min_score
            )

            logger.info(f"🏆 Selected {len(top_videos)} top performers")

            # Display top 5
            logger.info(f"\n  Top 5 performers:")
            for i, video in enumerate(top_videos[:5], 1):
                logger.info(f"  {i}. {video['title'][:50]}... (score: {video['performance_score']:.2f})")

            # Update learned examples
            logger.info(f"\n💾 Updating learned examples...")
            updated_count = self.analyzer.update_learned_examples(
                streamer_id,
                top_videos,
                platform=platform
            )

            # Calculate elapsed time
            elapsed = time.time() - start_time

            logger.info(f"\n✅ Learning loop complete!")
            logger.info(f"  Videos analyzed: {len(performances)}")
            logger.info(f"  Top performers: {len(top_videos)}")
            logger.info(f"  Examples updated: {updated_count}")
            logger.info(f"  Elapsed time: {elapsed:.1f}s")

            return self._success_result(
                streamer_id,
                len(performances),
                len(top_videos),
                updated_count,
                elapsed
            )

        except Exception as e:
            logger.error(f"❌ Learning loop failed for {streamer_id}: {e}")
            import traceback
            traceback.print_exc()
            return self._error_result(streamer_id, str(e))

    def run_all(self) -> List[Dict]:
        """
        Run learning loop for all streamers with YouTube channels.

        Returns:
            List of result dicts for each streamer
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"LEARNING LOOP: Running for all streamers")
        logger.info(f"{'='*60}")

        profiles = self.streamer_manager.list_all()
        results = []

        for profile in profiles:
            # Skip if no YouTube channel
            if 'youtube' not in profile.platforms:
                logger.info(f"Skipping {profile.streamer_id} (no YouTube channel)")
                continue

            # Run learning loop
            result = self.run(profile.streamer_id, platform='youtube')
            results.append(result)

            # Brief pause between API calls (respect rate limits)
            time.sleep(1)

        # Summary
        logger.info(f"\n{'='*60}")
        logger.info(f"ALL STREAMERS COMPLETE")
        logger.info(f"{'='*60}")

        successful = sum(1 for r in results if r['success'])
        total_videos = sum(r.get('videos_analyzed', 0) for r in results)
        total_examples = sum(r.get('examples_updated', 0) for r in results)

        logger.info(f"  Streamers processed: {successful}/{len(results)}")
        logger.info(f"  Total videos analyzed: {total_videos}")
        logger.info(f"  Total examples updated: {total_examples}")

        return results

    def get_learning_stats(self, streamer_id: str) -> Dict:
        """
        Get learning statistics for a streamer.

        Args:
            streamer_id: Streamer identifier

        Returns:
            Dict with stats:
            {
                'total_learned_examples': int,
                'avg_performance_score': float,
                'top_example': {...},
                'last_updated': str
            }
        """
        import sqlite3
        import json

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Get learned examples
            cursor.execute("""
                SELECT COUNT(*), AVG(performance_score), MAX(updated_at)
                FROM streamer_learned_examples
                WHERE streamer_id = ? AND is_active = 1
            """, (streamer_id,))

            count, avg_score, last_updated = cursor.fetchone()

            # Get top example
            cursor.execute("""
                SELECT title, performance_score, views_count, published_at
                FROM streamer_learned_examples
                WHERE streamer_id = ? AND is_active = 1
                ORDER BY performance_score DESC
                LIMIT 1
            """, (streamer_id,))

            top_result = cursor.fetchone()

            conn.close()

            stats = {
                'total_learned_examples': count or 0,
                'avg_performance_score': round(avg_score or 0.0, 2),
                'last_updated': last_updated or 'Never'
            }

            if top_result:
                stats['top_example'] = {
                    'title': top_result[0],
                    'score': round(top_result[1], 2),
                    'views': top_result[2],
                    'published_at': top_result[3]
                }

            return stats

        except Exception as e:
            logger.error(f"Failed to get stats for {streamer_id}: {e}")
            return {
                'total_learned_examples': 0,
                'avg_performance_score': 0.0,
                'last_updated': 'Error'
            }

    def _success_result(
        self,
        streamer_id: str,
        videos_analyzed: int,
        top_performers: int,
        examples_updated: int,
        elapsed_seconds: float
    ) -> Dict:
        """Create success result dict"""
        return {
            'success': True,
            'streamer_id': streamer_id,
            'videos_analyzed': videos_analyzed,
            'top_performers': top_performers,
            'examples_updated': examples_updated,
            'elapsed_seconds': round(elapsed_seconds, 1)
        }

    def _error_result(self, streamer_id: str, error: str) -> Dict:
        """Create error result dict"""
        return {
            'success': False,
            'streamer_id': streamer_id,
            'error': error,
            'videos_analyzed': 0,
            'top_performers': 0,
            'examples_updated': 0,
            'elapsed_seconds': 0
        }


def run_learning_loop(
    streamer_id: str = None,
    youtube_api_key: str = None,
    db_path: str = "data/uploader.db",
    top_n: int = 20,
    min_score: float = 5.0
) -> List[Dict]:
    """
    Convenience function: Run learning loop.

    Args:
        streamer_id: Specific streamer (or None for all)
        youtube_api_key: YouTube API key
        db_path: Database path
        top_n: Top N videos to keep
        min_score: Minimum performance score

    Returns:
        List of result dicts
    """
    from pipeline.streamers import get_manager

    manager = get_manager()

    config = {
        'top_n': top_n,
        'min_score': min_score
    }

    loop = LearningLoop(manager, youtube_api_key, db_path, config)

    if streamer_id:
        return [loop.run(streamer_id)]
    else:
        return loop.run_all()
