# AI Metadata Generation - Quick Start Guide

## Dla Asmongold/Zackrawrr VODs

### 1. Dodaj API Keys do .env

```bash
# .env (już istnieje - tylko wypełnij)
OPENAI_API_KEY=sk-proj-TWÓJ_KLUCZ_TUTAJ
YOUTUBE_API_KEY=AIzaSy-TWÓJ_KLUCZ_TUTAJ
```

**Gdzie uzyskać klucze**:
- OpenAI: https://platform.openai.com/api-keys
- YouTube: Patrz `docs/YOUTUBE_API_SETUP.md`

---

### 2. Profil Asmongolda już istnieje!

✅ `pipeline/streamers/profiles/asmongold.yaml`
- Wspiera: Twitch (zackrawrr), Kick (asmongold), YouTube
- 5 seed examples (react, gaming, commentary, IRL, shorts)
- Styl: meme-heavy, casual, caps lock, emojis 😂💀🔥

---

### 3. Testuj AI Generation (BEZ YouTube uploadu)

```bash
# Test z przykładowymi clipami (Asmongold style)
python scripts/generate_metadata_standalone.py --test --streamer asmongold

# Output:
# ✅ METADATA GENERATED
# 📝 TITLE: Asmon Reacts to Insane Gaming Drama 😂
# 📄 DESCRIPTION: Asmongold reacts to the latest...
# 💰 COST: $0.0045
# 💾 CACHED: False
```

---

### 4. Auto-detekcja streamera z nazwy pliku

```bash
# System automatycznie wykryje "asmongold" z nazwy pliku:
python scripts/generate_metadata_standalone.py \
    --input output/asmongold_2024_12_23/selected_clips.json

# Wykryje "zackrawrr" z ścieżki:
python scripts/generate_metadata_standalone.py \
    --input vods/zackrawrr/selected_clips.json

# Manualnie podaj streamera:
python scripts/generate_metadata_standalone.py \
    --input selected_clips.json \
    --streamer asmongold
```

**Wzorce rozpoznawania**:
- Nazwa pliku: `asmongold_react.mp4`, `zackrawrr-drama.mp4`
- Katalog: `vods/asmongold/`, `content/zackrawrr/`
- Bracket: `[Asmongold] React.mp4`

---

### 5. Uruchom Learning Loop (jeśli masz YouTube channel)

```bash
# Pobierz TOP 20 najlepszych filmów z YouTube
python scripts/run_learning_loop.py \
    --streamer asmongold \
    --api-key YOUR_YOUTUBE_API_KEY

# Output:
# 🏆 Selected 18 top performers
# 💾 Updating learned examples...
# ✅ Examples updated: 18
```

**Co robi**:
- Pobiera ostatnie 50 filmów z Asmongold TV
- Analizuje metryki (views, likes, retention)
- Wybiera TOP 20 (performance score > 5.0)
- Zapisuje do bazy jako "learned examples"
- **Następne generacje używają tych przykładów!**

---

### 6. Zintegruj z pipeline (Stage 9 YouTube Upload)

**Opcja A: Modyfikuj config.yml**
```yaml
youtube:
  enabled: true
  default_streamer: "asmongold"  # ← DODAJ TO (nowy parametr)
```

**Opcja B: Flag podczas uruchamiania**
```bash
# Pipeline z auto-detekcją
python app.py --streamer asmongold

# LUB processor
python processor.py \
    --input vods/asmongold/stream.mp4 \
    --streamer asmongold
```

---

## Przykładowe wygenerowane tytuły (Asmongold style)

### React content:
```
🔥 Asmon Reacts to INSANE Gaming Drama - Community LOSES IT 😂
💀 This Game Developer ACTUALLY Said This... Asmon's Response
😱 Asmon's WORST Take Ever - Chat Goes CRAZY
```

### Gameplay:
```
⚡ This New MMO is ACTUALLY GOOD - Asmongold First Impressions
🎮 IMPOSSIBLE Boss Fight - Asmon Attempts the Ultimate Challenge
💥 Asmon DESTROYS Speedrunner's World Record (Gone Wrong)
```

### Commentary:
```
🔥 Asmon GOES OFF on Modern Game Development
💀 Why This Game is DYING - The Brutal Truth
😤 The REAL Reason Gamers Are Fed Up (Asmon Rant)
```

### IRL/Just Chatting:
```
📋 Asmon Answers Your Questions - Reddit Recap
💬 Chatting with Asmon - Life Advice & Hot Takes
🤔 Asmon's Thoughts on Streaming in 2024
```

---

## Różnice: Sejm vs Asmongold

| Aspect | Sejm | Asmongold |
|--------|------|-----------|
| **Język** | Polski | English |
| **Emojis** | 🔥💥⚡ (professional) | 😂💀🔥 (meme-heavy) |
| **Caps Lock** | SEJM, Tusk, Kaczyński | INSANE, ACTUALLY, LOSES IT |
| **Style** | Formal, political | Casual, gaming slang |
| **Content Types** | meeting, press conf, briefing | react, gaming, commentary, IRL |

**System automatycznie dostosowuje style** bazując na profilu!

---

## Troubleshooting

### "Streamer profile not found: zackrawrr"

**Problem**: Nie ma profilu "zackrawrr", jest tylko "asmongold"

**Fix**: Użyj `--streamer asmongold` (Zackrawrr to alias Asmongolda)

---

### "Could not auto-detect streamer, using default: sejm"

**Problem**: Nazwa pliku nie zawiera "asmongold" ani "zackrawrr"

**Fix**: Albo:
1. Zmień nazwę pliku: `mv video.mp4 asmongold_react.mp4`
2. Użyj explicit flag: `--streamer asmongold`
3. Umieść w katalogu: `vods/asmongold/video.mp4`

---

### "Database shows 0 learned examples after generation"

**Problem**: Standalone script NIE uruchamia learning loop

**Wyjaśnienie**:
- `generate_metadata_standalone.py` → generuje + cache metadata
- `run_learning_loop.py` → pobiera YouTube metrics + learned examples

**To są dwie oddzielne operacje!**

---

## Next Steps

1. ✅ Wypełnij .env z API keys
2. ✅ Test: `python scripts/generate_metadata_standalone.py --test`
3. ✅ Generuj dla swoich clipów: `--input selected_clips.json --streamer asmongold`
4. ✅ (Optional) Learning loop: `python scripts/run_learning_loop.py`
5. ✅ Zintegruj z pipeline: dodaj `--streamer` flag

---

## Koszty

### Standalone generation (bez learning loop):
- **$0.0055 per video** (title + description + context)
- 100 filmów = **$0.55**
- 1000 filmów = **$5.50**

### Learning loop (YouTube Data API):
- **FREE** (10,000 units/day quota)
- ~150 units per run (50 videos)
- Można uruchamiać ~66 razy/dzień za darmo

### Caching:
- Identyczne klipy → **$0.00** (reuse cached)
- Database przechowuje wyniki na zawsze

---

## Co dalej?

Czy chcesz:
1. **Test teraz** - uruchomić `--test` żeby zobaczyć jak działa?
2. **Learning loop** - ustawić YouTube API i pobrać examples?
3. **Pipeline integration** - dodać auto-detection do app.py?
4. **Więcej streamerów** - stworzyć profile dla innych?

Daj znać! 🚀
