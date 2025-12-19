# Multi-account upload audit and setup

This document explains how the application models multiple accounts per platform, how tokens are mapped, and how to configure and verify new accounts.

## 1. Audyt aktualnej obsługi wielu kont

### Centralne modele i kolejka
- Każdy cel uploadu przechowuje `platform` i `account_id` w `UploadTarget`; identyfikator jest używany w nazwach palet konfiguracji kont i w kluczach UI/SQLite.【F:uploader/models.py†L10-L54】
- `UploadManager` ładuje konfigurację kont z `accounts.yml` (jeśli istnieje), zapisuje targety w SQLite i propaguje `account_id` przy tworzeniu fingerprintu oraz logów.【F:uploader/manager.py†L42-L209】【F:uploader/manager.py†L351-L360】
- UI pobiera `accounts_config` z `UploadManager` i buduje listy kont per platforma (`_account_options_for_platform`), wybierając domyślnie pierwszy wpis z sekcji platformy.【F:app.py†L210-L239】【F:app.py†L1744-L1800】

### Mapowanie platform → konto → token → upload
- **YouTube (long + shorts)**: `_resolve_account` wybiera wpis z `accounts.yml -> youtube`, ustala `credential_profile`, `client_secret_path` i `expected_channel_id`. Token OAuth jest pobierany z `secrets/youtube_token_<credential_profile>.json` (tworzony przy pierwszym logowaniu). Upload weryfikuje, że token jest zalogowany na oczekiwany channel_id przed publikacją.【F:uploader/youtube.py†L52-L212】
- **Facebook/Instagram (Meta)**: `_resolve_account` w sekcji `meta` wymaga `platform` (instagram/facebook) oraz nazwy zmiennej środowiskowej `access_token_env`; opcjonalnie `ig_user_id` i `page_id`. Token jest pobierany z ENV i wstrzykiwany do Graph API klienta per konto.【F:uploader/meta.py†L38-L168】
- **TikTok**: `_resolve_account` w sekcji `tiktok` wybiera tryb (`OFFICIAL_API`/`MANUAL_ONLY`) i zmienną środowiskową `access_token_env`; każde konto może mieć własny `advertiser_id` i domyślny podpis. Brak tokenu lub tryb manualny kończy się stanem `MANUAL_REQUIRED` dla wskazanego `account_id`.【F:uploader/tiktok.py†L20-L164】

### Czy aplikacja obsługuje wiele kont?
- **Tak** – każda sekcja (`youtube`, `meta`, `tiktok`) jest słownikiem `account_id -> config`; UI buduje dropdown z kluczami, więc można dodać dowolną liczbę kont na platformę.【F:app.py†L1744-L1800】【F:README.md†L330-L440】
- Rozróżnienie kont następuje przez `account_id` (musi istnieć w `accounts.yml`); fingerprint targetu zawiera `account_id`, co pozwala schedulować i logować osobno.【F:uploader/manager.py†L92-L105】【F:uploader/manager.py†L185-L209】
- Tokeny są zawsze przypisane do wpisu konta: YouTube → plik tokenu zależny od `credential_profile`; Meta/TikTok → zmienna środowiskowa zdefiniowana w konfiguracji konta.【F:uploader/youtube.py†L52-L186】【F:uploader/meta.py†L111-L147】【F:uploader/tiktok.py†L70-L125】

### Jak UI pobiera listę kont w zakładce „Upload”?
- `SejmHighlightsApp` ładuje `accounts.yml` podczas inicjalizacji uploadera; dropdown w kolumnie „Account” jest wypełniany kluczami z sekcji platformy (`youtube` dla obu `youtube_long` i `youtube_shorts`, osobne sekcje dla `facebook`, `instagram`, `tiktok`). Brak konta powoduje komunikat i blokadę dodania targetu.【F:app.py†L210-L239】【F:app.py†L1744-L1800】

## 2. Struktura konfiguracji wielu kont (`accounts.yml`)

Repo nie zawiera domyślnego `accounts.yml`; plik należy utworzyć w katalogu głównym obok `config.yml` i przekazać do aplikacji (ładowany automatycznie). Aktualny kod oczekuje słownika per platforma z kluczami `account_id`.

Przykładowa struktura (z obsługą wielu kont na każdej platformie):

```yaml
youtube:
  yt_main:
    credential_profile: yt_main           # steruje nazwą pliku tokenu secrets/youtube_token_yt_main.json
    expected_channel_id: "UCxxxx"
    client_secret_path: secrets/youtube_client_secret.json
    default_privacy: unlisted
    category_id: 22
    tags: ["sejm", "polityka"]
    default_for: ["long", "shorts"]     # własne pole dla UI – patrz propozycje zmian
  yt_alt:
    credential_profile: yt_alt
    expected_channel_id: "UCyyyy"
    default_privacy: private
    category_id: 22

meta:
  fb_page_main:
    platform: facebook
    page_id: "123456"
    access_token_env: META_TOKEN_FB_PAGE_MAIN
  ig_main:
    platform: instagram
    ig_user_id: "1789..."
    page_id: "123456"
    access_token_env: META_TOKEN_IG_MAIN

instagram: {}  # nieużywane – IG korzysta z sekcji meta

facebook: {}   # nieużywane – FB korzysta z sekcji meta

tiktok:
  tt_main:
    mode: OFFICIAL_API
    access_token_env: TIKTOK_TOKEN_MAIN
    advertiser_id: "adv_123"
    default_caption: "#sejm #shorts"
  tt_backup:
    mode: MANUAL_ONLY
```

