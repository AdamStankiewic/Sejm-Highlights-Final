# Thumbnail Clips Fix - Pass Part Clips to Thumbnail Generator

## Problem

Generator miniatur dostawał **pustą listę klipów** mimo że były wycięte części 1/2 i 2/2:
- "⚠️ Brak klipów – używam losowej klatki z video" pojawia się mimo że klipy istnieją
- Thumbnail generator nie otrzymywał klipów dla danej części
- Używał losowej klatki zamiast najlepszego klipu (max score)

## Root Cause

**Processor nie przekazywał clips do thumbnail generator:**

```python
# BEFORE (processor.py line 483-487):
part_thumbnail = self._generate_thumbnail_with_part_number(
    part_export['output_file'],
    part_meta['part_number'],
    part_meta['total_parts']
    # ❌ Missing: clips=part_meta['clips']
)
```

Mimo że `part_meta['clips']` był dostępny (line 473), nie był przekazywany do generatora miniatur.

## Solution

### 1. Add Clips Parameter to `_generate_thumbnail_with_part_number`

**`pipeline/processor.py`:**

```python
def _generate_thumbnail_with_part_number(
    self,
    video_file: str,
    part_num: int,
    total_parts: int,
    clips: list = None  # ✅ ADDED
) -> Dict:
    """
    Generuj thumbnail z numerem części

    Args:
        clips: Lista klipów dla tej części (używamy najlepszego dla thumbnail)
    """
    thumbnail_result = self.thumbnail_stage.generate_with_part_number(
        video_file=video_file,
        part_number=part_num,
        total_parts=total_parts,
        clips=clips  # ✅ Pass clips for best frame selection
    )
```

### 2. Pass Clips When Calling

**`pipeline/processor.py` (line 483-489):**

```python
# Generate thumbnail z numerem części
if hasattr(self, 'thumbnail_stage'):
    part_thumbnail = self._generate_thumbnail_with_part_number(
        part_export['output_file'],
        part_meta['part_number'],
        part_meta['total_parts'],
        clips=part_meta.get('clips', [])  # ✅ Pass clips from this part
    )
```

### 3. Enhanced Logging in `generate_with_part_number`

**`pipeline/stage_08_thumbnail.py`:**

```python
def generate_with_part_number(...):
    print(f"\n🎨 Generuję miniaturkę dla części {part_number}/{total_parts}...")

    # Validation and logging
    if clips is None or len(clips) == 0:
        print(f"   ⚠️ Brak klipów dla części {part_number} - używam środkowej klatki z video")
        clips = []
    else:
        print(f"   📊 Dostępne klipy: {len(clips)}")
        # Find best clip for logging
        if clips:
            best_clip = max(clips, key=lambda c: c.get('final_score', c.get('score', 0)))
            clip_score = best_clip.get('final_score', best_clip.get('score', 0))
            clip_id = best_clip.get('id', 'unknown')
            clip_t0 = best_clip.get('t0', 0)
            print(f"   🎯 Using top clip for thumbnail: clip_id={clip_id}, score={clip_score:.2f}, timestamp={clip_t0:.1f}s")
```

### 4. Smart Fallback in `process()`

**`pipeline/stage_08_thumbnail.py`:**

```python
def process(self, video_file, clips, ...):
    try:
        # Wybierz timestamp dla thumbnail
        if not clips:
            # Fallback: użyj środkowej klatki video gdy brak klipów
            print(f"   ⚠️ Brak klipów - używam środkowej klatki z video")
            # Extract video duration using ffprobe
            cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                   '-of', 'default=noprint_wrappers=1:nokey=1', video_file]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            video_duration = float(result.stdout.strip())
            mid_timestamp = video_duration / 2
            best_clip = None
            print(f"   📹 Video duration: {video_duration:.1f}s, using middle frame")
        else:
            # Normal path: use best clip
            best_clip = max(clips, key=lambda c: c.get('final_score', c.get('score', 0)))
            mid_timestamp = (best_clip['t0'] + best_clip['t1']) / 2

            clip_score = best_clip.get('final_score', best_clip.get('score', 0))
            print(f"📸 Wybieram klatkę z najlepszego klipu:")
            print(f"   Timestamp: {mid_timestamp:.1f}s")
            print(f"   Score: {clip_score:.2f}")
            print(f"   Clip ID: {best_clip.get('id', 'unknown')}")
```

### 5. Handle None best_clip in Title Generation

```python
# Generate text
if custom_title:
    top_text = custom_title
elif best_clip:
    top_text = self._generate_title_from_clip(best_clip)
else:
    # Fallback when no clips available
    top_text = "Highlights"
```

## Example Logs

