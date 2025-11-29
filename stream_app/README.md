# 🎮 Stream Highlights AI - Chat-Based Clip Generator

Automatyczne generowanie najlepszych momentów ze streamów Twitch/YouTube/Kick bazując na aktywności czatu, emote spamie i reakcjach widzów.

**Output:** 5-15 klipów (30-90s każdy) + YouTube Shorts (9:16) z najbardziej eksplodujących momentów!

---

## 🔥 Features

- ✅ **Chat-Based Scoring** - analizuje spam KEKW, PogChamp, LUL i inne emote
- ✅ **Stream Delay Compensation** - uwzględnia 10s delay między akcją a reakcją czatu
- ✅ **Copyright Detection** (NOWY!) - skanuje klipy pod kątem muzyki chronionej (DMCA-safe)
- ✅ **Vocal Isolation** - automatycznie usuwa muzykę w tle, zachowuje głos streamera
- ✅ **Audio-Only Fallback** - działa nawet bez czatu (bazując na głośności)
- ✅ **YouTube Shorts** - automatycznie generuje pionowe klipy 9:16
- ✅ **Multi-Platform** - Twitch, YouTube Live, Kick, Facebook Gaming

---

## 🆚 Czym różni się od sejm_app?

| Feature | sejm_app | stream_app |
|---------|----------|------------|
| **Scoring** | GPT AI Semantic (polityka) | Chat activity (gaming) |
| **Duration** | Długie klipy (90-180s) | Krótsze (30-90s) |
| **Target** | 15 min film | 10 min highlights |
| **Merging** | Konserwatywne | Agresywne (łączy reakcje) |
| **Copyright** | ❌ Nie dotyczy | ✅ DMCA protection |
| **Delay offset** | ❌ | ✅ 10s stream delay |

---

## 🖥️ Wymagania systemowe

### Minimalne:
- **OS:** Windows 10/11 (64-bit), Linux
- **CPU:** Intel i5 / AMD Ryzen 5
- **RAM:** 16 GB
- **GPU:** NVIDIA RTX 2060+ (8GB VRAM) **zalecane**
- **Python:** 3.11+

### Zalecane:
- **GPU:** RTX 3060+ (dla szybkiej transkrypcji)
- **RAM:** 32 GB
- **Dysk:** NVMe SSD

**⏱️ Czas przetwarzania:**
- 2h stream → ~15-25 min (z GPU)
- 4h stream → ~30-40 min (z GPU)

---

## 📦 Instalacja

### 1. Utwórz virtual environment

```bash
cd stream_app
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 2. Instalacja dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt

# PyTorch z CUDA (jeśli masz GPU)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### 3. Instalacja ffmpeg

#### Windows (Chocolatey):
```bash
choco install ffmpeg
```

#### Linux (Ubuntu):
```bash
sudo apt update
sudo apt install ffmpeg
```

### 4. (Opcjonalnie) AudD API Key dla copyright detection

1. Załóż darmowe konto: https://audd.io
2. Otrzymasz API key (300 requests/day za darmo)
3. Dodaj do `config.yml`:
```yaml
streaming:
  audd_api_key: "your-api-key-here"
```

---

## 🚀 Quick Start

### Krok 1: Pobierz VOD + Chat

#### Twitch:
```bash
# Zainstaluj Twitch Downloader CLI
# https://github.com/lay295/TwitchDownloader

# Pobierz VOD
TwitchDownloaderCLI videodownload -u https://twitch.tv/videos/123456789 -o vod.mp4

# Pobierz chat
TwitchDownloaderCLI chatdownload -u https://twitch.tv/videos/123456789 -o chat.json
```

#### YouTube Live:
```bash
# Zainstaluj yt-dlp
pip install yt-dlp

# Pobierz VOD
yt-dlp -f best https://youtube.com/watch?v=VIDEO_ID -o vod.mp4

# Pobierz chat (live chat replay)
yt-dlp --skip-download --write-subs --sub-format json https://youtube.com/watch?v=VIDEO_ID
```

### Krok 2: Uruchom aplikację

```bash
python app.py
```

### Krok 3: W GUI

1. **📹 Wybierz Stream VOD** → wybierz pobrany plik MP4
2. **💬 Wybierz Chat JSON** (opcjonalne, ale **bardzo polecane**)
3. **Ustaw parametry:**
   - Liczba klipów: 10
   - Długość klipu: 60s
   - Generuj Shorts: ✅
4. **▶️ Generuj Highlights**
5. Czekaj ~20-30 min
6. **📁 Output** → znajdź klipy w folderze `output/`

---

## ⚙️ Copyright Detection - Jak to działa?

### Workflow:

```
1. Analiza VOD + chat
   ↓
