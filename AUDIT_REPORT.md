# Title/Description Generation Audit Report

**Generated:** 2025-12-19
**Project:** Sejm Highlights Video Processing Pipeline
**Purpose:** Audit current title/description generation architecture

---

## Executive Summary

This pipeline processes long-form video content (e.g., parliamentary sessions, live streams) into highlight reels for YouTube/Twitch/Kick. Title and description generation occurs at multiple stages using both template-based and LLM-powered approaches.

**Key Findings:**
- 7 distinct title generation functions across 5 files
- 2 description generation functions
- Uses OpenAI GPT-4o-mini for both title and semantic scoring
- File-based storage (JSON) for metadata
- SQLite for upload tracking only
- No centralized title/description service

---

## 1. Title/Description Generation Functions

### 1.1 Title Generation

| Function | File | Line | Method | Use Case |
|----------|------|------|--------|----------|
| `_generate_clickbait_title()` | `stage_09_youtube.py` | 37 | Template-based | YouTube video titles (simple) |
| `_generate_gpt_title()` | `stage_07_export.py` | 36 | **OpenAI GPT-4o-mini** | Export stage clickbait titles |
| `_generate_title()` | `stage_06_selection.py` | 591 | Keyword extraction | Individual clip titles |
| `_generate_shorts_title()` | `stage_06_selection.py` | 667 | Keyword extraction | YouTube Shorts titles |
| `generate_enhanced_title()` | `highlight_packer.py` | 376 | Keyword + politician names | Multi-part video titles |
| `_generate_youtube_title()` | `processor.py` | 166 | Keyword + politician names | Final YouTube upload titles |
| Title cards | `stage_07_export.py` | 256-309 | From clip metadata | Visual title overlays |

### 1.2 Description Generation

| Function | File | Line | Method | Use Case |
|----------|------|------|--------|----------|
| `_generate_description()` | `stage_09_youtube.py` | 204 | Template + timestamps | YouTube video descriptions |

### 1.3 Generation Methods Breakdown

#### **Template-Based (5 functions)**
- Simple keyword insertion
- Date formatting
- Politician name extraction from keywords
- Emoji prefixes (🔥, 💥, ⚡, etc.)

**Example from `stage_09_youtube.py:37-75`:**
```python
templates = [
    f"🔥 SEJM: {' vs '.join(top_keywords[:2]).upper()} - Najgorętsze Momenty!",
    f"💥 SEJM Eksploduje! {top_keywords[0].upper()} - Top Momenty {date_str}",
    f"⚡ SEJM: {top_keywords[0].upper()} - TO MUSISZ ZOBACZYĆ! {date_str}",
]
```

#### **LLM-Powered (1 function)**
- Uses OpenAI GPT-4o-mini
- Context: Top 3 clip transcripts + scores
- Prompt: Clickbait generation with specific formatting rules

**Example from `stage_07_export.py:36-90`:**
```python
response = self.openai_client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": "Jesteś ekspertem od viralowych tytułów politycznych."},
        {"role": "user", "content": prompt}
    ],
    max_tokens=100,
    temperature=0.9
)
```

---

## 2. LLM API Usage

### 2.1 OpenAI API Calls

| Purpose | File | Model | Cost Impact | Caching |
|---------|------|-------|-------------|---------|
| **Title Generation** | `stage_07_export.py:74-86` | gpt-4o-mini | Low (1 call/export) | ❌ No |
| **Semantic Scoring** | `stage_05_scoring_gpt.py:277-305` | gpt-4o-mini | **High** (batched, ~40+ segments) | ✅ Yes (cache_manager) |

### 2.2 Semantic Scoring Details

**Location:** `pipeline/stage_05_scoring_gpt.py`

**Process:**
1. Pre-filter to top 40-100 segments (configurable)
2. Batch process in groups of 10
3. Score each segment 0.0-1.0 for "interestingness"
4. Used for clip selection, NOT directly for titles