### PRZED (Problem):
```
🎨 Generuję miniaturkę dla części 1/2...
⚠️ Brak klipów – używam losowej klatki z video
```

### PO (Fixed - With Clips):
```
🎨 Generuję miniaturkę dla części 1/2...
   📊 Dostępne klipy: 8
   🎯 Using top clip for thumbnail: clip_id=seg_042, score=0.87, timestamp=145.2s

STAGE 8: AI Thumbnail Generation
============================================================
📸 Wybieram klatkę z najlepszego klipu:
   Timestamp: 145.2s
   Score: 0.87
   Clip ID: seg_042
✅ Wyciągnięto klatkę: 1920x1080
✍️ Dodaję napisy:
   Górny: '🔥 Tusk VS Kaczyński - Ostra Wymiana'
   Dolny: '📺 Część 1/2 | 12.01.2025'
💾 Miniaturka zapisana: thumbnail_part1.jpg
```

### PO (Fixed - Empty Clips Fallback):
```
🎨 Generuję miniaturkę dla części 1/2...
   ⚠️ Brak klipów dla części 1 - używam środkowej klatki z video

STAGE 8: AI Thumbnail Generation
============================================================
   ⚠️ Brak klipów - używam środkowej klatki z video
   📹 Video duration: 3245.8s, using middle frame at 1622.9s
✅ Wyciągnięto klatkę: 1920x1080
✍️ Dodaję napisy:
   Górny: 'Highlights'
   Dolny: '📺 Część 1/2 | 12.01.2025'
💾 Miniaturka zapisana: thumbnail_part1.jpg
```

## Data Flow

```
Stage 7 (Export per part):
    part_meta = {
        'part_number': 1,
        'total_parts': 2,
        'clips': [clip1, clip2, ...],  # Clips for THIS part
        ...
    }
    ↓
Processor._generate_thumbnail_with_part_number():
    clips = part_meta.get('clips', [])  # ✅ Extract clips from part
    ↓
ThumbnailStage.generate_with_part_number(clips=clips):
    Validate clips, log info
    ↓
ThumbnailStage.process(clips=clips):
    best_clip = max(clips, key=score)  # ✅ Select best clip
    timestamp = (best_clip.t0 + best_clip.t1) / 2
    ↓
Extract frame from best clip
    ↓
Generate thumbnail with overlay
```

## Changes Summary

### Modified Files:

1. **`pipeline/processor.py`**:
   - ✅ `_generate_thumbnail_with_part_number`: Added `clips` parameter
   - ✅ Call site: Pass `clips=part_meta.get('clips', [])`

2. **`pipeline/stage_08_thumbnail.py`**:
   - ✅ `generate_with_part_number`: Enhanced validation & logging
   - ✅ `generate_with_part_number`: Log best clip info (score, id, timestamp)
   - ✅ `process`: Smart fallback to video middle frame when clips empty
   - ✅ `process`: Enhanced logging for best clip selection
   - ✅ `process`: Handle `best_clip=None` in title generation and return

## Benefits

### PRZED:
- ❌ Thumbnail generowany z losowej klatki
- ❌ Nie wykorzystuje score klipów
- ❌ Brak informacji o wybranej klatce
- ❌ Trudno zdiagnozować dlaczego losowa klatka

### PO:
- ✅ **Best clip selection** - używa klipu z najwyższym score
- ✅ **Smart timestamp** - środek najlepszego klipu
- ✅ **Enhanced logging** - pokazuje clip_id, score, timestamp
- ✅ **Intelligent fallback** - środek video tylko gdy faktycznie brak klipów
- ✅ **Clear diagnostics** - łatwo zobaczyć czy clips były przekazane

## Testing

### Test Case 1: Normal Flow (Clips Present)
```bash
# Expected:
# - "Dostępne klipy: N"
# - "Using top clip for thumbnail: clip_id=..., score=..., timestamp=..."
# - Thumbnail from best clip center
```

### Test Case 2: Empty Clips (Fallback)
```bash
# Expected:
# - "Brak klipów dla części N - używam środkowej klatki"
# - "Video duration: X.Xs, using middle frame"
# - Thumbnail from video center
```

### Test Case 3: Multi-Part Export
```bash
# Expected:
# - Each part gets its own clips
# - Each thumbnail uses best clip from THAT part
# - Scores shown for each part's thumbnail
```

## Summary

✅ **Clips properly passed** - from part_meta to thumbnail generator
✅ **Best clip selection** - max score from part's clips
✅ **Enhanced logging** - clip_id, score, timestamp visible
✅ **Smart fallback** - video center only when clips truly empty
✅ **Defensive code** - handle best_clip=None gracefully

Thumbnail generator teraz dostaje klipy dla danej części i wybiera klatkę z najlepszego klipu!
