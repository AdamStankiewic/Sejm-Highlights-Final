# Highlight Packer Refactor - Dokumentacja

## Problem

**Smart Splitter** miał mieszane odpowiedzialności:
1. ❌ Nazwa sugeruje "techniczny podział materiału" (chunking)
2. ✅ Faktycznie robi "pakowanie highlightów do premier" (scheduling)
3. ❌ Confusion: czy to chunking dla VAD/Whisper, czy scheduling premier?

## Rozwiązanie: Separation of Concerns

### Analiza odpowiedzialności:

#### 1. **LongMediaChunker** (techniczny podział) - NIE POTRZEBNY
- **Odpowiedzialność**: Podział długich materiałów na chunks dla przetwarzania
- **Używany**: PRZED/W TRAKCIE Stage 1-3 (Ingest, VAD, Transcribe)
- **Status**: ✅ **Już zaimplementowany w VAD Stage**
  - `config.vad.max_segment_duration` = 180s (3 min hard limit)
  - VAD automatycznie dzieli segmenty > max_segment_duration
  - Nie ma potrzeby osobnej klasy

#### 2. **HighlightPacker** (pakowanie highlightów) - ZAIMPLEMENTOWANY
- **Odpowiedzialność**: Pakowanie WYBRANYCH klipów do części z harmonogramem premier
- **Używany**: MIĘDZY Stage 6 (Selection) a Stage 7 (Export)
- **Input**: selected_clips.json (Stage 6 output)
- **Output**: parts_metadata z harmonogramem premier YouTube
- **Nowe API**:
  - `calculate_packing_strategy()` zamiast `calculate_split_strategy()`
  - `print_packing_summary()` zamiast `print_split_summary()`
  - `PackingPlan` zamiast `SplitPlan`

---

## Zmienione nazwy

### Pliki:
- `pipeline/smart_splitter.py` → `pipeline/highlight_packer.py`

### Klasy:
- `SmartSplitter` → `HighlightPacker`
- `SplitPlan` → `PackingPlan`
- `SmartSplitterConfig` → `HighlightPackerConfig`

### Config:
- `config.splitter` → `config.packer`
- `self.smart_splitter` → `self.highlight_packer`

### Zmienne:
- `split_plan` → `packing_plan`
- `split_strategy` → (usunięte, teraz PackingPlan)

---

## Nowy przepływ danych

### PRZED:

```
Stage 1: Ingest
   ↓
Smart Splitter (?): calculate_split_strategy()  # ← NIEJASNE: chunking czy scheduling?
   ↓
Stage 2-5: VAD → Transcribe → Features → Scoring
   ↓
Stage 6: Selection
   ↓
Smart Splitter: split_clips_into_parts()        # ← Faktycznie pakowanie
   ↓
Smart Splitter: print_split_summary()           # ← "SMART SPLITTER - PLAN PODZIAŁU"
   ↓
Stage 7: Export (per part)
```

**Problemy:**
- ❌ Nazwa "Smart Splitter" sugeruje chunking, nie scheduling
- ❌ Używany w dwóch miejscach z różnymi celami
- ❌ Confusion między technicznym podziałem a biznesowym pakowaniem

### PO:

```
Stage 1: Ingest
   ↓
HighlightPacker: calculate_packing_strategy()  # Wstępna analiza (adjust target duration)
   ↓
Stage 2-5: VAD → Transcribe → Features → Scoring
   │
   │  (VAD automatycznie dzieli segmenty > max_segment_duration)
   │
   ↓
Stage 6: Selection → selected_clips.json
   ↓
   ↓
========================================================================
📦 HIGHLIGHT PACKER - Pakowanie selected_clips do części
========================================================================
   ↓
HighlightPacker: split_clips_into_parts(selected_clips)
   - Input: selected_clips z Stage 6
   - Dzieli klipy na części według strategii
   ↓
HighlightPacker: generate_part_metadata(parts)
   - Generuje harmonogram premier YouTube
   - Metadata dla każdej części (tytuł, premiera, keywords)
   ↓
HighlightPacker: print_packing_summary(packing_plan)
   - Wyświetla "HIGHLIGHT PACKER - PLAN PAKOWANIA"
   - Pokazuje harmonogram premier
   ↓
========================================================================
   ↓
Stage 7: Export (dla każdej części osobno)
   ↓
Stage 8: Thumbnail (z numerem części)
   ↓
Stage 9: YouTube Upload (z premiere scheduling)
```

