# 🔍 KRYTYCZNA ANALIZA: AI Metadata Generation Issues

**Data**: 2024-12-26
**Problem**: System wygenerował tytuł o polskiej polityce ("Polish Politics: Pis vs Po Showdown!") dla streamu Asmongolda/Zackrawrr

---

## 🔴 PROBLEM 1: Błędna Detekcja Contentu (Sejm vs Streamer)

### Co się stało:
```
Input:  temp/.../zackrawrr - [DROPS ON] BIG DAY HUGE DRAMA.../selected_clips.json (40 clips)
Streamer: asmongold
Generated Title: "Unbelievable Moment in Polish Politics: Pis vs Po Showdown! 🇵🇱🔥"
Content Type: asmongold_gaming
```

**To jest CAŁKOWICIE błędny tytuł dla contentu Asmongolda!**

### Główne Przyczyny:

#### A) Niewłaściwy content w clips.json
**Hipoteza**: Plik `selected_clips.json` prawdopodobnie zawiera **transkrypcje z Sejmu**, nie z Asmongolda.

**Dlaczego tak myślę:**
1. Auto-detekcja analizuje pierwsze 3 clipy (generator.py:182-184):
   ```python
   for clip in clips[:3]:
       text += " " + clip.get("title", "").lower()
       text += " " + clip.get("transcript", "")[:200].lower()
   ```

2. Sprawdza słowa kluczowe (generator.py:191-202):
   ```python
   if any(kw in text for kw in ["posiedzenie", "obrady sejmu", "obrady"]):
       return f"sejm_meeting{lang_suffix}"
   ```

3. Jeśli transkrypcja zawiera "PiS", "PO", "obrady" → AI generuje tytuł o polityce

**POTRZEBUJEMY ZWERYFIKOWAĆ**: Co faktycznie jest w tym pliku clips.json?

```powershell
# Sprawdź pierwsze 3 clipy w pliku:
python -c "import json; clips = json.load(open(r'C:\Users\adams\Desktop\Sejm higlights CODEX\temp\20251223_145519_2gmy_[12-19-25] zackrawrr - [DROPS ON] BIG DAY HUGE DRAMA EPSTEIN RELEASE NEW BIG NEWS AND GAMES MULTISTREAMING+REACTS  ｜ Follow  @asmongold247\selected_clips.json')); print('\n\n'.join([f\"Clip {i+1}:\nTitle: {c.get('title', 'N/A')}\nTranscript: {c.get('transcript', '')[:200]}...\" for i, c in enumerate(clips[:3])]))"
```

#### B) Brak rozróżnienia SEJM mode vs STREAMER mode

**Problem**: Nawet jeśli `content_type = "asmongold_gaming"`, prompty NIE PODKREŚLAJĄ różnicy stylu:

**SEJM mode powinien:**
- Formalny, poważny ton
- Kontekst polityczny
- Brak emojis/memes
- Język profesjonalny
- Przykład: "Gorąca debata w Sejmie: PiS kontra PO w sprawie budżetu"

**STREAMER mode powinien:**
- Casual, memowy ton
- Gaming slang
- Dużo emojis (🔥💥😱)
- CAPS LOCK dla emfazy
- Cytaty z streamera
- Przykład: "ASMON REACTS TO INSANE DRAMA 😱 Chat Goes WILD! 🔥"

**Obecnie prompty są UNIWERSALNE** - nie ma specjalnych instrukcji dla różnych modów!

---

## 🔴 PROBLEM 2: Język NIE REAGUJE na ustawienia GUI

### Czego oczekujesz:
```
GUI: Transcription Language = PL → Tytuł po polsku
GUI: Transcription Language = EN → Tytuł po angielsku
```

### Co faktycznie się dzieje:

```python
# generator.py:87
lang = language or profile.primary_language

# asmongold.yaml:27
primary_language: "en"

# sejm.yaml:15
primary_language: "pl"
```

**Język pochodzi z profilu streamera (hardcoded w YAML), NIE z GUI!**

### Brakujący Link:

1. **Gdzie GUI przechowuje ustawienie języka transkrypcji?**
   - app.py? config.yaml? session settings?

2. **Jak przekazać to do generate_metadata_standalone.py?**
   - Obecnie script NIE MA dostępu do GUI settings

