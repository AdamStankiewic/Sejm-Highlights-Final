# Multi-Language Support (PL/EN) - Implementation Documentation

## Problem

Pipeline był hardcoded dla języka polskiego:
- **Whisper**: language="pl" (bez możliwości zmiany)
- **spaCy**: pl_core_news_lg (tylko polski model)
- **Keywords**: tylko keywords.csv (polskie słowa kluczowe)
- **GPT Prompts**: tylko polskie prompty dla scoringu
- **UI Text**: "Część", "Gorące Momenty Sejmu", daty po polsku
- **Output names**: hardcoded "Posiedzenie Sejmu"

To uniemożliwiało generowanie shortsów dla anglojęzycznych streamerów.

## Rozwiązanie: Global Language Parameter

Dodano parametr `language` do `Config` (wartości: "pl" lub "en"), który propaguje się przez cały pipeline:

### 1. Config (`pipeline/config.py`)

**Dodano:**
```python
@dataclass
class Config:
    # General settings
    language: str = "pl"  # Pipeline language: "pl" or "en"
```

**Language-aware defaults w `__post_init__`:**
```python
# Set ASR language from global language
if self.asr.language == "pl" and self.language != "pl":
    self.asr.language = self.language

# Set spaCy model based on language
if self.features.spacy_model is None:
    self.features.spacy_model = "pl_core_news_lg" if self.language == "pl" else "en_core_web_lg"

# Set keywords file based on language
if self.features.keywords_file is None:
    self.features.keywords_file = f"models/keywords_{self.language}.csv"

# Set language-aware interest labels for scoring
self.scoring.set_language_aware_labels(self.language)
```

### 2. Stage 3: Whisper/Transcribe (`pipeline/stage_03_transcribe.py`)

**Changes:**
- ✅ Force configured language (no auto-detect): `language=self.config.asr.language`
- ✅ Always use configured language in output (not detected): `'language': self.config.asr.language`
- ✅ Language-aware initial prompts:
  - PL: "Posiedzenie Sejmu Rzeczypospolitej Polskiej. Posłowie: ..."
  - EN: "Live streaming session. Topics: gaming, commentary, discussion..."

### 3. Stage 4: Features (`pipeline/stage_04_features.py`)

**Changes:**
- ✅ Keywords: `keywords_pl.csv` lub `keywords_en.csv` (log warning if missing)
- ✅ spaCy model switching:
  - PL: `pl_core_news_lg` → fallback: `pl_core_news_md`, `pl_core_news_sm`
  - EN: `en_core_web_lg` → fallback: `en_core_web_md`, `en_core_web_sm`
- ✅ Auto-install fallback models if primary not available

**Logs:**
```
📚 Ładowanie keywords z keywords_en.csv (language: en)
   ✓ Załadowano 45 keywords
📥 Ładowanie spaCy model: en_core_web_lg (language: en)
   ✓ spaCy załadowany
```

### 4. Stage 5: Scoring (`pipeline/stage_05_scoring_gpt.py`)

**Changes:**
- ✅ Language-aware GPT prompts (PL i EN)
- ✅ Language-aware system prompts
- ✅ Language-aware interest labels

**PL Prompt:**
```
Oceń te fragmenty debaty sejmowej pod kątem INTERESANTOŚCI dla widza YouTube (0.0-1.0):
Kryteria WYSOKIEGO score (0.7-1.0):
- Ostra polemika, kłótnie, wymiana oskarżeń
- Emocje, podniesiony głos, sarkazm, ironia
...
```

**EN Prompt:**
```
Rate these stream/video segments for INTERESTINGNESS for YouTube viewers (0.0-1.0):
HIGH score criteria (0.7-1.0):
- Heated arguments, debates, confrontations
- Emotional moments, raised voice, sarcasm, irony
- Meme-worthy, funny, absurd moments
- Exciting gameplay moments, clutch plays, fails
...
```

**Interest Labels (EN):**
```python
{
    "heated debate and exchange of accusations": 2.2,
    "emotional or raised voice": 1.7,
    "controversial statement or accusation": 2.0,
    "humor sarcasm or meme moment": 1.8,
    "exciting gameplay moment or clutch play": 2.0,
    "funny fail or mistake": 1.9,
    "dead air or waiting": -2.8,
    ...
}
```

