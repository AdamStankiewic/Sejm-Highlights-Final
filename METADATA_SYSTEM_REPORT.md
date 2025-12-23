# AI Metadata Generation & Streamer Learning - Status Report

**Data**: 2025-12-23
**Requested by**: User (verification of title/description generation + streamer learning)

---

## 📊 EXECUTIVE SUMMARY

The AI metadata generation system and streamer learning loop are **fully implemented** but **have not been executed yet**. All database tables are empty (0 learned examples, 0 cached metadata, 0 API costs).

**Status**:
- ✅ **Implementation**: Complete
- ⚠️ **Execution**: Never run
- 📊 **Database**: Empty (all tables 0 rows)
- 🎯 **Next Step**: Run pipeline with YouTube upload OR manually trigger learning loop

---

## 1. SYSTEM ARCHITECTURE

### 1.1 AI Metadata Generation (`pipeline/ai_metadata/`)

**Components**:
```
MetadataGenerator
  ├─► ContextBuilder (builds StreamingBrief from clips)
  ├─► PromptBuilder (creates prompts with few-shot examples)
  ├─► Database caching (avoids regeneration for identical videos)
  └─► Cost tracking (tracks API costs)
```

**Integration Point**: `pipeline/stage_09_youtube.py:80-86`

```python
self.ai_metadata_generator = MetadataGenerator(
    openai_client=openai_client,
    streamer_manager=self.streamer_manager,
    platform_config=platform_config
)
```

**Generation Flow**:
```
Stage 6: Selection → selected_clips.json
    ↓
Stage 9: YouTube Upload
    ↓
MetadataGenerator.generate_metadata(clips, streamer_id="sejm")
    ↓
    1. Build context (StreamingBrief) from clips
    2. Get few-shot examples (seed + learned)
    3. Generate title (GPT-4o)
    4. Generate description (GPT-4o)
    5. Cache results in database
    ↓
Output: {title, description, cost, cached, content_type}
```

**Models Used** (for "sejm" profile):
- **Title**: GPT-4o (best for clickbait)
- **Description**: GPT-4o (best for structure)
- **Context**: GPT-4o-mini (cheaper for extraction)

---

### 1.2 Streamer Learning Loop (`pipeline/learning/`)

**Components**:
```
LearningLoop
  ├─► YouTubeMetricsAPI (fetches video data from YouTube Data API)
  ├─► PerformanceAnalyzer (calculates performance scores)
  └─► Database storage (streamer_learned_examples table)
```

**Learning Flow**:
```
1. Fetch recent 50 videos from YouTube channel
    ↓
2. Get metrics (views, likes, comments, retention, CTR)
    ↓
3. Calculate performance score for each video
    ↓
4. Select TOP 20 best performers (score > 5.0)
    ↓
5. Store in database as "learned examples"
    ↓
6. Future AI generations use these as few-shot examples
```

**Performance Score Formula**:
```python
score = (
    0.30 * views_score +       # 30% weight (normalized by channel avg)
    0.25 * likes_score +       # 25% weight (likes/views ratio)
    0.20 * comments_score +    # 20% weight (engagement)
    0.15 * ctr_score +         # 15% weight (click-through rate)
    0.10 * retention_score     # 10% weight (avg view duration)
)
```

---

## 2. CURRENT STATUS

### 2.1 Database Tables

**Checked**: `data/uploader.db`

| Table | Rows | Status |
|-------|------|--------|
| `streamer_learned_examples` | 0 | ⚠️ Empty - Learning loop never run |
| `video_generation_cache` | 0 | ⚠️ Empty - AI generation never used |
| `api_cost_tracking` | 0 | ⚠️ Empty - No API calls tracked |

**Diagnosis**:
- Learning loop has never been executed
- AI metadata generation has never been triggered
- Either YouTube upload wasn't used, OR it's using fallback generation

---

### 2.2 Streamer Profiles

**Location**: `pipeline/streamers/profiles/`

**Profiles Found**:
- ✅ `sejm.yaml` (configured)
- ❌ No other streamer profiles (user mentioned "streamer highlights")

**Sejm Profile Configuration**:
```yaml
streamer_id: "sejm"
name: "Sejm RP"
platforms:
  youtube:
    channel_id: "UCSlsIpJrotOvA1wbA4Z46zA"

generation:
  context_model: "gpt-4o-mini"
  title_model: "gpt-4o"
  description_model: "gpt-4o"
  temperature: 0.8

seed_examples: 4  # Manual examples for few-shot learning
  - sejm_meeting_pl
  - sejm_press_conference_pl
  - sejm_briefing_pl
  - sejm_committee_pl
```

**⚠️ ISSUE**: User mentioned making "streamer highlights", but no streamer profiles exist besides "sejm".

