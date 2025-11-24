# 🚀 Quick Fix - Nie generuje filmików

## Przyczyna problemu

Twoje logi pokazują że system **wybiera tylko 1 klip** zamiast wielu, co sugeruje że:

1. **Min score threshold jest za wysoki** (Smart Splitter podnosi go do 7.0 dla długich materiałów)
2. **Za mało segmentów spełnia kryteria**
3. **Problem z konfiguracją selection**

## Rozwiązanie natychmiastowe

### Krok 1: Napraw ostrzeżenie pkg_resources

```bash
# W twoim venv (venv\Scripts\activate na Windows)
pip install "setuptools<81.0.0"
```

### Krok 2: Edytuj config.yml

Otwórz `config.yml` i zmień:

```yaml
# PRZED (może być problem):
selection:
  min_clip_duration: 45.0
  target_total_duration: 2400.0  # 40 min
  max_clips: 25

splitter:
  enabled: true  # ← To podnosi min_score do 7.0!
```

```yaml
# PO (powinno działać):
selection:
  min_clip_duration: 30.0        # Zmniejszone z 45
  target_total_duration: 1200.0  # 20 min (łatwiejszy cel)
  max_clips: 20                  # Wystarczająco dużo
  min_clips: 3                   # Min 3 klipy

splitter:
  enabled: false  # ← WYŁĄCZ Smart Splitter na początku!
```

### Krok 3: Sprawdź czy Shorts są potrzebne

Jeśli NIE chcesz Shorts:

```yaml
shorts:
  enabled: false  # Wyłącz Shorts
```

Jeśli TAK:

```yaml
shorts:
  enabled: true
  min_duration: 10.0  # Zmniejsz z 15
  max_duration: 90.0  # Zwiększ z 60
  max_shorts_count: 15
```

### Krok 4: Uruchom diagnostic

```bash
python diagnose.py
```

To sprawdzi:
- ✅ Python version
- ✅ ffmpeg
- ✅ OpenAI API key
- ✅ Pakiety
- ✅ Config

### Krok 5: Uruchom ponownie

```bash
python app.py
```

Teraz **sprawdź logi** i szukaj:

```
📊 Rozpoczęto selekcję klipów:
   - Segmentów do wyboru: 220
   - Min score threshold: 0.0    ← Powinno być 0.0, nie 7.0!
   - Target duration: 1200s
   - Max clips: 20

✅ Zakończono selekcję:
   - Wybrano klipów: 15          ← Powinno być >3 !
   - Total duration: 18.5 min
```

## ⚠️ Jeśli nadal tylko 1 klip

### Debug 1: Sprawdź scoring
```bash
# Włącz szczegółowe logi
# W config.yml:
general:
  log_level: "DEBUG"
```

### Debug 2: Obniż wymagania
```yaml
selection:
  min_clip_duration: 20.0  # Jeszcze krótsze
  target_total_duration: 600.0  # 10 min
```

### Debug 3: Sprawdź temp/ folder
```yaml
general:
  keep_intermediate: true
```

Po uruchomieniu sprawdź:
```
temp/
  nazwa_pliku_TIMESTAMP/
    clips/  ← Czy tu są MP4?
```

Jeśli **clips/** jest **pusty** → problem z ffmpeg
Jeśli **clips/** ma pliki ale **brak output/** → problem z concatenation

## 📞 Dalej nie działa?

Uruchom:
```bash
python diagnose.py > diagnostic_report.txt
```

I wyślij `diagnostic_report.txt` + **PEŁNE LOGI Z KONSOLI**.

---

## 🎯 Expected Output

Po naprawie powinieneś zobaczyć:

```
✅ Zakończono selekcję:
   - Wybrano klipów: 15
   - Wybrano shorts: 10
   - Total duration: 18.5 min

🎬 Video export: 15 klipów...
   Wycinanie 15 klipów...
   ✓ Wycięto 15 klipów
   🔗 Łączenie 15 klipów w final video...
   ✅ Video wygenerowane: SEJM_HIGHLIGHTS_nazwa_2025-11-24.mp4
   📦 Rozmiar: 450.2 MB

📱 YouTube Shorts Generator (ENHANCED)
📱 Generowanie 10 Shorts...
   ...
   ✅ Wygenerowano 10 Shorts!
```

I pliki w `output/`:
```
output/
  SEJM_HIGHLIGHTS_nazwa_2025-11-24.mp4    ← GŁÓWNY FILM
  SEJM_HIGHLIGHTS_nazwa_2025-11-24.jpg    ← THUMBNAIL
  shorts/
    short_01.mp4
    short_02.mp4
    ...
```

---

**Data:** 2025-11-24
**Autor:** Claude AI Assistant