**API Configuration:**
- Batch size: 10 segments
- Temperature: 0.3
- Max tokens: 200
- Response format: JSON

**Caching:**
- Uses `CacheManager` (file: `pipeline/cache_manager.py`)
- Cache key: `hash(input_video) + hash(config)`
- Stores: VAD, Transcribe, and Scoring results
- Location: `cache/` directory

---

## 3. Data Flow & Architecture

### 3.1 Pipeline Stages

```
┌──────────────────────────────────────────────────────────────┐
│                      VIDEO INPUT                              │
│                    (MP4, MKV, etc.)                           │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 1: Ingest (stage_01_ingest.py)                       │
│  - Extract audio (FFmpeg)                                   │
│  - Normalize audio (EBU R128)                               │
│  Output: normalized_audio.wav                               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 2: VAD (stage_02_vad.py)                             │
│  - Voice Activity Detection (Silero v4)                     │
│  - Segment speech regions                                   │
│  Output: vad_segments.json                                  │
│  Cache: ✅ YES                                              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 3: Transcribe (stage_03_transcribe.py)               │
│  - Whisper ASR (large-v3)                                   │
│  - Word-level timestamps                                    │
│  Output: transcribed_segments.json                          │
│  Cache: ✅ YES                                              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 4: Features (stage_04_features.py)                   │
│  - Acoustic features (RMS, spectral)                        │
│  - Keyword matching (keywords_pl.csv)                       │
│  - Speaker detection (spaCy NER)                            │
│  Output: features_segments.json                             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 5: Scoring (stage_05_scoring_gpt.py)                 │
│  🤖 LLM API CALL #1: GPT-4o-mini Semantic Scoring           │
│  - Pre-filter to top 40-100 segments                        │
│  - Batch score (10 at a time)                               │
│  - Composite score: acoustic + keyword + semantic           │
│  Output: scored_segments.json                               │
│  Cache: ✅ YES                                              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 6: Selection (stage_06_selection.py)                 │
│  - Select top clips (NMS algorithm)                         │
│  - Smart merge nearby clips                                 │
│  - Generate clip titles (keyword-based)                     │
│  📝 TITLE GENERATION #1: _generate_title()                  │
│  📝 TITLE GENERATION #2: _generate_shorts_title()           │
│  Output: selected_clips.json, shorts_candidates.json        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ HIGHLIGHT PACKER (highlight_packer.py)                     │
│  - Split into parts if >1h source                           │
│  - Generate premiere schedule                               │
│  📝 TITLE GENERATION #3: generate_enhanced_title()          │
│  Output: packing_plan with parts_metadata                   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 7: Export (stage_07_export.py)                       │
│  - Extract clips (FFmpeg)                                   │
│  - Add transitions/fades                                    │
│  - Generate hardsub (optional)                              │
│  🤖 LLM API CALL #2: GPT-4o-mini Title Generation           │
│  📝 TITLE GENERATION #4: _generate_gpt_title()              │
│  Output: SEJM_HIGHLIGHTS_*.mp4                              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 8: Thumbnail (stage_08_thumbnail.py)                 │
│  - Extract best frame                                       │
│  - Add clickbait text overlay                               │
│  Output: thumbnail.jpg                                      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 9: YouTube Upload (stage_09_youtube.py)              │
│  - Authenticate (OAuth 2.0)                                 │
│  - Upload video + thumbnail                                 │
│  📝 TITLE GENERATION #5: _generate_clickbait_title()        │
│  📝 DESCRIPTION GENERATION: _generate_description()         │
│  Output: YouTube video ID + URL                             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 10: Shorts (stage_10_shorts.py) [OPTIONAL]           │
│  - Generate vertical shorts                                 │
│  - Face detection + cropping                                │
│  Output: short_001.mp4, short_002.mp4, etc.                 │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Video Facts / Metadata Flow

**Source of video_facts:**
1. **Clip Selection (`stage_06_selection.py:591-609`)**
   - AI categories (if available)
   - Keywords from feature extraction
   - Transcript preview (first 200 chars)
   - Score metadata

2. **Feature Extraction (`stage_04_features.py`)**
   - Matched keywords from `keywords_pl.csv`
   - Named entities (politician names via spaCy)
   - Acoustic features (RMS, spectral, pause patterns)

**Storage Locations:**
- `selected_clips.json` - Final selected clips with metadata
- `scored_segments.json` - All segments with scores
- `features_segments.json` - Segments with extracted features
- Passed through pipeline as Python dicts (in-memory)

### 3.3 Where Titles/Descriptions Are Used

| Stage | Usage | Persistence |
|-------|-------|-------------|
| **Selection** | Clip titles for internal tracking | `selected_clips.json` |
| **Export** | Title cards (visual overlays) | Burned into video |
| **Thumbnail** | Text overlay on thumbnail image | `thumbnail.jpg` |
| **YouTube** | Video title, description, tags | YouTube API → YouTube database |
| **Processor** | Orchestration, final title selection | Passed to YouTube stage |

---

## 4. Storage & Dependencies

### 4.1 Data Storage

| Type | Format | Location | Purpose |
|------|--------|----------|---------|
| **Metadata** | JSON | `temp/{session_id}/` | Intermediate results per stage |
| **Clips** | JSON | `selected_clips.json` | Final clip metadata |
| **Shorts** | JSON | `shorts_candidates.json` | Shorts metadata |
| **Configuration** | YAML | `config.yml` | Pipeline settings |
| **Upload Tracking** | SQLite | `data/uploader.db` | Upload job queue |
| **Cache** | JSON | `cache/` | VAD, Transcribe, Scoring cache |

**Database Schema (SQLite in `uploader/store.py`):**
```sql
CREATE TABLE upload_jobs (
    job_id TEXT PRIMARY KEY,
    file_path TEXT,
    title TEXT,              -- ✅ Title stored here
    description TEXT,        -- ✅ Description stored here
    created_at TEXT,
    kind TEXT,
    copyright_status TEXT,
    original_path TEXT,
    tags TEXT,
    thumbnail_path TEXT
);