> Sekcje `instagram`/`facebook` są zarezerwowane, ale obecny uploader używa sekcji `meta` dla obu platform; pozostawione pustymi dla jasności.【F:uploader/meta.py†L111-L168】

## 3. Instrukcja krok po kroku (per platforma)

### YouTube (wiele kanałów)
1. **Dodanie kanału**: dopisz wpis pod `youtube:` w `accounts.yml` z unikalnym `account_id`, `credential_profile` i `expected_channel_id` (brand account).【F:uploader/youtube.py†L165-L187】
2. **Token**: uruchom aplikację z nowym profilem – podczas pierwszej autoryzacji zapisze token do `secrets/youtube_token_<credential_profile>.json`. Przechowuj `secrets/youtube_client_secret.json` z danymi OAuth.【F:uploader/youtube.py†L52-L67】【F:README.md†L325-L344】
3. **Wykrywanie Brand Accounts**: `expected_channel_id` jest porównywany z `channels().list(mine=True)`; mismatch blokuje upload i zwraca błąd non-retryable.【F:uploader/youtube.py†L190-L212】
4. **Widoczność w UI**: po restarcie aplikacji wpis pojawi się w dropdownie kont dla `YouTube`/`YouTube Shorts`; pierwszy wpis w sekcji `youtube` jest wybierany domyślnie.【F:app.py†L1744-L1800】
5. **Domyślny kanał dla Shorts/Long**: aktualnie brak wsparcia w kodzie – wybierany jest pierwszy wpis. Można wprowadzić pole `default_for` (patrz sekcja „Propozycje zmian”) i przypisać je w UI.

### YouTube Shorts
- Shorts korzystają z tej samej sekcji `youtube` i uploader-a; odróżnia je `target.platform` (`youtube_shorts`) oraz flaga `is_short` w uploaderze (dodaje `#shorts` do opisu/tagów).【F:uploader/youtube.py†L214-L239】
- Kanał wybierany jest identycznie jak dla longów (dropdown `youtube`), więc konto musi być zdefiniowane w `accounts.yml`.
- Różnice parametrów: dla `mode=NATIVE_SCHEDULE` nadal ustawiany jest `publishAt`, ale metadata zostaje wzbogacona o `#shorts` i tag `shorts`.

### Facebook (wiele stron)
1. **Konto**: dodaj wpis w `accounts.yml` sekcji `meta` z `platform: facebook`, `page_id` i `access_token_env` (token Page Access z uprawnieniem `pages_show_list` + publikacja video).【F:uploader/meta.py†L111-L168】
2. **Token**: ustaw zmienną środowiskową przed uruchomieniem aplikacji; brak tokenu → stan `MANUAL_REQUIRED` dla danego targetu.【F:uploader/meta.py†L127-L147】
3. **Dodanie kolejnej strony**: dopisz nowy `account_id` w sekcji `meta`; UI pokaże go w dropdownie „facebook”.【F:app.py†L1744-L1800】

### Instagram (Business/Creator)
1. **Powiązanie z Page**: wpis w sekcji `meta` wymaga `ig_user_id` i `page_id` (IG Business/Creator powiązany z Page).【F:uploader/meta.py†L111-L168】
2. **Dodanie drugiego konta IG**: dodaj nowy `account_id` z własnym `ig_user_id`/`page_id` i zmienną tokena. UI pokaże oddzielny wpis w dropdownie „instagram”.【F:app.py†L1744-L1800】
3. **Wybór w UI**: domyślnie pierwszy wpis; brak konfiguracji blokuje dodanie targetu IG.

### TikTok (wiele kont)
1. **Token per konto**: dodaj wpis w `tiktok:` z `access_token_env` i `mode`. OFFICIAL_API wymaga ważnego tokena; MANUAL_ONLY zawsze ustawia `MANUAL_REQUIRED`.【F:uploader/tiktok.py†L70-L125】
2. **Kolejne konto**: dopisz nowy `account_id`; UI pokaże go w dropdownie „tiktok”.【F:app.py†L1744-L1800】
3. **Wybór w UI**: pierwszy wpis jest domyślny; zmień konto w tabeli targetów (kolumna „Account”).

## 4. UI/UX – Account Manager (propozycja)

Obecny UI oferuje tylko dropdowny w tabeli uploadów; brak widoku do zarządzania kontami, statusami tokenów i domyślnymi mapowaniami.【F:app.py†L1744-L1800】

