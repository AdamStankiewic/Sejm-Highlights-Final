# Content Type Support - Implementation Guide

## Overview

This document provides step-by-step implementation for adding content type support to the system.

---

## Phase 1: Database Migration

### Step 1.1: Create Migration Script

**File**: `database/migration_content_type.py`

```python
#!/usr/bin/env python3
"""
Database migration: Add content_type support

Adds content_type column to video_generation_cache and streamer_learned_examples
"""
import sqlite3
import sys
from pathlib import Path

def migrate_database(db_path: str = "data/uploader.db"):
    """Add content_type columns to database"""

    print(f"Migrating database: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 1. Add content_type to video_generation_cache
        print("\n1. Adding content_type to video_generation_cache...")
        cursor.execute("""
            ALTER TABLE video_generation_cache
            ADD COLUMN content_type TEXT DEFAULT 'default'
        """)
        print("   ✅ Column added")

        # 2. Add content_type to streamer_learned_examples
        print("\n2. Adding content_type to streamer_learned_examples...")
        cursor.execute("""
            ALTER TABLE streamer_learned_examples
            ADD COLUMN content_type TEXT DEFAULT 'default'
        """)
        print("   ✅ Column added")

        # 3. Create index for performance
        print("\n3. Creating index...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_learned_examples_content_type
            ON streamer_learned_examples(streamer_id, content_type, is_active, performance_score DESC)
        """)
        print("   ✅ Index created")

        # 4. Commit changes
        conn.commit()
        print("\n✅ Migration complete!")

        # 5. Verify
        print("\nVerifying migration...")
        cursor.execute("PRAGMA table_info(video_generation_cache)")
        cache_columns = [row[1] for row in cursor.fetchall()]

        cursor.execute("PRAGMA table_info(streamer_learned_examples)")
        examples_columns = [row[1] for row in cursor.fetchall()]

        if 'content_type' in cache_columns and 'content_type' in examples_columns:
            print("✅ Verification passed: content_type column exists in both tables")
            return True
        else:
            print("❌ Verification failed: content_type column missing")
            return False

    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("⚠️ Column already exists (migration already applied)")
            return True
        else:
            print(f"❌ Migration failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    finally:
        conn.close()

def rollback_migration(db_path: str = "data/uploader.db"):
    """
    Rollback migration (SQLite doesn't support DROP COLUMN easily)

    Note: This requires recreating tables without content_type column.
    Only use if absolutely necessary.
    """
    print("⚠️ Rollback not supported for SQLite ALTER TABLE")
    print("   To rollback: restore from backup or set content_type to 'default'")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate database for content type support")
    parser.add_argument("--db", default="data/uploader.db", help="Database path")
    parser.add_argument("--rollback", action="store_true", help="Rollback migration (not supported)")

    args = parser.parse_args()

    if args.rollback:
        rollback_migration(args.db)
    else:
        success = migrate_database(args.db)
        sys.exit(0 if success else 1)
```

**Usage:**
```bash
# Run migration
python database/migration_content_type.py

# Specify custom database path
python database/migration_content_type.py --db data/uploader.db
```

---

## Phase 2: Content Type Classifier

### Step 2.1: Create Classifier Module

**File**: `pipeline/ai_metadata/content_classifier.py`