3. **Jak synchronizować język transkrypcji z językiem tytułu?**
   - Jeśli user wybierze "Polish transcription" → tytuł powinien być PL
   - Jeśli user wybierze "English transcription" → tytuł powinien być EN

### Możliwe Rozwiązania:

#### Opcja A: CLI argument
```powershell
python scripts/generate_metadata_standalone.py \
  --input selected_clips.json \
  --streamer asmongold \
  --language pl   # ← NOWY PARAMETR
```

#### Opcja B: Odczyt z session config
```python
# W app.py, zapisz language do session metadata
session_config = {
    "transcription_language": "pl",  # z GUI
    "streamer_id": "asmongold"
}

# generate_metadata_standalone.py odczytuje:
with open("output/session_xxx/config.json") as f:
    config = json.load(f)
    language = config.get("transcription_language", "pl")
```

#### Opcja C: Smart detection z transkrypcji
```python
# Wykryj język z pierwszych 3 transkrypcji
def detect_language(clips):
    # Jeśli większość słów to polski → "pl"
    # Jeśli większość słów to angielski → "en"
    pass
```

---

## 🔴 PROBLEM 3: Słaba Auto-Detekcja Content Type

### Obecny kod (generator.py:204-209):
```python
# Gaming streamers - simple heuristic
else:
    if any(kw in text for kw in ["irl", "just chatting", "talking", "reacts"]):
        return f"{streamer_id}_irl"
    else:
        return f"{streamer_id}_gaming"
```

### Problemy:

1. **Tylko 4 keywords w języku angielskim**
   - Jeśli transkrypcja jest PO POLSKU: "Asmon reaguje na..." → NIE wykryje "reacts"
   - Potrzebne polskie odpowiedniki: ["reaguje", "rozmawia", "czat"]

2. **Nie weryfikuje czy clipsy są od właściwego streamera**
   - Co jeśli user podał `--streamer asmongold` ale clips.json zawiera Sejm content?
   - System nie sprawdza spójności!

3. **Mieszany content**
   - Jeśli 2/3 clipów to gaming, 1/3 to IRL → co wybrać?
   - Potrzebna lepsza heurystyka (większość wygrywa?)

### Lepsze Rozwiązanie:

```python
def _auto_detect_content_type(self, clips, streamer_id, language):
    # 1. Sprawdź czy to w ogóle właściwy streamer
    self._validate_clips_match_streamer(clips, streamer_id)

    # 2. Multi-language keyword matching
    keywords = {
        "irl": {
            "en": ["irl", "just chatting", "talking", "reacts", "react"],
            "pl": ["irl", "rozmawia", "reaguje", "czat", "reakcja"]
        },
        "gaming": {
            "en": ["game", "gaming", "playing", "boss", "level"],
            "pl": ["gra", "granie", "gra w", "boss", "poziom"]
        },
        "sejm": {
            "pl": ["posiedzenie", "sejm", "obrady", "poseł", "pis", "po"]
        }
    }

    # 3. Score każdego typu contentu
    scores = self._score_content_types(clips, keywords, language)

    # 4. Zwróć najwyższy score
    return max(scores, key=scores.get)
```

---

## 🔴 PROBLEM 4: Brak Walidacji Input → Output

### Co powinno się dziać:

```python
# PRZED generowaniem AI metadata:
def validate_generation_request(clips, streamer_id):
    """Weryfikuj czy request ma sens"""

    # 1. Sprawdź czy clips pasują do streamera
    detected_streamer = detect_streamer_from_clips(clips)
    if detected_streamer != streamer_id:
        raise ValueError(
            f"❌ CONFLICT: Clips look like {detected_streamer} content, "
            f"but you specified --streamer {streamer_id}!\n"
            f"   Are you using the right clips.json file?"
        )

    # 2. Sprawdź czy język transkrypcji pasuje do profilu
    detected_lang = detect_language_from_transcripts(clips)
    profile_lang = profile.primary_language

    if detected_lang != profile_lang:
        logger.warning(
            f"⚠️  Transcripts are in {detected_lang}, "
            f"but {streamer_id} profile uses {profile_lang}. "
            f"Titles will be generated in {profile_lang}."
        )
```

---

## 💡 REKOMENDOWANE ROZWIĄZANIA

### 🎯 Priorytet 1: Zweryfikuj Content Clips