**Korzyści:**
- ✅ Jasna odpowiedzialność: pakowanie highlightów, NIE chunking
- ✅ Nazwa odzwierciedla cel: "packing" a nie "splitting"
- ✅ Logi wyraźnie mówią "HIGHLIGHT PACKER"
- ✅ FLOW: Stage 6 (selected_clips) → HighlightPacker → Stage 7 (Export per part)

---

## Diff zmian

### 1. `pipeline/highlight_packer.py` (renamed from `smart_splitter.py`)

**Klasy:**
```diff
- class SmartSplitter:
+ class HighlightPacker:
    """
-   Inteligentny podział treści na części z auto-schedulingiem premier
+   Pakuje wybrane highlighty do części z auto-schedulingiem premier YouTube.
+
+   Używany MIĘDZY Stage 6 (Selection) a Stage 7 (Export).
+   NIE dotyczy technicznego podziału materiału źródłowego.
    """
```

```diff
- @dataclass
- class SplitPlan:
+ @dataclass
+ class PackingPlan:
    """
-   Single source of truth dla strategii podziału.
+   Single source of truth dla strategii pakowania highlightów.
+   Wyliczany RAZ po Stage 6 (Selection) i używany przez Stage 7-9.
    """
```

**Metody:**
```diff
- def calculate_split_strategy(...) -> SplitPlan:
+ def calculate_packing_strategy(...) -> PackingPlan:
    """
-   Oblicz optymalną strategię podziału
+   Oblicz optymalną strategię pakowania highlightów (wyliczana RAZ po Stage 6!)
    """
```

```diff
- def print_split_summary(self, plan: SplitPlan):
+ def print_packing_summary(self, plan: PackingPlan):
    """
-   Wydrukuj podsumowanie planu podziału
+   Wydrukuj podsumowanie planu pakowania highlightów
    """
    print("="*80)
-   print("📊 SMART SPLITTER - PLAN PODZIAŁU")
+   print("📦 HIGHLIGHT PACKER - PLAN PAKOWANIA")
    print("="*80)
```

### 2. `pipeline/config.py`

```diff
  @dataclass
- class SmartSplitterConfig:
+ class HighlightPackerConfig:
+   """
+   Konfiguracja pakowania highlightów do części z harmonogramem premier.
+
+   UWAGA: To NIE jest chunking materiału źródłowego.
+          To jest pakowanie WYBRANYCH klipów (Stage 6) do części dla YouTube.
+   """
    enabled: bool = True
    premiere_hour: int = 18
    ...
```

```diff
  @dataclass
  class Config:
    # Sub-configs
    audio: AudioConfig = None
    ...
-   splitter: SmartSplitterConfig = None
+   packer: HighlightPackerConfig = None  # Renamed from 'splitter'
    youtube: YouTubeConfig = None
    ...
```

```diff
  def __post_init__(self):
    ...
-   if self.splitter is None:
-       self.splitter = SmartSplitterConfig()
+   if self.packer is None:  # Renamed from 'splitter'
+       self.packer = HighlightPackerConfig()
    ...
```

**Backward compatibility:**
```python
# Support both old 'splitter' and new 'packer' keys for backward compatibility
packer = HighlightPackerConfig(**data.get('packer', data.get('splitter', {})))
```

### 3. `pipeline/processor.py`

**Import:**
```diff
- from .smart_splitter import SmartSplitter
+ from .highlight_packer import HighlightPacker
```

**Inicjalizacja:**
```diff
- # Smart Splitter
- self.smart_splitter = None
- if hasattr(config, 'splitter') and config.splitter.enabled:
-     self.smart_splitter = SmartSplitter(
-         premiere_hour=config.splitter.premiere_hour,
-         premiere_minute=config.splitter.premiere_minute
-     )
+ # Highlight Packer (pakowanie selected_clips do części z premierami)
+ self.highlight_packer = None
+ if hasattr(config, 'packer') and config.packer.enabled:
+     self.highlight_packer = HighlightPacker(
+         premiere_hour=config.packer.premiere_hour,
+         premiere_minute=config.packer.premiere_minute
+     )
```