```python
"""
Content Type Classifier

Auto-detects content type from video metadata (title, description, etc.)
Uses keyword-based heuristics and streamer-specific rules.
"""
from typing import Dict, List, Optional
import re
import logging
from pathlib import Path
import yaml

logger = logging.getLogger(__name__)


class ContentTypeClassifier:
    """
    Classifies video content into types based on metadata.

    Uses streamer-specific rules defined in profiles or fallback heuristics.

    Examples:
        classifier = ContentTypeClassifier()
        content_type = classifier.classify("sejm", "Posiedzenie Sejmu - debata o budżecie", "...")
        # Returns: "sejm_meeting"
    """

    def __init__(self, profiles_dir: str = "pipeline/streamers/profiles"):
        """
        Args:
            profiles_dir: Directory containing streamer profile YAML files
        """
        self.profiles_dir = Path(profiles_dir)
        self._rules_cache = {}

    def classify(
        self,
        streamer_id: str,
        title: str,
        description: str = "",
        manual_override: str = None
    ) -> str:
        """
        Classify content type from video metadata.

        Args:
            streamer_id: Streamer identifier
            title: Video title
            description: Video description (optional)
            manual_override: Manual content type override (optional)

        Returns:
            Content type string (e.g., "sejm_meeting", "stream_gaming", "default")
        """
        # Manual override takes precedence
        if manual_override:
            logger.info(f"Using manual content type override: {manual_override}")
            return manual_override

        # Load streamer-specific rules
        rules = self._load_rules(streamer_id)

        # Try to match against rules
        if rules:
            content_type = self._match_rules(title, description, rules)
            if content_type:
                logger.debug(f"Matched content type '{content_type}' for '{title[:50]}...'")
                return content_type

        # Fallback to built-in heuristics
        content_type = self._fallback_heuristics(streamer_id, title, description)
        logger.debug(f"Fallback content type '{content_type}' for '{title[:50]}...'")
        return content_type

    def _load_rules(self, streamer_id: str) -> Optional[List[Dict]]:
        """Load content type rules from streamer profile"""

        # Check cache
        if streamer_id in self._rules_cache:
            return self._rules_cache[streamer_id]

        # Load profile
        profile_path = self.profiles_dir / f"{streamer_id}.yaml"
        if not profile_path.exists():
            logger.debug(f"No profile found for {streamer_id}")
            self._rules_cache[streamer_id] = None
            return None

        try:
            with open(profile_path, 'r', encoding='utf-8') as f:
                profile = yaml.safe_load(f)

            # Extract content_types rules
            rules = profile.get('content_types', [])
            self._rules_cache[streamer_id] = rules if rules else None
            return self._rules_cache[streamer_id]

        except Exception as e:
            logger.warning(f"Failed to load rules for {streamer_id}: {e}")
            self._rules_cache[streamer_id] = None
            return None

    def _match_rules(self, title: str, description: str, rules: List[Dict]) -> Optional[str]:
        """Match title/description against content type rules"""

        title_lower = title.lower()
        desc_lower = description.lower()

        # Try each rule in order (first match wins)
        for rule in rules:
            content_type = rule.get('type')
            keywords = rule.get('keywords', [])

            # Check if any keyword matches
            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in title_lower or keyword_lower in desc_lower:
                    return content_type

        return None

    def _fallback_heuristics(self, streamer_id: str, title: str, description: str) -> str:
        """Built-in fallback heuristics for common cases"""

        title_lower = title.lower()
        desc_lower = description.lower()

        # Sejm-specific heuristics
        if streamer_id == "sejm":
            if any(kw in title_lower for kw in ["posiedzenie", "obrady sejmu"]):
                return "sejm_meeting"
            elif any(kw in title_lower for kw in ["konferencja prasowa"]):
                return "sejm_press_conference"
            elif any(kw in title_lower for kw in ["briefing", "komunikat"]):
                return "sejm_briefing"
            elif any(kw in title_lower for kw in ["komisja", "posiedzenie komisji"]):
                return "sejm_committee"
            elif any(kw in title_lower for kw in ["wystąpienie", "przemówienie"]):
                return "sejm_speech"
            else:
                return "sejm_other"

        # Gaming streamer heuristics
        elif streamer_id in ["asmongold", "pokimane", "shroud", "xqc"]:
            if any(kw in title_lower for kw in ["irl", "just chatting", "talking", "reacts"]):
                return "stream_irl"
            else:
                return "stream_gaming"

        # Default
        return "default"

    def get_available_types(self, streamer_id: str) -> List[str]:
        """Get list of available content types for a streamer"""

        rules = self._load_rules(streamer_id)
        if rules:
            return [rule['type'] for rule in rules]

        # Fallback types
        if streamer_id == "sejm":
            return [
                "sejm_meeting",
                "sejm_press_conference",
                "sejm_briefing",
                "sejm_committee",
                "sejm_speech",
                "sejm_other"
            ]
        else:
            return ["default"]


# Convenience function
def classify_content(
    streamer_id: str,
    title: str,
    description: str = "",
    manual_override: str = None
) -> str:
    """
    Quick content type classification.

    Args:
        streamer_id: Streamer ID
        title: Video title
        description: Video description
        manual_override: Manual override

    Returns:
        Content type string
    """
    classifier = ContentTypeClassifier()
    return classifier.classify(streamer_id, title, description, manual_override)
```