CREATE TABLE upload_targets (
    target_id TEXT PRIMARY KEY,
    job_id TEXT,
    platform TEXT,           -- "youtube", "tiktok", etc.
    account_id TEXT,
    scheduled_at TEXT,
    mode TEXT,
    state TEXT,              -- "PENDING", "UPLOADED", "FAILED"
    result_id TEXT,          -- YouTube video ID
    result_url TEXT,         -- YouTube video URL
    fingerprint TEXT UNIQUE,
    retry_count INTEGER,
    next_retry_at TEXT,
    last_error TEXT,
    updated_at TEXT
);
```

**Key Insight:** The SQLite database stores titles/descriptions AFTER generation, primarily for the upload scheduler. It does NOT generate titles itself.

### 4.2 External APIs & Dependencies

#### **APIs**

| Service | Purpose | Authentication | Cost | Rate Limits |
|---------|---------|----------------|------|-------------|
| **OpenAI GPT-4o-mini** | Title generation + semantic scoring | API Key (`.env`) | ~$0.15 per 1M input tokens<br>~$0.60 per 1M output tokens | 10,000 RPM (Tier 1) |
| **YouTube Data API v3** | Video upload, channel management | OAuth 2.0 (`client_secret.json`) | Free (10,000 units/day) | 10,000 units/day<br>Upload = 1600 units |
| **Google OAuth 2.0** | YouTube authentication | Client credentials | Free | - |

**OpenAI API Key Location:**
- Environment variable: `OPENAI_API_KEY` (loaded via `dotenv` from `.env` file)
- Referenced in:
  - `stage_05_scoring_gpt.py:103`
  - `stage_07_export.py:29`

**YouTube Credentials:**
- OAuth 2.0 client secret: `client_secret.json` (path from `config.yml`)
- Token storage: `youtube_token.json` (auto-generated after first auth)

#### **Local Tools**

| Tool | Purpose | Installation |
|------|---------|--------------|
| **FFmpeg** | Video/audio processing | System binary |
| **Whisper (faster-whisper)** | Speech-to-text | Python package |
| **Silero VAD** | Voice activity detection | Python package |
| **spaCy** | Named entity recognition | Python package + model (`pl_core_news_lg`) |

### 4.3 Configuration Files

**Main Configuration: `config.yml`**

Key sections affecting titles/descriptions:
```yaml
general:
  language: "pl"                    # Affects prompts & keywords

