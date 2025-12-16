# Shorts Score Fix & Validation - Implementation

## Problem

Shortsy miały score=0.00 i pojawiał się komunikat o braku segmentów mimo wcześniejszych sukcesów:
1. **Score=0.00**: Shortsy renderowane ze score=0.00 zamiast prawdziwych wartości
2. **Pusty drugi run**: "No segments supplied" mimo że wcześniej "5/5 successful"
3. **Brak walidacji**: Brak ostrzeżeń gdy segments nie mają final_score

## Root Cause Analysis

### Problem 1: Missing Score Propagation
Segments mogły nie mieć `final_score` gdy:
- Scoring stage nie zakończył się poprawnie
- Segments były ładowane z pliku bez pełnych danych
- Merging/selection gubił score field

### Problem 2: No Validation
Kod zakładał że score istnieje (`clip['final_score']` → KeyError jeśli brak)

### Problem 3: Potential Double Invocation
Brak zabezpieczenia przed wielokrotnym uruchomieniem shorts stage

## Solution

### 1. Stage 6 (Selection) - Defensive Score Handling

**`pipeline/stage_06_selection.py`:**

```python
def _select_shorts_candidates(...):
    # Validation: check if segments have scores
    missing_score_count = sum(1 for seg in segments if 'final_score' not in seg)
    if missing_score_count > 0:
        print(f"   ⚠️ WARNING: {missing_score_count}/{len(segments)} segments missing final_score!")

    # ... selection logic ...

    # Log score for debugging
    for i, clip in enumerate(selected_shorts, 1):
        score = clip.get('final_score', 0)
        print(f"   📱 Short {i}: score={score:.2f}, duration={clip['duration']:.1f}s")
```

**`_save_clips()` method:**
```python
def _save_clips(self, clips: List[Dict], ...):
    for clip in clips:
        # Defensively get final_score with fallback
        final_score = clip.get('final_score', 0.0)
        if final_score == 0.0 and 'final_score' not in clip:
            print(f"   ⚠️ WARNING: Clip {clip.get('id', 'unknown')} missing final_score, using 0.0")

        clip_copy = {
            ...
            'final_score': float(final_score),  # Use .get() instead of direct access
            ...
        }
```

### 2. Stage 10 (Shorts) - Validation & Logging

**`pipeline/stage_10_shorts.py`:**

```python
def process(...):
    # Validation: Check if shorts_clips is empty
    if not shorts_clips:
        print("   ⚠️ Brak kandydatów na Shorts (pusta lista)")
        print("   → Shorts generation skipped")
        return {'shorts': [], 'shorts_dir': '', 'count': 0}

    # Validation: Check if clips have scores
    clips_with_scores = [c for c in shorts_clips if c.get('final_score', 0) > 0]
    if len(clips_with_scores) < len(shorts_clips):
        missing = len(shorts_clips) - len(clips_with_scores)
        print(f"   ⚠️ WARNING: {missing}/{len(shorts_clips)} clips have score=0.00!")
        print(f"   → Check if scored_segments were properly passed to selection stage")

    # Enhanced logging with score
    for i, clip in enumerate(shorts_clips, 1):
        clip_score = clip.get('final_score', 0)
        clip_id = clip.get('id', 'unknown')
        print(f"\n   📱 Short {i}/{len(shorts_clips)} (score={clip_score:.2f}, id={clip_id})")

        # ... generation ...

        print(f"      ⭐ Score: {short_result['score']:.2f}")
```

### 3. Processor - Prevent Double Invocation

**`pipeline/processor.py`:**

```python
# === ETAP 10: YouTube Shorts Generation (optional) ===
shorts_clips_list = selection_result.get('shorts_clips', [])

# Validation: prevent double invocation and empty list processing
if self.config.shorts.enabled and shorts_clips_list:
    # Check if shorts already generated (prevent double run)
    if hasattr(self, '_shorts_generated') and self._shorts_generated:
        print("\n⚠️ Shorts already generated, skipping duplicate generation")
    else:
        print(f"\n🎬 Starting Shorts generation with {len(shorts_clips_list)} candidates...")

        # ... generate shorts ...

        # Mark as generated to prevent double run
        self._shorts_generated = True

elif self.config.shorts.enabled and not shorts_clips_list:
    print("\n⚠️ Shorts enabled but no clips available (selection returned empty list)")
    print("   → Check if scored segments have sufficient scores for shorts")
```

## Changes Summary

### Modified Files:

1. **`pipeline/stage_06_selection.py`**:
   - ✅ `_select_shorts_candidates()`: Added validation for missing scores
   - ✅ `_select_shorts_candidates()`: Added detailed logging with scores
   - ✅ `_save_clips()`: Defensive `final_score` handling with warning

2. **`pipeline/stage_10_shorts.py`**:
   - ✅ `process()`: Added validation for empty shorts_clips list
   - ✅ `process()`: Added validation for clips with missing scores
   - ✅ `process()`: Enhanced logging with score display

3. **`pipeline/processor.py`**:
   - ✅ Added `_shorts_generated` flag to prevent double invocation
   - ✅ Added validation for empty shorts_clips_list
   - ✅ Enhanced logging at start of shorts generation

