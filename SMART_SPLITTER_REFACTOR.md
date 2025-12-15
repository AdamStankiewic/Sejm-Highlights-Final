# Smart Splitter Refactor - Dokumentacja

## Problem

W logach pipeline'u pojawiały się **niespójne komunikaty** o podziale:

```
Smart Splitter: Wykryto 7.3h materiału...
  → 5 części (~15min każda)          # ← PIERWSZA INFORMACJA

# ... przetwarzanie ...

Strategia: Podział na 2 części        # ← INNA INFORMACJA!
  → ~20min każda

Dostosowano target duration: 1500s → 2400s  # ← BEZ WYJAŚNIENIA DLACZEGO
```

### Przyczyna

1. **Dwa wywołania `print_split_summary()`**:
   - Pierwsze: `processor.py:275` z **pustą listą części** (tylko prognoza)
   - Drugie: `processor.py:377` z **rzeczywistymi danymi** po Selection Stage

2. **Brak single source of truth**:
   - `calculate_split_strategy()` zwracał Dict
   - Dane były kopiowane i modyfikowane w różnych miejscach
   - Logika obliczania była rozproszona

3. **Brak wyjaśnień**:
   - Nie było informacji DLACZEGO wybrano daną liczbę części
   - Nie było wyjaśnienia DLACZEGO zmieniono target duration

---

## Rozwiązanie

### 1. SplitPlan - Single Source of Truth

```python
@dataclass
class SplitPlan:
    """
    Single source of truth dla strategii podziału.
    Wyliczany RAZ i używany przez cały pipeline.
    """
    # Input
    source_duration: float

    # Strategy (computed once)
    num_parts: int
    target_duration_per_part: int
    total_target_duration: int
    min_score_threshold: float
    compression_ratio: float

    # Reasoning (why this strategy)
    reason: str = ""

    # Computed parts (filled after selection)
    parts_metadata: List[Dict[str, Any]] = field(default_factory=list)

    def has_parts(self) -> bool:
        """Czy plan ma wygenerowane części (po selection)"""
        return len(self.parts_metadata) > 0
```

**Korzyści:**
- ✅ Dane wyliczane RAZ
- ✅ Niemutowalny plan (immutable strategy)
- ✅ Łatwe śledzenie przepływu danych
- ✅ Zawiera reasoning ("dlaczego")

### 2. Calculate Once, Display Once

**Przed:**
```python
# processor.py:273
split_strategy = self.smart_splitter.calculate_split_strategy(source_duration)
self.smart_splitter.print_split_summary(split_strategy, [])  # ← PUSTE!

# ... po selection (linia 377) ...
parts_metadata = self.smart_splitter.generate_part_metadata(parts, ...)
self.smart_splitter.print_split_summary(split_strategy, parts_metadata)  # ← PEŁNE!
```

**Po:**
```python
# processor.py:280 - Wylicz plan RAZ
split_plan = self.smart_splitter.calculate_split_strategy(
    source_duration,
    override_parts=override_parts,
    override_target_minutes=override_target_mins
)

# processor.py:394 - Wypełnij częściami po Selection
split_plan.parts_metadata = parts_metadata

# processor.py:397 - Wyświetl FINALNY plan (RAZ!)
self.smart_splitter.print_split_summary(split_plan)
```

### 3. Wyjaśnienia "Dlaczego"

**Nowa metoda:**
```python
def _explain_num_parts_decision(self, duration: float, num_parts: int) -> str:
    hours = duration / 3600

    if num_parts == 1:
        return f"Material {hours:.1f}h < 1h → pojedynczy film (optymalna retencja)"
    elif num_parts == 2:
        return f"Material {hours:.1f}h = 1-2h → 2 części (dobra dla daily schedule)"
    elif num_parts == 3:
        return f"Material {hours:.1f}h = 2-4h → 3 części (optimal split dla retencji)"
    elif num_parts == 4:
        return f"Material {hours:.1f}h = 4-6h → 4 części (długi live, premium content)"
    else:
        return f"Material {hours:.1f}h > 6h → {num_parts} części (bardzo długi live)"
```

**Wyjaśnienie zmian config:**
```python
if split_plan.total_target_duration != original_target:
    change_reason = (
        f"Smart Splitter dostosował target duration: {original_target}s → {split_plan.total_target_duration}s\n"
        f"   Powód: Materiał {source_duration/3600:.1f}h wymaga {split_plan.num_parts} części "
        f"po ~{split_plan.target_duration_per_part/60:.0f}min każda dla optymalnej retencji"
    )
    print(f"\n⚙️  {change_reason}")
    split_plan._config_change_reason = change_reason
```

