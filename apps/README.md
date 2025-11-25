# 🎬 Apps - Domain-Specific Applications

Ten folder zawiera **osobne aplikacje GUI** dla różnych typów contentu.

Każda aplikacja używa tego samego **core pipeline** ale z różnymi **strategiami scoringu**.

---

## 📊 Dostępne Aplikacje

### 1. **sejm_app.py** - Political Highlights
```bash
python apps/sejm_app.py
```

**Przeznaczenie:** Transmisje polityczne (Sejm, konferencje prasowe, debaty)

**Scoring oparty na:**
- 🤖 GPT-4o-mini semantic analysis (70%)
- 🔊 Acoustic features (głośność, energia) (10%)
- 🔑 Keywords (nazwiska, kontrowersyjne słowa) (10%)
- 👥 Speaker changes (wymiana zdań) (10%)

**Funkcje:**
- ✅ URL download (YouTube)
- ✅ Local file processing
- ✅ Smart Splitter (multi-part dla długich materiałów >1h)
- ✅ YouTube auto-upload z premiering
- ✅ Shorts generation (9:16)
- ✅ Wszystkie opcje scoring/selection w GUI

**Najlepsze dla:**
- Posiedzenia Sejmu/Senatu
- Konferencje prasowe polityków
- Debaty polityczne
- Wystąpienia publiczne

---

### 2. **stream_app.py** - Streaming Highlights ✅ ACTIVE (v1.2.1)
```bash
python apps/stream_app.py
```

**Przeznaczenie:** Streamy Twitch/YouTube/Kick Gaming/Just Chatting

**Scoring oparty na:** *(IMPLEMENTED v1.2.1)*
- 💬 Chat activity spikes (30%) - baseline normalization
- 😂 Emote quality (25%) - platform-specific weights
- 👥 Engagement (20%) - diversity, message quality, VIP participation
- 🔊 Audio features (15%) - loudness, energy, spectral flux
- 📊 Viewer normalized (10%) - MPVS (if available)

**Status:** ✅ **FUNCTIONAL**
- ✅ Chat analysis - Multi-platform (Twitch/YouTube/Kick)
- ✅ Emote detection - Platform-specific scoring
- ✅ Baseline normalization - Spike detection (3x threshold)
- ✅ Engagement scoring - Diversity, quality, conversations
- ✅ **Delay offset** - Accounts for stream delay (v1.2.1)
- ⏳ Twitch API integration - Planned for v1.3

**v1.2 Features:**
- Chat-based scoring replaces GPT semantic analysis
- Upload chat JSON (Twitch Downloader, yt-dlp, Kick export)
- Auto-detection platformy (Twitch/YouTube/Kick)
- Fallback to audio-only jeśli brak chatu
- Real-time chat statistics display
- Threading with cancel button

**v1.2.1 Features (NEW):**
- ⏱️ **Chat delay offset** - Captures action BEFORE chat reaction
- Stream delay: Twitch 3-10s, YouTube 10-30s, Kick 5-15s
- Configurable in `config.yml` (streaming.chat_delay_offset)
- Separate `min_clip_duration` (45s main) vs `min_short_duration` (20s Shorts)

---

## 🔄 Różnice między aplikacjami

| Feature                  | sejm_app.py | stream_app.py |
|--------------------------|-------------|---------------|
| GPT Scoring              | ✅ TAK      | ❌ NIE        |
| Chat Analysis            | ❌ NIE      | ✅ TAK (v1.2) |
| Emote Detection          | ❌ NIE      | ✅ TAK (v1.2) |
| Baseline Normalization   | ❌ NIE      | ✅ TAK (v1.2) |
| Engagement Scoring       | ❌ NIE      | ✅ TAK (v1.2) |
| Smart Splitter           | ✅ TAK      | ❌ NIE        |
| YouTube Upload           | ✅ TAK      | 🚧 Planned    |
| Shorts Generation        | ✅ TAK      | ✅ TAK        |
| Scoring Weights UI       | ✅ TAK      | ⏳ Simple     |
| Multi-Platform Support   | ❌ NIE      | ✅ TAK (Tw/YT/Kick) |

---

## 🚀 Uruchomienie

### Windows
```powershell
# Aktywuj venv
venv\Scripts\activate

# Sejm
python apps\sejm_app.py

# Streaming
python apps\stream_app.py
```

### Linux/Mac
```bash
# Aktywuj venv
source venv/bin/activate

# Sejm
python apps/sejm_app.py

# Streaming
python apps/stream_app.py
```

---

## 🏗️ Architektura (Planned Refactor)

```
Sejm-Highlights-Final/
├── apps/                    # ← DOMAIN-SPECIFIC UIs
│   ├── sejm_app.py         # Politics GUI
│   └── stream_app.py       # Streaming GUI
│
├── core/                    # ← SHARED ENGINE (planned)
│   ├── audio/              # Extraction, VAD, normalization
│   ├── transcription/      # Whisper ASR
│   ├── features/           # Acoustic, prosodic, lexical
│   └── export/             # Video composer, subtitles
│
├── modules/                 # ← PLUGGABLE SCORERS (planned)
│   ├── politics/           # GPT-based controversy scoring
│   └── streaming/          # Chat-based excitement scoring
│
└── pipeline/                # ← CURRENT MONOLITH
    ├── processor.py        # Orchestrator
    ├── stage_01_ingest.py
    ├── stage_02_vad.py
    ├── ...
    └── stage_10_shorts.py
```

**Roadmap:**
1. ✅ **Phase 1:** Create apps/ folder (DONE)
2. ⏳ **Phase 2:** Extract core logic to core/
3. ⏳ **Phase 3:** Create modules/politics/
4. ✅ **Phase 4:** Create modules/streaming/ (DONE v1.2)
5. ⏳ **Phase 5:** Full refactor to modular architecture

---

## 📝 Development Notes

### Adding New App

1. Create `apps/my_app.py`
2. Import parent directory:
   ```python
   import sys
   from pathlib import Path
   sys.path.insert(0, str(Path(__file__).parent.parent))
   ```
3. Import pipeline:
   ```python
   from pipeline.processor import PipelineProcessor
   from pipeline.config import Config
   ```
4. Implement custom scoring logic (future: use modules/)

### Testing Apps

```bash
# Test sejm_app
python apps/sejm_app.py

# Test stream_app
python apps/stream_app.py

# Run both in parallel (for testing)
python apps/sejm_app.py & python apps/stream_app.py
```

---

## 🐛 Known Issues

1. **stream_app.py** - Viewer count normalization requires chat JSON with metadata
   - Workaround: Falls back to baseline normalization (works great!)
   - Enhancement: Extract viewer count from Twitch API in v1.3

2. **Both apps** - Share same config.yml
   - Workaround: Edit config.yml before switching apps
   - Fix: Separate configs per app (planned v2.0)

3. **stream_app.py** - YouTube upload not implemented yet
   - Workaround: Use sejm_app.py for auto-upload
   - Fix: Planned for v1.3

---

## 📞 Support

- Sejm app issues: [GitHub Issues](https://github.com/AdamStankiewic/Sejm-Highlights-Final/issues)
- Streaming app: Coming soon

---

**Last Updated:** 2025-11-25
**Version:** 2.0.0 (sejm_app) | 1.2.1 (stream_app)