### Step 2.2: Unit Tests for Classifier

**File**: `tests/test_content_classifier.py`

```python
#!/usr/bin/env python3
"""
Test suite for Content Type Classifier
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from pipeline.ai_metadata.content_classifier import ContentTypeClassifier


def test_sejm_meeting():
    """Test Sejm meeting detection"""
    print("\nTEST 1: Sejm Meeting Detection")

    classifier = ContentTypeClassifier()

    test_cases = [
        ("Posiedzenie Sejmu - debata o budżecie", "sejm_meeting"),
        ("Obrady Sejmu RP - 15 stycznia 2024", "sejm_meeting"),
        ("POSIEDZENIE SEJMU: Ustawa o ochronie środowiska", "sejm_meeting"),
    ]

    for title, expected in test_cases:
        result = classifier.classify("sejm", title, "")
        status = "✅" if result == expected else "❌"
        print(f"{status} '{title[:40]}...' → {result} (expected: {expected})")
        if result != expected:
            return False

    return True


def test_sejm_press_conference():
    """Test press conference detection"""
    print("\nTEST 2: Press Conference Detection")

    classifier = ContentTypeClassifier()

    test_cases = [
        ("Konferencja prasowa premier Morawieckiego", "sejm_press_conference"),
        ("KONFERENCJA PRASOWA: Nowe obostrzenia", "sejm_press_conference"),
    ]

    for title, expected in test_cases:
        result = classifier.classify("sejm", title, "")
        status = "✅" if result == expected else "❌"
        print(f"{status} '{title[:40]}...' → {result} (expected: {expected})")
        if result != expected:
            return False

    return True


def test_sejm_briefing():
    """Test briefing detection"""
    print("\nTEST 3: Briefing Detection")

    classifier = ContentTypeClassifier()

    test_cases = [
        ("Briefing po spotkaniu z prezydentem", "sejm_briefing"),
        ("Komunikat prasowy - nowe przepisy", "sejm_briefing"),
    ]

    for title, expected in test_cases:
        result = classifier.classify("sejm", title, "")
        status = "✅" if result == expected else "❌"
        print(f"{status} '{title[:40]}...' → {result} (expected: {expected})")
        if result != expected:
            return False

    return True


def test_manual_override():
    """Test manual override functionality"""
    print("\nTEST 4: Manual Override")

    classifier = ContentTypeClassifier()

    # Even though title suggests meeting, override should win
    result = classifier.classify(
        "sejm",
        "Posiedzenie Sejmu",
        "",
        manual_override="sejm_press_conference"
    )

    if result == "sejm_press_conference":
        print(f"✅ Manual override works: {result}")
        return True
    else:
        print(f"❌ Manual override failed: {result}")
        return False


def test_available_types():
    """Test getting available content types"""
    print("\nTEST 5: Available Types")

    classifier = ContentTypeClassifier()
    types = classifier.get_available_types("sejm")

    expected_types = [
        "sejm_meeting",
        "sejm_press_conference",
        "sejm_briefing",
        "sejm_committee",
        "sejm_speech",
        "sejm_other"
    ]

    for t in expected_types:
        if t in types:
            print(f"✅ {t}")
        else:
            print(f"❌ Missing: {t}")
            return False

    return True


def main():
    """Run all tests"""
    print("=" * 60)
    print("CONTENT TYPE CLASSIFIER - TEST SUITE")
    print("=" * 60)

    results = {
        "Sejm Meeting": test_sejm_meeting(),
        "Press Conference": test_sejm_press_conference(),
        "Briefing": test_sejm_briefing(),
        "Manual Override": test_manual_override(),
        "Available Types": test_available_types(),
    }

    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:20s}: {status}")

    all_passed = all(results.values())

    if all_passed:
        print("\n✅ ALL TESTS PASSED")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

---

## Phase 3: Update Streamer Profiles

### Step 3.1: Extend Sejm Profile

**File**: `pipeline/streamers/profiles/sejm.yaml` (add content_types section)

```yaml
streamer_id: sejm
display_name: "Kancelaria Sejmu"
language: pl