### 5. UI Text & Output Names

**HighlightPacker (`pipeline/highlight_packer.py`):**
- ✅ "Część" → "Part" (titles, logs)
- ✅ Translated: Tytuł, Premiera, Długość, Klipy, Średni score, Keywords

**ThumbnailStage (`pipeline/stage_08_thumbnail.py`):**
- ✅ Thumbnail bottom text: "📺 Część 1/5" → "📺 Part 1/5"

**Processor (`pipeline/processor.py`):**
- ✅ Generic titles (no hardcoded "Posiedzenie Sejmu", "Gorące Momenty"):
  - PL: "Najlepsze Momenty | 12.01.2025"
  - EN: "Best Moments | 12.01.2025"
- ✅ Personality-based titles:
  - PL: "💥 Kaczyński - Najgorętsze Momenty"
  - EN: "💥 Kaczyński - Best Moments"

### 6. Cache Invalidation

**Cache Manager (`pipeline/cache_manager.py`):**
- ✅ Dodano `global_language` do config hash dla:
  - **Stage 3 (Transcribe)**: language zmienia initial_prompt i ASR behavior
  - **Stage 5 (Scoring)**: language zmienia GPT prompts i interest labels
- ✅ Cache jest invalidated gdy zmienia się język

---

## Example Config

### Polski (default):
```yaml
general:
  language: pl
  output_dir: output
  temp_dir: temp
```

### Angielski:
```yaml
general:
  language: en
  output_dir: output
  temp_dir: temp
```

---

## Example Logs

### Language: PL
```
📌 STAGE 3/7 - Transcribe [RUN_ID: 20250116_120045_abc]
📥 Ładowanie Whisper model: large-v3
   ✓ Model załadowany na CUDA
🎤 Transkrypcja 100 segmentów...
   Language: pl (forced)
   Initial prompt: Posiedzenie Sejmu Rzeczypospolitej Polskiej...
   ✓ Transkrybowano 5234 słów

📌 STAGE 4/7 - Features [RUN_ID: 20250116_120045_abc]
📚 Ładowanie keywords z keywords_pl.csv (language: pl)
   ✓ Załadowano 127 keywords
📥 Ładowanie spaCy model: pl_core_news_lg (language: pl)
   ✓ spaCy załadowany

📌 STAGE 5/7 - Scoring [RUN_ID: 20250116_120045_abc]
🧠 AI Semantic Scoring dla 100 segmentów...
   System prompt: Jesteś ekspertem od analizy politycznych debat i treści viralowych.
   ✓ Batch 1: avg score 0.67

📦 HIGHLIGHT PACKER - PLAN PAKOWANIA

📅 HARMONOGRAM PREMIER (3 części):
--------------------------------------------------------------------------------

  Część 1/3:
  📺 Tytuł: 💥 Kaczyński - Najgorętsze Momenty | CZĘŚĆ 1/3 | 12.01.2025
  🗓️  Premiera: 13.01.2025 o 18:00
  ⏱️  Długość: 12m 30s
  🎬 Klipy: 8
  ⭐ Średni score: 0.74
```

### Language: EN
```
📌 STAGE 3/7 - Transcribe [RUN_ID: 20250116_120045_xyz]
📥 Ładowanie Whisper model: large-v3
   ✓ Model załadowany na CUDA
🎤 Transkrypcja 150 segmentów...
   Language: en (forced)
   Initial prompt: Live streaming session. Topics: gaming, commentary...
   ✓ Transkrybowano 8912 słów

📌 STAGE 4/7 - Features [RUN_ID: 20250116_120045_xyz]
📚 Ładowanie keywords z keywords_en.csv (language: en)
   ✓ Załadowano 89 keywords
📥 Ładowanie spaCy model: en_core_web_lg (language: en)
   ✓ spaCy załadowany

📌 STAGE 5/7 - Scoring [RUN_ID: 20250116_120045_xyz]
🧠 AI Semantic Scoring dla 150 segmentów...
   System prompt: You are an expert at analyzing live streams and viral content.
   ✓ Batch 1: avg score 0.71

📦 HIGHLIGHT PACKER - PLAN PAKOWANIA

📅 HARMONOGRAM PREMIER (2 części):
--------------------------------------------------------------------------------

  Part 1/2:
  📺 Title: 🎯 Best Moments | PART 1/2 | 12.01.2025
  🗓️  Premiere: 13.01.2025 o 18:00
  ⏱️  Duration: 14m 15s
  🎬 Clips: 12
  ⭐ Avg score: 0.68
```