**Po Stage 1 (Ingest):**
```diff
- # === SMART SPLITTER: Analiza strategii podziału ===
- split_plan = None
- if self.smart_splitter and source_duration >= self.config.splitter.min_duration_for_split:
-     print("\n🤖 Wykryto długi materiał - uruchamiam Smart Splitter...")
-     split_plan = self.smart_splitter.calculate_split_strategy(...)
+ # === HIGHLIGHT PACKER: Wstępna analiza strategii pakowania ===
+ # (Faktyczne pakowanie nastąpi PO Stage 6 - Selection)
+ packing_plan = None
+ if self.highlight_packer and source_duration >= self.config.packer.min_duration_for_split:
+     print("\n📦 Materiał kwalifikuje się do pakowania w części - analiza strategii...")
+     packing_plan = self.highlight_packer.calculate_packing_strategy(...)
```

```diff
-     change_reason = f"Smart Splitter dostosował target duration: ..."
+     change_reason = f"HighlightPacker dostosował target duration: ..."
```

**Po Stage 6 (Selection):**
```diff
- # === Po stage 6 (Selection): Podział na części jeśli potrzebny ===
+ # === HIGHLIGHT PACKER: Pakowanie selected_clips do części ===
+ # (FLOW: Stage 6 selected_clips → HighlightPacker → Stage 7 Export per part)
  parts_metadata = None
- if split_plan:
-     print("\n✂️ Dzielę klipy na części według planu...")
-     parts = self.smart_splitter.split_clips_into_parts(...)
-     parts_metadata = self.smart_splitter.generate_part_metadata(...)
-     split_plan.parts_metadata = parts_metadata
-     self.smart_splitter.print_split_summary(split_plan)
+ if packing_plan:
+     print(f"\n📦 Pakowanie {len(selected_clips)} klipów do {packing_plan.num_parts} części...")
+     parts = self.highlight_packer.split_clips_into_parts(...)
+     parts_metadata = self.highlight_packer.generate_part_metadata(...)
+     packing_plan.parts_metadata = parts_metadata
+     self.highlight_packer.print_packing_summary(packing_plan)
```

**Result dict:**
```diff
  result = {
    ...
-   'split_plan': split_plan,
+   'packing_plan': packing_plan,  # Renamed from 'split_plan'
    ...
  }
```

---

## Przykładowe logi PO zmianach

### Materiał 7.3h - pakowanie do 5 części:

```
================================================================================
🚀 PIPELINE START - RUN_ID: 20250115_182045_k9x2
================================================================================

📌 STAGE 1/7 - Ingest [RUN_ID: 20250115_182045_k9x2]
   ✅ Audio extraction zakończony

📦 Materiał kwalifikuje się do pakowania w części - analiza strategii...

⚙️  HighlightPacker dostosował target duration: 1500s → 3000s
   Powód: Materiał 7.3h wymaga 5 części po ~10min każda dla optymalnej retencji

# ... Stages 2-6: VAD, Transcribe, Features, Scoring, Selection ...

📌 STAGE 6/7 - Selection [RUN_ID: 20250115_182045_k9x2]
   ✅ Wybrano 47 klipów [RUN_ID: 20250115_182045_k9x2]

📦 Pakowanie 47 klipów do 5 części...

================================================================================
📦 HIGHLIGHT PACKER - PLAN PAKOWANIA
================================================================================

🎯 Strategia: Podział na 5 części (7.3h → 5x ~10min)
📦 Liczba części: 5
⏱️  Czas na część: ~10m 0s
📊 Score threshold: 0.55
🎬 Kompresja: 11.4%

💡 Powód:
   Material 7.3h > 6h → 5 części (bardzo długi live, serialized content)

⚙️  Config adjustment: HighlightPacker dostosował target duration: 1500s → 3000s
   Powód: Materiał 7.3h wymaga 5 części po ~10min każda dla optymalnej retencji

📅 HARMONOGRAM PREMIER (5 części):
--------------------------------------------------------------------------------

  Część 1/5:
  📺 Tytuł: 🔥 Tusk VS Kaczyński - Posiedzenie Sejmu - Część 1/5 | 12.01.2025
  🗓️  Premiera: 13.01.2025 o 18:00
  ⏱️  Długość: 10m 24s
  🎬 Klipy: 9
  ⭐ Średni score: 0.72
  🔑 Keywords: budżet, podatki, rząd, opozycja, debata

  Część 2/5:
  📺 Tytuł: 💥 Hołownia w Sejmie - Najgorętsze Momenty - Część 2/5 | 12.01.2025
  🗓️  Premiera: 14.01.2025 o 18:00
  ⏱️  Długość: 9m 51s
  🎬 Klipy: 8
  ⭐ Średni score: 0.68
  🔑 Keywords: marszałek, głosowanie, procedura

  # ... części 3-5 ...

================================================================================

📌 STAGE 7/7 - Export [RUN_ID: 20250115_182045_k9x2]

🎬 Eksport części 1/5... [RUN_ID: 20250115_182045_k9x2]
   ✅ Część 1/5 wyeksportowana

# ... reszta exportu ...
```