# Content type definitions for Sejm channel
content_types:
  - type: "sejm_meeting"
    display_name: "Posiedzenie Sejmu"
    keywords:
      - "posiedzenie"
      - "obrady sejmu"
      - "obrady"
    title_patterns:
      - "Posiedzenie Sejmu - {topic}"
      - "{day} posiedzenie Sejmu - {topic}"
    performance_thresholds:
      min_views: 50000
      min_score: 6.0

  - type: "sejm_press_conference"
    display_name: "Konferencja prasowa"
    keywords:
      - "konferencja prasowa"
      - "konferencja"
    title_patterns:
      - "Konferencja prasowa - {speaker}"
      - "{speaker}: {topic}"
    performance_thresholds:
      min_views: 30000
      min_score: 5.5

  - type: "sejm_briefing"
    display_name: "Briefing"
    keywords:
      - "briefing"
      - "komunikat"
    title_patterns:
      - "Briefing - {topic}"
      - "Komunikat: {topic}"
    performance_thresholds:
      min_views: 20000
      min_score: 5.0

  - type: "sejm_committee"
    display_name: "Posiedzenie komisji"
    keywords:
      - "komisja"
      - "posiedzenie komisji"
    title_patterns:
      - "Komisja {name} - {topic}"
    performance_thresholds:
      min_views: 15000
      min_score: 4.5

  - type: "sejm_speech"
    display_name: "Wystąpienie"
    keywords:
      - "wystąpienie"
      - "przemówienie"
    title_patterns:
      - "Wystąpienie {speaker} - {topic}"
    performance_thresholds:
      min_views: 25000
      min_score: 5.5

  - type: "sejm_other"
    display_name: "Inne"
    keywords: []
    performance_thresholds:
      min_views: 10000
      min_score: 4.0

platforms:
  youtube:
    channel_id: "UCWd8gHV5Qt-bBa4dI98cS0Q"
    channel_name: "Kancelaria Sejmu"

seed_examples:
  - video_id: "example1"
    title: "Posiedzenie Sejmu - debata o budżecie państwa"
    description: "Transmisja obrad Sejmu RP..."
    content_type: "sejm_meeting"  # NEW field
    video_type: "long"
    performance_notes: "High engagement on budget debates"

  - video_id: "example2"
    title: "Konferencja prasowa premier Morawieckiego"
    description: "Premier przedstawia..."
    content_type: "sejm_press_conference"  # NEW field
    video_type: "long"
    performance_notes: "Press conferences get good CTR"
```

---

## Phase 4: Update Learning Loop

### Step 4.1: Modify PerformanceAnalyzer

**File**: `pipeline/learning/performance.py` (modifications)

```python
# Add content_type parameter to update_learned_examples

def update_learned_examples(
    self,
    streamer_id: str,
    top_videos: List[Dict],
    platform: str = "youtube",
    content_type: str = None  # NEW parameter
) -> int:
    """
    Update learned examples in database with top performers.

    Args:
        streamer_id: Streamer ID
        top_videos: List of top performing videos
        platform: Platform (youtube/twitch/kick)
        content_type: Optional content type for all videos

    Returns:
        Number of examples updated
    """
    # ... existing code ...

    for video in top_videos:
        cursor.execute("""
            INSERT INTO streamer_learned_examples (
                streamer_id,
                platform,
                video_id,
                title,
                description,
                video_type,
                content_type,  -- NEW column
                views_count,
                likes_count,
                engagement_rate,
                performance_score,
                published_at,
                updated_at,
                is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 1)
            ON CONFLICT(streamer_id, platform, video_id) DO UPDATE SET
                views_count = excluded.views_count,
                performance_score = excluded.performance_score,
                content_type = excluded.content_type,  -- NEW
                updated_at = CURRENT_TIMESTAMP
        """, (
            streamer_id,
            platform,
            video['video_id'],
            video['title'],
            video.get('description', ''),
            video.get('video_type', 'long'),
            video.get('content_type', content_type or 'default'),  -- NEW
            video['views'],
            video.get('likes', 0),
            video.get('engagement_rate', 0.0),
            video['performance_score'],
            video.get('published_at', '')
        ))

    # ... rest of code ...
