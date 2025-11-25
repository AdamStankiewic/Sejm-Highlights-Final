```markdown
# 🎮 Streaming Highlights Module

Multi-platform chat-based highlight detection for **Twitch**, **YouTube**, and **Kick** streams.

---

## 📦 Components

### 1. **ChatAnalyzer** - Multi-platform chat parser
Parses chat JSON files and performs spike detection.

**Supported platforms:**
- **Twitch** (Twitch Downloader format)
- **YouTube** (yt-dlp, chat-downloader)
- **Kick** (API export, browser export)

**Features:**
- Auto-detects platform from JSON structure
- Baseline normalization (median message rate)
- Spike detection (3x above baseline)
- Local baseline (context-aware)
- Viewer count support (if available)

### 2. **EmoteScorer** - Platform-specific emote analysis
Scores messages based on emote types and density.

**Emote weights:**
- **Twitch**: KEKW (2.5), PogChamp (2.8), OMEGALUL (3.0), Kappa (0.8)
- **YouTube**: 😂 (2.5), 🤣 (2.8), 🔥 (2.0), ❤️ (1.5)
- **Kick**: Shares Twitch + platform-specific (kickPog, kickHype)

**Scoring:**
- Emote quality: Which emotes (PogChamp > Kappa)
- Emote density: What % of messages contain emotes
- Spam detection: Heavy emote spam filtering

### 3. **EngagementScorer** - Chat quality metrics
Analyzes engagement beyond just volume.

**Metrics:**
- **Chatter diversity**: Unique users vs total messages
- **Message quality**: Length, complexity
- **Conversations**: @ mentions, quick replies (<2s)
- **VIP participation**: Subs/VIPs/Mods = higher signal

### 4. **StreamingScorer** - Composite scoring system
Combines all signals for final highlight selection.

**Scoring formula:**
```python
final_score = (
    chat_spike * 0.30 +           # Activity vs baseline
    emote_quality * 0.25 +        # Emote types (PogChamp > Kappa)
    engagement * 0.20 +           # Diversity, message quality
    audio * 0.15 +                # Loudness, energy
    viewer_normalized * 0.10      # MPVS (if available)
)
```

**Output:** Score 0.0 - 10.0 per segment

---

## 🚀 Quick Start

### Basic usage (with chat file):

```python
from modules.streaming import create_scorer_from_chat

# Create scorer from chat JSON
scorer = create_scorer_from_chat(
    chat_json_path="path/to/chat.json",
    vod_duration=7200,  # 2 hours
    platform="twitch",   # or 'youtube', 'kick' (auto-detected if omitted)
    chat_delay_offset=10.0  # NEW v1.2.1: Account for stream delay (default: 10s)
)

# Score a segment (e.g., 10:30 - 11:00)
# NOTE: Scorer automatically looks ahead by delay_offset to catch delayed reactions
score, breakdown = scorer.score_segment(
    start_time=630,   # 10:30 in seconds
    end_time=660,     # 11:00
    audio_features={  # Optional
        'loudness': 85.0,
        'energy': 0.8,
        'spectral_flux': 0.6
    }
)

print(f"Score: {score:.2f}/10")
print(f"Breakdown: {breakdown}")
```

### Find top highlights:

```python
# Get top 10 highlights (min score 6.0)
highlights = scorer.get_top_highlights(
    segments=all_segments,
    top_n=10,
    min_score=6.0
)

for clip in highlights:
    print(f"⭐ {clip['t0']:.1f}s - Score: {clip['final_score']:.2f}")
```

### Detect chat spikes:

```python
from modules.streaming import ChatAnalyzer

analyzer = ChatAnalyzer("chat.json")

# Find spikes (3x above baseline)
spikes = analyzer.detect_spikes(
    window_size=30,        # 30-second windows
    spike_threshold=3.0,   # 3x baseline
    min_messages=10        # At least 10 messages
)