**Implications**:
- If user is processing actual Twitch/Kick streamers → profiles need to be created
- If "streamer" refers to Sejm politicians → sejm profile should work
- Content type auto-detection may not work properly without streamer profiles

---

## 3. HOW IT WORKS

### 3.1 Title Generation

**Method**: AI-powered with few-shot learning

**Input**:
- Clips from Stage 6 (selected_clips.json)
- Streamer profile (e.g., sejm.yaml)
- Few-shot examples (seed + learned)

**Process**:
1. Build StreamingBrief from clips:
   - Main narrative (what happened)
   - Key entities (names, topics)
   - Emotional tone (heated, professional, urgent)
   - Controversy score (0-10)

2. Get few-shot examples:
   - Seed examples from profile (4 manual examples)
   - Learned examples from database (TOP 20 performers)
   - Filter by content_type if specified

3. Generate title with GPT-4o:
   ```python
   prompt = f"""
   Generate clickbait YouTube title for:
   {brief}

   Examples:
   {few_shot_examples}

   Guidelines:
   - Use emojis (🔥, 💥, ⚡)
   - Include key names if available
   - Max 100 characters
   - Emotional hook
   """
   ```

**Output Example**:
```
"🔥 SEJM: Tusk vs Kaczyński - Najgorętsze Momenty Debaty! | 15.12.2024"
```

---

### 3.2 Description Generation

**Method**: AI-powered with structured format

**Input**:
- StreamingBrief (from title generation)
- Generated title
- Few-shot examples

**Process**:
1. Generate description with GPT-4o:
   ```python
   prompt = f"""
   Generate YouTube description for video titled:
   {title}

   Brief:
   {brief}

   Format:
   - Hook (1-2 sentences)
   - Bullet points with key moments
   - Timestamps (if available)
   - Call to action
   """
   ```

**Output Example**:
```
🎯 Najciekawsze i najbardziej kontrowersyjne momenty z Sejmu RP!

📋 CO W ODCINKU:
• Donald Tusk odpowiada na zarzuty opozycji
• Ostra wymiana zdań o budżecie państwa
• Jarosław Kaczyński ripostuje
• Marszałek przerywa burzliwą dyskusję

⏱️ TIMESTAMPY:
0:00 - Tusk rozpoczyna przemówienie
2:15 - Kaczyński zabiera głos
5:30 - Burza w Sejmie
...
```

---

### 3.3 Streamer Learning

**When It Runs**: Manually or via scheduled task

**Command**:
```python
from pipeline.learning import run_learning_loop

# For specific streamer
results = run_learning_loop(
    streamer_id="sejm",
    youtube_api_key="YOUR_API_KEY"
)

# For all streamers
results = run_learning_loop(youtube_api_key="YOUR_API_KEY")
```

**What It Does**:
1. Connects to YouTube Data API
2. Fetches recent 50 videos from channel
3. Gets metrics:
   - Views
   - Likes
   - Comments
   - Estimated CTR
   - Avg view duration

4. Calculates performance score (0-10)
5. Selects TOP 20 performers (score > 5.0)
6. Stores in database:
   ```sql
   INSERT INTO streamer_learned_examples (
       streamer_id, video_id, title, description,
       performance_score, views_count, ...
   )
   ```

**Future Generations**:
- MetadataGenerator queries database for learned examples
- Uses them as few-shot examples alongside seed examples
- AI learns from what actually performed well on YouTube

---

## 4. WHY IT'S NOT WORKING YET

### Root Cause Analysis:

**Empty Database** → Three possible reasons:

1. **YouTube upload never used**:
   - Pipeline runs Stages 1-8 only
   - Stage 9 (YouTube) is opt-in via config: `youtube.enabled = true`
   - If user exports videos manually → AI generation never triggers

2. **Fallback generation used**:
   - If streamer profile missing → uses simple fallback
   - Fallback doesn't use database or AI
   - Check logs for "Using fallback simple generation"

3. **Learning loop never executed**:
   - Requires manual trigger OR scheduled task
   - Needs YouTube API key
   - Hasn't been set up yet

---

## 5. HOW TO VERIFY IT WORKS

### Test 1: Check if AI metadata is being used

**Run pipeline with YouTube upload**:
```bash
# In config.yml, ensure:
youtube:
  enabled: true

# Run pipeline
python processor.py --input video.mp4
```

**Look for in logs**:
```
🤖 Generating AI metadata for sejm (youtube/long/sejm_meeting_pl)
✅ Using cached metadata for sejm  (if run before)
💾 Updating learned examples...
```

**Check database after run**:
```python
import sqlite3
conn = sqlite3.connect("data/uploader.db")
cursor = conn.cursor()

# Check if metadata was cached
cursor.execute("SELECT COUNT(*) FROM video_generation_cache;")
print(f"Cached metadata: {cursor.fetchone()[0]}")

# Check API costs
cursor.execute("SELECT SUM(cost_usd) FROM api_cost_tracking;")
print(f"Total API cost: ${cursor.fetchone()[0]:.4f}")
```