```

### Step 4.2: Modify LearningLoop

**File**: `pipeline/learning/learning_loop.py` (modifications)

```python
from .youtube_api import YouTubeMetricsAPI
from .performance import PerformanceAnalyzer
from pipeline.ai_metadata.content_classifier import ContentTypeClassifier  # NEW import

class LearningLoop:
    def __init__(self, ...):
        # ... existing code ...
        self.classifier = ContentTypeClassifier()  # NEW: Initialize classifier

    def run(
        self,
        streamer_id: str,
        platform: str = "youtube",
        content_type: str = None,  # NEW: Optional content type filter
        force_refresh: bool = False
    ) -> Dict:
        """
        Run learning loop for a single streamer.

        Args:
            streamer_id: Streamer identifier
            platform: Platform (youtube/twitch/kick)
            content_type: Optional content type filter (e.g., "sejm_meeting")
            force_refresh: Force re-fetch even if recently updated
        """
        # ... existing fetch code ...

        # NEW: Classify content types for all videos
        logger.info(f"🏷️ Classifying content types...")
        for video_id, metrics in video_metrics.items():
            detected_type = self.classifier.classify(
                streamer_id,
                metrics.get('title', ''),
                metrics.get('description', '')
            )
            metrics['content_type'] = detected_type

        # NEW: Filter by content type if specified
        if content_type:
            logger.info(f"🔍 Filtering for content_type: {content_type}")
            video_metrics = {
                vid: m for vid, m in video_metrics.items()
                if m.get('content_type') == content_type
            }
            logger.info(f"   Remaining videos: {len(video_metrics)}")

        # Show content type distribution
        from collections import Counter
        type_counts = Counter(m.get('content_type', 'unknown') for m in video_metrics.values())
        logger.info(f"📊 Content type distribution:")
        for ctype, count in type_counts.most_common():
            logger.info(f"   {ctype}: {count} videos")

        # ... existing analysis code ...

        # Update learned examples with content types
        logger.info(f"💾 Updating learned examples...")
        updated_count = self.analyzer.update_learned_examples(
            streamer_id,
            top_videos,
            platform=platform,
            content_type=None  # Don't force - use individual video content_types
        )

        # ... rest of code ...
```

---

## Phase 5: Update Metadata Generator

### Step 5.1: Modify MetadataGenerator

**File**: `pipeline/ai_metadata/generator.py` (modifications)

```python
from .content_classifier import ContentTypeClassifier  # NEW import

