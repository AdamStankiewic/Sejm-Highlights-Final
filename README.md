# 🎬 Sejm Highlights AI - Desktop Application

Automatyczne generowanie kompilacji "Najlepszych momentów z Sejmu" z długich transmisji (2-8h) poprzez inteligentną ekstrakcję i łączenie najciekawszych fragmentów politycznych debat.

**Output:** Film 10-20 minut zawierający 8-15 kluczowych momentów, gotowy do publikacji.

---

## 📋 Spis treści

- [Wymagania systemowe](#wymagania-systemowe)
- [Instalacja](#instalacja)
- [Użycie](#użycie)
- [Konfiguracja](#konfiguracja)
- [Architektura](#architektura)
- [Troubleshooting](#troubleshooting)

---

## 🖥️ Wymagania systemowe

### Minimalne (CPU only):
- **OS:** Windows 10/11 (64-bit)
- **CPU:** Intel i5 8th gen / AMD Ryzen 5 2600 lub lepszy
- **RAM:** 16 GB
- **Dysk:** 50 GB wolnego miejsca (SSD zalecany)
- **Python:** 3.11+

### Zalecane (GPU accelerated):
- **GPU:** NVIDIA GeForce RTX 3060 lub lepszy (min. 8GB VRAM)
- **CUDA:** 12.1+
- **RAM:** 32 GB
- **Dysk:** 100 GB wolnego miejsca (NVMe SSD)

**⏱️ Czas przetwarzania:**
- CPU only: ~60-90 min dla 4h transmisji
- GPU (RTX 3060): ~25-35 min dla 4h transmisji
- GPU (RTX 4090): ~15-20 min dla 4h transmisji

---

## 📦 Instalacja

### 1. Instalacja Python

Pobierz Python 3.11+ z [python.org](https://www.python.org/downloads/)

✅ **Ważne:** Zaznacz "Add Python to PATH" podczas instalacji!

### 2. Instalacja CUDA (dla GPU)

Jeśli masz kartę NVIDIA:

1. Pobierz CUDA Toolkit 12.1+: https://developer.nvidia.com/cuda-downloads
2. Zainstaluj drivers NVIDIA (najnowsze)
3. Zrestartuj komputer

### 3. Instalacja ffmpeg

#### Opcja A: Chocolatey (zalecane)
```bash
# W PowerShell (jako Administrator)
Set-ExecutionPolicy Bypass -Scope Process -Force
iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))
choco install ffmpeg
```

#### Opcja B: Manualna
1. Pobierz ffmpeg z: https://www.gyan.dev/ffmpeg/builds/
2. Wypakuj do `C:\ffmpeg`
3. Dodaj `C:\ffmpeg\bin` do PATH:
   - Szukaj "Environment Variables" w Windows
   - Edytuj "Path" w System variables
   - Dodaj nową ścieżkę: `C:\ffmpeg\bin`

**Sprawdź instalację:**
```bash
ffmpeg -version
```

### 4. Sklonuj/Pobierz projekt

```bash
# Opcja A: Git
git clone https://github.com/yourusername/sejm-highlights-ai.git
cd sejm-highlights-ai

# Opcja B: Pobierz ZIP i wypakuj
```

### 5. Utwórz virtual environment

```bash
# W folderze projektu
python -m venv venv

# Aktywuj (Windows)
venv\Scripts\activate
```

### 6. Instalacja dependencies

```bash
# Podstawowe pakiety
pip install --upgrade pip
pip install -r requirements.txt

# Model spaCy
python -m spacy download pl_core_news_lg
```

**Jeśli masz GPU (CUDA 12.1):**
```bash
# PyTorch z CUDA
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

**Jeśli CPU only:**
```bash
pip install torch torchvision torchaudio
```

### 7. Weryfikacja instalacji

```bash
python -c "import torch; print('CUDA available:', torch.cuda.is_available())"
# Powinno wyświetlić: CUDA available: True (jeśli masz GPU)
```

---

## 🚀 Użycie

### Quick Start

1. **Aktywuj virtual environment:**
```bash
venv\Scripts\activate
```

2. **Uruchom aplikację:**
```bash
python app.py
```

3. **W GUI:**
   - Kliknij **"📁 Wybierz plik MP4"** → wybierz transmisję Sejmu
   - Dostosuj ustawienia w zakładkach (opcjonalnie)
   - Kliknij **"▶️ Start Processing"**
   - Czekaj (~25-60 min)
   - Po zakończeniu kliknij **"📁 Open Output Folder"** lub **"▶️ Play Video"**

### Konfiguracja przez GUI

#### ⚙️ Output Settings
- **Docelowa długość filmu:** 10-30 minut (default: 15 min)
- **Liczba klipów:** 5-20 (default: 12)
- **Min/Max długość klipu:** 60-300s (default: 90-180s)
- **Dodaj title cards:** Włącz/wyłącz intro dla każdego klipu
- **Hardsub:** Wersja z wgranymi napisami (dla social media)

#### 🤖 AI Settings
- **Model Whisper:** 
  - `large-v3` - najlepszy (wolniejszy, 8GB VRAM)
  - `medium` - kompromis (szybszy, 4GB VRAM)
  - `small` - najszybszy (2GB VRAM, gorsza accuracy nazwisk)
- **Próg semantic scoring:** 0.0-1.0 (wyższy = bardziej selektywny)

#### 🔧 Advanced
- **Folder wyjściowy:** Gdzie zapisać wyniki
- **Zachowaj pliki pośrednie:** Debugging (audio, segmenty, itp.)

---

## ⚙️ Konfiguracja zaawansowana

Edytuj `config.yml` dla pełnej kontroli:

```yaml
# Przykład: zmiana target duration
selection:
  target_total_duration: 1200.0  # 20 minut

# Przykład: bardziej agresywny AI scoring
scoring:
  weight_semantic: 0.70  # Więcej wagi na AI
  weight_acoustic: 0.15
```

**Pola kluczowe:**

| Parametr | Opis | Default |
|----------|------|---------|
| `asr.model` | Model Whisper | `large-v3` |
| `selection.target_total_duration` | Długość filmu (s) | 900 (15 min) |
| `selection.max
---

## 🏗️ Architektura Pipeline

Aplikacja składa się z 10 zsynchronizowanych etapów przetwarzania:

```
┌──────────────────────────────────────────────────────────────────┐
│                    INPUT: Transmisja Sejmu (MP4)                  │
│                         2-8h, 1920x1080                           │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │   STAGE 1:      │
                    │   INGEST        │  Audio extraction + normalization
                    │   FFmpeg        │  (EBU R128 loudness)
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   STAGE 2:      │
                    │   VAD           │  Voice Activity Detection
                    │   Silero VAD    │  (PyTorch, GPU accelerated)
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   STAGE 3:      │
                    │   TRANSCRIBE    │  Speech-to-Text
                    │   Whisper       │  (word-level timestamps)
                    │   large-v3      │  [MOŻNA CACHE'OWAĆ]
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   STAGE 4:      │
                    │   FEATURES      │  Feature extraction:
                    │   librosa+spaCy │  - Acoustic (RMS, spectral)
                    │                 │  - Prosodic (speech rate)
                    │                 │  - Lexical (keywords, NER)
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   STAGE 5:      │
                    │   SCORING       │  AI Semantic Analysis
                    │   GPT-4o-mini   │  (top 100 segments only)
                    │                 │  Composite score: 70% AI + 30% features
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   STAGE 6:      │
                    │   SELECTION     │  Intelligent clip selection:
                    │   Knapsack+NMS  │  - Temporal diversity
                    │                 │  - Smart merging
                    │                 │  - Duration constraints
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   STAGE 7:      │
                    │   EXPORT        │  Video rendering
                    │   FFmpeg        │  (H.264, CRF 21)
                    │                 │  + Subtitles (optional)
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   STAGE 8:      │
                    │   THUMBNAIL     │  Thumbnail generation
                    │   OpenCV        │  (from high-score moments)
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   STAGE 9:      │
                    │   YOUTUBE       │  YouTube upload (optional)
                    │   API v3        │  + Premiere scheduling
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   STAGE 10:     │
                    │   SHORTS        │  Vertical video (9:16)
                    │   MediaPipe     │  + Face detection
                    │                 │  + AI titles
                    └────────┬────────┘
                             │
            ┌────────────────▼────────────────┐
            │     OUTPUT: Highlights MP4       │
            │  15-20 min │ 8-15 klipów         │
            │  + Thumbnails + Shorts           │
            └──────────────────────────────────┘
```

### Kluczowe Optymalizacje (v2.1+):

- **🔥 GPU Acceleration:** Automatyczne wykrywanie CUDA i fallback na CPU
- **💾 Transcription Caching:** Pickle-based cache eliminuje powtórną transkrypcję
- **⚡ Parallel Processing:** Multiprocessing dla VAD i feature extraction
- **✅ Input Validation:** FFprobe-based validation przed przetwarzaniem
- **🛡️ Enhanced Error Handling:** User-friendly błędy po polsku
- **📊 Structured Logging:** Kolorowane logi + zapis do pliku
- **🧪 Pytest Testing:** 15 testów jednostkowych dla core pipeline

---

## 🐛 Troubleshooting

### Problem: "CUDA out of memory"

**Przyczyna:** Model Whisper wymaga więcej VRAM niż dostępne.

**Rozwiązania:**
1. Użyj mniejszego modelu:
   - `large-v3` → `medium` (10GB → 5GB VRAM)
   - `medium` → `small` (5GB → 2GB VRAM)

2. Zamknij inne aplikacje GPU (gry, inne AI tools)

3. Zmniejsz batch size w `config.yml`:
   ```yaml
   asr:
     batch_size: 5  # Domyślnie 10
   ```

4. Włącz CPU mode (wolniejsze, ale działa):
   ```yaml
   asr:
     use_gpu: false
   ```

---

### Problem: "No module named 'spacy'" lub "Can't find model 'pl_core_news_lg'"

**Przyczyna:** Model spaCy nie jest zainstalowany.

**Rozwiązanie:**
```bash
# Aktywuj venv
venv\Scripts\activate

# Zainstaluj model Polski
python -m spacy download pl_core_news_lg

# Weryfikacja
python -c "import spacy; nlp = spacy.load('pl_core_news_lg'); print('OK')"
```

---

### Problem: "ffmpeg not found" lub "FFmpeg is required"

**Przyczyna:** FFmpeg nie jest zainstalowany lub nie ma go w PATH.

**Rozwiązanie (Windows):**

1. **Przez Chocolatey (zalecane):**
   ```bash
   choco install ffmpeg
   ```

2. **Ręcznie:**
   - Pobierz z [gyan.dev/ffmpeg](https://www.gyan.dev/ffmpeg/builds/)
   - Rozpakuj do `C:\ffmpeg`
   - Dodaj `C:\ffmpeg\bin` do PATH:
     - Windows + R → `sysdm.cpl`
     - Zakładka "Zaawansowane" → "Zmienne środowiskowe"
     - Edytuj `Path` → Dodaj `C:\ffmpeg\bin`

3. **Weryfikacja:**
   ```bash
   ffmpeg -version
   ```

---

### Problem: "OpenAI API key not found"

**Przyczyna:** Brak klucza API w `.env` lub GPT scoring jest włączony bez klucza.

**Rozwiązanie:**

**Opcja A: Dodaj klucz API (zalecane)**
1. Utwórz plik `.env` w folderze projektu:
   ```
   OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
2. Pobierz klucz z [platform.openai.com/api-keys](https://platform.openai.com/api-keys)

**Opcja B: Wyłącz GPT scoring (fallback na keyword)**
```yaml
# config.yml
scoring:
  use_gpt: false  # Używa tylko acoustic + keyword scoring
```

---

### Problem: Wolne przetwarzanie (>2h dla 4h materiału)

**Możliwe przyczyny i rozwiązania:**

1. **CPU mode zamiast GPU:**
   - Sprawdź: `python -c "import torch; print(torch.cuda.is_available())"`
   - Jeśli `False`, zainstaluj PyTorch z CUDA:
     ```bash
     pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
     ```

2. **Duży model Whisper na słabym GPU:**
   - Zmień `large-v3` → `medium` w GUI

3. **Brak cache'owania:**
   - Cache jest włączony automatycznie od v2.1
   - Folder: `./cache/`
   - Sprawdź logi: `[Cache] Using cached transcription`

4. **Dysk HDD zamiast SSD:**
   - Przenieś projekt na SSD

5. **Inne procesy CPU/GPU:**
   - Zamknij inne aplikacje

---

### Problem: "Video file is corrupted" lub "Failed to read metadata"

**Przyczyna:** Uszkodzony plik MP4 lub nieprawidłowy kontener.

**Rozwiązanie:**

1. **Przekonwertuj video przez FFmpeg:**
   ```bash
   ffmpeg -i input.mp4 -c:v libx264 -crf 21 -c:a aac output.mp4
   ```

2. **Sprawdź metadane:**
   ```bash
   ffprobe -v error -show_format -show_streams input.mp4
   ```

3. **Pobierz ponownie** (jeśli z internetu)

---

### Problem: Aplikacja się crashuje bez błędu

**Rozwiązanie:**

1. **Uruchom przez terminal** (nie double-click):
   ```bash
   python app.py
   ```
   Zobaczysz pełny stack trace błędu.

2. **Sprawdź logi:**
   - Folder: `./logs/`
   - Najnowszy plik: `sejm_highlights_YYYYMMDD_HHMMSS.log`

3. **Usuń cache i spróbuj ponownie:**
   ```bash
   rm -rf cache/*
   rm -rf temp/*
   ```

4. **Reinstall dependencies:**
   ```bash
   pip install --upgrade --force-reinstall -r requirements.txt
   ```

---

### Problem: "MemoryError" lub "Out of RAM"

**Przyczyna:** Niewystarczająca pamięć RAM (długie video + duże modele).

**Rozwiązanie:**

1. **Włącz Smart Splitter** (automatyczny podział na części):
   ```yaml
   smart_splitter:
     enabled: true
     max_part_duration: 3600  # 1h per part
   ```

2. **Zwiększ swap/pagefile (Windows):**
   - Windows + R → `sysdm.cpl`
   - Zaawansowane → Wydajność → Ustawienia
   - Zaawansowane → Pamięć wirtualna → Zmień
   - Ustaw: 32GB (jeśli masz 16GB RAM)

3. **Użyj krótszego video** lub podziel ręcznie

---

### Problem: Złe rozpoznawanie nazwisk polityków (Whisper)

**Przyczyna:** Domyślny Whisper nie zna polskich nazwisk politycznych.

**Rozwiązanie:**

1. **Używaj `large-v3`** (najlepsza accuracy)

2. **Dodaj initial prompt** w `config.yml`:
   ```yaml
   asr:
     initial_prompt: "Transmisja Sejmu RP. Politycy: Tusk, Kaczyński, Morawiecki, Czarzasty, Hołownia."
   ```

3. **Edytuj słownik keywords:**
   - Plik: `models/keywords_sejm.csv`
   - Dodaj nazwiska jako high-weight keywords:
     ```csv
     token,weight,category
     Kaczyński,1.0,politician
     Morawiecki,1.0,politician
     ```

---

### Problem: Testy pytest nie przechodzą

**Rozwiązanie:**

1. **Zainstaluj pytest:**
   ```bash
   pip install pytest
   ```

2. **Uruchom testy:**
   ```bash
   pytest -v
   ```

3. **Jeśli błędy importu:**
   ```bash
   export PYTHONPATH="${PYTHONPATH}:$(pwd)"  # Linux/Mac
   set PYTHONPATH=%PYTHONPATH%;%CD%  # Windows CMD
   pytest -v
   ```

4. **Pomiń testy wymagające GPU:**
   ```bash
   pytest -v -m "not gpu"
   ```

---

### Dodatkowe Zasoby

- **Dokumentacja integracji:** Zobacz `INTEGRATION_GUIDE.md`
- **Testy jednostkowe:** `tests/README.md`
- **Przykłady:** `examples/` (TODO)
- **Issues:** [GitHub Issues](https://github.com/AdamStankiewic/Sejm-Highlights-Final/issues)

---

## 📊 Performance Tips

### Optymalizacja CPU/GPU Usage:

1. **GPU Memory Monitoring:**
   ```python
   from pipeline.utils.gpu_utils import get_gpu_manager
   gpu = get_gpu_manager()
   gpu.monitor_memory()  # Loguje current usage
   ```

2. **Cache Statistics:**
   ```python
   from pipeline.utils.cache_manager import get_cache_manager
   cache = get_cache_manager()
   print(cache.get_stats())  # Rozmiar cache, liczba plików
   ```

3. **Parallel Processing:**
   - VAD i feature extraction działają równolegle (od v2.1)
   - Automatyczne wykorzystanie wszystkich rdzeni CPU

4. **Batch Size Tuning:**
   ```yaml
   # config.yml
   asr:
     batch_size: 10  # Zwiększ dla RTX 4090 (20+)
   ```

---

## 🔄 Changelog

### v2.1.0 (2025-01-XX) - Performance & Stability

**Nowe funkcje:**
- ✅ Pytest testing framework (15 testów)
- ✅ Formal logging module z GUI callbacks
- ✅ GPU acceleration utilities (CUDA detection)
- ✅ Transcription caching (pickle-based)
- ✅ Parallel processing (VAD + features)
- ✅ Enhanced error handling (Polish messages)
- ✅ Input validation (ffprobe-based)
- ✅ Auto-save configuration
- ✅ Video preview z player selection

**Wydajność:**
- ⚡ 30-40% faster dla powtórnych transkrypcji (cache)
- ⚡ 20-25% faster feature extraction (parallel)
- ⚡ Automatic GPU memory management

**Stability:**
- 🛡️ Graceful handling of CUDA OOM errors
- 🛡️ Automatic fallback to CPU
- 🛡️ Video validation przed przetwarzaniem

### v2.0.0 - Smart Splitter Edition
- Multi-part video splitting
- YouTube premiere scheduling
- YouTube Shorts generation (9:16)
- 5 professional templates for gaming/IRL streams
- MediaPipe face detection

### v1.0.0 - Initial Release
- 10-stage AI pipeline
- Whisper + GPT-4o-mini
- Desktop GUI (PyQt6)

---

## 📄 Licencja

MIT License - Zobacz `LICENSE` file.

---

## 🤝 Contributing

Pull requests mile widziane! Dla większych zmian, otwórz issue do dyskusji.

**Setup deweloperskie:**
```bash
git clone https://github.com/AdamStankiewic/Sejm-Highlights-Final.git
cd Sejm-Highlights-Final
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pytest  # Uruchom testy
```

---

## 📧 Kontakt

- **Issues:** [GitHub Issues](https://github.com/AdamStankiewic/Sejm-Highlights-Final/issues)
- **Email:** [adam@example.com](mailto:adam@example.com)

---

**Zbudowane z ❤️ dla polskiej polityki**