Rekomendowany ekran „Account Manager” (nowy widok):
- Lista kont per platforma z kolumnami: `account_id`, opis (np. channel/page/user), status tokenu (OK/EXPIRED/MISSING na podstawie pliku tokenu lub ENV), znaczniki `default_for` (`shorts`/`long`).
- Akcje: **Verify** (sprawdzenie kanału / uprawnień), **Refresh token** (rozpoczęcie OAuth / link do regeneracji), **Open token folder** (otwiera `secrets/`).
- Edycje powinny aktualizować `accounts.yml` lub oddzielny store i odświeżać dropdowny w zakładce Upload.

## 5. Weryfikacja i testy

- **Sprawdzenie podłączenia**:
  - YouTube: uruchom upload testowy; log „Uploading to YouTube account_id=… expected_channel_id=…” powinien potwierdzić profil i kanał, a mismatch zakończy się błędem zanim materiał zostanie opublikowany.【F:uploader/youtube.py†L214-L239】
  - Meta: brak tokena lub uprawnień skutkuje stanem `MANUAL_REQUIRED` w tabeli targetów i logiem o brakujących permissionach.【F:uploader/meta.py†L111-L168】
  - TikTok: `MANUAL_REQUIRED` gdy `mode=MANUAL_ONLY` lub brak tokena; log wskazuje konkretną zmienną ENV.【F:uploader/tiktok.py†L70-L125】
- **Oczekiwane logi**: scheduler loguje `target_due` z `platform` i `account_id`; uploader loguje wynik lub błąd i zapisuje `last_error` w SQLite.【F:uploader/manager.py†L144-L209】
- **Rotacja tokenów**: podmień pliki `secrets/youtube_token_<profile>.json` lub zmień wartości ENV dla Meta/TikTok; restart aplikacji wczyta nowe tokeny. Zachowaj kopie poprzednich tokenów w bezpiecznym katalogu poza repo.

## 6. Dostawy i brakujące elementy

A) **Pliki do utworzenia**
- `accounts.yml` w katalogu głównym (wzór powyżej).
- Pliki tokenów OAuth YouTube w `secrets/youtube_token_<credential_profile>.json` (tworzone automatycznie przy logowaniu).【F:uploader/youtube.py†L52-L67】
- Plik `secrets/youtube_client_secret.json` z danymi OAuth.【F:README.md†L325-L344】
- Zmienne środowiskowe dla tokenów Meta/TikTok (`META_TOKEN_*`, `TIKTOK_TOKEN_*`).【F:uploader/meta.py†L111-L147】【F:uploader/tiktok.py†L70-L125】

B) **Braki w aktualnym kodzie**
- Brak pliku `accounts.yml` i walidacji jego schematu; UI wybiera pierwszy wpis zamiast „domyślny dla shorts/long”.【F:app.py†L1744-L1800】
- Brak dedykowanego ekranu „Account Manager” oraz sprawdzania ważności tokenów przed uploadem (YouTube refreshuje token tylko w runtime uploadu).【F:uploader/youtube.py†L52-L67】【F:uploader/meta.py†L127-L147】

C) **Propozycje zmian w kodzie**

```diff
# app.py
- def _default_account(self, platform: str) -> str | None:
-     accounts = self._account_options_for_platform(platform)
-     return accounts[0] if accounts else None
+ def _default_account(self, platform: str) -> str | None:
+     key = "youtube" if platform.startswith("youtube") else platform
+     accounts = self.accounts_config.get(key, {}) or {}
+     # honor optional default_for list in accounts.yml
+     requested_kind = "shorts" if platform == "youtube_shorts" else "long"
+     for acc_id, cfg in accounts.items():
+         if requested_kind in (cfg.get("default_for") or []):
+             return acc_id
+     return next(iter(accounts), None)
```

```diff
# uploader/manager.py
- self.accounts_config = accounts_config or self._load_accounts_config(accounts_config_path)
+ self.accounts_config = accounts_config or self._load_accounts_config(accounts_config_path)
+ # TODO: validate accounts.yml schema (platform sections + required keys) and surface warnings in UI/logs.
```

```diff
# New UI module (e.g., ui/account_manager.py)
+ # Render per-platform tables with account_id, description, token status.
+ # Buttons: Verify (calls platform-specific check), Refresh token (launch OAuth/opens help), Open token folder.
+ # Allows marking default_for shorts/long and saving back to accounts.yml.
```

D) **Checklist – Quick Start dodania nowego konta**
1. Skopiuj wzór `accounts.yml` i dodaj wpis dla nowego konta z unikalnym `account_id`.
2. Ustaw wymagane sekrety: YouTube – OAuth client + interaktywny token; Meta/TikTok – zmienne ENV z ważnymi tokenami.
3. Uruchom aplikację, wybierz plik do uploadu, zaznacz platformę i sprawdź, czy dropdown pokazuje nowe konto.
4. Wykonaj próbny upload; zweryfikuj logi i link w tabeli targetów.
5. (Opcjonalnie) Zaktualizuj pola `default_for`, aby UI domyślnie wybierało właściwy kanał dla Shorts/Long.
