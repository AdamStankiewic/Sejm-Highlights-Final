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