class MetadataGenerator:
    def __init__(self, ...):
        # ... existing code ...
        self.classifier = ContentTypeClassifier()  # NEW

    def generate_metadata(
        self,
        clips: List,
        streamer_id: str,
        platform: str = "youtube",
        video_type: str = "long",
        language: str = None,
        content_type: str = None,  # NEW parameter
        force_regenerate: bool = False
    ) -> Dict:
        """
        Generate AI-powered title and description.

        Args:
            clips: List of video clips
            streamer_id: Streamer ID
            platform: Platform (youtube/twitch/kick)
            video_type: Video type (long/short/clip)
            language: Language override
            content_type: Content type (e.g., "sejm_meeting") - auto-detected if None
            force_regenerate: Skip cache
        """
        # ... existing context building code ...

        # NEW: Detect content type if not provided
        if not content_type:
            # Try to detect from video facts/brief
            title_hint = brief.get('suggested_title', '')
            desc_hint = brief.get('key_topics', [''])[0] if brief.get('key_topics') else ''

            content_type = self.classifier.classify(
                streamer_id,
                title_hint,
                desc_hint
            )
            logger.info(f"Auto-detected content type: {content_type}")

        # Store content type in brief for logging
        brief['content_type'] = content_type

        # Get few-shot examples filtered by content type
        examples = self._get_few_shot_examples(
            streamer_id,
            platform,
            content_type=content_type  # NEW parameter
        )

        logger.info(f"Using {len(examples)} few-shot examples for content_type='{content_type}'")

        # ... rest of generation code ...

        # Store content_type in cache
        self._cache_metadata(
            video_facts,
            facts_hash,
            brief,
            metadata,
            streamer_id,
            platform,
            content_type=content_type  # NEW
        )

    def _get_few_shot_examples(
        self,
        streamer_id: str,
        platform: str,
        content_type: str = None,  # NEW parameter
        limit: int = 5
    ) -> List[Dict]:
        """Get learned examples, optionally filtered by content type"""

        # ... existing code ...

        # Build query with optional content_type filter
        query = """
            SELECT video_id, title, description, video_type, content_type,
                   views_count, likes_count, performance_score
            FROM streamer_learned_examples
            WHERE streamer_id = ? AND platform = ? AND is_active = 1
        """
        params = [streamer_id, platform]

        # NEW: Filter by content type if specified
        if content_type and content_type != 'default':
            query += " AND content_type = ?"
            params.append(content_type)

        query += " ORDER BY performance_score DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        learned_examples = cursor.fetchall()

        logger.debug(f"Found {len(learned_examples)} learned examples for content_type='{content_type}'")

        # ... rest of code ...

    def _cache_metadata(
        self,
        video_facts: Dict,
        facts_hash: str,
        brief: Dict,
        metadata: Dict,
        streamer_id: str,
        platform: str,
        content_type: str = "default"  # NEW parameter
    ):
        """Cache generated metadata with content type"""

        # ... existing code ...

        cursor.execute("""
            INSERT INTO video_generation_cache (
                facts_hash, video_facts_json, brief_json, title, description,
                streamer_id, platform, content_type, generated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            facts_hash,
            json.dumps(video_facts),
            json.dumps(brief),
            metadata.get('title', ''),
            metadata.get('description', ''),
            streamer_id,
            platform,
            content_type  # NEW
        ))

        # ... rest of code ...
```

---

## Phase 6: Update CLI Tool

### Step 6.1: Extend CLI with Content Type Options

**File**: `scripts/update_learned_examples.py` (modifications)

```python
def main():
    parser = argparse.ArgumentParser(...)

    # ... existing arguments ...

    # NEW: Content type filter
    parser.add_argument(
        '--content-type',
        type=str,
        help='Filter by content type (e.g., sejm_meeting, sejm_press_conference)'
    )

    # NEW: List available content types
    parser.add_argument(
        '--list-types',
        action='store_true',
        help='List available content types for a streamer'
    )

    args = parser.parse_args()

    # NEW: List content types
    if args.list_types:
        list_content_types(args.streamer_id)
        return

    # Pass content_type to run_update
    if args.stats:
        show_stats(args.streamer_id, args.content_type)
    else:
        run_update(args.streamer_id, args)

def list_content_types(streamer_id: str = None):
    """List available content types"""
    from pipeline.ai_metadata.content_classifier import ContentTypeClassifier

    classifier = ContentTypeClassifier()

    if streamer_id:
        types = classifier.get_available_types(streamer_id)
        print(f"\n📋 Available content types for '{streamer_id}':")
        for t in types:
            print(f"  - {t}")
    else:
        print("\n⚠️ Please specify a streamer_id to list content types")

def run_update(streamer_id: str = None, args=None):
    """Run learning loop with content type support"""

    # ... existing code ...

    content_type = args.content_type if args else None

    if content_type:
        print(f"  Content type filter: {content_type}")

    results = run_learning_loop(
        streamer_id=streamer_id,
        top_n=top_n,
        min_score=min_score,
        content_type=content_type  # NEW parameter
    )

    # ... rest of code ...
```

**New Usage Examples:**
```bash
# List available content types for Sejm
python scripts/update_learned_examples.py sejm --list-types

# Update only Sejm meetings
python scripts/update_learned_examples.py sejm --content-type sejm_meeting

# Update only press conferences with custom thresholds
python scripts/update_learned_examples.py sejm --content-type sejm_press_conference --min-score 6.0

# Show stats for specific content type
python scripts/update_learned_examples.py sejm --stats --content-type sejm_meeting
```

---

## Testing Checklist

### Pre-Migration Tests
- [ ] Backup database: `cp data/uploader.db data/uploader.db.backup`
- [ ] Verify current schema: `sqlite3 data/uploader.db ".schema"`

### Migration Tests
- [ ] Run migration: `python database/migration_content_type.py`
- [ ] Verify columns added: Check both tables have `content_type`
- [ ] Verify index created: `sqlite3 data/uploader.db ".indexes streamer_learned_examples"`
- [ ] Test migration idempotence: Run migration again, should not error

### Classifier Tests
- [ ] Run classifier tests: `python tests/test_content_classifier.py`
- [ ] Test Sejm meeting detection: Should classify "Posiedzenie Sejmu" correctly
- [ ] Test press conference detection: Should classify "Konferencja prasowa" correctly
- [ ] Test manual override: Should respect manual content_type parameter

### Integration Tests
- [ ] Run learning loop with content type: `python scripts/update_learned_examples.py sejm --content-type sejm_meeting`
- [ ] Verify content_type stored in database: Check `streamer_learned_examples` table
- [ ] Generate metadata with content type: Test Stage 09 integration
- [ ] Verify few-shot examples filtered by type: Check generator uses correct examples

### End-to-End Test
```bash
# 1. Migrate database
python database/migration_content_type.py

# 2. Test classifier
python tests/test_content_classifier.py

# 3. List content types
python scripts/update_learned_examples.py sejm --list-types

# 4. Update examples for specific type
python scripts/update_learned_examples.py sejm --content-type sejm_meeting

# 5. Check stats
python scripts/update_learned_examples.py sejm --stats --content-type sejm_meeting

# 6. Generate video metadata (should use type-specific examples)
# Run your normal pipeline and verify it uses correct content type
```

---

## Rollout Strategy

### Phase 1: Migration (Low Risk)
1. Backup database
2. Run migration script
3. Verify columns exist
4. No behavior change yet (all default to 'default')

### Phase 2: Classification (Medium Risk)
1. Deploy content classifier
2. Test with --list-types and --content-type flags
3. Verify detection accuracy manually
4. Adjust keywords if needed

### Phase 3: Learning Loop Integration (Medium Risk)
1. Deploy updated learning loop
2. Run for one streamer with content_type filter
3. Verify examples stored with correct type
4. Gradually enable for all streamers

### Phase 4: Generator Integration (High Risk)
1. Deploy updated generator with content_type support
2. Test with force_regenerate to verify new examples used
3. Monitor quality of generated titles/descriptions
4. Rollback if quality degrades

### Phase 5: Auto-Detection (High Risk)
1. Enable auto-detection in generator
2. Monitor content_type assignments
3. Add manual overrides where needed
4. Tune classifier keywords based on results

---

## Monitoring and Validation

### Database Queries for Validation

**Check content type distribution:**
```sql
SELECT content_type, COUNT(*) as count
FROM streamer_learned_examples
WHERE streamer_id = 'sejm'
GROUP BY content_type
ORDER BY count DESC;
```

**Check top performers by content type:**
```sql
SELECT content_type, title, performance_score
FROM streamer_learned_examples
WHERE streamer_id = 'sejm' AND content_type = 'sejm_meeting'
ORDER BY performance_score DESC
LIMIT 10;
```

**Verify content_type stored in cache:**
```sql
SELECT content_type, COUNT(*) as count
FROM video_generation_cache
WHERE streamer_id = 'sejm'
GROUP BY content_type;
```

### Expected Outcomes

After full implementation:
- ✅ Different content types stored separately in database
- ✅ Performance scores compared within content type only
- ✅ Few-shot examples filtered by content type
- ✅ AI generates type-appropriate titles/descriptions
- ✅ Manual override available for edge cases

---

## Next Steps

1. **Review and approve this implementation plan**
2. **Run migration script** to add content_type columns
3. **Deploy content classifier** and test detection accuracy
4. **Update learning loop** to classify and store content types
5. **Update generator** to use type-specific examples
6. **Monitor quality** and tune classifier as needed

**Estimated Total Implementation Time**: 4-6 hours

**Priority**: HIGH (critical for production quality with Sejm content)
