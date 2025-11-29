# Stream App Examples

This folder contains example files for testing the Stream Highlights AI application.

## 📄 sample_chat.json

Example chat file in **Twitch Downloader** format.

### Format Structure

```json
{
  "comments": [
    {
      "content_offset_seconds": 120.5,  // Timestamp in seconds
      "message": {
        "body": "KEKW",                  // Message text
        "user_color": "#FF0000"           // User color (optional)
      },
      "commenter": {
        "display_name": "viewer123"       // Username
      }
    }
  ],
  "video": {
    "duration": 600,                      // Video duration (optional)
    "title": "Stream Title"               // Stream title (optional)
  }
}
```

### Highlight Moments in Sample

This sample chat contains **3 highlight moments** with emote spam:

1. **~120s (2:00)** - KEKW spam (funny moment)
   - 10 messages in 4 seconds
   - Multiple chatters reacting with KEKW, OMEGALUL, LULW

2. **~300s (5:00)** - PogChamp spam (exciting play)
   - 12 messages in 3.6 seconds
   - PogChamp, POG, POGGERS spam

3. **~540s (9:00)** - monkaS spam (tense moment)
   - 5 messages in 1.5 seconds
   - monkaS, monkaW reactions

### Testing Workflow

1. **Load in GUI**:
   ```
   stream_app/app.py → 💬 Wybierz Chat JSON → examples/sample_chat.json
   ```

2. **Expected Behavior**:
   - Chat analyzer should detect **3 spike regions**
   - Baseline message rate: ~0.05 msg/s
   - Peak rates: ~2.5-3.5 msg/s during spam
   - Delay offset: -10s (chat reactions come 10s after action)

3. **Top Clips** (with 10s delay offset):
   - Clip 1: ~110-120s (KEKW moment)
   - Clip 2: ~290-300s (PogChamp moment)
   - Clip 3: ~530-540s (monkaS moment)

### How to Download Real Chat

#### Twitch (using Twitch Downloader CLI)

```bash
# Download chat
TwitchDownloaderCLI chatdownload -u https://twitch.tv/videos/123456789 -o chat.json

# Format: Twitch Downloader (same as sample)
```

Download: https://github.com/lay295/TwitchDownloader

#### YouTube Live (using yt-dlp)

```bash
# Download live chat replay
yt-dlp --skip-download --write-subs --sub-format json3 https://youtube.com/watch?v=VIDEO_ID

# Output: VIDEO_ID.live_chat.json
```

Note: YouTube format is different - use ChatAnalyzer to parse both formats.

## 🎵 Copyright Detection Testing

The sample chat can be used with any short video to test copyright detection:

1. **With Music**: Use a video with background music
   - Should detect copyrighted tracks (if using real AudD API)
   - Should flag clips for vocal isolation

2. **Without Music**: Use a video with only voice/game sounds
   - Should not detect music
   - Clips exported without filtering

### Example Test Workflow

```bash
# 1. Get a short test video (~10 min)
yt-dlp -f worst "https://youtube.com/watch?v=TEST_VIDEO" -o test_vod.mp4

# 2. Load in stream_app GUI:
#    - VOD: test_vod.mp4
#    - Chat: examples/sample_chat.json
#    - Enable copyright detection
#    - Enter AudD API key

# 3. Generate highlights
#    - Should create 3 clips (at highlight moments)
#    - Copyright scan runs on selected clips
#    - Vocal isolation applied if music detected
```

## 📝 Notes

- **sample_chat.json** is designed for **10-minute videos**
- Scale timestamps if your test video is longer/shorter
- Emote spam sections are intentionally exaggerated for testing
- Real streams have more variable message rates and fewer clear spikes
