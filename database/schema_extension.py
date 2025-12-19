"""
Database schema extension for AI metadata caching and learning loop.
This extends the existing uploader/store.py SQLite database.
"""
import sqlite3
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class DatabaseExtension:
    """
    Extends existing SQLite database with new tables for:
    - Video generation cache (avoid regenerating same content)
    - Learned examples (track what works for each streamer)
    - API cost tracking
    """

    def __init__(self, db_path: str = "data/uploader.db"):
        """
        Args:
            db_path: Path to existing SQLite database
        """
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            logger.warning(f"Database {db_path} doesn't exist yet, will be created")
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def extend_schema(self):
        """Add new tables to existing database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            # Table 1: Video Generation Cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS video_generation_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT UNIQUE NOT NULL,
                    streamer_id TEXT NOT NULL,
                    platform TEXT NOT NULL,

                    -- Input hash for deduplication
                    video_facts_hash TEXT NOT NULL,
                    video_facts_json TEXT NOT NULL,

                    -- Stage 1: Context extraction
                    streaming_brief_json TEXT,
                    brief_generated_at TEXT,
                    brief_model TEXT,
                    brief_cost REAL,

                    -- Stage 2: Metadata generation
                    generated_metadata_json TEXT,
                    metadata_generated_at TEXT,
                    metadata_model TEXT,
                    metadata_cost REAL,
                    metadata_examples_used_json TEXT,

                    -- Validation
                    validation_passed INTEGER DEFAULT 1,
                    validation_issues_json TEXT,

                    -- Final metadata (after human edits)
                    final_metadata_json TEXT,
                    published_at TEXT,

                    -- Tracking
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_video_id
                ON video_generation_cache(video_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_facts_hash
                ON video_generation_cache(video_facts_hash)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_streamer_date
                ON video_generation_cache(streamer_id, created_at)
            """)

            # Table 2: Learned Examples (top performing content)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS streamer_learned_examples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    streamer_id TEXT NOT NULL,
                    video_id TEXT NOT NULL,
                    platform TEXT NOT NULL,

                    -- Generated content
                    title TEXT NOT NULL,
                    description TEXT,
                    brief_json TEXT NOT NULL,
                    video_facts_json TEXT NOT NULL,

                    -- Performance metrics
                    views_count INTEGER,
                    ctr_24h REAL,
                    ctr_7d REAL,
                    watch_time_avg INTEGER,
                    likes_ratio REAL,

                    -- Relative performance
                    ctr_vs_avg REAL,
                    watch_time_vs_avg REAL,
                    performance_score REAL,

                    -- Metadata
                    published_at TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    is_active INTEGER DEFAULT 1
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_streamer_performance
                ON streamer_learned_examples(streamer_id, performance_score DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_streamer_active
                ON streamer_learned_examples(streamer_id, is_active)
            """)

            # Table 3: API Cost Tracking
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_cost_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT,
                    streamer_id TEXT,
                    operation TEXT NOT NULL,
                    model TEXT NOT NULL,

                    -- Token usage
                    input_tokens INTEGER,
                    output_tokens INTEGER,

                    -- Cost
                    cost_usd REAL NOT NULL,

                    -- Performance
                    latency_ms INTEGER,

                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_daily_costs
                ON api_cost_tracking(timestamp)
            """)

            conn.commit()
            logger.info("✅ Database schema extended successfully")

        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Failed to extend schema: {e}")
            raise

        finally:
            conn.close()

    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)


def extend_database(db_path: str = "data/uploader.db"):
    """
    Convenience function to extend existing database.
    Safe to call multiple times (uses IF NOT EXISTS).
    """
    ext = DatabaseExtension(db_path)
    ext.extend_schema()


if __name__ == "__main__":
    # Test/initialization script
    import sys

    logging.basicConfig(level=logging.INFO)

    db_path = sys.argv[1] if len(sys.argv) > 1 else "data/uploader.db"

    print(f"Extending database: {db_path}")
    extend_database(db_path)
    print("Done!")
