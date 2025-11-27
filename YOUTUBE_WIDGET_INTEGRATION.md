# YouTube Manager Widget - Integration Guide

## Integracja z sejm_app.py i stream_app.py

### Krok 1: Import w aplikacji

```python
from youtube_manager_widget import YouTubeManagerWidget
```

### Krok 2A: Integracja w sejm_app.py

```python
class SejmHighlightsApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = Config.load_default()
        # ...
        self.init_ui()

    def create_youtube_tab(self) -> QWidget:
        """TAB: YouTube Settings"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # === UŻYJ WIDGET ===
        self.youtube_manager = YouTubeManagerWidget(
            config=self.config,
            default_profile="sejm",  # Domyślnie sejm dla sejm_app
            parent=self
        )
        layout.addWidget(self.youtube_manager)

        # === POZOSTAŁE USTAWIENIA (opcjonalne) ===
        layout.addSpacing(20)

        # Schedule as premiere
        self.youtube_premiere = QCheckBox("🎬 Scheduluj jako Premiery")
        self.youtube_premiere.setChecked(True)
        layout.addWidget(self.youtube_premiere)

        # Privacy status override
        privacy_layout = QHBoxLayout()
        privacy_layout.addWidget(QLabel("🔒 Status prywatności (override):"))
        self.youtube_privacy = QComboBox()
        self.youtube_privacy.addItems(["Z profilu", "Unlisted", "Private", "Public"])
        privacy_layout.addWidget(self.youtube_privacy)
        privacy_layout.addStretch()
        layout.addLayout(privacy_layout)

        # Credentials
        cred_layout = QHBoxLayout()
        cred_layout.addWidget(QLabel("🔑 Client Secret JSON:"))
        self.youtube_creds = QLineEdit()
        self.youtube_creds.setText("client_secret.json")
        cred_layout.addWidget(self.youtube_creds)
        layout.addLayout(cred_layout)

        layout.addStretch()
        return tab

    def start_processing(self):
        """Rozpocznij przetwarzanie"""
        # Pobierz ustawienia z widgetu
        upload_profile = self.youtube_manager.get_selected_profile()
        use_queue = self.youtube_manager.is_queue_mode()

        # Aktualizuj config
        self.youtube_manager.update_config()
        self.update_config_from_gui()  # Twoje inne ustawienia

        # Uruchom processing
        self.processing_thread = ProcessingThread(
            input_file,
            self.config,
            upload_profile=upload_profile,
            use_queue=use_queue
        )
        # ...
```

### Krok 2B: Integracja w stream_app.py

```python
class StreamHighlightsApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = Config.load_default()
        # ...
        self.init_ui()

    def create_youtube_tab(self) -> QWidget:
        """TAB: YouTube Settings"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # === UŻYJ WIDGET ===
        self.youtube_manager = YouTubeManagerWidget(
            config=self.config,
            default_profile="stream",  # Domyślnie stream dla stream_app!
            parent=self
        )
        layout.addWidget(self.youtube_manager)

        # Reszta identyczna jak w sejm_app.py
        # ...

        layout.addStretch()
        return tab

    def start_processing(self):
        """Rozpocznij przetwarzanie"""
        # Identyczny kod jak w sejm_app.py
        upload_profile = self.youtube_manager.get_selected_profile()
        use_queue = self.youtube_manager.is_queue_mode()

        self.youtube_manager.update_config()
        # ...
```

### Krok 3: Update ProcessingThread (w każdej aplikacji)

```python
class ProcessingThread(QThread):
    # ... signals ...

    def __init__(self, input_file: str, config: Config,
                 upload_profile: str = None, use_queue: bool = False):
        super().__init__()
        self.input_file = input_file
        self.config = config
        self.upload_profile = upload_profile
        self.use_queue = use_queue
        self.processor = None
        self._is_running = True

    def run(self):
        try:
            if self.upload_profile:
                self.log_message.emit("INFO", f"📋 Używam profilu YouTube: {self.upload_profile}")

            if self.use_queue:
                self.log_message.emit("INFO", f"📋 Tryb Upload Queue - filmy zostaną dodane do kolejki")

            # Inicjalizacja processora
            self.processor = PipelineProcessor(
                self.config,
                upload_profile=self.upload_profile,
                use_queue=self.use_queue
            )
            # ...
```

---

## API YouTubeManagerWidget

### Metody publiczne:

```python
# Pobierz wybrany profil
profile = widget.get_selected_profile()  # "sejm" | "stream" | None

# Sprawdź czy upload włączony
enabled = widget.is_upload_enabled()  # True | False

# Sprawdź czy tryb kolejki
queue_mode = widget.is_queue_mode()  # True | False

# Pobierz playlist IDs
playlists = widget.get_playlist_ids()  # {'main': '...', 'shorts': '...'}

# Aktualizuj config
widget.update_config()
```

### Sygnały:

```python
# Reaguj na zmianę profilu
widget.profile_changed.connect(lambda profile_name: print(f"Zmieniono na: {profile_name}"))
```

---

## Różnice między sejm_app.py i stream_app.py

| Parametr | sejm_app.py | stream_app.py |
|----------|-------------|---------------|
| `default_profile` | `"sejm"` | `"stream"` |
| Channel ID | UCSlsIpJrotOvA1wbA4Z46zA | UCq5S2-INMkM8AEvYsFu4BOg |
| Token file | youtube_token_sejm.json | youtube_token_stream.json |
| Main privacy | unlisted | public |
| Premieres | Tak (enabled) | Nie (disabled) |

**Widget automatycznie dostosowuje się do wybranego profilu!**

---

## Przykład kompleksowy

```python
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QTabWidget
from youtube_manager_widget import YouTubeManagerWidget
from pipeline.config import Config

class MyApp(QMainWindow):
    def __init__(self, app_type="sejm"):  # "sejm" or "stream"
        super().__init__()
        self.config = Config.load_default()
        self.app_type = app_type
        self.init_ui()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Tabs
        tabs = QTabWidget()
        tabs.addTab(self.create_youtube_tab(), "📺 YouTube")
        layout.addWidget(tabs)

    def create_youtube_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # YouTube Manager Widget
        self.youtube_manager = YouTubeManagerWidget(
            config=self.config,
            default_profile=self.app_type,  # sejm lub stream
            parent=self
        )
        layout.addWidget(self.youtube_manager)

        layout.addStretch()
        return tab

    def start_processing(self):
        profile = self.youtube_manager.get_selected_profile()
        queue_mode = self.youtube_manager.is_queue_mode()

        print(f"Profile: {profile}")
        print(f"Queue: {queue_mode}")

        # Start processing...
```

---

## Zalety tego rozwiązania

✅ **Kod reużywalny** - jeden widget dla obu aplikacji
✅ **Konsystentny UI** - identyczny wygląd wszędzie
✅ **Łatwa konserwacja** - zmiana w jednym miejscu
✅ **Automatyczna konfiguracja** - widget sam zarządza swoim stanem
✅ **Profile-aware** - automatyczne dostosowanie do sejm/stream
✅ **Type-safe API** - jasne metody publiczne
✅ **Signal-based** - reaktywne powiadomienia o zmianach

---

## Testowanie

```python
# Test w sejm_app
app = SejmHighlightsApp()
assert app.youtube_manager.get_selected_profile() == "sejm"

# Test w stream_app
app = StreamHighlightsApp()
assert app.youtube_manager.get_selected_profile() == "stream"

# Test zamiany profilu
app.youtube_manager.youtube_profile.setCurrentText("sejm")
assert app.youtube_manager.get_selected_profile() == "sejm"
```
