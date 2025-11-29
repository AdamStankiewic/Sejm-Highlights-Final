# 🎬 Sejm Highlights AI - Desktop Application

Automatyczne generowanie kompilacji "Najlepszych momentów z Sejmu" z długich transmisji (2-8h) poprzez inteligentną ekstrakcję i łączenie najciekawszych fragmentów politycznych debat.

**Output:** Film 10-20 minut zawierający 8-15 kluczowych momentów, gotowy do publikacji.

---

## 📋 Features

- ✅ **Automatyczna transkrypcja** (Whisper large-v3) z optymalizacją dla polskich nazwisk
- ✅ **AI Semantic Scoring** (GPT-based) - wykrywa najbardziej kontrowersyjne momenty
- ✅ **Smart Splitter** - automatyczny podział długich materiałów (>1h) na części z premiami
- ✅ **YouTube Shorts** - generuje pionowe klipy 9:16 z najlepszych fragmentów
- ✅ **Auto-upload do YouTube** - z miniaturkami, tytułami i schedulowanymi premierami
- ✅ **Pobieranie z URL** - wspiera YouTube, Twitch, Facebook Live i 1000+ platform
- ✅ **GPU Acceleration** - CUDA dla szybkiego przetwarzania

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
3. Dodaj `C:\ffmpeg\bin` do PATH

**Sprawdź instalację:**
```bash
ffmpeg -version
```

### 4. Utwórz virtual environment

```bash
# W folderze sejm_app
python -m venv venv

# Aktywuj (Windows)
venv\Scripts\activate
```

### 5. Instalacja dependencies

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

### 6. Weryfikacja instalacji

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
   - Lub użyj **"📥 Pobierz z URL"** → wklej link YouTube
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

#### 🤖 Smart Splitter
- **Automatyczny podział** materiałów >1h na części ~15 min
- **Schedulowane premiery** - każda część ma osobną premierę (dzień po dniu)
- **Automatyczne tytuły** z nazwiskami polityków (TUSK VS KACZYŃSKI)

#### 📺 YouTube
- **Auto-upload** gotowych filmów
- **Premiery** - schedulowane publikacje
- **Miniaturki** - automatycznie generowane z wyborem stylu

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

---

## 📁 Struktura projektu

```
sejm_app/
├── app.py                      # Główna aplikacja GUI
├── video_downloader.py         # Pobieranie video z URL
├── config.yml                  # Konfiguracja
├── requirements.txt            # Dependencies
├── pipeline/                   # Pipeline przetwarzania
│   ├── stage_01_ingest.py     # Analiza video
│   ├── stage_02_vad.py        # Voice Activity Detection
│   ├── stage_03_transcribe.py # Whisper transkrypcja
│   ├── stage_04_features.py   # Feature engineering
│   ├── stage_05_scoring_gpt.py # AI Semantic Scoring
│   ├── stage_06_selection.py  # Wybór najlepszych klipów
│   ├── stage_07_export.py     # Eksport video
│   ├── stage_08_thumbnail.py  # Generowanie miniaturek
│   ├── stage_09_youtube.py    # Upload do YouTube
│   └── stage_10_shorts.py     # Generowanie Shorts
└── models/
    └── keywords.csv           # Słowa kluczowe dla Sejmu
```

---

## 🐛 Troubleshooting

### Error: "CUDA out of memory"
- Zmień model Whisper na `medium` lub `small`
- Zmniejsz `batch_size` w config.yml
- Zamknij inne aplikacje używające GPU

### Error: "ffmpeg not found"
- Sprawdź czy ffmpeg jest w PATH: `ffmpeg -version`
- Przeinstaluj ffmpeg używając Chocolatey

### Slow processing (CPU only)
- Zmień Whisper model na `small` lub `medium`
- Zmniejsz `target_total_duration` (krótszy film = szybciej)

### YouTube upload fails
- Sprawdź czy `client_secret.json` istnieje
- Sprawdź czy kanał w `config.yml` jest poprawny
- Usuń `youtube_token.json` i spróbuj ponownie (wymusi nową autoryzację)

---

## 📝 License

MIT License - See LICENSE file for details

---

## 🙏 Credits

- **Whisper** - OpenAI
- **yt-dlp** - Video downloading
- **PyQt6** - GUI framework
- **ffmpeg** - Video processing