### 4. Parametry konfiguracyjne

**Dodane do `SmartSplitterConfig`:**
```python
@dataclass
class SmartSplitterConfig:
    # ... existing fields ...

    # Manual overrides (opcjonalne parametry CLI/GUI)
    force_num_parts: Optional[int] = None        # --parts 3
    target_part_minutes: Optional[int] = None    # --target-part-minutes 20
```

**Użycie:**
```python
# processor.py:276-283
override_parts = getattr(self.config.splitter, 'force_num_parts', None)
override_target_mins = getattr(self.config.splitter, 'target_part_minutes', None)

split_plan = self.smart_splitter.calculate_split_strategy(
    source_duration,
    override_parts=override_parts,
    override_target_minutes=override_target_mins
)
```

---

## Przykładowe logi PO zmianach

### Przypadek 1: Material 7.3h (długi live Sejmu)

```
================================================================================
🚀 PIPELINE START - RUN_ID: 20250115_182045_k9x2
================================================================================

📁 Session directory: temp/20250115_182045_k9x2_sejm_2025_01_12

📌 STAGE 1/7 - Ingest [RUN_ID: 20250115_182045_k9x2]
   Audio extraction i normalizacja... [RUN_ID: 20250115_182045_k9x2]
   ✅ Audio extraction zakończony [RUN_ID: 20250115_182045_k9x2]

🤖 Wykryto długi materiał - uruchamiam Smart Splitter...

⚙️  Smart Splitter dostosował target duration: 1500s → 3000s
   Powód: Materiał 7.3h wymaga 5 części po ~10min każda dla optymalnej retencji

# ... Stages 2-6 (VAD, Transcribe, Features, Scoring, Selection) ...

📌 STAGE 6/7 - Selection [RUN_ID: 20250115_182045_k9x2]
   Selekcja najlepszych klipów... [RUN_ID: 20250115_182045_k9x2]
   ✅ Wybrano 47 klipów [RUN_ID: 20250115_182045_k9x2]

✂️ Dzielę klipy na części według planu...

================================================================================
📊 SMART SPLITTER - PLAN PODZIAŁU
================================================================================

🎯 Strategia: Podział na 5 części (7.3h → 5x ~10min)
📦 Liczba części: 5
⏱️  Czas na część: ~10m 0s
📊 Score threshold: 0.55
🎬 Kompresja: 11.4%

💡 Powód:
   Material 7.3h > 6h → 5 części (bardzo długi live, serialized content)

⚙️  Config adjustment: Smart Splitter dostosował target duration: 1500s → 3000s
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

🎬 Eksport części 2/5... [RUN_ID: 20250115_182045_k9x2]
   ✅ Część 2/5 wyeksportowana

# ... części 3-5 ...

================================================================================
✅ PIPELINE COMPLETE - RUN_ID: 20250115_182045_k9x2
Total time: 1h 28m 33s
================================================================================

🔓 Pipeline lock released [RUN_ID: 20250115_182045_k9x2]
```

### Przypadek 2: Material 1.5h (krótszy live)

```
🤖 Wykryto długi materiał - uruchamiam Smart Splitter...

⚙️  Smart Splitter dostosował target duration: 900s → 1800s
   Powód: Materiał 1.5h wymaga 2 części po ~15min każda dla optymalnej retencji

# ... Stages 2-6 ...

✂️ Dzielę klipy na części według planu...

================================================================================
📊 SMART SPLITTER - PLAN PODZIAŁU
================================================================================

🎯 Strategia: Podział na 2 części (1.5h → 2x ~15min)
📦 Liczba części: 2
⏱️  Czas na część: ~15m 0s
📊 Score threshold: 0.45
🎬 Kompresja: 33.3%

💡 Powód:
   Material 1.5h = 1-2h → 2 części (dobra dla daily schedule)

⚙️  Config adjustment: Smart Splitter dostosował target duration: 900s → 1800s
   Powód: Materiał 1.5h wymaga 2 części po ~15min każda dla optymalnej retencji

📅 HARMONOGRAM PREMIER (2 części):
--------------------------------------------------------------------------------

  Część 1/2:
  📺 Tytuł: ⚡ Sejm: Budżet vs Opozycja - Część 1/2 | 12.01.2025
  🗓️  Premiera: 13.01.2025 o 18:00
  ⏱️  Długość: 14m 58s
  🎬 Klipy: 12
  ⭐ Średni score: 0.65

  Część 2/2:
  📺 Tytuł: 🎯 Posiedzenie Sejmu - Gorące Momenty - Część 2/2 | 12.01.2025
  🗓️  Premiera: 14.01.2025 o 18:00
  ⏱️  Długość: 15m 02s
  🎬 Klipy: 11
  ⭐ Średni score: 0.61

================================================================================
```