**NAJPIERW SPRAWDŹ** co jest w tym pliku selected_clips.json!

```powershell
# Wyświetl pierwsze 3 transkrypcje:
python -c "import json; clips = json.load(open(r'C:\Users\adams\Desktop\Sejm higlights CODEX\temp\20251223_145519_2gmy_[12-19-25] zackrawrr - [DROPS ON] BIG DAY HUGE DRAMA EPSTEIN RELEASE NEW BIG NEWS AND GAMES MULTISTREAMING+REACTS  ｜ Follow  @asmongold247\selected_clips.json')); [print(f'Clip {i+1}:\n{c.get(\"transcript\", \"\")[:300]}\n') for i, c in enumerate(clips[:3])]"
```

**Jeśli to faktycznie SEJM content** → używasz złego pliku!
**Jeśli to Asmongold content** → mamy poważny bug w generowaniu tytułów.

### 🎯 Priorytet 2: Dodaj --language Argument

```python
# scripts/generate_metadata_standalone.py
parser.add_argument(
    "--language", "-l",
    choices=["pl", "en"],
    help="Title/description language (overrides profile default)"
)

# Przekaż do generator:
metadata = generator.generate_metadata(
    clips=clips,
    streamer_id=streamer_id,
    platform=platform,
    video_type=video_type,
    language=args.language,  # ← NOWY
    force_regenerate=force_regenerate
)
```

### 🎯 Priorytet 3: Mode-Specific Prompts

Stwórz osobne prompt templates dla różnych modów:

```python
# prompt_builder.py
def _get_mode_specific_instructions(self, content_type):
    if "sejm" in content_type:
        return """
        TRYB: Polska Polityka / Sejm
        - Używaj formalnego, dziennikarskiego języka
        - Podkreśl kontekst polityczny i instytucjonalny
        - Unikaj emojis (chyba że 🇵🇱)
        - Zachowaj bezstronność
        - Przykład: "Gorąca debata w Sejmie: PiS vs PO ws. budżetu"
        """
    else:
        return """
        TRYB: Gaming Streamer / React Content
        - Używaj casualowego, memowego języka
        - Dużo CAPS LOCK dla EMFAZY
        - Emoji są MILE WIDZIANE (🔥💥😱🎮)
        - Cytuj streamera
        - Przykład: "ASMON REACTS TO INSANE DRAMA 😱 Chat Goes WILD! 🔥"
        """
```

### 🎯 Priorytet 4: Content Validation

```python
# generator.py - na początku generate_metadata()
def generate_metadata(self, clips, streamer_id, ...):
    # WALIDACJA PRZED GENEROWANIEM
    self._validate_clips_consistency(clips, streamer_id, language)

    # ... reszta kodu
```

---

## 📋 PODSUMOWANIE

| Problem | Priorytet | Czas Naprawy | Wpływ |
|---------|-----------|--------------|-------|
| Sprawdź co jest w clips.json | 🔴 P0 | 5 min | CRITICAL - może to być po prostu zły plik! |
| Dodaj --language argument | 🔴 P1 | 30 min | HIGH - user control nad językiem |
| Mode-specific prompts (Sejm vs Streamer) | 🟡 P2 | 2h | HIGH - jakość tytułów |
| Lepsza auto-detekcja content type | 🟡 P2 | 3h | MEDIUM - reliability |
| Content validation | 🟢 P3 | 2h | MEDIUM - user experience |
| Integracja z GUI language settings | 🟢 P3 | 4h | LOW - nice to have |

---

## ❓ PYTANIA DO USER

1. **Co jest w tym pliku clips.json?**
   - Czy to faktycznie clipsy z Asmongolda/Zackrawrr?
   - Czy transkrypcje są po angielsku czy po polsku?

2. **Gdzie GUI przechowuje język transkrypcji?**
   - Jaki plik config/settings?
   - Jak to przekazać do standalone script?

3. **Czy chcesz:**
   - Automatyczne wykrywanie języka z transkrypcji?
   - Manualny parametr `--language pl/en`?
   - Synchronizację z GUI settings?

4. **Styl tytułów dla streamerów:**
   - Zawsze meme-heavy z emoji?
   - Zależny od content type (gaming vs IRL)?
   - Inny dla różnych streamerów (Asmongold vs inni)?
