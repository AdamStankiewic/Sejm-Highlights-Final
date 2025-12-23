# Smart Splitter (HighlightPacker) - Audit Report

**Data audytu**: 2025-12-23
**Powód**: User zgłosił nieprawidłowe dzielenie filmu (2 części zamiast 1)
**Status**: DESIGN FLAW ZIDENTYFIKOWANY - funkcja domyślnie wyłączona

---

## 🔴 PROBLEM

### Raportowany przypadek użytkownika:

| Parametr | Wartość |
|----------|---------|
| Materiał źródłowy | 6.3 godzin |
| Wybrane klipy (Stage 6) | 24.1 minut |
| Ustawiony target duration | 33 minuty (1980s) |
| Smart Splitter | WŁĄCZONY |
| **Rezultat** | **2 filmy: Part 1 (11m 55s) + Part 2 (12m 10s)** |
| **Oczekiwanie** | **1 film (24.1 min)** |

### Pytanie użytkownika:
> "W takim razie Sam SMART SPLITTER MA sens? jest sens go trzymać w tej aplikacji?"

---

## 🔍 ROOT CAUSE ANALYSIS

### DESIGN FLAW #1: Decyzje oparte na długości ŹRÓDŁA, nie WYNIKACH selekcji

**Lokalizacja**: `pipeline/processor.py:289-301`

```python
# BŁĘDNA LOGIKA:
if self.highlight_packer and source_duration >= self.config.packer.min_duration_for_split:
    # ❌ Decyzja PRZED selekcją klipów!
    packing_plan = self.highlight_packer.calculate_packing_strategy(
        source_duration  # ❌ Używa długości ŹRÓDŁA (6.3h)
    )
```

**Problem**:
- System analizuje długość źródła (6.3h) i decyduje: "potrzebne 2 części"
- Następnie Stage 6 (Selection) wybiera tylko 24.1 min klipów
- Ale decyzja o podziale już została podjęta!
- Rezultat: 24.1 min dzielone na 2 części po ~12 min każda

**Powinno być**:
```python
# POPRAWNA LOGIKA (nie zaimplementowana):
# 1. Stage 6: Selection → selected_clips (24.1 min)
# 2. Porównaj: 24.1 min < 33 min target → NO SPLIT NEEDED
# 3. Generuj 1 film
```

---

### DESIGN FLAW #2: Nadpisywanie user settings bez pytania

**Lokalizacja**: `pipeline/processor.py:304-311`

```python
original_target = self.config.selection.target_total_duration  # 1980s (33 min)
if packing_plan.total_target_duration != original_target:
    change_reason = (
        f"HighlightPacker dostosował target duration: {original_target}s → {packing_plan.total_target_duration}s\n"
        f"   Powód: Materiał {source_duration/3600:.1f}h wymaga {packing_plan.num_parts} części "
    )
    # ❌ NADPISANIE bez user approval!
```

**Problem**:
- User jawnie ustawił: **33 minuty**
- System nadpisał: **38 minut** (2 × 19 min)
- Uzasadnienie: "6.3h source wymaga 2 części"
- To jest naruszenie user intent!

---

### DESIGN FLAW #3: Agresywny threshold (1 godzina)

**Lokalizacja**: `pipeline/config.py:281`, `pipeline/highlight_packer.py:63-69`

```python
# Config:
min_duration_for_split: float = 3600.0  # 1h threshold

# HighlightPacker thresholds:
THRESHOLDS = {
    'short': 3600,      # < 1h → 1 część
    'medium': 7200,     # 1-2h → 2 części  ← 6.3h > 7200 → FORCED 2 parts
    'long': 14400,      # 2-4h → 3 części
    'very_long': 21600  # 4-6h → 4 części
}

def _calculate_num_parts(self, duration: float) -> int:
    if duration < self.THRESHOLDS['short']:  # < 1h
        return 1
    elif duration < self.THRESHOLDS['medium']:  # 1-2h
        return 2  # ← 6.3h triggers this (actually goes to next branch)
    elif duration < self.THRESHOLDS['long']:  # 2-4h
        return 3
    elif duration < self.THRESHOLDS['very_long']:  # 4-6h
        return 4
    else:
        # 6.3h = 22680s > 21600s → min(6, ceil(22680/14400)) = min(6, 2) = 2
        return min(6, math.ceil(duration / 14400))  # ← 6.3h → 2 parts
```

**Problem**:
- 6.3h source → automatycznie 2 części wymuszonych
- Ignoruje fakt, że selection wybierze tylko ~10% (24 min)
- Threshold powinien być oparty na SELECTED duration, nie source!

---

## 📊 FLOW COMPARISON

### OBECNY FLOW (BŁĘDNY):
```
Stage 1: Ingest
    ↓
    source_duration = 6.3h
    ↓
HighlightPacker.calculate_packing_strategy(6.3h)
    ↓
    6.3h > 1h threshold → FORCE 2 parts
    ↓
    Adjust target: 33 min → 38 min (2×19min)
    ↓
Stage 6: Selection (targeting 38 min)
    ↓
    Only 24.1 min selected (not enough high-score clips)
    ↓
HighlightPacker.split_clips_into_parts(24.1 min, num_parts=2)
    ↓
    Part 1: 11m 55s
    Part 2: 12m 10s
    ↓
Stage 7: Export 2 parts ❌ NIEPOTRZEBNE!
```