### Przypadek 3: Manual override (--parts 3 --target-part-minutes 12)

```
🤖 Wykryto długi materiał - uruchamiam Smart Splitter...

⚙️  Smart Splitter dostosował target duration: 900s → 2160s
   Powód: Materiał 5.0h wymaga 3 części po ~12min każda dla optymalnej retencji

# ... Stages 2-6 ...

================================================================================
📊 SMART SPLITTER - PLAN PODZIAŁU
================================================================================

🎯 Strategia: Podział na 3 części (5.0h → 3x ~12min)
📦 Liczba części: 3
⏱️  Czas na część: ~12m 0s
📊 Score threshold: 0.50
🎬 Kompresja: 12.0%

💡 Powód:
   Manual override: 3 części wymuszonych przez użytkownika | Target duration: 12min (manual override)

# ... reszta planu ...

================================================================================
```

---

## Pliki zmodyfikowane

### 1. `pipeline/smart_splitter.py`

**Zmiany:**
- ✅ Dodano `SplitPlan` dataclass (single source of truth)
- ✅ Zmieniono `calculate_split_strategy()` aby zwracało `SplitPlan` zamiast `Dict`
- ✅ Dodano parametry `override_parts` i `override_target_minutes`
- ✅ Dodano metodę `_explain_num_parts_decision()` dla wyjaśnień
- ✅ Refaktoryzacja `print_split_summary()` - przyjmuje `SplitPlan`, wyświetla reasoning
- ✅ Naprawiono test w `if __name__ == "__main__"`

### 2. `pipeline/processor.py`

**Zmiany:**
- ✅ Zmieniono `split_strategy` (Dict) na `split_plan` (SplitPlan)
- ✅ **USUNIĘTO pierwsze** `print_split_summary()` z pustą listą (linia 275)
- ✅ Dodano pobieranie `override_parts` i `override_target_minutes` z config
- ✅ Dodano szczegółowe logowanie DLACZEGO target duration został zmieniony
- ✅ Wypełnienie `split_plan.parts_metadata` po Selection Stage
- ✅ **Jedno wywołanie** `print_split_summary(split_plan)` z pełnymi danymi
- ✅ Naprawiono return value: `'split_plan': split_plan` zamiast `split_strategy`

### 3. `pipeline/config.py`

**Zmiany:**
- ✅ Dodano `force_num_parts: Optional[int] = None` do `SmartSplitterConfig`
- ✅ Dodano `target_part_minutes: Optional[int] = None` do `SmartSplitterConfig`

---

## Test

```bash
# Testuj Smart Splitter (mock data)
python pipeline/smart_splitter.py

# Output:
# Strategia dla 5.0h materiału:
#   - Części: 4
#   - Czas na część: 720s (~12.0 min)
#   - Threshold: 0.50
#   - Powód: Material 5.0h = 4-6h → 4 części (długi live, premium content)
#
# [Pełny plan z harmonogramem premier...]
```

---

## Korzyści

### Przed refaktorem:
❌ Niespójne komunikaty ("5 części" vs "2 części")
❌ Brak wyjaśnienia DLACZEGO wybrano strategię
❌ Zmiana target duration bez powodu
❌ Dwa wywołania `print_split_summary()` z różnymi danymi
❌ Dict jako nośnik danych (łatwo zmutowalny)

### Po refaktorze:
✅ **Spójne komunikaty** - plan wyświetlany RAZ, z pełnymi danymi
✅ **Wyjaśnienia** - widać DLACZEGO wybrano daną strategię
✅ **Transparentność** - zmiany config mają reasoning
✅ **Single source of truth** - `SplitPlan` jako jedyne źródło prawdy
✅ **Konfigurowalne** - parametry `--parts` i `--target-part-minutes`
✅ **Łatwe debugowanie** - pełna kontrola nad przepływem danych

---

## Podsumowanie

Refaktoryzacja rozwiązała problem **niespójnych logów** poprzez:

1. **SplitPlan dataclass** - single source of truth
2. **Calculate once, display once** - plan wyliczany i wyświetlany RAZ
3. **Reasoning** - każda decyzja ma wyjaśnienie "dlaczego"
4. **Configurability** - opcjonalne parametry override
5. **Clean logs** - czytelne, spójne, informacyjne logi

Teraz użytkownik widzi **jeden, spójny komunikat** z pełnym planem podziału i jasnym uzasadnieniem wszystkich decyzji systemu.