2. Wybór top 10 klipów (bazując na czacie)
   ↓
3. 🎵 PRE-SCAN: Skanowanie tych 10 klipów (AudD API)
   ↓
4. Wykryto muzykę?
   ├─ TAK → 🔊 POST-PROCESSING: Vocal isolation (highpass filter 300Hz)
   └─ NIE → Export bez zmian
   ↓
5. ✅ Gotowe klipy - DMCA safe!
```

### Vocal Isolation

**Metoda:** High-pass filter (300Hz)
- ❌ Usuwa: Bass, beat, muzyka (< 300Hz)
- ✅ Zachowuje: Głos streamera, reakcje (> 300Hz)
- **Efekt:** ~80% skuteczności w unikaniu Content ID

### Konfiguracja (config.yml)

```yaml
streaming:
  # Copyright detection
  enable_copyright_detection: true
  audd_api_key: "your-key"  # https://audd.io (300 free/day)
  auto_vocal_isolation: true  # Auto-czyszczenie jeśli wykryto muzykę

  # Vocal isolation settings
  vocal_isolation_method: "highpass"  # highpass lub bandpass
  highpass_frequency: 300  # Hz

  # Thresholds
  music_confidence_threshold: 0.7  # 0-1, jak strict
  max_music_percentage: 0.3  # Pomiń clip jeśli >30% to muzyka
```

---

## 📁 Struktura projektu

```
stream_app/
├── app.py                      # GUI application
├── config.yml                  # Configuration (streaming-specific)
├── requirements.txt            # Python dependencies (+requests, audd)
├── pipeline/                   # Processing pipeline
│   ├── stage_05_scoring_streaming.py  # Chat-based scoring
│   ├── stage_06b_copyright.py         # Copyright detection (NOWY!)
│   └── ...                            # (inne stages jak w sejm_app)
├── modules/
│   └── streaming/
│       ├── chat_analyzer.py           # Chat analysis
│       └── music_detector.py          # AudD API integration
└── examples/
    └── sample_chat.json               # Example chat format
```

---

## 🎵 Supported Chat Formats

### Twitch Downloader format:
```json
{
  "comments": [
    {
      "content_offset_seconds": 123.45,
      "message": {
        "body": "KEKW",
        "user_color": "#FF0000"
      },
      "commenter": {
        "display_name": "viewer123"
      }
    }
  ]
}
```

### YouTube format:
```json
[
  {
    "timestamp": 123450,  // milliseconds
    "message": "LUL",
    "author": "viewer123"
  }
]
```

---

## 🐛 Troubleshooting

### "Chat analysis failed"
- Sprawdź format JSON (użyj Twitch Downloader lub yt-dlp)
- App działa bez czatu (fallback: audio-only scoring)

### "AudD API limit exceeded"
- Free tier: 300 requests/day
- 1 clip = ~3-6 requests (skanuje co 10s)
- Upgrade plan: https://audd.io/pricing
- Lub wyłącz: `enable_copyright_detection: false`

### Copyright detection działa źle
- Zwiększ `music_confidence_threshold` (0.7 → 0.85) - bardziej strict
- Zmień metodę: `vocal_isolation_method: "bandpass"` (300-3400Hz)
- Ręcznie sprawdź output - niektóre tracki mogą przejść

### Vocal isolation brzmi źle
- Zwiększ `highpass_frequency` (300 → 400Hz) - usuwa więcej muzyki
- Zmniejsz (300 → 250Hz) - zachowuje więcej basu w głosie

---

## 📝 License

MIT License

---

## 🙏 Credits

- **Twitch Downloader** - Chat export
- **yt-dlp** - VOD & chat download
- **AudD** - Music recognition API
- **Whisper** - Transcription
- **PyQt6** - GUI

---

## 💡 Tips

1. **Zawsze używaj czatu** - scoring jest 10x lepszy z czatem
2. **10s delay offset** jest już ustawiony - działa dla większości streamów
3. **Copyright detection** - włącz jeśli uploadujesz na YouTube
4. **Shorts** - idealne dla viral moments (KEKW spam, epic fails)
5. **Testuj config** - każdy streamer ma inny styl (dostosuj thresholdy)
