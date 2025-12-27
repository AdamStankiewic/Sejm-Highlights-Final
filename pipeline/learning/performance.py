"""
Performance Analyzer - Calculate video performance scores for learning loop.
"""
from typing import Dict, List, Optional, Tuple
import logging
from datetime import datetime, timedelta
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


class PerformanceAnalyzer:
    """
    Analyze video performance to identify top-performing content.

    Metrics:
    - CTR (Click-Through Rate) - views/impressions
    - Watch time - avg viewing duration
    - Engagement - likes/views ratio
    - Relative performance - vs channel average

    Performance score formula:
        score = (ctr_vs_avg * 0.4) + (watch_time_vs_avg * 0.3) +
                (engagement_vs_avg * 0.2) + (recency_bonus * 0.1)
    """

    def __init__(self, db_path: str = "data/uploader.db"):
        """
        Args:
            db_path: Path to SQLite database
        """
        self.db_path = Path(db_path)

    def calculate_performance_score(
        self,
        video_metrics: Dict,
        channel_avg: Dict
    ) -> float:
        """
        Calculate performance score for a single video.

        Args:
            video_metrics: Dict with 'views', 'likes', 'duration_seconds', etc.
            channel_avg: Dict with channel averages for comparison

        Returns:
            Performance score (0.0-10.0, higher is better)
        """
        # Extract metrics
        views = video_metrics.get('views', 0)
        likes = video_metrics.get('likes', 0)
        duration = video_metrics.get('duration_seconds', 1)

        if views == 0:
            return 0.0

        # Calculate engagement rate (likes/views)
        engagement_rate = likes / views if views > 0 else 0

        # Estimate CTR (5% baseline for highlights)
        estimated_ctr = 0.05  # Fallback when impressions unavailable

        # Estimate watch time (45% retention for highlights)
        estimated_watch_time = duration * 0.45

        # Get channel averages
        avg_engagement = channel_avg.get('engagement_rate', 0.02)
        avg_ctr = channel_avg.get('ctr', 0.05)
        avg_watch_time = channel_avg.get('watch_time', duration * 0.4)

        # Calculate relative performance (vs channel average)
        engagement_vs_avg = self._safe_ratio(engagement_rate, avg_engagement)
        ctr_vs_avg = self._safe_ratio(estimated_ctr, avg_ctr)
        watch_time_vs_avg = self._safe_ratio(estimated_watch_time, avg_watch_time)

        # Recency bonus (videos from last 30 days get bonus)
        recency_bonus = self._calculate_recency_bonus(
            video_metrics.get('published_at', '')
        )

        # Weighted score
        score = (
            ctr_vs_avg * 0.4 +           # CTR is king (40%)
            watch_time_vs_avg * 0.3 +    # Watch time matters (30%)
            engagement_vs_avg * 0.2 +    # Engagement important (20%)
            recency_bonus * 0.1          # Recent content bonus (10%)
        )

        # Normalize to 0-10 scale
        normalized_score = min(score * 5, 10.0)

        return round(normalized_score, 2)

    def analyze_channel_videos(
        self,
        streamer_id: str,
        video_metrics: Dict[str, Dict]
    ) -> List[Dict]:
        """
        Analyze all videos for a channel and rank by performance.

        Args:
            streamer_id: Streamer identifier
            video_metrics: Dict mapping video_id -> metrics

        Returns:
            List of video performance dicts, sorted by score (descending)
        """
        if not video_metrics:
            logger.warning(f"No video metrics for {streamer_id}")
            return []

        # Calculate channel averages
        channel_avg = self._calculate_channel_averages(video_metrics)

        # Calculate scores for all videos
        performances = []

        for video_id, metrics in video_metrics.items():
            score = self.calculate_performance_score(metrics, channel_avg)

            performances.append({
                'video_id': video_id,
                'title': metrics.get('title', ''),
                'views': metrics.get('views', 0),
                'likes': metrics.get('likes', 0),
                'duration_seconds': metrics.get('duration_seconds', 0),
                'published_at': metrics.get('published_at', ''),
                'performance_score': score,
                'engagement_rate': metrics.get('likes', 0) / max(metrics.get('views', 1), 1)
            })

        # Sort by performance score (descending)
        performances.sort(key=lambda x: x['performance_score'], reverse=True)

        logger.info(f"Analyzed {len(performances)} videos for {streamer_id}")
        logger.info(f"Top score: {performances[0]['performance_score']:.2f}")
        logger.info(f"Channel avg engagement: {channel_avg['engagement_rate']:.4f}")

        return performances

    def get_top_performers(
        self,
        performances: List[Dict],
        top_n: int = 20,
        min_score: float = 5.0
    ) -> List[Dict]:
        """
        Get top N performing videos.

        Args:
            performances: List of video performance dicts
            top_n: Number of top videos to return
            min_score: Minimum performance score threshold

        Returns:
            Top N videos with score >= min_score
        """
        # Filter by minimum score
        qualified = [p for p in performances if p['performance_score'] >= min_score]

        # Take top N
        top_videos = qualified[:top_n]

        logger.info(f"Selected {len(top_videos)} top performers (min_score={min_score})")

        return top_videos

    def update_learned_examples(
        self,
        streamer_id: str,
        top_videos: List[Dict],
        platform: str = "youtube"
    ) -> int:
        """
        Update learned examples table with top performers.

        Args:
            streamer_id: Streamer identifier
            top_videos: List of top-performing video dicts
            platform: Platform (youtube/twitch/kick)

        Returns:
            Number of examples updated
        """
        if not self.db_path.exists():
            logger.error(f"Database not found: {self.db_path}")
            return 0

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            updated_count = 0

            for video in top_videos:
                # Check if this video already has generated metadata in cache
                cursor.execute("""
                    SELECT generated_metadata_json, streaming_brief_json
                    FROM video_generation_cache
                    WHERE video_id LIKE ?
                    AND streamer_id = ?
                    AND generated_metadata_json IS NOT NULL
                """, (f"%{video['video_id']}%", streamer_id))

                result = cursor.fetchone()

                if not result:
                    logger.debug(f"No cached metadata for {video['video_id']}, skipping")
                    continue

                import json
                metadata = json.loads(result[0])
                brief_json = result[1] or "{}"

                # Insert or update learned example
                cursor.execute("""
                    INSERT OR REPLACE INTO streamer_learned_examples (
                        streamer_id,
                        video_id,
                        platform,
                        title,
                        description,
                        brief_json,
                        video_facts_json,
                        views_count,
                        ctr_24h,
                        ctr_7d,
                        watch_time_avg,
                        likes_ratio,
                        ctr_vs_avg,
                        watch_time_vs_avg,
                        performance_score,
                        published_at,
                        created_at,
                        is_active
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    streamer_id,
                    video['video_id'],
                    platform,
                    metadata.get('title', video['title']),
                    metadata.get('description', ''),
                    brief_json,
                    json.dumps(video),
                    video.get('views', 0),
                    None,  # ctr_24h - requires Analytics API
                    None,  # ctr_7d - requires Analytics API
                    None,  # watch_time_avg - requires Analytics API
                    video.get('engagement_rate', 0.0),
                    1.0,   # ctr_vs_avg - placeholder
                    1.0,   # watch_time_vs_avg - placeholder
                    video['performance_score'],
                    video.get('published_at', ''),
                    datetime.now().isoformat(),
                    1  # is_active
                ))

                updated_count += 1

            conn.commit()
            conn.close()

            logger.info(f"✅ Updated {updated_count} learned examples for {streamer_id}")
            return updated_count

        except Exception as e:
            logger.error(f"Failed to update learned examples: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def _calculate_channel_averages(self, video_metrics: Dict[str, Dict]) -> Dict:
        """Calculate channel-wide averages for comparison"""
        if not video_metrics:
            return {
                'engagement_rate': 0.02,
                'ctr': 0.05,
                'watch_time': 0,
                'views': 0
            }

        total_views = 0
        total_likes = 0
        total_duration = 0
        count = 0

        for metrics in video_metrics.values():
            views = metrics.get('views', 0)
            likes = metrics.get('likes', 0)
            duration = metrics.get('duration_seconds', 0)

            total_views += views
            total_likes += likes
            total_duration += duration
            count += 1

        avg_views = total_views / count if count > 0 else 0
        avg_engagement = total_likes / total_views if total_views > 0 else 0.02
        avg_duration = total_duration / count if count > 0 else 0
        avg_watch_time = avg_duration * 0.45  # Typical 45% retention

        return {
            'engagement_rate': avg_engagement,
            'ctr': 0.05,  # Default 5% CTR for highlights
            'watch_time': avg_watch_time,
            'views': avg_views
        }

    def _safe_ratio(self, value: float, baseline: float) -> float:
        """Calculate ratio with safe division"""
        if baseline == 0:
            return 1.0
        ratio = value / baseline
        # Clamp to reasonable range (0.1x - 5x)
        return max(0.1, min(ratio, 5.0))

    def _calculate_recency_bonus(self, published_at: str) -> float:
        """
        Calculate recency bonus (recent videos get higher scores).

        Args:
            published_at: ISO 8601 timestamp

        Returns:
            Bonus multiplier (0.0-2.0)
        """
        if not published_at:
            return 1.0

        try:
            published_date = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
            days_ago = (datetime.now(published_date.tzinfo) - published_date).days

            if days_ago <= 7:
                return 2.0    # Very recent (last week)
            elif days_ago <= 30:
                return 1.5    # Recent (last month)
            elif days_ago <= 90:
                return 1.2    # Somewhat recent (last 3 months)
            else:
                return 1.0    # Older content

        except Exception:
            return 1.0


def analyze_and_update(
    streamer_id: str,
    video_metrics: Dict[str, Dict],
    db_path: str = "data/uploader.db",
    top_n: int = 20,
    min_score: float = 5.0
) -> Tuple[List[Dict], int]:
    """
    Convenience function: Analyze videos and update learned examples.

    Args:
        streamer_id: Streamer identifier
        video_metrics: Dict mapping video_id -> metrics
        db_path: Database path
        top_n: Number of top videos to keep
        min_score: Minimum performance score

    Returns:
        Tuple of (all_performances, updated_count)
    """
    analyzer = PerformanceAnalyzer(db_path)

    # Analyze all videos
    performances = analyzer.analyze_channel_videos(streamer_id, video_metrics)

    # Get top performers
    top_videos = analyzer.get_top_performers(performances, top_n, min_score)

    # Update database
    updated_count = analyzer.update_learned_examples(streamer_id, top_videos)

    return performances, updated_count