---

## Podsumowanie zmian

### Pliki zmodyfikowane:
1. ✅ `pipeline/smart_splitter.py` → `pipeline/highlight_packer.py`
2. ✅ `pipeline/config.py` - `SmartSplitterConfig` → `HighlightPackerConfig`
3. ✅ `pipeline/processor.py` - import, flow, logi

### Zmiany koncepcyjne:
1. ✅ **LongMediaChunker** - Nie jest potrzebny (VAD już robi chunking)
2. ✅ **HighlightPacker** - Nowa jasna nazwa dla pakowania highlightów
3. ✅ **PackingPlan** - Nowa nazwa dla planu pakowania (było SplitPlan)
4. ✅ **Logi** - "HIGHLIGHT PACKER" zamiast "SMART SPLITTER"

### Flow:
```
PRZED: Smart Splitter (confusion: chunking czy scheduling?)
   ↓
PO:    HighlightPacker (jasne: pakowanie selected_clips do premier)
```

### Nowy przepływ danych:
```
Stage 6 (Selection)
   → selected_clips.json
      → HighlightPacker.split_clips_into_parts()
         → HighlightPacker.generate_part_metadata()
            → PackingPlan.parts_metadata
               → Stage 7 (Export per part)
                  → Stage 9 (YouTube Upload with premiere scheduling)
```

---

## Test

```bash
# Test HighlightPacker
python pipeline/highlight_packer.py

# Output:
# Strategia pakowania dla 5.0h materiału źródłowego:
#   - Części: 4
#   - Czas na część: 720s (~12.0 min)
#   - Threshold: 0.50
#   - Powód: Material 5.0h = 4-6h → 4 części (długi live, premium content)
#
# Spakowano 30 klipów do 4 części:
#   Część 1: 12 klipów, 30.0 min
#   ...
#
# ================================================================================
# 📦 HIGHLIGHT PACKER - PLAN PAKOWANIA
# ================================================================================
# [Pełny harmonogram premier...]
```

---

## Korzyści

### PRZED:
❌ "Smart Splitter" sugeruje chunking, nie scheduling
❌ Mieszane odpowiedzialności (chunking vs pakowanie)
❌ Confusion w logach i nazewnictwie
❌ Niejasny flow danych

### PO:
✅ **HighlightPacker** - jasna nazwa, jasna odpowiedzialność
✅ **Separation of concerns** - chunking (VAD) vs pakowanie (HighlightPacker)
✅ **Czytelne logi** - "HIGHLIGHT PACKER - PLAN PAKOWANIA"
✅ **Jasny flow** - Stage 6 → HighlightPacker → Stage 7
✅ **Dokumentacja** - komentarze wyjaśniają "NIE chunking, pakowanie highlightów"
✅ **Backward compatibility** - config wspiera zarówno 'packer' jak i 'splitter'