scoring:
  prefilter_top_n: 100              # How many segments to score with GPT
  interest_labels:                  # GPT scoring criteria
    "ostra polemika...": 2.2
    "emocjonalna...": 1.7
    ...

youtube:
  auto_title: true                  # Enable auto-title generation
  auto_description: true            # Enable auto-description
  tags: ["sejm", "polska", ...]     # Base tags

packer:                             # Multi-part video settings
  use_politicians_in_titles: true   # Include politician names
  premiere_hour: 18                 # Premiere scheduling
```

**Other Configs:**
- `.env` - OpenAI API key
- `keywords_pl.csv` - Keyword lists for extraction
- `client_secret.json` - YouTube OAuth credentials

---

## 5. Key Findings & Observations

### 5.1 Title Generation Redundancy

**Issue:** Multiple functions generate similar titles with overlapping logic.

**Functions with duplicate logic:**
1. `_generate_clickbait_title()` (YouTube stage)
2. `generate_enhanced_title()` (Packer)
3. `_generate_youtube_title()` (Processor)

**Recommendation:** Consolidate into a single `TitleGenerator` service class.

### 5.2 LLM Usage Pattern

**Current:**
- GPT-4o-mini used for BOTH scoring AND title generation
- Scoring is cached, title generation is NOT
- Title generation happens late in pipeline (Stage 7)

**Opportunity:**
- Could use scoring API response to generate titles (same context)
- Or generate titles during selection stage when we already have clip metadata

### 5.3 Data Flow Observation

**Video Metadata Journey:**
```
Raw Transcript (Stage 3)
  → Keywords Extracted (Stage 4)
  → Score Calculated (Stage 5)
  → Clips Selected (Stage 6)
  → Title Generated (Stage 7/9)
  → Uploaded to YouTube (Stage 9)
```

**Gap:** Title generation happens AFTER clip selection, using limited context. Could be improved by generating titles during scoring when we have full transcript context.

### 5.4 Storage Architecture

**Current:**
- File-based (JSON) for pipeline data
- SQLite only for upload queue management
- No persistent metadata database

**Implications:**
- Must re-run pipeline to regenerate titles
- No history of previous generations
- Cannot A/B test titles easily

---

## 6. Text-Based Data Flow Diagram

```
┌─────────────┐
│ VIDEO INPUT │
└──────┬──────┘
       │
       ▼
┌─────────────────────┐
│  Stage 1: Ingest    │  Extracts: Audio waveform
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│  Stage 2: VAD       │  Extracts: Speech segments (t0, t1)
└──────┬──────────────┘  Cache: ✅
       │
       ▼
┌─────────────────────┐
│ Stage 3: Transcribe │  Extracts: Text transcripts + word timestamps
└──────┬──────────────┘  Cache: ✅
       │
       ▼
