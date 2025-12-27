# Critical Architecture Analysis: Content Type & Streamer Isolation

## Executive Summary

**Current Status**: ✅ Streamer aggregation works, ⚠️ Content type distinction missing

The system properly isolates different streamers via `streamer_id`, but **lacks content type differentiation**. This creates a critical issue: Sejm meetings, conferences, and press briefings are all mixed together in learned examples, potentially causing AI to learn inappropriate patterns.

---

## 1. Streamer Aggregation Analysis

### ✅ What Works Currently

**Database Isolation by Streamer:**
```sql
-- All tables properly isolate by streamer_id
video_generation_cache.streamer_id        -- Sejm, asmongold, etc.
streamer_learned_examples.streamer_id     -- Separate pools
api_cost_tracking.streamer_id             -- Separate cost tracking
```

**Profile System:**
- Each streamer has isolated profile: `pipeline/streamers/profiles/{streamer_id}.yaml`
- StreamerManager.get('sejm') returns only Sejm data
- Learning loop processes streamers independently

**Evidence from Code:**
```python
# pipeline/learning/learning_loop.py:97
profile = self.streamer_manager.get(streamer_id)  # Isolated per streamer

# pipeline/learning/performance.py:195
cursor.execute("""
    INSERT INTO streamer_learned_examples (streamer_id, ...)
    VALUES (?, ...)
""", (streamer_id, ...))  # Each streamer's examples separate
```

**Verdict**: ✅ **Streamer aggregation works correctly**
- Different streamers (Sejm, Asmongold, Pokimane) are fully isolated
- No cross-contamination between streamers
- Each maintains separate learned examples pool

---

## 2. Content Type Distinction Analysis

### ❌ Critical Gap: No Streaming vs SEJM Mode

**Current Problem:**
```python
# pipeline/ai_metadata/generator.py:450
def _get_few_shot_examples(self, streamer_id, platform):
    cursor.execute("""
        SELECT title, description, video_type, views_count, performance_score
        FROM streamer_learned_examples
        WHERE streamer_id = ? AND platform = ? AND is_active = 1
        ORDER BY performance_score DESC
        LIMIT ?
    """, (streamer_id, platform, limit))
    # ❌ NO content_type filtering!
```

**What This Means:**
- Sejm meeting titles mixed with conference titles
- Gaming stream titles mixed with IRL stream titles
- AI learns from ALL content types simultaneously
- Performance metrics compared across incomparable content

### Real-World Impact Example

**Scenario: Sejm Channel**
```
Learned Examples Pool (all mixed):
1. "Posiedzenie Sejmu - debata o budżecie" (meeting, score: 8.5)
2. "Konferencja prasowa premier" (press conference, score: 7.8)
3. "Briefing po spotkaniu" (briefing, score: 6.2)
4. "Obrady komisji" (committee session, score: 8.0)
```

**Problem:**
When generating title for a Sejm meeting, AI sees examples from:
- ✅ Meetings (appropriate)
- ❌ Press conferences (different style)
- ❌ Briefings (different audience)
- ❌ Committee sessions (different format)

**Result**: Inconsistent titles that don't match content type conventions

---

## 3. Multi-Streamer Scenarios

### ✅ Different Streamers Properly Isolated

**Test Case 1: Multiple Gaming Streamers**
```
Asmongold (streamer_id: "asmongold")
├── learned_examples: 20 gaming videos
├── profile: English, gaming focus
└── No cross-talk with other streamers

Pokimane (streamer_id: "pokimane")
├── learned_examples: 20 gaming videos
├── profile: English, variety gaming
└── Completely separate pool
```

**Test Case 2: Sejm vs Gaming Streamer**
```
Sejm (streamer_id: "sejm")
├── learned_examples: Political content
├── profile: Polish, formal language
└── Zero contamination from gaming

Asmongold (streamer_id: "asmongold")
├── learned_examples: Gaming content
└── Zero contamination from politics
```

**Verdict**: ✅ **Multi-streamer handling works correctly**

---

## 4. Sejm Content Type Variations

### ❌ Critical Issue: All Sejm Content Treated Identically

**Content Types in Sejm Channel:**

| Content Type | Characteristics | Current Handling |
|-------------|-----------------|------------------|
| **Posiedzenia Sejmu** | Long debates, formal language | ❌ Mixed with all |
| **Konferencje prasowe** | Shorter, Q&A format | ❌ Mixed with all |
| **Briefingi** | Quick updates, urgent | ❌ Mixed with all |
| **Komisje** | Committee work, specialized | ❌ Mixed with all |
| **Wystąpienia** | Individual speeches | ❌ Mixed with all |

**Performance Metric Incomparability:**
```
Meeting (2 hours):     100K views, 5K watch time → Score: 7.5
Press Conference (20m): 50K views, 15m watch time → Score: 8.2
```