---

### Test 2: Run Learning Loop manually

**Prerequisites**:
- YouTube Data API key
- Uploaded videos on channel
- Videos published in last 30 days

**Run**:
```python
from pipeline.learning import run_learning_loop

results = run_learning_loop(
    streamer_id="sejm",
    youtube_api_key="YOUR_YOUTUBE_API_KEY_HERE",
    top_n=20,
    min_score=5.0
)

# Check results
print(f"Success: {results[0]['success']}")
print(f"Videos analyzed: {results[0]['videos_analyzed']}")
print(f"Examples updated: {results[0]['examples_updated']}")
```

**Expected Output**:
```
============================================================
LEARNING LOOP: sejm (youtube)
============================================================
📥 Fetching recent videos from channel: UCSlsIpJrotOvA1wbA4Z46zA
Found 42 recent videos
📊 Fetching metrics for 42 videos...
Got metrics for 42 videos
🔍 Analyzing video performance...
🏆 Selected 18 top performers

  Top 5 performers:
  1. 🔥 SEJM: Tusk vs Kaczyński - Najgorętsze Momenty... (score: 8.73)
  2. 💥 Konferencja Prasowa - Minister Odpowiada... (score: 7.95)
  3. ⚡ PILNY Briefing - Marszałek Wydaje Oświadczenie (score: 7.42)
  ...

💾 Updating learned examples...
✅ Learning loop complete!
  Videos analyzed: 42
  Top performers: 18
  Examples updated: 18
  Elapsed time: 12.3s
```

**Verify in database**:
```python
import sqlite3
conn = sqlite3.connect("data/uploader.db")
cursor = conn.cursor()

cursor.execute("""
    SELECT title, performance_score, views_count
    FROM streamer_learned_examples
    WHERE streamer_id = 'sejm'
    ORDER BY performance_score DESC
    LIMIT 5
""")

for row in cursor.fetchall():
    print(f"  {row[0][:50]}... | Score: {row[1]:.2f} | Views: {row[2]:,}")
```

---

### Test 3: Verify few-shot learning works

**After running learning loop**, generate new metadata:

```python
from pipeline.ai_metadata import MetadataGenerator
from pipeline.streamers import get_manager
import yaml

# Load platform config
with open("config/platforms.yaml") as f:
    platform_config = yaml.safe_load(f)

# Initialize
manager = get_manager()
generator = MetadataGenerator(openai_client, manager, platform_config)

# Generate (with learned examples)
metadata = generator.generate_metadata(
    clips=[...],
    streamer_id="sejm",
    platform="youtube",
    video_type="long"
)

print(f"Title: {metadata['title']}")
print(f"Examples used: {metadata['examples_used']}")
print(f"Cost: ${metadata['cost']:.4f}")
```

**Expected**:
- `examples_used`: 3-5 (seed + learned)
- Generated title should match style of top performers
- Cost: ~$0.002-0.005 per generation

---

## 6. SETTING UP FOR STREAMERS

### Issue: User mentioned "streamer highlights" but only sejm profile exists

**To support actual Twitch/Kick streamers**, create profiles:

**Example**: `pipeline/streamers/profiles/asmongold.yaml`
```yaml
streamer_id: "asmongold"
name: "Asmongold"
aliases: ["Asmon", "Zack"]

platforms:
  twitch:
    channel_id: "asmongold"
  youtube:
    channel_id: "UCxxxxxxxxxxxxxx"

content:
  primary_platform: "twitch"
  channel_type: "gaming"
  primary_language: "en"
  categories: ["gaming", "mmo", "commentary"]

generation:
  context_model: "gpt-4o-mini"
  title_model: "gpt-4o"
  description_model: "gpt-4o"
  temperature: 0.9  # Higher for more creative titles
  enable_research: false

seed_examples:
  - title: "Asmon LOSES IT Watching Drama Unfold 😂"
    description: "Asmon reacts to the latest gaming drama with hilarious commentary..."
    metadata:
      content_type: "asmongold_reaction"
      emotional_tone: "humorous"
      video_type: "long"

  - title: "This Game is INSANE - Asmon First Impressions"
    description: "Asmon tries out the newest MMO release and shares his thoughts..."
    metadata:
      content_type: "asmongold_gaming"
      emotional_tone: "excited"
      video_type: "long"
```

**Then run learning loop** to populate learned examples from actual channel performance.

---

## 7. CONTENT TYPE AUTO-DETECTION

**How It Works**: `pipeline/ai_metadata/generator.py:168-210`

