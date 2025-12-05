# 🧹 Plan Uporządkowania i Stabilizacji Projektu

**Data utworzenia:** 2025-12-05
**Status:** DRAFT - Do zatwierdzenia

---

## 📋 SPIS TREŚCI

1. [Cleanup Lokalny (Twój Folder)](#1-cleanup-lokalny-twój-folder)
2. [Cleanup Repository (Git)](#2-cleanup-repository-git)
3. [Checklist Funkcjonalności](#3-checklist-funkcjonalności)
4. [Strategia Rozwoju](#4-strategia-rozwoju)

---

## 1. CLEANUP LOKALNY (Twój Folder)

### ❌ DO USUNIĘCIA (Lokalne Foldery)

```bash
# Foldery auto-generated / cache
__pycache__/          # Python bytecode cache
.ruff_cache/          # Ruff linter cache

# Foldery robocze (można odtworzyć)
output/               # Wyniki przetwarzania
temp/                 # Pliki tymczasowe
downloads/            # Pobrane pliki (można odtworzyć)

# Virtual environments (NIGDY nie commituj do git!)
venv/                 # Python venv
venv311/              # Python 3.11 venv
```

**Polecenia do wykonania:**
```bash
# W folderze projektu:
cd "C:\Users\adams\Desktop\Sejm Highlights Final"

# Usuń cache i temp (BEZPIECZNE)
rm -rf __pycache__
rm -rf .ruff_cache
rm -rf temp/*         # Zachowaj folder, usuń zawartość
rm -rf output/*       # Zachowaj folder, usuń zawartość

# Usuń venv (możesz potem odtworzyć z requirements.txt)
# UWAGA: Najpierw skopiuj requirements.txt w bezpieczne miejsce!
rm -rf venv
rm -rf venv311
```

### ⚠️ SPRAWDŹ PRZED USUNIĘCIEM

```bash
# Te foldery mogą zawierać ważne dane:
downloads/            # Sprawdź czy nie ma cennych plików
models/               # Modele Whisper/Silero (duże, ale potrzebne)
```

---

## 2. CLEANUP REPOSITORY (Git)

### ❌ DO USUNIĘCIA Z REPO (Pliki tracked, ale niepotrzebne)

**Development Scripts (nie używane w production):**
- `APP_URL_INTEGRATION_SNIPPET.py` - snippet integracyjny (dev only)
- `check_srt.py` - narzędzie dev do sprawdzania SRT
- `finish_processing.py` - prawdopodobnie stary dev tool
- `list_youtube_channels.py` - dev tool do listowania kanałów
- `quick_export.py` - dev shortcut (nie część pipeline)
- `regenerate_hardsub.py` - dev tool do regeneracji napisów
- `monitor_gpu.py` - dev monitoring tool
- `test_correct_channel.py` - test script
- `test_youtube_auth.py` - test script

**Duplikaty:**
- `requirements_clean.txt` - jeśli jest duplikatem `requirements.txt`

### ✅ DO ZACHOWANIA W REPO

**Core aplikacji:**
- `app.py` - główna aplikacja GUI ✅
- `setup.py` - instalator ✅
- `video_downloader.py` - downloader YouTube/Twitch ✅
- `config.yml` - konfiguracja domyślna ✅
- `requirements.txt` - dependencies ✅

**Pipeline:**
- `pipeline/*.py` - wszystkie stage'y (01-10 + chat_analysis) ✅
- `pipeline/config.py` - konfiguracja ✅
- `pipeline/processor.py` - główny procesor ✅
- `pipeline/smart_splitter.py` - multi-part splitter ✅

**Dokumentacja:**
- `README.md` ✅
- `.gitignore` ✅

**Modele (folder):**
- `models/__init__.py` ✅

### 🔒 KRYTYCZNE: Sprawdź .gitignore

**Te pliki NIE MOGĄ być w repo (secrets!):**
```bash
# Sprawdź czy te pliki NIE SĄ w git:
git ls-files | grep -E "(client_secret|youtube_token|\.env)"

# Jeśli znajdzie coś - NATYCHMIAST usuń z historii:
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch client_secret.json youtube_token.json .env" \
  --prune-empty --tag-name-filter cat -- --all
```

### 📦 Polecenia Cleanup Git

**KROK 1: Przenieś dev tools do folderu `dev/`**
```bash
mkdir dev
git mv APP_URL_INTEGRATION_SNIPPET.py dev/
git mv check_srt.py dev/
git mv finish_processing.py dev/
git mv list_youtube_channels.py dev/
git mv quick_export.py dev/
git mv regenerate_hardsub.py dev/
git mv monitor_gpu.py dev/
git mv test_correct_channel.py dev/
git mv test_youtube_auth.py dev/

git commit -m "chore: Move development tools to dev/ folder"
```

**KROK 2: Dodaj `dev/` do .gitignore (opcjonalnie)**
```bash
echo "" >> .gitignore
echo "# Development tools (not needed in production)" >> .gitignore
echo "dev/" >> .gitignore

git add .gitignore
git commit -m "chore: Ignore dev/ folder in future commits"
```

**KROK 3: Dodaj brakujące pozycje do .gitignore**
```bash
cat >> .gitignore << 'EOF'

# Project-specific
output/
temp/
downloads/
models/*.pt
models/*.bin
venv311/

# Development
dev/
*.swp
*.swo
*~
.DS_Store
Thumbs.db

# IDE
.vscode/
.idea/
*.code-workspace

EOF

git add .gitignore
git commit -m "chore: Improve .gitignore with project-specific patterns"
```

---

## 3. CHECKLIST FUNKCJONALNOŚCI

### 🎯 CORE FEATURES (Muszą działać w 100%)

#### **Pipeline Stages**

- [ ] **Stage 01: Audio Ingest**
  - [ ] Ekstrakcja audio z video (FFmpeg hwaccel)
  - [ ] Normalizacja głośności (EBU R128)
  - [ ] GPU hardware decoding (`-hwaccel cuda`)

- [ ] **Stage 02: VAD (Voice Activity Detection)**
  - [ ] Silero VAD na GPU
  - [ ] Detekcja segmentów mowy
  - [ ] Min/max duration constraints

- [ ] **Stage 03: Transcribe**
  - [ ] Faster-Whisper na GPU
  - [ ] Transkrypcja polskich nazwisk (initial prompt)
  - [ ] Batch processing dla performance

- [ ] **Stage 04: Acoustic Features**
  - [ ] GPU-accelerated feature extraction (torchaudio + CUDA)
  - [ ] RMS, spectral centroid, spectral flux, ZCR
  - [ ] Keyword extraction (spaCy NER)

- [ ] **Stage 05: AI Scoring (GPT)**
  - [ ] Pre-filtering (top 40 candidates)
  - [ ] GPT-4o-mini semantic analysis
  - [ ] Composite scoring (acoustic + keyword + semantic + speaker_change)
  - [ ] **NOWE:** Chat analysis integration (Twitch/YouTube/Kick)
  - [ ] Chat lag compensation (5s przed spike)
  - [ ] Emote analysis (90+ emotes)

- [ ] **Stage 06: Selection**
  - [ ] Tryb Sejm (długie klipy, debaty)
  - [ ] Tryb Stream (krótkie klipy, viral moments)
  - [ ] Diversity filtering (temporal spread)
  - [ ] Target duration enforcement

- [ ] **Stage 07: Export**
  - [ ] Clip extraction z FFmpeg
  - [ ] GPU encoding (h264_nvenc, preset p5)
  - [ ] Hardsub generation (SRT + ASS)
  - [ ] Transitions (fade in/out)

- [ ] **Stage 08: Thumbnail**
  - [ ] Best frame extraction (blur/brightness check)
  - [ ] Clickbait text overlay (3 styles: center, top_bottom, split)
  - [ ] Image enhancement (contrast, saturation, sharpness)
  - [ ] YouTube 1280x720 output

- [ ] **Stage 09: YouTube Upload**
  - [ ] OAuth2 authentication
  - [ ] Video upload z metadata
  - [ ] Scheduled premieres
  - [ ] Privacy settings (unlisted/private/public)
  - [ ] Thumbnail upload

- [ ] **Stage 10: Shorts Generation**
  - [ ] Auto template detection (face detection via MediaPipe)
  - [ ] 5 templates: simple, pip_modern, classic_gaming, irl_fullface, dynamic_speaker
  - [ ] 9:16 aspect ratio conversion
  - [ ] GPU encoding (NVENC)

#### **Smart Splitter (Multi-Part Videos)**

- [ ] Auto-detect długość video (>1h)
- [ ] Podział na części (~15min każda)
- [ ] Równa dystrybucja klipów między części
- [ ] Auto-generowane tytuły z numerami części
- [ ] Scheduled premieres (co dzień, custom hour)
- [ ] Osobne thumbnails dla każdej części

#### **GUI (app.py)**

- [ ] Mode selection: Sejm vs Stream
- [ ] File input (browse + drag-drop)
- [ ] URL download (YouTube/Twitch via yt-dlp)
- [ ] **NOWE:** Chat.json upload (dla Stream mode)
- [ ] Config adjustments (duration, clips, model)
- [ ] Progress tracking (stage-by-stage)
- [ ] Results preview (clips list, YouTube links)
- [ ] Shorts template selector

#### **GPU Optimization**

- [ ] Stage 01: `-hwaccel cuda` (hardware decoding)
- [ ] Stage 04: torchaudio CUDA (audio features)
- [ ] Stage 07: `h264_nvenc` (hardware encoding)
- [ ] Stage 10: `h264_nvenc` (shorts encoding)
- [ ] **Performance:** ~2x speedup (63min → 30-35min for 12h video)
- [ ] **GPU Utilization:** 80-85% (was 30%)

#### **Chat Analysis (Stream Mode)**

- [ ] Auto-detect platform (Twitch/YouTube/Kick)
- [ ] Parse chat.json (TwitchDownloader, yt-dlp, chat-downloader)
- [ ] Chat lag compensation (5s przed spike)
- [ ] Spike detection (2x baseline)
- [ ] Emote analysis (KEKW, OMEGALUL, Pog, etc.)
- [ ] Velocity score (momentum tracking)
- [ ] Integration with Stage 05 (15% weight)

---

### 🧪 TESTING CHECKLIST

#### **Test Case 1: Sejm Mode (12h video)**
- [ ] Pobierz 12h transmisję Sejmu
- [ ] Uruchom w trybie "Sejm Highlights"
- [ ] Sprawdź Smart Splitter (podział na ~5 części)
- [ ] Zweryfikuj thumbnails (wszystkie części)
- [ ] Sprawdź scheduled premieres
- [ ] Verify GPU utilization (80%+)

#### **Test Case 2: Stream Mode (3h gaming stream)**
- [ ] Pobierz 3h stream Twitch
- [ ] Pobierz chat.json (TwitchDownloader)
- [ ] Uruchom w trybie "Stream Highlights"
- [ ] Załaduj chat.json
- [ ] Sprawdź chat spike detection
- [ ] Zweryfikuj emote analysis w logach
- [ ] Sprawdź shorts generation (5 templates)

#### **Test Case 3: YouTube Shorts**
- [ ] Gaming stream (webcam detection → pip_modern)
- [ ] IRL stream (face detection → irl_fullface)
- [ ] Sejm (no faces → simple)
- [ ] Verify 9:16 aspect ratio
- [ ] Check NVENC encoding

#### **Test Case 4: Error Handling**
- [ ] Brak OPENAI_API_KEY (fallback scoring)
- [ ] Brak chat.json (normal scoring)
- [ ] Brak YouTube credentials (skip Stage 09)
- [ ] Corrupted video file
- [ ] Network timeout podczas download

---

## 4. STRATEGIA ROZWOJU

### 🌳 Branch Strategy (Git Flow)

```
main (production-ready)
  ├─ stabilization/v1.0 (CURRENT: cleanup + bug fixes)
  │   ├─ fix/chat-analysis-gui
  │   ├─ fix/smart-splitter-thumbnails
  │   └─ chore/cleanup-dev-tools
  │
  ├─ feature/chat-velocity-v2 (FUTURE)
  ├─ feature/multi-language-support (FUTURE)
  └─ feature/real-time-preview (FUTURE)
```

### 📅 Development Phases

#### **PHASE 1: STABILIZATION (OBECNA FAZA) ✅**
**Branch:** `stabilization/v1.0`
**Timeline:** 1-2 tygodnie
**Cel:** Stabilny, production-ready pipeline

**Tasks:**
1. ✅ GPU optimization (DONE)
2. ✅ Chat analysis (DONE)
3. ✅ Stage 08 thumbnail fix (DONE)
4. 🔄 Cleanup dev tools (IN PROGRESS)
5. ⬜ Testing checklist (wszystkie test cases)
6. ⬜ Bug fixes z testów
7. ⬜ Documentation update (README + user guide)

**Exit Criteria:**
- Wszystkie test cases PASS
- Zero critical bugs
- GPU utilization >80%
- README zaktualizowane

---

#### **PHASE 2: POLISH & OPTIMIZATION**
**Branch:** `feature/polish-v1.1`
**Timeline:** 1 tydzień
**Cel:** UI/UX improvements, performance tweaks

**Potencjalne Features:**
- Better progress indicators (estimated time remaining)
- Batch processing (wiele plików naraz)
- Config presets (Gaming, IRL, Podcast, Politics)
- Advanced chat filters (spam detection, bot filtering)
- Export formats (MP4, MKV, WebM)

---

#### **PHASE 3: ADVANCED FEATURES**
**Branch:** `feature/advanced-v2.0`
**Timeline:** 2-3 tygodnie
**Cel:** Nowe funkcjonalności

**Ideas:**
- Real-time preview (podgląd klipów przed export)
- Multi-language support (EN, DE, ES transcription)
- Cloud processing (AWS/GCP integration)
- AI thumbnail generation (DALL-E 3, Stable Diffusion)
- Advanced analytics (clip performance tracking)
- Webhook notifications (Discord, Slack)
- Clips database (SQLite, search & filter)

---

### 🔧 Workflow Recommendations

**1. Feature Development:**
```bash
# Start nowego feature
git checkout main
git pull origin main
git checkout -b feature/nazwa-feature

# Praca...
git commit -m "feat: opis"

# Przed merge - rebase na main
git fetch origin
git rebase origin/main

# Create PR
git push origin feature/nazwa-feature
```

**2. Bug Fixes:**
```bash
# Hotfix z main
git checkout main
git checkout -b fix/nazwa-bug

# Fix...
git commit -m "fix: opis"

# Merge ASAP
git push origin fix/nazwa-bug
```

**3. Testing Workflow:**
```bash
# Local testing
pytest tests/
python -m pipeline.test_pipeline

# Integration testing
python app.py  # Manual GUI testing

# Performance testing
python benchmark.py  # Measure GPU util, time, memory
```

---

### 📊 Success Metrics

**Stabilization Phase:**
- ✅ All test cases PASS
- ✅ GPU utilization >80%
- ✅ Processing time <35min for 12h video
- ✅ Zero crashes w 10 test runs
- ✅ Documentation completeness >90%

**Production Ready:**
- ✅ User guide published
- ✅ Installation script tested (Windows/Linux)
- ✅ Example configs provided
- ✅ Demo video created
- ✅ GitHub release tagged (v1.0.0)

---

## 🚀 IMMEDIATE NEXT STEPS

### Priorytet 1: Cleanup (Dzisiaj)
1. [ ] Usuń lokalne foldery (cache, venv)
2. [ ] Przenieś dev tools do `dev/`
3. [ ] Update `.gitignore`
4. [ ] Commit cleanup changes

### Priorytet 2: Testing (Ten Tydzień)
1. [ ] Wykonaj Test Case 1 (Sejm 12h)
2. [ ] Wykonaj Test Case 2 (Stream + chat.json)
3. [ ] Wykonaj Test Case 3 (Shorts)
4. [ ] Wykonaj Test Case 4 (Error handling)
5. [ ] Dokumentuj wszystkie bugi

### Priorytet 3: Bug Fixes (Następny Tydzień)
1. [ ] Fix bugs z testów
2. [ ] Performance optimization (jeśli potrzebne)
3. [ ] Documentation update

### Priorytet 4: Release (Za 2 Tygodnie)
1. [ ] Tag v1.0.0
2. [ ] GitHub Release Notes
3. [ ] Demo video
4. [ ] User guide PDF

---

## 📝 NOTES & CONSIDERATIONS

**Pytania do rozważenia:**
1. Czy chcesz zachować `dev/` folder w repo czy całkowicie usunąć?
2. Czy potrzebujesz CI/CD (GitHub Actions dla auto-testing)?
3. Czy planujesz public release (PyPI package)?
4. Jakie platformy są priorytetem? (Windows? Linux? Mac?)

**Bezpieczeństwo:**
- ⚠️ KRYTYCZNE: Upewnij się że `client_secret.json`, `youtube_token.json`, `.env` NIE SĄ w git!
- Rozważ użycie environment variables zamiast `.env` file
- Dodaj GitHub Secrets dla CI/CD

**Performance:**
- Rozważ batch processing dla Stage 04 (2-3x additional speedup)
- Możliwe multi-GPU support dla bardzo długich video
- Memory optimization dla 24h+ streams

---

**AUTHOR:** Claude (AI Assistant)
**LAST UPDATED:** 2025-12-05
**STATUS:** DRAFT - Wymaga zatwierdzenia użytkownika
