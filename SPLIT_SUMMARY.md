# Project Split Summary

**Date:** 2025-11-29
**Reason:** Separate sejm_app and stream_app into independent projects for easier maintenance and development

---

## 📁 New Structure

```
Sejm-Highlights-Final/
├── sejm_app/              # Sejm Parliament highlights
│   ├── app.py
│   ├── video_downloader.py
│   ├── config.yml         # Sejm-specific config
│   ├── README.md          # Sejm-specific docs
│   ├── requirements.txt   # Sejm dependencies
│   ├── .gitignore
│   ├── pipeline/          # Full pipeline (GPT scoring)
│   └── models/
│
├── stream_app/            # Twitch/YouTube stream highlights
│   ├── app.py
│   ├── video_downloader.py
│   ├── config.yml         # Streaming-specific config
│   ├── README.md          # Streaming-specific docs
│   ├── requirements.txt   # Streaming dependencies (+requests)
│   ├── .gitignore
│   ├── pipeline/          # Full pipeline (chat scoring)
│   ├── modules/
│   │   └── streaming/     # Chat analyzer, music detector
│   └── examples/
│
├── pipeline/              # Original (shared reference)
├── config.yml             # Original
└── README.md              # Original (now points to split apps)
```

---

## 🔄 Key Differences

| Feature | sejm_app | stream_app |
|---------|----------|------------|
| **Purpose** | Polish Parliament debates | Gaming/casual streams |
| **Scoring** | GPT AI Semantic | Chat activity (KEKW, PogChamp) |
| **Config** | No `StreamingConfig` | Has `StreamingConfig` |
| **Dependencies** | OpenAI | requests (AudD API) |
| **Clip Duration** | 90-180s (long speeches) | 30-90s (quick reactions) |
| **Target Length** | 15 min | 10 min |
| **Smart Merge** | Conservative | Aggressive |
| **Copyright** | N/A (public domain) | DMCA detection + vocal isolation |
| **Keywords** | Political terms | None (generic) |

---

## ✅ What Was Done

### 1. Folder Structure
- Created `sejm_app/` and `stream_app/` folders
- Copied all pipeline stages to both apps
- Created separate `models/`, `modules/` folders

### 2. Configuration Files
- **sejm_app/config.yml** - Removed `streaming` section, kept Sejm-specific settings
- **stream_app/config.yml** - Added `streaming` section with copyright detection settings

### 3. Code Changes
- **sejm_app/pipeline/config.py** - Removed `StreamingConfig` class
- **stream_app/pipeline/config.py** - Kept `StreamingConfig`, added initialization in `__post_init__`

### 4. Documentation
- Created separate `README.md` for each app with specific installation instructions
- **sejm_app/README.md** - Focus on Polish Parliament, GPT scoring, Smart Splitter
- **stream_app/README.md** - Focus on streaming, chat analysis, copyright detection

### 5. Dependencies
- **sejm_app/requirements.txt** - Unchanged (openai for GPT)
- **stream_app/requirements.txt** - Added `requests>=2.31.0` for AudD API

### 6. Gitignore
- Created `.gitignore` for both apps
- `stream_app/.gitignore` - Also ignores `*.mp4`, `*.mkv`, `chat.json` (stream-specific)

---

## 🚀 How to Use

### Sejm App
```bash
cd sejm_app
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

### Stream App
```bash
cd stream_app
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

---

## 📦 What's Shared

Both apps share the same **pipeline architecture**:
- Stage 01-10 structure
- Video processing logic
- FFmpeg integration
- YouTube upload capability

But each app has **customized stages**:
- **sejm_app**: `stage_05_scoring_gpt.py` (GPT AI scoring)
- **stream_app**: `stage_05_scoring_streaming.py` (Chat scoring)
- **stream_app**: `stage_06b_copyright.py` (Copyright detection) **[TO BE IMPLEMENTED]**

---

## 🔮 Future Development

Each app can now be developed independently:

### Sejm App
- Improve political keyword detection
- Better politician name recognition
- Multi-part premiere scheduling
- Enhanced Smart Splitter

### Stream App
- Implement copyright detection stage
- Add vocal isolation post-processing
- Support more chat formats (Kick, Facebook Gaming)
- Real-time processing (live stream highlights)

---

## ⚠️ Migration Notes

If you have **existing code or configs** that reference the old structure:

1. **Update imports** - No parent directory imports needed now
2. **Update config paths** - Point to `sejm_app/config.yml` or `stream_app/config.yml`
3. **Separate venvs** - Each app should have its own virtual environment
4. **No shared state** - Apps are completely independent

---

## 📊 Project Status

- ✅ Folder structure created
- ✅ Files copied and organized
- ✅ Configs split and customized
- ✅ README documentation written
- ✅ Dependencies separated
- ✅ Gitignore files created
- ⏳ Copyright detection stage (to be implemented)
- ⏳ Testing both apps independently

---

**Next Steps:**
1. Test sejm_app runs independently
2. Test stream_app runs independently
3. Implement `stage_06b_copyright.py` for stream_app
4. Update main README.md to point to split apps
