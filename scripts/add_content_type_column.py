#!/usr/bin/env python3
"""
Database migration: Add content_type column

Adds content_type column to video_generation_cache and streamer_learned_examples tables.
"""
import sqlite3
import sys
from pathlib import Path

def migrate_database(db_path: str = "data/uploader.db"):
    """Add content_type columns to database"""

    print(f"Migrating database: {db_path}")

    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        print("   Create it first by running the application")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 1. Add to video_generation_cache
        print("\n1. Adding content_type to video_generation_cache...")
        try:
            cursor.execute("""
                ALTER TABLE video_generation_cache
                ADD COLUMN content_type TEXT DEFAULT 'default'
            """)
            print("   ✅ Column added")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("   ℹ️ Column already exists")
            else:
                raise

        # 2. Add to streamer_learned_examples
        print("\n2. Adding content_type to streamer_learned_examples...")
        try:
            cursor.execute("""
                ALTER TABLE streamer_learned_examples
                ADD COLUMN content_type TEXT DEFAULT 'default'
            """)
            print("   ✅ Column added")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("   ℹ️ Column already exists")
            else:
                raise

        # 3. Commit changes
        conn.commit()
        print("\n✅ Migration complete!")

        # 4. Verify
        print("\nVerifying migration...")
        cursor.execute("PRAGMA table_info(video_generation_cache)")
        cache_columns = [row[1] for row in cursor.fetchall()]

        cursor.execute("PRAGMA table_info(streamer_learned_examples)")
        examples_columns = [row[1] for row in cursor.fetchall()]

        if 'content_type' in cache_columns:
            print("✅ video_generation_cache.content_type exists")
        else:
            print("❌ video_generation_cache.content_type missing!")
            return False

        if 'content_type' in examples_columns:
            print("✅ streamer_learned_examples.content_type exists")
        else:
            print("❌ streamer_learned_examples.content_type missing!")
            return False

        return True

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        conn.close()


if __name__ == "__main__":
    success = migrate_database()
    sys.exit(0 if success else 1)
