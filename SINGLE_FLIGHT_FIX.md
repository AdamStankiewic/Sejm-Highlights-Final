# Single-Flight Fix - Dokumentacja

## Problem

W logach pipeline pojawiało się **podwójne uruchomienie** tego samego procesu:

```
Wybrano plik: ...mp4
Smart Splitter: Wykryto 7.3h materiału...
Załadowano ... Chat.json
Rozpoczęto przetwarzanie...

# ... w trakcie transkrypcji (seg_0084) ...

Wybrano plik: ...mp4  # ← PONOWNE URUCHOMIENIE!
Smart Splitter: Wykryto 7.3h materiału...
ponowne Załadowano ... Chat.json
ponowne Rozpoczęto przetwarzanie... + ponowne ładowanie modeli
```

To powodowało:
- **~3h czasu przetwarzania** zamiast normalnych ~1.5h
- Mieszanie outputów dwóch równoległych procesów
- Potencjalne nadpisywanie plików tymczasowych
- Konflikty w dostępie do GPU

## Źródło problemu

**Znalezione miejsca podwójnego triggera:**

1. **`app.py:932` - `start_processing()`**
   - BRAK kontroli czy `self.processing_thread` już działa
   - Wielokrotne kliknięcie przycisku "Start" tworzyło nowe thready

2. **`pipeline/processor.py:169` - `process()`**
   - BRAK mechanizmu "single flight" - każde wywołanie tworzyło nowy session

## Rozwiązanie

### 1. Thread-safe Lock w `PipelineProcessor`

```python
class PipelineProcessor:
    # Class-level lock (współdzielony między wszystkie instancje)
    _global_lock = threading.Lock()
    _is_running = False
    _current_run_id: Optional[str] = None

    def process(self, input_file: str) -> Dict[str, Any]:
        # === SINGLE-FLIGHT CHECK ===
        with PipelineProcessor._global_lock:
            if PipelineProcessor._is_running:
                raise RuntimeError(
                    f"⚠️ PIPELINE ALREADY RUNNING!\n"
                    f"Current RUN_ID: {PipelineProcessor._current_run_id}\n"
                )

            PipelineProcessor._is_running = True
            self.run_id = self._generate_run_id()
            PipelineProcessor._current_run_id = self.run_id

        try:
            # ... przetwarzanie ...
            return result
        finally:
            # === ZWOLNIJ LOCK ===
            with PipelineProcessor._global_lock:
                PipelineProcessor._is_running = False
                PipelineProcessor._current_run_id = None
```

### 2. RUN_ID dla każdej sesji

Format: `YYYYMMDD_HHMMSS_RANDOM` (np. `20250115_143052_a7f3`)

**Używany w:**
- Katalogach temp: `temp/20250115_143052_a7f3_sejm_2025_01_12/`
- Nazwach plików JSON: `*.json` (w session_dir)
- Logach Stage 1-8: `📌 STAGE 1/7 - Ingest [RUN_ID: 20250115_143052_a7f3]`

**Korzyści:**
- Każde uruchomienie ma unikalny katalog - brak konfliktów
- Łatwe debugowanie - widać w logach który run ma problem
- Artefakty nie nadpisują się między uruchomieniami

### 3. GUI Protection w `app.py`

```python
def start_processing(self):
    # === OCHRONA PRZED WIELOKROTNYM URUCHOMIENIEM ===
    if self.processing_thread and self.processing_thread.isRunning():
        self.log("⚠️ Pipeline już działa! Ignoruję kolejne kliknięcie Start.", "WARNING")
        QMessageBox.warning(
            self,
            "Pipeline już działa",
            "Przetwarzanie jest już w toku.\n\n"
            "Proszę poczekać na zakończenie lub kliknąć Cancel."
        )
        return

    # ... kontynuuj normalnie ...
```

## Logowanie w Stages

Każdy Stage teraz loguje RUN_ID:

```
================================================================================
🚀 PIPELINE START - RUN_ID: 20250115_143052_a7f3
================================================================================

📁 Session directory: temp/20250115_143052_a7f3_sejm_2025_01_12

📌 STAGE 1/7 - Ingest [RUN_ID: 20250115_143052_a7f3]
   Audio extraction i normalizacja... [RUN_ID: 20250115_143052_a7f3]
   ✅ Audio extraction zakończony [RUN_ID: 20250115_143052_a7f3]

📌 STAGE 2/7 - VAD [RUN_ID: 20250115_143052_a7f3]
   Voice Activity Detection... [RUN_ID: 20250115_143052_a7f3]
   ✅ VAD zakończony [RUN_ID: 20250115_143052_a7f3]

# ... itd dla wszystkich stages ...

================================================================================
✅ PIPELINE COMPLETE - RUN_ID: 20250115_143052_a7f3
Total time: 1h 32m 15s
================================================================================

🔓 Pipeline lock released [RUN_ID: 20250115_143052_a7f3]
```

## Test manualny

**Aby przetestować single-flight:**

1. Uruchom aplikację GUI (`python app.py`)
2. Wybierz plik video
3. Kliknij "Start Processing"
4. **NATYCHMIAST** kliknij "Start Processing" ponownie (2-3x szybko)

**Expected behavior:**
- Pierwszy click: Pipeline startuje normalnie
- Kolejne clicks: Wyświetlają popup "Pipeline już działa"
- W logach: TYLKO JEDEN RUN_ID, brak podwójnego startu

**Previous behavior (BEZ FIX):**
- Każdy click tworzył nowy thread
- W logach widzisz 2+ RUN_ID równocześnie
- Pipeline mieszał outputy

## Efekt końcowy

✅ **Jeden pipeline = jeden RUN_ID = jedna praca**

✅ **Logi czytelne** - widać dokładnie który run wykonuje którą operację

✅ **Brak konfliktów** - każdy run ma własny temp directory

✅ **Skrócony czas** - ~1.5h zamiast ~3h (brak duplikacji pracy)

✅ **Thread-safe** - Lock chroni przed race conditions

## Pliki zmodyfikowane

1. `pipeline/processor.py`:
   - Dodano `_global_lock`, `_is_running`, `_current_run_id`
   - Dodano `_generate_run_id()` i `_create_session_directory_with_run_id()`
   - Dodano single-flight check w `process()`
   - Dodano logowanie RUN_ID w każdym Stage
   - Dodano `finally` block do zwolnienia locka

2. `app.py`:
   - Dodano check `if self.processing_thread.isRunning()` w `start_processing()`
   - Dodano QMessageBox warning przy próbie podwójnego startu

3. `test_single_flight.py`:
   - Test weryfikujący mechanizm (wymaga mock'ów - environment bez torch)

## Debugging

Jeśli widzisz w logach:

```
⚠️ PIPELINE ALREADY RUNNING!
Current RUN_ID: 20250115_143052_a7f3
Ignoring duplicate start request to prevent conflicts.
```

To znaczy że **mechanizm działa poprawnie** - zablokował podwójne uruchomienie!

Jeśli widzisz **dwa różne RUN_ID** w tym samym czasie:
```
🚀 PIPELINE START - RUN_ID: 20250115_143052_a7f3
🚀 PIPELINE START - RUN_ID: 20250115_143053_b8k2  # ← PROBLEM!
```

To znaczy że **coś ominęło mechanizm** - trzeba znaleźć inne miejsce triggera.