┌─────────────────────────────┐
│ Stage 4: Features           │  Extracts: Keywords, entities, acoustic features
└──────┬──────────────────────┘  Keywords from: keywords_pl.csv
       │                          NER model: pl_core_news_lg (spaCy)
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Stage 5: Scoring (GPT)                                 │
│ ┌────────────────────────────────────────────────────┐ │
│ │ 🤖 OPENAI API CALL #1                              │ │
│ │ Model: gpt-4o-mini                                 │ │
│ │ Input: Top 40-100 segment transcripts (batches)    │ │
│ │ Output: Semantic score (0.0-1.0) per segment       │ │
│ │ Purpose: Identify "interesting" moments            │ │
│ └────────────────────────────────────────────────────┘ │
└──────┬─────────────────────────────────────────────────┘
       │ Cache: ✅
       │ Output: scored_segments.json
       │    ├─ final_score (composite)
       │    ├─ semantic_score (GPT)
       │    ├─ keyword_score
       │    └─ transcript
       │
       ▼
┌─────────────────────────────────────────────────────┐
│ Stage 6: Selection                                  │
│ ┌─────────────────────────────────────────────────┐ │
│ │ 📝 TITLE GENERATION #1 & #2                     │ │
│ │ Function: _generate_title()                     │ │
│ │ Method: Extract keywords/AI categories          │ │
│ │ Output: Clip titles (e.g., "Tusk • Kaczyński")  │ │
│ │                                                  │ │
│ │ Function: _generate_shorts_title()              │ │
│ │ Output: Shorts titles with [TOP]/[HOT] prefix   │ │
│ └─────────────────────────────────────────────────┘ │
└──────┬──────────────────────────────────────────────┘
       │ Output: selected_clips.json, shorts_candidates.json
       │    ├─ clip_id, title, keywords
       │    ├─ t0, t1, duration
       │    └─ final_score
       │
       ▼
┌─────────────────────────────────────────────────────┐
│ Highlight Packer (if source > 1h)                  │
│ ┌─────────────────────────────────────────────────┐ │
│ │ 📝 TITLE GENERATION #3                          │ │
│ │ Function: generate_enhanced_title()             │ │
│ │ Method: Politician names + keywords             │ │
│ │ Output: "🔥 Tusk VS Kaczyński | CZĘŚĆ 1/3"      │ │
│ └─────────────────────────────────────────────────┘ │
└──────┬──────────────────────────────────────────────┘
       │ Output: packing_plan.parts_metadata[]
       │
       ▼
┌─────────────────────────────────────────────────────┐
│ Stage 7: Export                                     │
│ ┌─────────────────────────────────────────────────┐ │
│ │ 🤖 OPENAI API CALL #2                           │ │
│ │ Function: _generate_gpt_title()                 │ │
│ │ Model: gpt-4o-mini                              │ │
│ │ Input: Top 3 clip transcripts + scores          │ │
│ │ Prompt: "Generate clickbait title..."           │ │
│ │ Output: "OSTRA WYMIANA! 🔥 | Sejm 19.12.2025"   │ │
│ └─────────────────────────────────────────────────┘ │
└──────┬──────────────────────────────────────────────┘
       │ Output: SEJM_HIGHLIGHTS_*.mp4
       │
       ▼
┌─────────────────────────────────────────────────────┐
│ Stage 8: Thumbnail                                  │
│   - Extracts best frame                             │
│   - Adds title overlay to image                     │
└──────┬──────────────────────────────────────────────┘
       │ Output: thumbnail.jpg
       │
       ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 9: YouTube Upload                                     │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 📝 TITLE GENERATION #5                                  │ │
│ │ Function: _generate_clickbait_title()                   │ │
│ │ Method: Template-based (keywords + emoji + date)        │ │
│ │ Output: "🔥 SEJM: TUSK vs KACZYŃSKI - Najgorętsze!"     │ │
│ │                                                          │ │
│ │ 📝 DESCRIPTION GENERATION                               │ │
│ │ Function: _generate_description()                       │ │
│ │ Method: Timestamps + clip previews                      │ │
│ │ Output: "🎯 Najciekawsze momenty..."                    │ │
│ │         "📋 CO W ODCINKU:"                              │ │
│ │         "⏱️ 00:00 - [clip 1 preview]"                   │ │
│ │         "⏱️ 02:15 - [clip 2 preview]"                   │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 🔗 YOUTUBE API CALL                                     │ │
│ │ Authentication: OAuth 2.0                                │ │
│ │ Upload: videos().insert()                                │ │
│ │ Thumbnail: thumbnails().set()                            │ │
│ └─────────────────────────────────────────────────────────┘ │
└──────┬──────────────────────────────────────────────────────┘
       │ Output: YouTube video ID, URL
       │
       ▼