### PRAWIDŁOWY FLOW (POWINIEN BYĆ):
```
Stage 1: Ingest
    ↓
    source_duration = 6.3h (tylko info, nie decyzja!)
    ↓
Stage 6: Selection (targeting 33 min)
    ↓
    selected_clips = 24.1 min
    ↓
Decision Point:
    24.1 min < 33 min target → NO SPLIT NEEDED
    ↓
Stage 7: Export 1 film (24.1 min) ✅ POPRAWNE!
```

---

## 💡 PRZYPADKI UŻYCIA

### Kiedy Smart Splitter MÓGŁBY mieć sens:

1. **Netflix-style serialization**
   - Zawsze dziel content na 15-min odcinki (jak serial)
   - User NIE ustawia target duration - system w pełni autonomiczny

2. **Daily upload schedule**
   - Cel: Zawsze 3 części = 3 dni contentu
   - Deterministyczny podział niezależnie od długości

3. **API/automation mode**
   - Brak user input
   - System podejmuje wszystkie decyzje

### Dlaczego NIE PASUJE do obecnego use case:

❌ User chce mieć **kontrolę** nad długością filmu (33 min)
❌ System ma **szanować** user target, nie nadpisywać go
❌ Podział powinien być **opt-in** (gdy selected > target), nie forced

---

## 🛠️ ROZWIĄZANIA

### ✅ ZAIMPLEMENTOWANE: Quick Fix (disable by default)

**Zmienione pliki**:

1. **`pipeline/config.py:278`**
```python
enabled: bool = False  # DISABLED: fixes unwanted splits until logic refactored
```

2. **`app.py:1146`**
```python
self.splitter_enabled.setChecked(False)  # DISABLED by default
```

**Rezultat**:
- Smart Splitter domyślnie wyłączony
- User może manualnie włączyć jeśli potrzebuje multi-part scheduling
- System respektuje user target duration (33 min)
- 24.1 min selected clips → 1 film ✅

---

### 🔄 DŁUGOTERMINOWE: Refaktor logiki (nie zaimplementowane)

**Zmiana fundamentalnej logiki**:

```python
# PRZED (processor.py) - ZŁE:
if source_duration >= min_duration_for_split:
    packing_plan = calculate_packing_strategy(source_duration)

# PO - POPRAWIONE:
# Stage 6: Selection
selected_clips_duration = sum(clip['duration'] for clip in selected_clips)

# Split ONLY if selected clips exceed target
if selected_clips_duration > user_target * 1.2:  # 20% tolerance
    packing_plan = calculate_packing_strategy_from_selection(
        selected_clips_duration,  # ← Use ACTUAL selection, not source!
        user_target=user_target
    )
else:
    packing_plan = None  # No split needed
```

**Zalety refaktoru**:
- ✅ Decyzje oparte na FAKTYCZNEJ selekcji, nie założeniach
- ✅ Respektuje user target
- ✅ Split tylko gdy NAPRAWDĘ potrzebny

**Wymagania**:
- Przeniesienie logiki HighlightPacker PO Stage 6
- Nowa metoda `calculate_packing_strategy_from_selection()`
- Testy dla różnych scenariuszy (selected < target, selected > target)

---

## 📝 WNIOSKI

1. **Smart Splitter w obecnej formie ma fundamentalny design flaw**
   - Podejmuje decyzje PRZED poznaniem wyników selekcji
   - Nadpisuje user settings bez pytania
   - Wymusza split nawet gdy nie jest potrzebny

2. **Quick fix (disable by default) rozwiązuje problem natychmiast**
   - User może ręcznie włączyć jeśli potrzebuje multi-part content
   - System respektuje user target duration
   - Brak niespodzianek w postaci niepotrzebnych splitów

3. **Długoterminowe rozwiązanie wymaga refaktoru**
   - Logika powinna działać PO Stage 6 (Selection)
   - Decyzje oparte na selected_clips_duration, nie source_duration
   - Opt-in approach: split tylko gdy selected > target

4. **Alternatywa: Całkowite usunięcie funkcji**
   - Jeśli user chce 2 filmy → może uruchomić pipeline 2× z target=15min
   - Simplicity > complexity
   - Mniej "magicznych" zachowań = bardziej przewidywalny system

---

## 🎯 REKOMENDACJA

**Status**: Smart Splitter **WYŁĄCZONY DOMYŚLNIE** (commit: pending)

**Dla użytkowników**:
- System będzie respektował Twój target duration
- Jeśli potrzebujesz multi-part content → włącz manualnie w GUI
- Brak automatycznych splitów i nadpisywania targetu

**Dla developerów**:
- Rozważ refaktor logiki (decyzje PO selekcji, nie przed)
- Albo całkowite usunięcie funkcji jeśli nie jest kluczowa
- Dokumentuj design decisions i trade-offs

---

**Pytanie użytkownika**: "Czy Smart Splitter ma sens?"
**Odpowiedź**: **NIE w obecnej formie** - ma design flaw, dlatego został wyłączony domyślnie.
