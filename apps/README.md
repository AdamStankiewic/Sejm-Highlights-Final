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

### 2. **stream_app.py** - Streaming Highlights ⚠️ BETA
```bash
python apps/stream_app.py
```

**Przeznaczenie:** Streamy Twitch/YouTube Gaming/Just Chatting

**Scoring oparty na:** *(planned)*
- 💬 Chat activity spikes (40%)
- 😂 Emote density (KEKW, LUL, PogChamp) (25%)
- 📊 Clip count from Twitch API (20%)
- 🔊 Audio loudness (15%)

**Status:** 🚧 **Under Development**
- Chat analysis - **TODO**
- Emote detection - **TODO**
- Twitch API integration - **TODO**

Obecnie używa tego samego pipeline co `sejm_app.py`.

**Planowane dla v1.1:**
- Upload chat JSON (z Twitch Downloader)
- Automatyczna detekcja emote spamów
- Integration z Twitch Clips API
- Streamlined UX dla streamerów

---

## 🔄 Różnice między aplikacjami

| Feature                  | sejm_app.py | stream_app.py |
|--------------------------|-------------|---------------|
| GPT Scoring              | ✅ TAK      | ❌ NIE        |
| Chat Analysis            | ❌ NIE      | 🚧 Planned    |
| Emote Detection          | ❌ NIE      | 🚧 Planned    |
| Smart Splitter           | ✅ TAK      | ❌ NIE        |
| YouTube Upload           | ✅ TAK      | 🚧 Planned    |
| Shorts Generation        | ✅ TAK      | ✅ TAK        |
| Scoring Weights UI       | ✅ TAK      | ⏳ Simple     |

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
4. ⏳ **Phase 4:** Create modules/streaming/
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

1. **stream_app.py** - Chat analysis not yet implemented
   - Workaround: Use sejm_app.py for now
   - Fix: Implement modules/streaming/ scorer

2. **Both apps** - Share same config.yml
   - Workaround: Edit config.yml before switching apps
   - Fix: Separate configs per app

---

## 📞 Support

- Sejm app issues: [GitHub Issues](https://github.com/AdamStankiewic/Sejm-Highlights-Final/issues)
- Streaming app: Coming soon

---

**Last Updated:** 2025-11-24
**Version:** 2.0.0 (sejm_app) | 1.0.0-beta (stream_app)