┌─────────────────────────────────────────────────────┐
│ SQLite Storage (uploader/store.py)                  │
│   - Stores: job_id, title, description, video URL   │
│   - Purpose: Upload queue management, retry logic   │
│   - NOT used for generation                         │
└─────────────────────────────────────────────────────┘
```

---

## 7. File Reference Summary

### Core Pipeline Files

| File | Purpose | Title/Desc Functions |
|------|---------|---------------------|
| `pipeline/processor.py` | Main orchestrator | `_generate_youtube_title()` |
| `pipeline/stage_05_scoring_gpt.py` | AI scoring (GPT) | - |
| `pipeline/stage_06_selection.py` | Clip selection | `_generate_title()`, `_generate_shorts_title()` |
| `pipeline/stage_07_export.py` | Video export | `_generate_gpt_title()` |
| `pipeline/stage_08_thumbnail.py` | Thumbnail generation | Uses titles from previous stages |
| `pipeline/stage_09_youtube.py` | YouTube upload | `_generate_clickbait_title()`, `_generate_description()` |
| `pipeline/highlight_packer.py` | Multi-part splitting | `generate_enhanced_title()` |
| `pipeline/config.py` | Configuration | - |

### Supporting Files

| File | Purpose |
|------|---------|
| `config.yml` | Pipeline configuration (YAML) |
| `models/keywords_pl.csv` | Keyword list for extraction |
| `uploader/store.py` | SQLite database for upload tracking |
| `.env` | Environment variables (OpenAI API key) |
| `client_secret.json` | YouTube OAuth credentials |

---

## 8. Recommendations

### 8.1 Immediate Actions

1. **Consolidate Title Generation**
   - Create `TitleGenerator` service class
   - Reduce from 7 functions to 1-2 with strategy pattern

2. **Add Title Caching**
   - Cache GPT-generated titles with clip metadata
   - Avoid regeneration on re-runs

3. **Improve LLM Context**
   - Use full clip transcript for GPT title generation
   - Currently only uses first 300 chars (truncated)

### 8.2 Future Improvements

1. **A/B Testing Infrastructure**
   - Store multiple title variations
   - Track performance metrics (CTR, views)

2. **Title Quality Metrics**
   - Character count validation (YouTube limit: 100)
   - Emoji usage analysis
   - Keyword diversity scoring

3. **Centralized Metadata Service**
   - Replace file-based storage with database
   - Enable title history tracking
   - Support versioning

---

## Appendix A: Function Call Graph

```
processor.process()
  │
  ├─► stage_05_scoring_gpt.process()
  │    └─► openai_client.chat.completions.create()  [GPT API CALL #1]
  │
  ├─► stage_06_selection.process()
  │    ├─► _generate_title()               [Clip titles]
  │    └─► _generate_shorts_title()        [Shorts titles]
  │
  ├─► highlight_packer.split_clips_into_parts()
  │    └─► generate_enhanced_title()       [Multi-part titles]
  │
  ├─► stage_07_export.process()
  │    └─► _generate_gpt_title()           [GPT API CALL #2]
  │
  ├─► stage_08_thumbnail.process()
  │    └─► Uses titles from previous stages
  │
  └─► stage_09_youtube.process()
       ├─► _generate_clickbait_title()     [Final YouTube title]
       └─► _generate_description()         [YouTube description]
```

---

## Appendix B: Environment Variables

```bash
# Required
OPENAI_API_KEY=sk-...                    # OpenAI API key

# Optional (for GPU acceleration)
CUDA_VISIBLE_DEVICES=0
```

---

**End of Audit Report**
