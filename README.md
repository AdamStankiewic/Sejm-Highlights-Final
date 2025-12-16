# 🎬 Sejm Highlights AI - Desktop Application

Automatyczne generowanie kompilacji "Najlepszych momentów z Sejmu" z długich transmisji (2-8h) poprzez inteligentną ekstrakcję i łączenie najciekawszych fragmentów politycznych debat.

**Output:** Film 10-20 minut zawierający 8-15 kluczowych momentów, gotowy do publikacji.

---

## 📋 Spis treści

- [Wymagania systemowe](#wymagania-systemowe)
- [Instalacja](#instalacja)
- [Użycie](#użycie)
- [Konfiguracja](#konfiguracja)
- [Architektura](#architektura)
- [Troubleshooting](#troubleshooting)
- [Opis Architektury Shorts 2.0](#opis-architektury-shorts-20)
- [Konfiguracja Shorts](#konfiguracja-shorts)
- [Instrukcja użytkownika (Shorts)](#instrukcja-uzytkownika-shorts)
- [Troubleshooting (Shorts)](#troubleshooting-shorts)
- [Plan wdrożenia Shorts 2.0](#plan-wdrozenia-shorts-20)

---

## 🖥️ Wymagania systemowe

### Minimalne (CPU only):
- **OS:** Windows 10/11 (64-bit)
- **CPU:** Intel i5 8th gen / AMD Ryzen 5 2600 lub lepszy
- **RAM:** 16 GB
- **Dysk:** 50 GB wolnego miejsca (SSD zalecany)
- **Python:** 3.11+

### Zalecane (GPU accelerated):
- **GPU:** NVIDIA GeForce RTX 3060 lub lepszy (min. 8GB VRAM)
- **CUDA:** 12.1+
- **RAM:** 32 GB
- **Dysk:** 100 GB wolnego miejsca (NVMe SSD)

**⏱️ Czas przetwarzania:**
- CPU only: ~60-90 min dla 4h transmisji
- GPU (RTX 3060): ~25-35 min dla 4h transmisji
- GPU (RTX 4090): ~15-20 min dla 4h transmisji

---

## 📦 Instalacja

### 1. Instalacja Python

Pobierz Python 3.11+ z [python.org](https://www.python.org/downloads/)

✅ **Ważne:** Zaznacz "Add Python to PATH" podczas instalacji!

### 2. Instalacja CUDA (dla GPU)

Jeśli masz kartę NVIDIA:

1. Pobierz CUDA Toolkit 12.1+: https://developer.nvidia.com/cuda-downloads
2. Zainstaluj drivers NVIDIA (najnowsze)
3. Zrestartuj komputer

### 3. Instalacja ffmpeg

#### Opcja A: Chocolatey (zalecane)
```bash
# W PowerShell (jako Administrator)
Set-ExecutionPolicy Bypass -Scope Process -Force
iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))
choco install ffmpeg
```

#### Opcja B: Manualna
1. Pobierz ffmpeg z: https://www.gyan.dev/ffmpeg/builds/
2. Wypakuj do `C:\ffmpeg`
3. Dodaj `C:\ffmpeg\bin` do PATH:
   - Szukaj "Environment Variables" w Windows
   - Edytuj "Path" w System variables
   - Dodaj nową ścieżkę: `C:\ffmpeg\bin`

**Sprawdź instalację:**
```bash
ffmpeg -version
```

### 4. Sklonuj/Pobierz projekt

```bash
# Opcja A: Git
git clone https://github.com/yourusername/sejm-highlights-ai.git
cd sejm-highlights-ai

# Opcja B: Pobierz ZIP i wypakuj
```

#### Jak zaktualizować istniejący folder do najnowszych zmian (branch `ai-experiments`)

- **Jeśli folder nie ma `.git` (pobrany jako ZIP):**
  ```powershell
  cd "C:\Users\<user>\Desktop\Sejm higlights CODEX"  # Twój folder
  git init
  git remote add origin https://github.com/<org>/<repo>.git
  git fetch
  git checkout ai-experiments
  git pull origin ai-experiments
  ```

- **Jeśli to już repo, ale nie ma zdalnego `origin`:**
  ```powershell
  cd "C:\Users\<user>\Desktop\Sejm higlights CODEX"
  git remote add origin https://github.com/<org>/<repo>.git
  git pull origin ai-experiments
  ```

- **Jeśli repo ma błędny URL `origin`:**
  ```powershell
  cd "C:\Users\<user>\Desktop\Sejm higlights CODEX"
  git remote set-url origin https://github.com/<org>/<repo>.git
  git pull origin ai-experiments
  ```

- **Chcesz świeży klon wprost na branch `ai-experiments`:**
  ```powershell
  cd "C:\Users\<user>\Desktop"
  git clone --branch ai-experiments https://github.com/<org>/<repo>.git "Sejm higlights CODEX"
  ```

#### Szybka kontrola, czy masz aktualne zmiany
- Upewnij się, że pracujesz w **tym samym folderze**, w którym leży `.git` (nie w kopii z ZIP obok). W PowerShell:
  ```powershell
  cd "C:\Users\<user>\Desktop\Sejm higlights CODEX"
  git status -sb          # powinno pokazać '## ai-experiments' i brak zmian
  git branch --show-current
  git rev-parse --short HEAD
  ```
- Jeśli `git status` pokazuje lokalne modyfikacje, a nie widzisz nowych elementów GUI, zrób kopię zapasową plików i przywróć czyste repo:
  ```powershell
  git reset --hard
  git clean -fd
  git pull origin ai-experiments
  ```
- Po aktualizacji uruchom aplikację **z tego folderu**:
  ```powershell
  venv\Scripts\activate
  python app.py
  ```
  W GUI powinna być zakładka Stream/Sejm, Shortsy oraz Upload Manager. Brak zmian oznacza, że aplikacja startuje z innej lokalizacji – sprawdź ścieżkę w pasku PowerShell.

#### Automatyczny sprawdzacz repo (Windows/Linux)
- Jeśli wciąż nie widzisz nowych elementów GUI mimo `git pull`, uruchom skrypt diagnostyczny:
  ```bash
  python utils/sync_branch.py --branch ai-experiments
  ```
  Wyświetli aktualny HEAD lokalny i zdalny oraz poinformuje o brakującym remote. Aby wymusić czyste repo (uwaga: usuwa lokalne zmiany), użyj:
  ```bash
  python utils/sync_branch.py --branch ai-experiments --force-reset
  ```
  Po zakończeniu skryptu uruchom ponownie GUI z tego samego folderu (`python app.py`).

> Po `git pull` sprawdź w GUI, czy pojawiły się zakładki Stream/Sejm, Shortsy oraz Upload Manager. Jeśli nie, upewnij się, że pracujesz na branchu `ai-experiments` i że `git status` jest czysty.

### 5. Utwórz virtual environment

```bash
# W folderze projektu
python -m venv venv

# Aktywuj (Windows)
venv\Scripts\activate
```

### 6. Instalacja dependencies

```bash
# Podstawowe pakiety
pip install --upgrade pip
pip install -r requirements.txt

# Model spaCy
python -m spacy download pl_core_news_lg
```

**Jeśli masz GPU (CUDA 12.1):**
```bash
# PyTorch z CUDA
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

**Jeśli CPU only:**
```bash
pip install torch torchvision torchaudio
```

### 7. Weryfikacja instalacji

```bash
python -c "import torch; print('CUDA available:', torch.cuda.is_available())"
# Powinno wyświetlić: CUDA available: True (jeśli masz GPU)
```

---

## 🚀 Użycie

### Quick Start

1. **Aktywuj virtual environment:**
```bash
venv\Scripts\activate
```

2. **Uruchom aplikację:**
```bash
python app.py
```

3. **W GUI:**
   - Kliknij **"📁 Wybierz plik MP4"** → wybierz transmisję Sejmu
   - Dostosuj ustawienia w zakładkach (opcjonalnie)
   - Kliknij **"▶️ Start Processing"**
   - Czekaj (~25-60 min)
   - Po zakończeniu kliknij **"📁 Open Output Folder"** lub **"▶️ Play Video"**
   - W trybie **Stream** podaj `chat.json`; po poprawnym wczytaniu status zmieni się na zielony komunikat „Chat bursts aktywne (chat.json załadowany)”, a scoring użyje wagi chat_burst=0.65.
   - Zakładka **Shorts** korzysta z konfiguracji `ShortsConfig` (`shorts/config.py`) z domyślnym zakresem długości `min_duration=8s` / `max_duration=58s`; ustaw liczbę shortsów, szablon i napisy według potrzeb.

### Konfiguracja przez GUI

#### ⚙️ Output Settings
- **Docelowa długość filmu:** 10-30 minut (default: 15 min)
- **Liczba klipów:** 5-20 (default: 12)
- **Min/Max długość klipu:** 60-300s (default: 90-180s)
- **Dodaj title cards:** Włącz/wyłącz intro dla każdego klipu
- **Hardsub:** Wersja z wgranymi napisami (dla social media)

#### 🤖 AI Settings
- **Model Whisper:** 
  - `large-v3` - najlepszy (wolniejszy, 8GB VRAM)
  - `medium` - kompromis (szybszy, 4GB VRAM)
  - `small` - najszybszy (2GB VRAM, gorsza accuracy nazwisk)
- **Próg semantic scoring:** 0.0-1.0 (wyższy = bardziej selektywny)

#### 🔧 Advanced
- **Folder wyjściowy:** Gdzie zapisać wyniki
- **Zachowaj pliki pośrednie:** Debugging (audio, segmenty, itp.)

---

## ⚙️ Konfiguracja zaawansowana

Edytuj `config.yml` dla pełnej kontroli:

```yaml
# Przykład: zmiana target duration
selection:
  target_total_duration: 1200.0  # 20 minut

# Przykład: bardziej agresywny AI scoring
scoring:
  weight_semantic: 0.70  # Więcej wagi na AI
  weight_acoustic: 0.15
```

**Pola kluczowe:**

| Parametr | Opis | Default |
|----------|------|---------|
| `asr.model` | Model Whisper | `large-v3` |
| `selection.target_total_duration` | Długość filmu (s) | 900 (15 min) |
| `selection.max
## 🧭 Opis Architektury Shorts 2.0

Nowe Shortsy przechodzą z układu poziomego (facecam obok gameplay) na układ pionowy 9:16, w którym gameplay zajmuje pełną szerokość ekranu, a kamera pojawia się jako pasek na dole lub w postaci PIP. Multi-frame face detection (5 próbek) ignoruje twarze w centrum kadru, dzięki czemu automatycznie dobiera layout: kamerka na dole → pasek na dole, kamerka u góry/środku → PIP, brak kamerki → sam gameplay.

Dostępne szablony:
- **game_top_face_bottom_bar** – gameplay na górze, pasek z facecamem na dole (dla ujęć z kamerką w dolnej części kadru).
- **full_game_with_floating_face** – pełny gameplay + małe okno PIP (dla kamerek w górnej/środkowej części).
- **simple_game_only** – sam gameplay (fallback, gdy brak pewnej detekcji lub brak kamerki).
- **big_face_reaction** – duża twarz na rozmytym tle (użycie manualne, np. highlight reakcji).

**Nowa zależność:** MediaPipe (detekcja twarzy). Instalacja: `pip install mediapipe`.

## ⚙️ Konfiguracja Shorts

W sekcji `shorts:` w `config.yml` dodano parametry sterujące automatycznym doborem układu i detekcją kamerki:
- `face_detection` (bool) – włącza/wyłącza analizę facecama.
- `num_samples` – liczba próbek klatek do konsensusu (domyślnie 5).
- `detection_threshold` – minimalny udział klatek z dominującą strefą, aby uznać detekcję (0–1).
- `webcam_detection_confidence` – minimalna pewność detektora twarzy (MediaPipe).
- `template` – "auto" lub nazwa szablonu, by wymusić jeden globalnie.
- `manual_template` – jednorazowe wymuszenie szablonu dla bieżącej generacji.
- `game_top_face_bar.*` oraz `floating_face.*` – współczynniki układów (wysokości/padding PIP) dla dostrajania layoutu.

Przykłady konfiguracji:
- **Brak kamerki:** `face_detection: false`, `template: "simple_game_only"` – pipeline pomija detekcję i renderuje sam gameplay.
- **Wymuszona reakcja:** ustaw `manual_template: "big_face_reaction"` dla konkretnego klipu, aby uzyskać duży facecam na rozmytym tle.
- **Tuning progu:** jeśli pojawiają się false-positive twarze, zwiększ `detection_threshold` (np. 0.5); jeśli detekcja zbyt często odpada, zmniejsz próg lub zwiększ `num_samples`.

Stary układ side_left/side_right został usunięty; nowe szablony zastępują poprzednie layouty.

## 🧑‍🏫 Instrukcja użytkownika (Shorts)

- **Auto vs. manual:** ustaw `template: auto`, aby system sam dobierał układ; użyj `manual_template`, gdy chcesz konkretny layout (np. big_face_reaction).
- **Przełączanie detekcji:** `face_detection: true/false` – wyłącz analizę, jeśli w materiale nie ma kamerki.
- **Interpretacja logów:** niskie `detection_rate` oznacza brak stabilnej kamerki; `zone=center_ignored` informuje, że twarz była w centrum i została pominięta.
- **Najlepsze praktyki:** dla gier zostaw auto; dla materiałów bez gameplay ustaw `template: simple_game_only`; kontroluj napisy, jeśli PIP zasłania UI – w razie potrzeby wymuś inny układ lub dostosuj styl napisów.

## 🛠️ Troubleshooting (Shorts)

- **Brak detekcji twarzy:** sprawdź `face_detection: true`, instalację MediaPipe oraz czy twarz jest widoczna (niezbyt mała/zamaskowana).
- **Niewłaściwy wybór szablonu:** jeśli pipeline wybiera fallback mimo kamerki, obniż `detection_threshold` lub wydłuż materiał próbki; w razie potrzeby wymuś szablon manualnie.
- **PIP zasłania UI gry:** wygeneruj klip z innym układem (np. manual_template) lub przesuń PIP w postprocess; obecnie system zakłada, że pierwotne położenie kamerki omija najważniejsze elementy UI.
- **Wydajność:** multi-frame detekcja dodaje ~2-3s per short; upewnij się, że FFmpeg korzysta z akceleracji (jeśli dostępna) i masz aktualną wersję.
- **Kompatybilność:** nowe shorty wciąż 1080x1920; stary side_by_side nie jest już wspierany.

## 🚀 Plan wdrożenia Shorts 2.0

- **Faza 1 – Canary (tydzień 1):** uruchom nowy system dla ~10% shortów, zmierz czasy renderu i zweryfikuj poprawność layoutów; zbierz feedback zespołu.
- **Faza 2 – 50% rollout (tydzień 2):** jeśli brak krytycznych błędów, zwiększ udział do ~50% i wykonaj A/B test (CTR, zaangażowanie, czas produkcji).
- **Faza 3 – 100% (tydzień 3):** pełne przełączenie na nowe layouty; monitoruj pierwsze batchowe renderingi i rozważ cleanup legacy kodu w kolejnym sprzątaniu.
- **Rollback:** w razie krytycznych problemów użyj brancha `backup-before-vertical-templates` lub revertuj merge; kluczowe zmiany są odseparowane w `stage_10_shorts.py` i `config.yml`.
- **Komunikacja:** poinformuj zespół o zmianach, podeprzyj się README/MIGRATION; upewnij się, że MediaPipe jest doinstalowane w środowiskach buildowych.

## 🎥 YouTube upload (OAuth + native schedule)

1. **Sekrety i tokeny**
   - Umieść plik OAuth w `secrets/youtube_client_secret.json` (gitignored).
   - Pierwsze logowanie pobiera token do `secrets/youtube_token_<profile>.json` (również gitignored).

2. **Konta/ustawienia kanałów**
   - Skonfiguruj `accounts.yml` obok repo i wskaż *konkretny kanał* (Brand Account) poprzez `expected_channel_id`:

     ```yaml
     youtube:
       channel_main:
         credential_profile: yt_main
         expected_channel_id: "UCxxxxxxxxxxxx"
         default_privacy: unlisted
         category_id: 22
       channel_secondary:
         credential_profile: yt_secondary
         expected_channel_id: "UCyyyyyyyyyyyy"
         default_privacy: private
         category_id: 22
     ```

   - `account_id` z `UploadTarget` **musi** mieć sekcję w `accounts.yml`. Uploader weryfikuje, że token jest zalogowany na oczekiwany `expected_channel_id`; przy mismatch target kończy się błędem non-retryable, aby nie publikować na złym koncie. Jeśli `expected_channel_id` jest pominięty, zostanie zalogowane ostrzeżenie (mniej bezpieczne).

3. **Uruchomienie uploadu testowego**
   - Dodaj w kolejce plik MP4 (GUI lub `UploadManager.enqueue`).
   - Dla `mode=NATIVE_SCHEDULE` uploader ustawia `publishAt` w YouTube, a lokalny scheduler odpala upload o czasie targetu.

4. **Przykładowy log (due + native schedule)**

   ```text
   [scheduler] Target due -> youtube/channel_main @ 2024-05-01T12:00:00+00:00
   [youtube] YouTube upload progress: 35%
   [youtube] YouTube upload finished video_id=abc123
   [youtube] Uploaded video_id=abc123 with publishAt=2024-05-02T10:00:00+00:00
   ```

   Przykładowy log blokujący zły kanał (mismatch):

   ```text
   [youtube] Uploading to YouTube account_id=channel_main expected_channel_id=UC_expected profile=yt_main
   [youtube] ERROR YouTube channel mismatch: current=UC_other expected=UC_expected. Re-auth with the credential_profile bound to the expected channel.
   ```

## 📱 Meta upload (Instagram/Facebook Reels)

1. **Konta i tokeny**
   - Nie zapisuj tokenów w repo. W `accounts.yml` zmapuj `account_id` na ustawienia i nazwę zmiennej środowiskowej z tokenem:

     ```yaml
     meta:
       ig_main:
         platform: instagram
         ig_user_id: "1784xxxxxxxxxxxx"
         page_id: "1234567890"
         access_token_env: "META_TOKEN_IG_MAIN"
       fb_page_main:
         platform: facebook
         page_id: "1234567890"
         access_token_env: "META_TOKEN_FB_PAGE_MAIN"
     ```

   - Ustaw zmienne środowiskowe z ważnymi tokenami Graph API (wymagane scope do publikacji reels/stron). Brak tokena kończy target stanem `MANUAL_REQUIRED` z instrukcją.

2. **Walidacja i fallback**
   - Jeśli konto nie ma wymaganych uprawnień (np. IG Business/Creator niepowiązany z Page, brak scope), uploader ustawia `MANUAL_REQUIRED` bez retry i zapisuje wskazówki w `last_error`.
   - Scheduler nie retry’uje `MANUAL_REQUIRED`; inne błędy 429/5xx korzystają z istniejącego backoff.

3. **Flow publikacji**
   - Instagram: utworzenie kontenera reels, polling statusu (do ~10 min), a następnie `media_publish` → `media_id` zapisany jako `result_id`.
   - Facebook: upload na Page video endpoint → `video_id` zapisany jako `result_id`.

4. **Przykładowe logi**

   ```text
   [meta] Uploading Instagram reel account_id=ig_main ig_user_id=1784...
   [meta] Instagram reel published media_id=1784_999
   [meta] Uploading Facebook reel account_id=fb_page_main page_id=1234567890
   [meta] Retryable error for facebook|fb_page_main: status 429
   ```

   Manual fallback, gdy brak uprawnień:

  ```text
  [meta] Meta API error status=403 message=permissions missing instagram_content_publish (permissions required: ensure IG Business/Creator is linked to a Page and token has instagram_content_publish/Page access)
  [meta] Manual action required for /path/video.mp4|instagram|ig_main|...: permissions missing instagram_content_publish (...)
  ```

## 🎵 TikTok upload (Official API vs Manual)

* Konfiguracja kont w `accounts.yml` (tokeny tylko w ENV):

  ```yaml
  tiktok:
    tiktok_main:
      mode: "OFFICIAL_API"        # lub "MANUAL_ONLY" gdy API niedostępne
      access_token_env: "TIKTOK_ACCESS_TOKEN"
      advertiser_id: "123456"     # opcjonalnie, jeśli wymagane przez API
      default_caption: "#sejm #polityka"
  ```

* `UploadTarget.account_id` musi wskazywać wpis w sekcji `tiktok`. Brak konta lub tokena → stan `MANUAL_REQUIRED` z instrukcją ręcznego wgrania.
* Tryb `MANUAL_ONLY` zawsze kończy się `MANUAL_REQUIRED` (bez retry) – scheduler nie będzie próbował kolejnych uploadów.
* Tryb `OFFICIAL_API` używa oficjalnego endpointu (`/v2/post/publish/video/`). Błędy 429/5xx → retry/backoff; 400/401/403 → non-retryable (chyba że komunikat sugeruje brak dostępu → `MANUAL_REQUIRED`).
* Przykładowe logi:

  ```text
  [tiktok] Uploading TikTok video via official API (advertiser_id=123456, caption_len=22)
  [tiktok] TikTok upload succeeded video_id=abc123
  ```

  Manual fallback (np. brak tokena lub brak wsparcia API):

  ```text
  [tiktok] TikTok upload not available via official API for this setup → MANUAL_REQUIRED (Missing TikTok access token in env TIKTOK_ACCESS_TOKEN; upload manually or set the token env var)
  ```

## 📅 Kalendarz per target i bulk scheduling w GUI

* Tabela w zakładce Upload pokazuje każdy `UploadTarget` jako osobny wiersz (plik, platforma, konto, termin, tryb, status, result_id, last_error).
* Konta/kanały są pobierane z `accounts.yml`; brak konta → ostrzeżenie i blokada dodania targetu danej platformy.
* Edytuj termin (QDateTimeEdit), konto (dropdown) i tryb bez tworzenia duplikatów — aktualizacje są zapisywane w SQLite przez `UploadStore` i używane przez scheduler.
* Panel **Bulk schedule** pozwala rozdać terminy wielu targetom na raz (start datetime, lista godzin, odstęp dni, strefa czasowa) oraz wczytać preset z `config.yml` → sekcja `scheduling_presets`.
* Po restarcie aplikacja wysyła callback `jobs_restored`, a UI od razu renderuje przywrócone joby/targety z harmonogramem zapisanym w `data/uploader.db`.

## 🔗 Linki do opublikowanych materiałów

* Tabela targetów pokazuje kolumnę z linkiem (jeśli dostępny) oraz przyciski **Open**/**Copy**.
* YouTube i Facebook generują publiczne URL na podstawie `result_id`; Instagram/TikTok wymagają permalinka zwróconego przez API — jeśli go brak, Open pokaże instrukcję, a Copy skopiuje `result_id`.
* Linki są odtwarzane po restarcie dzięki zapisanemu `result_url` w SQLite (jeśli był dostępny) lub wyliczeniu z `result_id`.