---

## Files Modified

1. ✅ `pipeline/config.py`
   - Dodano `language: str = "pl"` do Config
   - Language-aware defaults w `__post_init__`
   - ScoringConfig.set_language_aware_labels()

2. ✅ `pipeline/stage_03_transcribe.py`
   - Force configured language
   - Language-aware initial prompts w ASRConfig

3. ✅ `pipeline/stage_04_features.py`
   - Language-aware keywords loading
   - Language-aware spaCy model with fallbacks

4. ✅ `pipeline/stage_05_scoring_gpt.py`
   - _get_system_prompt()
   - _get_scoring_prompt()
   - Language-aware interest labels

5. ✅ `pipeline/highlight_packer.py`
   - __init__(language: str)
   - _translate() method
   - Generic, language-aware titles

6. ✅ `pipeline/stage_08_thumbnail.py`
   - _translate() method
   - Language-aware thumbnail text

7. ✅ `pipeline/processor.py`
   - Pass language to HighlightPacker
   - Generic titles (no hardcoded "Sejm", "Gorące Momenty")

8. ✅ `pipeline/cache_manager.py`
   - Include `global_language` in config hash

---

## Korzyści

### PRZED:
- ❌ Tylko polski język
- ❌ Hardcoded "Posiedzenie Sejmu", "Gorące Momenty"
- ❌ Niemożliwe generowanie shortsów dla EN streamers
- ❌ Brak fallback dla spaCy models
- ❌ Keywords tylko po polsku

### PO:
- ✅ **Pełne wsparcie PL i EN**
- ✅ **Generic titles** - działa dla parlament + streamers
- ✅ **Automatyczna detekcja keywords** (keywords_pl.csv, keywords_en.csv)
- ✅ **Fallback dla spaCy models** (lg → md → sm)
- ✅ **GPT prompts dostosowane do contentu** (political debates vs gaming streams)
- ✅ **Cache invalidation** przy zmianie języka
- ✅ **Wszystkie UI texty przetłumaczone**

---

## Test Plan

### Test 1: Polski content (Sejm)
```bash
# config.yml
general:
  language: pl

# Run
python cli.py --input sejm_2025_01_12.mp4

# Expected:
# - Whisper language="pl"
# - Keywords: keywords_pl.csv
# - spaCy: pl_core_news_lg
# - GPT prompt: "Oceń te fragmenty debaty sejmowej..."
# - Titles: "Część 1/3", "Najlepsze Momenty"
```

### Test 2: English content (Gaming stream)
```bash
# config.yml
general:
  language: en

# Run
python cli.py --input gaming_stream_2025_01_12.mp4

# Expected:
# - Whisper language="en"
# - Keywords: keywords_en.csv (log warning if missing)
# - spaCy: en_core_web_lg (fallback to md/sm if needed)
# - GPT prompt: "Rate these stream/video segments..."
# - Titles: "Part 1/2", "Best Moments"
```

### Test 3: Cache invalidation
```bash
# Run 1: language=pl
python cli.py --input video.mp4
# → Cache saved: cache/{hash}_pl/

# Run 2: change language=en
python cli.py --input video.mp4
# → Cache miss dla Stage 3, 5 (language zmienił prompty i initial_prompt)
# → Cache saved: cache/{hash}_en/
```

---

## Summary

✅ **Language parameter** propagates through entire pipeline
✅ **Whisper**: forced language="en" (no auto-detect)
✅ **spaCy**: pl_core_news_lg → en_core_web_lg (z fallback)
✅ **Keywords**: keywords_pl.csv i keywords_en.csv (log warning if missing)
✅ **GPT**: PL i EN prompt versions + prompt_version dla cache
✅ **UI**: "Część" → "Part", daty, output names
✅ **Generic names**: no hardcoded "Gorące Momenty Sejmu"
✅ **Cache**: invalidation przy zmianie języka

Pipeline teraz wspiera zarówno polski parlament jak i anglojęzyczne livestreamy!