# Top 10 spikes
for timestamp, intensity, msg_count in spikes[:10]:
    mins = int(timestamp // 60)
    secs = int(timestamp % 60)
    print(f"{mins}:{secs:02d} - {intensity:.2f}x baseline ({msg_count} msgs)")
```

---

## 📁 Chat JSON Formats

### Twitch (Twitch Downloader)

**Download:**
```bash
TwitchDownloaderCLI -m chatdownload --id 1234567890 -o chat.json
```

**Format:**
```json
{
  "comments": [
    {
      "content_offset_seconds": 123.45,
      "commenter": {
        "display_name": "Viewer123"
      },
      "message": {
        "body": "KEKW message",
        "fragments": [
          {"text": "KEKW", "emoticon": {"emoticon_id": "..."}}
        ],
        "user_badges": [
          {"_id": "subscriber"}
        ]
      }
    }
  ]
}
```

### YouTube (yt-dlp)

**Download:**
```bash
yt-dlp --write-subs --skip-download https://youtube.com/watch?v=VIDEO_ID
# Or use chat-downloader:
chat_downloader https://youtube.com/watch?v=VIDEO_ID -o chat.json
```

**Format:**
```json
[
  {
    "timestamp": 123,
    "text": "Great moment!",
    "author": "ViewerName",
    "is_member": true
  }
]
```

### Kick (API/Browser Export)

**Format:**
```json
[
  {
    "created_at": "2025-01-15T20:02:03.000000Z",
    "content": "PogChamp",
    "sender": {
      "username": "kickviewer",
      "identity": {
        "badges": [
          {"type": "subscriber"}
        ]
      }
    }
  }
]
```

---

## ⏱️ Chat Delay Offset (v1.2.1)

### Why is delay offset important?

Streams have inherent delay between the streamer's action and chat's reaction:
- **Twitch**: 3-10 seconds (low-latency: 3-5s, normal: 8-10s)
- **YouTube**: 10-30 seconds (varies widely)
- **Kick**: 5-15 seconds

**The problem:** When chat explodes at timestamp T, the funny/exciting action actually happened at timestamp (T - delay).

**The solution:** `chat_delay_offset` makes the scorer look ahead in time to catch delayed reactions.

### How it works:

```python
# Without delay offset (WRONG):
# Segment [600, 630] → Chat messages [600, 630]
# Misses reactions that come at 631-640

# With delay offset=10s (CORRECT):
# Segment [600, 630] → Chat messages [600, 630+10]
# Captures both immediate AND delayed reactions

scorer = StreamingScorer(
    chat_analyzer=analyzer,
    chat_delay_offset=10.0  # Look ahead 10s for reactions
)
```

### Recommended values:

- **Twitch** (low-latency): 5s
- **Twitch** (normal): 10s
- **YouTube**: 15s
- **Kick**: 8s
- **Unknown**: 10s (safe default)

---

## ⚙️ Configuration

### Custom scoring weights:

```python
from modules.streaming import StreamingScorer, ChatAnalyzer

analyzer = ChatAnalyzer("chat.json")

scorer = StreamingScorer(
    chat_analyzer=analyzer,
    platform='twitch',
    weights={
        'chat_spike': 0.40,       # Increase chat importance
        'emote_quality': 0.30,
        'engagement': 0.20,
        'audio': 0.10,
        'viewer_normalized': 0.00  # Disable if no viewer data
    }
)
```

### Custom emote weights:

```python
from modules.streaming.emote_scorer import TWITCH_EMOTE_WEIGHTS

# Add custom emotes
TWITCH_EMOTE_WEIGHTS['MyCustomEmote'] = 2.5  # High value

# Or create custom scorer
from modules.streaming import EmoteScorer

scorer = EmoteScorer('twitch')
scorer.emote_weights['POGCRAZY'] = 3.0  # New emote
```

---

## 📊 Scoring Interpretation

### Final scores:
- **9.0 - 10.0**: 🔥 Peak moments (must-clip)
- **7.0 - 8.9**: ⭐ Great highlights
- **5.0 - 6.9**: ✅ Good moments
- **3.0 - 4.9**: 😐 Average
- **0.0 - 2.9**: 💤 Low value

### Component scores (each 0-10):

**Chat Spike:**
- 10.0 = 5x+ above baseline (massive hype)
- 8.0 = 3x above baseline
- 5.0 = Normal activity
- 2.0 = 0.5x baseline (dead chat)

**Emote Quality:**
- 10.0 = Heavy KEKW/PogChamp/OMEGALUL
- 7.0 = Good mix of emotes
- 5.0 = No emotes or neutral mix
- 3.0 = Spam emotes (Kappa, ResidentSleeper)

**Engagement:**
- 10.0 = High diversity, long messages, conversations
- 7.0 = Healthy discussion
- 5.0 = Normal chat
- 2.0 = Spam from few users

**Audio:**
- 10.0 = 90+ dB, high energy (shouting/hype)
- 7.0 = 80-90 dB (loud)
- 5.0 = 70-80 dB (normal)
- 3.0 = <70 dB (quiet)

**Viewer Normalized (MPVS):**
- 10.0 = 0.02+ messages/viewer/s (extremely active)
- 7.0 = 0.005-0.02 (active)
- 5.0 = 0.001-0.005 (normal)
- 3.0 = <0.001 (quiet relative to viewers)

---

## 🧪 Testing

### Test individual components:

```bash
# Test chat analyzer
python modules/streaming/chat_analyzer.py path/to/chat.json

# Test emote scorer
python modules/streaming/emote_scorer.py

# Test engagement scorer
python modules/streaming/engagement_scorer.py

# Test composite scorer
python modules/streaming/composite_scorer.py path/to/chat.json
```

### Expected output:
```
✅ Parsed 15234 messages from TWITCH
📊 Baseline: 2.35 msg/s

🔥 Top Spikes:
  1. 42:13 - 5.23x baseline (341 msgs)
  2. 1:15:42 - 4.87x baseline (298 msgs)
  3. 2:03:51 - 4.12x baseline (267 msgs)
```

---

## 🔧 Integration with Pipeline

### Use in custom pipeline:

```python
from modules.streaming import create_scorer_from_chat
from pipeline.processor import PipelineProcessor

# Create streaming scorer
scorer = create_scorer_from_chat("chat.json", vod_duration=7200)

# Override scoring in pipeline
class StreamingPipeline(PipelineProcessor):
    def __init__(self, config, chat_scorer):
        super().__init__(config)
        self.chat_scorer = chat_scorer

    def _score_segments(self, segments, features):
        # Use chat-based scoring instead of GPT
        scored = []
        for segment in segments:
            score, breakdown = self.chat_scorer.score_segment(
                segment['t0'],
                segment['t1'],
                audio_features=features.get(segment['id'])
            )
            segment['final_score'] = score
            scored.append(segment)
        return scored

# Run pipeline with chat scoring
pipeline = StreamingPipeline(config, scorer)
result = pipeline.process("stream_vod.mp4")
```

---

## 🐛 Troubleshooting

### Problem: "Unknown platform"
**Solution:** Manually specify platform:
```python
analyzer = ChatAnalyzer("chat.json", platform="twitch")
```

### Problem: Baseline is 0.0
**Cause:** No messages in chat JSON or malformed file
**Solution:** Check JSON format and message count:
```python
print(f"Messages loaded: {len(analyzer.messages)}")
```

### Problem: All scores are 5.0 (neutral)
**Cause:** No chat data provided to scorer
**Solution:** Ensure ChatAnalyzer is passed to StreamingScorer:
```python
scorer = StreamingScorer(chat_analyzer=analyzer)  # ← Must pass analyzer
```

### Problem: Emotes not detected
**Cause:** Different emote format than expected
**Solution:** Check emote extraction for your platform:
```python
for msg in analyzer.messages[:10]:
    print(f"{msg.message} → Emotes: {msg.emotes}")
```

---

## 📚 API Reference

### ChatAnalyzer

```python
class ChatAnalyzer:
    def __init__(chat_json_path, vod_duration=0, platform=None)
    def load_and_parse() -> List[ChatMessage]
    def detect_spikes(window_size=30, spike_threshold=3.0) -> List[Tuple]
    def get_messages_in_window(start, end) -> List[ChatMessage]
    def calculate_local_baseline(timestamp, lookback=300) -> float
    def get_statistics() -> Dict
```

### EmoteScorer

```python
class EmoteScorer:
    def __init__(platform='twitch')
    def score_messages(messages) -> float  # 0-10
    def score_emote_density(messages) -> float  # 0-10
    def detect_emote_spam(messages, threshold=0.7) -> bool
    def get_top_emotes(messages, top_n=5) -> List[Tuple]
    def score_composite(messages) -> float  # Quality + density
```

### EngagementScorer

```python
class EngagementScorer:
    def score_chatter_diversity(messages) -> float  # 0-10
    def score_message_quality(messages) -> float  # 0-10
    def detect_conversation_bursts(messages) -> float  # 0-10
    def score_vip_participation(messages) -> float  # 0-10
    def detect_spam_patterns(messages) -> bool
    def score_composite_engagement(messages) -> float  # Combined
    def get_engagement_breakdown(messages) -> Dict
```

### StreamingScorer

```python
class StreamingScorer:
    def __init__(chat_analyzer=None, platform='twitch', weights=None)
    def score_segment(start, end, audio=None, viewers=None) -> (float, Dict)
    def score_all_segments(segments, audio_list=None) -> List[Tuple]
    def get_top_highlights(segments, top_n=10, min_score=6.0) -> List[Dict]
    def print_score_report(start, end, audio=None)  # Debug
```

---

## 📝 Example: Full workflow

```python
from modules.streaming import create_scorer_from_chat

# 1. Load chat and create scorer
scorer = create_scorer_from_chat(
    chat_json_path="twitch_chat.json",
    vod_duration=7200  # 2 hours
)

# 2. Find chat spikes
spikes = scorer.chat_analyzer.detect_spikes(
    window_size=30,
    spike_threshold=2.5,
    min_messages=15
)

print(f"Found {len(spikes)} chat spikes")

# 3. Create segments around spikes (±15s)
segments = []
for spike_time, intensity, msg_count in spikes:
    segments.append({
        't0': spike_time - 15,
        't1': spike_time + 15,
        'duration': 30,
        'spike_intensity': intensity
    })

# 4. Score all segments
highlights = scorer.get_top_highlights(
    segments=segments,
    top_n=10,
    min_score=6.5
)

# 5. Print results
print(f"\n🎬 Top {len(highlights)} Highlights:")
for i, clip in enumerate(highlights, 1):
    mins = int(clip['t0'] // 60)
    secs = int(clip['t0'] % 60)
    print(f"{i}. {mins}:{secs:02d} - Score: {clip['final_score']:.2f}/10")

    # Optional: Print detailed breakdown
    scorer.print_score_report(clip['t0'], clip['t1'])
```

---

## 🎯 Best Practices

1. **Always provide VOD duration** for accurate baseline calculation
2. **Use 30-60s windows** for spike detection (too short = noisy, too long = miss moments)
3. **Set spike threshold 2.5-3.5x** (lower = more clips, higher = only peak moments)
4. **Combine with audio features** for best results (chat + audio = 🔥)
5. **Test different platforms separately** - each has different chat dynamics
6. **Cache scored segments** - scoring is expensive, reuse results
7. **Filter spam** - use engagement scorer to remove low-quality moments

---

## 🚀 Performance

- **Chat parsing**: ~1s for 10k messages
- **Spike detection**: ~0.5s for 2h VOD
- **Segment scoring**: ~10ms per segment
- **Full pipeline**: ~2-5s for typical stream (depends on message count)

**Optimization tips:**
- Use larger window sizes (60s vs 30s) for faster processing
- Enable caching in StreamingScorer (enabled by default)
- Pre-filter segments before scoring (remove obvious low-value)

---

**Version**: 1.2.1 (Added delay offset support)
**Last Updated**: 2025-11-25
**Supported Platforms**: Twitch, YouTube, Kick
```