These scores aren't comparable! Different content types have different:
- Expected lengths
- Audience sizes
- Engagement patterns
- Publishing schedules

---

## 5. Proposed Architecture Changes

### Solution 1: Add `content_type` Field

**Database Schema Extension:**
```sql
-- Extend video_generation_cache
ALTER TABLE video_generation_cache
ADD COLUMN content_type TEXT DEFAULT 'default';

-- Extend streamer_learned_examples
ALTER TABLE streamer_learned_examples
ADD COLUMN content_type TEXT DEFAULT 'default';

-- Index for performance
CREATE INDEX idx_learned_examples_content_type
ON streamer_learned_examples(streamer_id, content_type, is_active);
```

**Migration Path:**
1. Add column with default value 'default'
2. Existing data gets 'default' content_type
3. New videos classified by heuristics
4. Manual override available via CLI

### Solution 2: Content Type Detection

**Auto-Detection Heuristics:**
```python
# pipeline/ai_metadata/content_classifier.py
class ContentTypeClassifier:
    def detect_content_type(self, title: str, description: str, streamer_id: str) -> str:
        """Auto-detect content type from metadata"""

        # Load streamer-specific rules
        rules = self._load_content_rules(streamer_id)

        # For Sejm:
        if streamer_id == "sejm":
            if any(kw in title.lower() for kw in ["posiedzenie", "obrady"]):
                return "sejm_meeting"
            elif any(kw in title.lower() for kw in ["konferencja prasowa"]):
                return "sejm_press_conference"
            elif any(kw in title.lower() for kw in ["briefing"]):
                return "sejm_briefing"
            elif any(kw in title.lower() for kw in ["komisja"]):
                return "sejm_committee"
            else:
                return "sejm_other"

        # For gaming streamers:
        elif streamer_id in ["asmongold", "pokimane"]:
            if any(kw in title.lower() for kw in ["irl", "just chatting"]):
                return "stream_irl"
            else:
                return "stream_gaming"

        return "default"
```

### Solution 3: Profile-Based Content Types

**Extend Streamer Profiles:**
```yaml
# pipeline/streamers/profiles/sejm.yaml
streamer_id: sejm
display_name: "Kancelaria Sejmu"
language: pl

# NEW: Content type definitions
content_types:
  - type: "sejm_meeting"
    display_name: "Posiedzenie Sejmu"
    keywords:
      - "posiedzenie"
      - "obrady sejmu"
    title_patterns:
      - "Posiedzenie Sejmu - {topic}"
      - "{day} posiedzenie - {topic}"
    performance_thresholds:
      min_views: 50000
      min_score: 6.0

  - type: "sejm_press_conference"
    display_name: "Konferencja prasowa"
    keywords:
      - "konferencja prasowa"
      - "briefing prasowy"
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
    performance_thresholds:
      min_views: 20000
      min_score: 5.0

platforms:
  youtube:
    channel_id: "UCWd8gHV5Qt-bBa4dI98cS0Q"
    # ...
```

### Solution 4: Content-Type-Aware Learning Loop

**Modified Learning Flow:**
```python
# pipeline/learning/learning_loop.py
def run(self, streamer_id: str, content_type: str = None):
    """
    Run learning loop for specific content type

    Args:
        streamer_id: Streamer ID
        content_type: Optional content type filter (e.g., "sejm_meeting")
    """

    # 1. Fetch videos
    video_ids = self.youtube_api.get_channel_videos(...)

    # 2. Classify content types
    for video_id, metrics in video_metrics.items():
        detected_type = self.classifier.detect_content_type(
            metrics['title'],
            metrics['description'],
            streamer_id
        )
        metrics['content_type'] = detected_type

    # 3. Filter by content type if specified
    if content_type:
        video_metrics = {
            vid: m for vid, m in video_metrics.items()
            if m.get('content_type') == content_type
        }

    # 4. Analyze performance (within content type only!)
    performances = self.analyzer.analyze_channel_videos(
        streamer_id,
        video_metrics,
        content_type=content_type  # NEW: Compare within type only
    )

    # 5. Update learned examples with content_type
    self.analyzer.update_learned_examples(
        streamer_id,
        top_videos,
        platform=platform,
        content_type=content_type  # NEW: Store content type
    )
```

**Modified Metadata Generation:**
```python
# pipeline/ai_metadata/generator.py
def _get_few_shot_examples(self, streamer_id, platform, content_type=None):
    """Get learned examples filtered by content type"""

    query = """
        SELECT title, description, video_type, views_count, performance_score
        FROM streamer_learned_examples
        WHERE streamer_id = ?
          AND platform = ?
          AND is_active = 1
    """
    params = [streamer_id, platform]

    # NEW: Filter by content type if specified
    if content_type:
        query += " AND content_type = ?"
        params.append(content_type)

    query += " ORDER BY performance_score DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    # ...
```