**For Sejm**:
```python
if streamer_id == "sejm":
    if "posiedzenie" in text:
        return "sejm_meeting_pl"
    elif "konferencja prasowa" in text:
        return "sejm_press_conference_pl"
    elif "briefing" in text:
        return "sejm_briefing_pl"
    elif "komisja" in text:
        return "sejm_committee_pl"
    else:
        return "sejm_other_pl"
```

**For Gaming Streamers**:
```python
else:  # Gaming streamers
    if any(kw in text for kw in ["irl", "just chatting", "reacts"]):
        return f"{streamer_id}_irl"
    else:
        return f"{streamer_id}_gaming"
```

**Why It Matters**:
- Different content types use different few-shot examples
- Gaming highlights need different style than political debates
- Learned examples are filtered by content_type

---

## 8. API COSTS

**Estimated Costs** (per video):

| Operation | Model | Input Tokens | Output Tokens | Cost |
|-----------|-------|--------------|---------------|------|
| Context Extraction | gpt-4o-mini | ~800 | ~200 | $0.0002 |
| Title Generation | gpt-4o | ~500 | ~50 | $0.0018 |
| Description Generation | gpt-4o | ~600 | ~200 | $0.0035 |
| **TOTAL** | | | | **~$0.0055** |

**For 100 videos/month**: ~$0.55/month
**For 1000 videos/month**: ~$5.50/month

**Caching Saves Money**:
- Identical video facts → reuse cached metadata
- No API call needed
- Cost: $0.00

---

## 9. TROUBLESHOOTING

### Issue 1: "Using fallback simple generation"

**Cause**: Streamer profile not found OR OpenAI API error

**Check**:
```python
from pipeline.streamers import get_manager

manager = get_manager()
profile = manager.get("sejm")  # or your streamer_id

if profile:
    print(f"✅ Profile found: {profile.display_name}")
else:
    print("❌ Profile not found - create one!")
```

**Fix**: Create streamer profile in `pipeline/streamers/profiles/`

---

### Issue 2: Empty database after pipeline run

**Cause**: YouTube upload not enabled

**Check `config.yml`**:
```yaml
youtube:
  enabled: true  # Must be true!
```

**Alternative**: Use AI generation without YouTube upload

**TODO**: Expose AI generation as standalone feature (not tied to YouTube upload)

---

### Issue 3: Learning loop fails with API error

**Cause**: Missing or invalid YouTube API key

**Fix**:
```python
# Get API key from: https://console.cloud.google.com/apis/credentials
# Enable: YouTube Data API v3

from pipeline.learning import run_learning_loop

results = run_learning_loop(
    streamer_id="sejm",
    youtube_api_key="AIzaSy..."  # Your actual API key
)
```

---

## 10. RECOMMENDATIONS

### For User (Immediate):

1. **Verify current setup**:
   ```bash
   # Check if streamer profiles exist for your streamers
   ls pipeline/streamers/profiles/

   # If only sejm.yaml exists → create streamer profiles
   ```

2. **Create streamer profiles** (if processing Twitch/Kick content):
   - Copy `_TEMPLATE.yaml`
   - Fill in streamer details
   - Add 3-5 seed examples in their style

3. **Run learning loop** (if YouTube channel exists):
   ```python
   from pipeline.learning import run_learning_loop
   results = run_learning_loop("your_streamer_id", "YOUR_API_KEY")
   ```

4. **Test AI generation**:
   - Run pipeline with `youtube.enabled = true`
   - Check logs for "🤖 Generating AI metadata"
   - Verify database tables populated

---

### For Developers (Long-term):

1. **Expose AI generation as standalone**:
   - Currently tied to YouTube upload (Stage 9)
   - Should be available in Stage 7 (Export)
   - Allow generation without upload

2. **Scheduled learning loop**:
   - Add cron job to run daily/weekly
   - Auto-update learned examples
   - Track performance trends

3. **GUI integration**:
   - Show learned examples in app
   - Display performance scores
   - Manual trigger for learning loop

4. **Content type classification**:
   - Replace keyword matching with ML classifier
   - Better auto-detection
   - Support more content types

---

## 11. CONCLUSION

**Summary**:
- ✅ AI metadata generation: **Fully implemented, not yet used**
- ✅ Streamer learning: **Fully implemented, not yet executed**
- ⚠️ Database: **Empty (0 examples, 0 cache, 0 costs)**
- 🎯 Next step: **Run learning loop OR test with pipeline**

**To verify it works**:
1. Check if sejm profile is correct for your use case
2. Run learning loop with YouTube API key (if channel exists)
3. Run pipeline with YouTube upload enabled
4. Check database for populated tables
5. Verify generated titles match expected style

**If processing streamers (not Sejm)**:
- Create streamer profiles in `pipeline/streamers/profiles/`
- Add seed examples matching streamer style
- Run learning loop to populate database
- Content type auto-detection will work better

---

**Status**: ✅ **READY TO USE** (just needs to be triggered!)