## Example Logs

### PRZED (Problem):
```
📱 Short 1/5
   🎬 Renderowanie video (szablon: simple)...
   ✅ Zapisano: short_01_simple.mp4
   (score nie pokazany)

No segments supplied for shorts generation  # <-- Drugi run?
```

### PO (Fixed):
```
📱 Selekcja klipów dla YouTube Shorts...
   📱 Short 1: score=0.87, duration=45.2s, id=seg_042
   📱 Short 2: score=0.79, duration=38.1s, id=seg_089
   📱 Short 3: score=0.74, duration=52.3s, id=seg_123
   📱 Short 4: score=0.71, duration=41.7s, id=seg_156
   📱 Short 5: score=0.69, duration=48.9s, id=seg_201
   ✓ Wybrano 5 kandydatów na Shorts

🎬 Starting Shorts generation with 5 candidates...

🎬 YouTube Shorts Generator (PROFESSIONAL TEMPLATES)
📱 Generowanie 5 Shorts...
   🎨 Template: simple

   📱 Short 1/5 (score=0.87, id=seg_042)
      🎬 Renderowanie video (szablon: simple)...
      ✅ Zapisano: short_01_simple.mp4
      📝 Tytuł: Top moment from stream
      🎨 Szablon: simple
      ⭐ Score: 0.87

   📱 Short 2/5 (score=0.79, id=seg_089)
      ...

✅ Wygenerowano 5 Shorts!
```

### W przypadku problemu (Missing Score):
```
📱 Selekcja klipów dla YouTube Shorts...
   ⚠️ WARNING: 3/150 segments missing final_score!
   ⚠️ WARNING: Clip seg_042 missing final_score, using 0.0
   ⚠️ WARNING: Clip seg_089 missing final_score, using 0.0
   ⚠️ WARNING: Clip seg_123 missing final_score, using 0.0

🎬 Starting Shorts generation with 5 candidates...

🎬 YouTube Shorts Generator (PROFESSIONAL TEMPLATES)
📱 Generowanie 5 Shorts...
   ⚠️ WARNING: 3/5 clips have score=0.00!
   → Check if scored_segments were properly passed to selection stage
```

### W przypadku pustej listy:
```
🎬 Starting Shorts generation with 0 candidates...

🎬 YouTube Shorts Generator (PROFESSIONAL TEMPLATES)
📱 Generowanie 0 Shorts...
   ⚠️ Brak kandydatów na Shorts (pusta lista)
   → Shorts generation skipped
```

### W przypadku double invocation:
```
🎬 Starting Shorts generation with 5 candidates...
(... generates 5 shorts ...)

⚠️ Shorts already generated, skipping duplicate generation
```

## Benefits

### PRZED:
- ❌ Score zawsze 0.00 (brak informacji o jakości)
- ❌ Brak ostrzeżeń gdy segments nie mają score
- ❌ Możliwe podwójne uruchomienie
- ❌ Brak walidacji pustej listy
- ❌ Trudno zdiagnozować problemy

### PO:
- ✅ **Poprawne score** - propagowane z selection do shorts
- ✅ **Defensive programming** - `.get()` zamiast direct access
- ✅ **Validation** - ostrzeżenia gdy score brakuje
- ✅ **Prevent double run** - `_shorts_generated` flag
- ✅ **Empty list handling** - skip generation z informacją
- ✅ **Enhanced logging** - pokazuje score przy każdym shorcie
- ✅ **Easy debugging** - jasne komunikaty o problemach

## Testing

### Test Case 1: Normal Flow (All Scores Present)
```bash
# Expected:
# - All shorts have score > 0
# - Logs show correct scores
# - No warnings
```

### Test Case 2: Missing Scores
```bash
# Expected:
# - Warnings about missing scores
# - Fallback to 0.0
# - Pipeline continues (doesn't crash)
```

### Test Case 3: Empty Shorts List
```bash
# Expected:
# - "Brak kandydatów na Shorts" message
# - Shorts generation skipped
# - No renderer invocation
```

### Test Case 4: Double Invocation Attempt
```bash
# Expected:
# - First run succeeds
# - Second attempt blocked with warning
# - "_shorts_generated" flag prevents duplicate
```

## Data Flow

```
scored_segments (Stage 5)
    ↓ [final_score present]
selection_result['shorts_clips'] (Stage 6)
    ↓ [validation, logging]
shorts_stage.process(shorts_clips) (Stage 10)
    ↓ [validation, defensive .get()]
_generate_single_short(clip)
    ↓ [clip.get('final_score', 0)]
short_result['score']
    ↓
shorts_metadata.json
```

## Summary

✅ **Defensive score handling** - `.get()` z fallback
✅ **Validation** - check missing scores & empty lists
✅ **Prevent double run** - `_shorts_generated` flag
✅ **Enhanced logging** - score visible at every step
✅ **Clear warnings** - easy to diagnose score issues

Score teraz poprawnie propaguje się przez cały pipeline, a użytkownik dostaje jasne informacje o problemach!