---

## 6. Implementation Priority

### Phase 1: Database Extension (High Priority)
- Add `content_type` column to both tables
- Set default value to 'default' for backwards compatibility
- Create indexes for performance

### Phase 2: Content Type Classifier (High Priority)
- Implement keyword-based detection
- Add manual override via CLI flag
- Test with Sejm content types

### Phase 3: Profile Extension (Medium Priority)
- Add `content_types` to streamer YAML profiles
- Define patterns and thresholds per type
- Support custom type definitions

### Phase 4: Learning Loop Update (High Priority)
- Modify learning loop to classify content
- Compare performance within content type only
- Store content_type in learned examples

### Phase 5: Generator Update (High Priority)
- Filter few-shot examples by content type
- Auto-detect content type from video context
- Use type-specific examples for generation

---

## 7. Usage Examples After Implementation

### Example 1: Update Sejm Meetings Only
```bash
# Update only meeting examples
python scripts/update_learned_examples.py sejm --content-type sejm_meeting

# Update only press conferences
python scripts/update_learned_examples.py sejm --content-type sejm_press_conference
```

### Example 2: Generate Title with Content Type
```python
from pipeline.ai_metadata import MetadataGenerator

generator = MetadataGenerator()
metadata = generator.generate_metadata(
    clips=clips,
    streamer_id="sejm",
    platform="youtube",
    content_type="sejm_meeting"  # NEW: Type-specific generation
)
# Uses only "sejm_meeting" examples for few-shot learning
```

### Example 3: Stats Per Content Type
```bash
python scripts/update_learned_examples.py sejm --stats

Output:
📊 SEJM
  Content Types:
    sejm_meeting:          12 examples (avg score: 7.8)
    sejm_press_conference: 5 examples (avg score: 6.9)
    sejm_briefing:        3 examples (avg score: 6.2)
```

---

## 8. Recommendations Summary

### Immediate Actions Required

1. **✅ Keep Current Streamer Isolation**: Working correctly, no changes needed

2. **⚠️ Add Content Type Support**: Critical for quality
   - Implement `content_type` field in database
   - Build content classifier with keyword detection
   - Update learning loop to classify and filter by type

3. **⚠️ Separate Performance Pools**: Prevent false comparisons
   - Compare meeting scores only with other meetings
   - Compare press conference scores only with other conferences
   - Adjust performance thresholds per content type

4. **⚠️ Content-Type-Aware Few-Shot**: Improve AI quality
   - Filter learned examples by content type when generating
   - Use meeting examples for meetings, conference examples for conferences
   - Prevent style contamination across types

### Long-Term Enhancements

- **Manual Content Type Override**: CLI flag for edge cases
- **Machine Learning Classifier**: Replace keyword detection with ML model
- **Content Type Analytics**: Track performance trends per type
- **Automatic Type Discovery**: Learn new content types from data

---

## 9. Risk Assessment

### Current Risks (Without Content Type Support)

| Risk | Severity | Impact |
|------|----------|--------|
| Mixed content in learned examples | **HIGH** | AI learns wrong patterns |
| Incomparable performance scores | **MEDIUM** | Poor examples selected |
| Title style inconsistency | **HIGH** | User confusion |
| Wrong few-shot examples | **HIGH** | Low-quality generation |

### Mitigation (With Content Type Support)

| Risk | Mitigation | Effectiveness |
|------|------------|---------------|
| Mixed content | Filter by content_type | **HIGH** |
| Incomparable scores | Compare within type | **HIGH** |
| Style inconsistency | Type-specific examples | **HIGH** |
| Wrong examples | Type-aware selection | **HIGH** |

---

## 10. Conclusion

### Current Architecture Status

**Strengths:**
✅ Excellent streamer isolation (Sejm, Asmongold, etc. properly separated)
✅ Robust database structure with proper foreign keys
✅ Scalable to many streamers without code changes
✅ Cost tracking per streamer works correctly

**Critical Gaps:**
❌ No content type distinction (meetings vs conferences vs briefings)
❌ Performance scores compared across incomparable content types
❌ Few-shot examples mix all content types together
❌ No way to filter or classify content automatically

### Required Changes

The system **MUST** implement content type support to be production-ready for Sejm:

1. **Database**: Add `content_type` column
2. **Classification**: Implement auto-detection from title/description
3. **Learning**: Separate performance pools per content type
4. **Generation**: Use type-specific few-shot examples

Without these changes, the AI will learn inappropriate patterns by mixing different content types.

### Next Steps

1. Review this analysis
2. Decide on content type taxonomy for Sejm (meetings, conferences, briefings, etc.)
3. Implement database migration
4. Build content type classifier
5. Update learning loop and generator
6. Test with real Sejm content

**Estimated Implementation Time**: 4-6 hours for full content type support
