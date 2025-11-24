# 🔧 Troubleshooting Guide - Sejm Highlights AI

## ⚠️ Problem: Ostrzeżenie pkg_resources

### Objaw
```
C:\...\venv\Lib\site-packages\ctranslate2\__init__.py:8: UserWarning: pkg_resources is deprecated as an API.
```

### Rozwiązanie

**Opcja 1: Pin setuptools (zalecane)**
```bash
pip install "setuptools<81.0.0"
```

**Opcja 2: Upgrade ctranslate2 i faster-whisper**
```bash
pip install --upgrade faster-whisper ctranslate2
```

**Uwaga:** To ostrzeżenie NIE blokuje działania aplikacji - możesz je zignorować.

---

## 🎬 Problem: Nie generuje filmików ani shortsów

### Objawy
- Logi pokazują "Rozpoczeto przetwarzanie..." wielokrotnie
- Pokazuje "Zakonczone! Wybrano 1 klipow" wielokrotnie
- Brak plików w folderze `output/`
- Brak plików w folderze `temp/`

### Możliwe przyczyny i rozwiązania

#### 1. Za mało segmentów spełnia kryteria

**Diagnoza:**
```bash
# Uruchom app.py i sprawdź logi
python app.py
```

Szukaj w logach:
```
📊 Rozpoczęto selekcję klipów:
   - Segmentów do wyboru: X
   - Min score threshold: Y
```

**Rozwiązanie:**
Edytuj `config.yml`:
```yaml
scoring:
  prefilter_top_n: 100  # Zwiększ jeśli za mało

selection:
  min_clip_duration: 45.0  # Zmniejsz jeśli materiał krótki
  max_clips: 25  # Zwiększ
```

#### 2. Brak ffmpeg lub błędy w ffmpeg

**Diagnoza:**
```bash
# Sprawdź czy ffmpeg działa
ffmpeg -version
```

Jeśli błąd "ffmpeg not found":

**Windows:**
```bash
# Zainstaluj z https://ffmpeg.org/download.html
# Lub użyj chocolatey:
choco install ffmpeg
```

**Linux/Mac:**
```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# Mac
brew install ffmpeg
```

#### 3. Brak OPENAI_API_KEY (dla scoring)

**Diagnoza:**
Sprawdź plik `.env`:
```bash
OPENAI_API_KEY=sk-...
```

**Rozwiązanie:**
Utwórz plik `.env` w głównym katalogu:
```env
OPENAI_API_KEY=twój_klucz_api
```

Lub wyłącz GPT scoring (użyje tylko acoustic/keyword features).

#### 4. Błędy w pipeline - sprawdź temp folder

**Diagnoza:**
```bash
# Włącz keep_intermediate w config.yml
keep_intermediate: true
```

Następnie sprawdź folder `temp/`:
```
temp/
  plik_TIMESTAMP/
    clips/          # Czy są wycięte klipy?
    titles/         # Czy są title cards?
    shorts/         # Czy są shorts?
```

**Typowe błędy:**

- **Brak clips/** → Problem w stage 7 (Export)
- **Brak shorts/** → Problem w stage 10 (Shorts)
- **Puste foldery** → ffmpeg error lub brak miejsca na dysku

#### 5. Za wysoki min_score threshold (dla długich materiałów)

Gdy używasz Smart Splitter (dla materiałów >1h), system automatycznie podnosi `min_score` do 7.0.

**Rozwiązanie:**
Wyłącz Smart Splitter w `config.yml`:
```yaml
splitter:
  enabled: false
```

Lub zwiększ scoring weights dla GPT:
```yaml
scoring:
  weight_semantic: 0.80  # Zwiększ z 0.70
```

---

## 📱 Problem: Nie generuje Shorts

### Diagnoza

Sprawdź `config.yml`:
```yaml
shorts:
  enabled: true  # Musi być true!
  min_duration: 15.0
  max_duration: 60.0
  max_shorts_count: 10
```

Sprawdź logi:
```
📱 YouTube Shorts Generator (ENHANCED)
📱 Generowanie X Shorts...
```

Jeśli widzisz:
```
⚠️ Brak kandydatów na Shorts
```

**Rozwiązania:**

1. **Zmniejsz min_duration:**
```yaml
shorts:
  min_duration: 10.0  # Zamiast 15.0
```

2. **Zwiększ max_duration:**
```yaml
shorts:
  max_duration: 90.0  # Zamiast 60.0
```

3. **Zwiększ max_shorts_count:**
```yaml
shorts:
  max_shorts_count: 20  # Zamiast 10
```

---

## 🐛 Debugowanie - Włącz szczegółowe logi

Edytuj `config.yml`:
```yaml
general:
  log_level: "DEBUG"  # Zamiast INFO
  save_logs: true
```

Uruchom ponownie:
```bash
python app.py
```

Logi będą zawierały:
- Liczby segmentów na każdym etapie
- Score thresholdy
- Błędy ffmpeg
- Liczby wybranych klipów/shorts

---

## 📞 Gdzie szukać pomocy

1. **Sprawdź logi w konsoli** - zawsze pokazują szczegóły błędów
2. **Sprawdź folder `output/`** - czy są pliki MP4?
3. **Sprawdź folder `temp/` (gdy keep_intermediate=true)** - diagnozy pipeline
4. **GitHub Issues**: https://github.com/YOUR_REPO/issues

---

## 🔍 Quick Diagnostic Checklist

- [ ] ffmpeg zainstalowany i działa (`ffmpeg -version`)
- [ ] OPENAI_API_KEY w pliku `.env`
- [ ] Python 3.11+ (`python --version`)
- [ ] Wszystkie pakiety zainstalowane (`pip install -r requirements.txt`)
- [ ] Folder `output/` istnieje i ma uprawnienia zapisu
- [ ] Folder `temp/` istnieje
- [ ] config.yml poprawnie skonfigurowany
- [ ] Plik wejściowy MP4 jest poprawny (`ffprobe plik.mp4`)

---

## ⚡ Szybkie Naprawy

### Reset całego środowiska
```bash
# Usuń venv
rm -rf venv  # Linux/Mac
rmdir /s venv  # Windows

# Stwórz nowe
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate  # Windows

# Reinstaluj
pip install -r requirements.txt
```

### Clear cache i temp
```bash
rm -rf temp/*
rm -rf output/*
rm -rf __pycache__
```

### Test minimalny
```python
# test_minimal.py
from pipeline.config import Config
from pipeline.processor import PipelineProcessor

config = Config.load_default()
print(config)
config.validate()
print("✅ Config OK!")
```

---

**Ostatnia aktualizacja:** 2025-11-24
