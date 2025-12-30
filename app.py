"""
Sejm Highlights Desktop - Główna aplikacja GUI
Wersja: 2.0.0 - SMART SPLITTER EDITION
Python 3.11+ | PyQt6 | CUDA

Automatyczne generowanie najlepszych momentów z transmisji Sejmu
+ Inteligentny podział długich materiałów na części z auto-premiering
"""

import sys
import os
import json
import yaml
import logging
from typing import TYPE_CHECKING, Optional, Tuple
from video_downloader import VideoDownloader
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

# Load environment variables from .env file (for OPENAI_API_KEY, etc.)
load_dotenv()

# Module-level logger
logger = logging.getLogger(__name__)

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QTextEdit, QFileDialog,
    QGroupBox, QSpinBox, QDoubleSpinBox, QComboBox, QListWidget,
    QSplitter, QMessageBox, QTabWidget, QCheckBox, QLineEdit, QTimeEdit,
    QDialog, QRadioButton, QButtonGroup, QSlider, QTableWidget,
    QTableWidgetItem, QDateTimeEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QTime, QDateTime, QUrl
from PyQt6.QtGui import QDesktopServices, QFont, QTextCursor, QPixmap, QColor

# Import pipeline modules
from pipeline.processor import PipelineProcessor
from pipeline.config import CompositeWeights, Config
from pipeline.chat_burst import parse_chat_json
from utils.chat_parser import load_chat_robust
from utils.copyright_protection import CopyrightProtector, CopyrightSettings
from pipeline.streamers import get_profile_loader


if TYPE_CHECKING:  # import dla type checkera, bez twardej zależności przy runtime
    from shorts.generator import ShortsGenerator, Segment

from uploader.accounts import (
    STATUS_INVALID_CONFIG,
    STATUS_MANUAL_REQUIRED,
    STATUS_MISSING_ENV,
    STATUS_OK,
)
from uploader.manager import (
    UploadManager,
    UploadJob,
    UploadTarget,
    parse_scheduled_at,
)
from uploader.links import build_public_url
from uploader.scheduling import distribute_targets, parse_times_list

# OpenMP duplicate library workaround (Windows/NVIDIA toolchains sometimes conflict)
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logging.warning(
    "KMP_DUPLICATE_LIB_OK=TRUE ustawione automatycznie (OpenMP duplicate lib workaround)."
)


def _load_shorts_modules() -> Tuple[Optional["ShortsGenerator"], Optional["Segment"], Optional[str]]:
    """Lazy import modułów shorts, aby GUI nie crashował bez moviepy.

    Returns: (ShortsGenerator class, Segment class, error message if failed)
    """

    try:
        from shorts.generator import ShortsGenerator, Segment
        return ShortsGenerator, Segment, None
    except ModuleNotFoundError as exc:
        missing = exc.name or ""
        if missing.startswith("moviepy") or missing == "moviepy":
            return None, None, (
                "Brak biblioteki 'moviepy'. Uruchom: pip install -r requirements.txt "
                "(w aktywnym venv)."
            )
        return None, None, f"Brakujący moduł: {missing}"
    except Exception as exc:  # pragma: no cover - defensywny fallback
        return None, None, f"Nie udało się załadować modułu shorts: {exc}"


class ProcessingThread(QThread):
    """Worker thread dla przetwarzania video (żeby GUI nie zamarzało)"""
    
    # Sygnały do komunikacji z GUI
    progress_updated = pyqtSignal(int, str)  # (procent, etap)
    stage_completed = pyqtSignal(str, dict)  # (nazwa_etapu, statystyki)
    log_message = pyqtSignal(str, str)  # (level, message)
    processing_completed = pyqtSignal(dict)  # (wyniki)
    processing_failed = pyqtSignal(str)  # (error_message)
    
    def __init__(self, input_file: str, config: Config):
        super().__init__()
        self.input_file = input_file
        self.config = config
        self.processor = None
        self._is_running = True
    
    def run(self):
        """Główna pętla przetwarzania"""
        try:
            self.log_message.emit("INFO", f"🚀 Rozpoczynam przetwarzanie: {Path(self.input_file).name}")
            
            # Inicjalizacja processora
            self.processor = PipelineProcessor(self.config)
            
            # Callback dla progressu
            def progress_callback(stage: str, percent: int, message: str):
                if self._is_running:
                    self.progress_updated.emit(percent, f"{stage}: {message}")
                    self.log_message.emit("INFO", f"[{stage}] {message}")
            
            self.processor.set_progress_callback(progress_callback)
            
            # Uruchom pipeline
            result = self.processor.process(self.input_file)
            
            if self._is_running:
                self.log_message.emit("SUCCESS", "✅ Przetwarzanie zakończone!")
                self.processing_completed.emit(result)
                
        except Exception as e:
            if self._is_running:
                self.log_message.emit("ERROR", f"❌ Błąd: {str(e)}")
                self.processing_failed.emit(str(e))
    
    def stop(self):
        """Zatrzymaj przetwarzanie"""
        self._is_running = False
        if self.processor:
            self.processor.cancel()

class DownloadThread(QThread):
    """Worker thread dla pobierania video z URL"""
    
    # Sygnały
    progress_updated = pyqtSignal(int, str)  # (procent, message)
    download_completed = pyqtSignal(str)  # (file_path)
    download_failed = pyqtSignal(str)  # (error_message)
    info_retrieved = pyqtSignal(dict)  # (video_info)
    
    def __init__(self, url: str, download_dir: str = "downloads"):
        super().__init__()
        self.url = url
        self.download_dir = download_dir
        self.downloader = None
        self._is_running = True
        self.download_thread = None
        self.downloaded_file_path = None
    
    def run(self):
        """Download video"""
        try:
            # Initialize downloader
            self.downloader = VideoDownloader(download_dir=self.download_dir)
            
            # Set progress callback
            def progress(msg, percent):
                if self._is_running:
                    self.progress_updated.emit(percent, msg)
            
            self.downloader.set_progress_callback(progress)
            
            # Get info first
            self.progress_updated.emit(5, "Pobieranie informacji o video...")
            info = self.downloader.get_video_info(self.url)
            self.info_retrieved.emit(info)
            
            # Download
            self.progress_updated.emit(10, "Rozpoczynam pobieranie...")
            output_file = self.downloader.download(self.url, max_quality="1080")
            
            if self._is_running:
                self.download_completed.emit(output_file)
                
        except Exception as e:
            if self._is_running:
                self.download_failed.emit(str(e))
    
    def stop(self):
        """Stop download"""
        self._is_running = False


class SejmHighlightsApp(QMainWindow):
    """Główne okno aplikacji"""
    
    def __init__(self):
        super().__init__()
        self.config = Config.load_default()
        self.logger = logging.getLogger("app")
        self.processing_thread = None
        self.current_results = None
        self.download_thread = None
        self.downloaded_file_path = None
        self.copyright_protector = CopyrightProtector(
            CopyrightSettings(
                enable_protection=getattr(self.config.copyright, "enable_protection", True),
                audd_api_key=getattr(self.config.copyright, "audd_api_key", ""),
                music_detection_threshold=getattr(self.config.copyright, "music_detection_threshold", 0.7),
                royalty_free_folder=getattr(self.config.copyright, "royalty_free_folder", Path("assets/royalty_free")),
            )
        )
        self.upload_manager = UploadManager(
            protector=self.copyright_protector if getattr(self.config.copyright, "enabled", False) else None
        )
        self.accounts_registry = self.upload_manager.accounts_registry
        self.accounts_config = self.upload_manager.accounts_config or {}
        self.scheduling_presets = self._load_scheduling_presets()
        self.target_row_map: dict[str, int] = {}
        self.target_lookup: dict[str, tuple[UploadJob, UploadTarget]] = {}
        self._min_clip_customized = False
        self.shorts_generator_cls, self.segment_cls, self.shorts_import_error = _load_shorts_modules()
        self.translations = {
            "pl": {
                "generate_shorts": "Generuj shortsy z najlepszych segmentów",
                "shorts_template": "Szablon shortsa",
                "speedup": "Przyspieszenie",
                "add_subtitles": "Dodaj napisy",
                "remove_music": "Sprawdź i usuń muzykę chronioną prawem autorskim",
            },
            "en": {
                "generate_shorts": "Generate shorts from top segments",
                "shorts_template": "Shorts template",
                "speedup": "Speed up",
                "add_subtitles": "Add subtitles",
                "remove_music": "Scan & remove copyrighted music",
            },
        }

        if self.shorts_import_error:
            print(f"[Sejm Highlights] {self.shorts_import_error}")

        self.init_ui()
        self.setup_styles()

        # Detect streamer after UI is initialized
        try:
            self.detect_streamer()
        except Exception as e:
            logger.warning(f"Failed to detect streamer on init: {e}")

    def _t(self, key: str) -> str:
        lang = getattr(self.config, "language", "pl")
        return self.translations.get(lang, {}).get(key, key)
    
    def init_ui(self):
        """Inicjalizacja interfejsu użytkownika"""
        self.setWindowTitle("Sejm Highlights AI - Automated Video Compiler v2.0")
        self.setGeometry(100, 100, 1600, 900)
        self.setMinimumSize(1280, 800)
        
        # Główny widget i layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # === SEKCJA 1: Header ===
        header = self.create_header()
        main_layout.addWidget(header)
        
        # === SEKCJA 2: File Input ===
        file_group = self.create_file_input_section()
        main_layout.addWidget(file_group)
        
        # === SEKCJA 3: Configuration ===
        config_tabs = self.create_config_tabs()
        main_layout.addWidget(config_tabs)

        # Po zbudowaniu zakładek ustaw od razu widoczny status trybu
        self._sync_mode_hint()
        
        # === SEKCJA 4: Processing Control ===
        control_group = self.create_control_section()
        main_layout.addWidget(control_group)
        
        # === SEKCJA 5: Progress & Logs (split) ===
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Lewa strona: Progress + Stats
        left_panel = self.create_progress_panel()
        splitter.addWidget(left_panel)
        
        # Prawa strona: Logs
        right_panel = self.create_log_panel()
        splitter.addWidget(right_panel)
        
        splitter.setSizes([600, 800])
        main_layout.addWidget(splitter, stretch=1)
        
        # === SEKCJA 6: Results Preview (ukryte domyślnie) ===
        self.results_widget = self.create_results_section()
        self.results_widget.setVisible(False)
        main_layout.addWidget(self.results_widget)
    
    def create_header(self) -> QWidget:
        """Header z logo i opisem"""
        header = QWidget()
        layout = QHBoxLayout(header)
        
        # Tytuł
        title = QLabel("🎬 Sejm Highlights AI v2.0")
        title.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        layout.addWidget(title)
        
        layout.addStretch()
        
        # Badge: Smart Splitter
        smart_badge = QLabel("🤖 Smart Splitter")
        smart_badge.setFont(QFont("Segoe UI", 10))
        smart_badge.setStyleSheet("color: #FF6B35; font-weight: bold; padding: 5px;")
        layout.addWidget(smart_badge)

        # Info o GPU
        gpu_label = QLabel("🎮 CUDA Enabled")
        gpu_label.setFont(QFont("Segoe UI", 10))
        gpu_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        layout.addWidget(gpu_label)

        # HINT: szybki podgląd trybu, żeby użytkownik od razu widział Sejm/Stream
        self.mode_status_label = QLabel()
        self.mode_status_label.setStyleSheet(
            "color: #0B8043; font-weight: bold; padding: 6px 10px; background: #e8f5e9; border-radius: 6px;"
        )
        layout.addWidget(self.mode_status_label)

        return header
    
    def create_file_input_section(self) -> QGroupBox:
        """Sekcja wyboru pliku wejściowego (URL lub lokalny plik)"""
        group = QGroupBox("📂 Input Video")
        layout = QVBoxLayout()
        
        # Tabs: URL download vs Local file
        tabs = QTabWidget()
        
        # === TAB 1: Download from URL ===
        url_tab = QWidget()
        url_layout = QVBoxLayout(url_tab)
        
        # URL input
        url_input_layout = QHBoxLayout()
        url_label = QLabel("URL:")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://youtube.com/watch?v=...")
        self.url_input.setStyleSheet("padding: 8px; font-size: 14px;")
        url_input_layout.addWidget(url_label)
        url_input_layout.addWidget(self.url_input, stretch=1)
        url_layout.addLayout(url_input_layout)
        
        # Download button
        download_btn_layout = QHBoxLayout()
        self.download_btn = QPushButton("📥 Pobierz i załaduj")
        self.download_btn.clicked.connect(self.download_from_url)
        self.download_btn.setStyleSheet("padding: 10px; font-weight: bold;")
        download_btn_layout.addStretch()
        download_btn_layout.addWidget(self.download_btn)
        download_btn_layout.addStretch()
        url_layout.addLayout(download_btn_layout)
        
        # Download progress
        self.download_progress = QProgressBar()
        self.download_progress.setVisible(False)
        url_layout.addWidget(self.download_progress)
        
        self.download_status = QLabel()
        self.download_status.setVisible(False)
        self.download_status.setStyleSheet("padding: 8px; color: #666;")
        url_layout.addWidget(self.download_status)
        
        # Video info (after download)
        self.video_info_label = QLabel()
        self.video_info_label.setVisible(False)
        self.video_info_label.setStyleSheet("padding: 8px; background: #e8f5e9; border-radius: 4px;")
        url_layout.addWidget(self.video_info_label)
        
        url_layout.addStretch()
        tabs.addTab(url_tab, "🌐 Pobierz z URL")
        
        # === TAB 2: Local file (istniejący kod) ===
        local_tab = QWidget()
        local_layout = QVBoxLayout(local_tab)
        
        # File path display
        file_layout = QHBoxLayout()
        self.file_path_label = QLabel("Nie wybrano pliku")
        self.file_path_label.setStyleSheet("padding: 8px; background: #f0f0f0; border-radius: 4px;")
        file_layout.addWidget(self.file_path_label, stretch=1)
        
        # Browse button
        browse_btn = QPushButton("📁 Wybierz plik MP4")
        browse_btn.clicked.connect(self.browse_file)
        file_layout.addWidget(browse_btn)
        
        local_layout.addLayout(file_layout)
        
        # File info
        self.file_info_label = QLabel()
        self.file_info_label.setVisible(False)
        local_layout.addWidget(self.file_info_label)
        
        local_layout.addStretch()
        tabs.addTab(local_tab, "📁 Plik lokalny")
        
        layout.addWidget(tabs)
        group.setLayout(layout)
        return group

    def create_mode_tab(self) -> QWidget:
        """TAB 0: Tryb Sejm/Stream + chat i wagi"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Mode selection
        mode_group = QGroupBox("🎛️ Tryb przetwarzania")
        mode_layout = QHBoxLayout()
        self.mode_button_group = QButtonGroup(self)
        self.radio_mode_sejm = QRadioButton("Sejm")
        self.radio_mode_stream = QRadioButton("Stream")
        self.mode_button_group.addButton(self.radio_mode_sejm)
        self.mode_button_group.addButton(self.radio_mode_stream)

        if self.config.mode.lower() == "stream":
            self.radio_mode_stream.setChecked(True)
        else:
            self.radio_mode_sejm.setChecked(True)

        mode_layout.addWidget(self.radio_mode_sejm)
        mode_layout.addWidget(self.radio_mode_stream)
        mode_layout.addStretch()
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # Chat JSON input (tylko dla stream)
        chat_group = QGroupBox("💬 Chat (chat.json)")
        chat_layout = QHBoxLayout()
        self.chat_path_edit = QLineEdit()
        if self.config.chat_json_path:
            self.chat_path_edit.setText(str(self.config.chat_json_path))
        self.chat_path_edit.setPlaceholderText("Opcjonalnie: podaj chat.json z Twitch/YouTube")
        self.chat_path_edit.textChanged.connect(self._refresh_chat_status)
        self.chat_browse_btn = QPushButton("📂")
        self.chat_browse_btn.clicked.connect(self.browse_chat_file)
        self.chat_test_btn = QPushButton("🔍 Testuj format chat.json")
        self.chat_test_btn.clicked.connect(self.test_chat_file)
        chat_layout.addWidget(self.chat_path_edit)
        chat_layout.addWidget(self.chat_browse_btn)
        chat_layout.addWidget(self.chat_test_btn)
        chat_group.setLayout(chat_layout)
        layout.addWidget(chat_group)

        self.chat_status_label = QLabel()
        self.chat_status_label.setStyleSheet("font-weight: bold; padding-left: 4px;")
        layout.addWidget(self.chat_status_label)

        # Override weights
        self.override_weights_cb = QCheckBox("Nadpisz wagi")
        self.override_weights_cb.setChecked(bool(self.config.override_weights))
        self.override_weights_cb.toggled.connect(self.toggle_weight_override)
        layout.addWidget(self.override_weights_cb)

        self.weights_widget = QWidget()
        weights_layout = QVBoxLayout(self.weights_widget)
        self.weight_sliders = {}

        for key, label_text in [
            ("chat_burst_weight", "Chat burst weight"),
            ("acoustic_weight", "Acoustic weight"),
            ("semantic_weight", "Semantic weight"),
        ]:
            slider_row = self._create_weight_slider_row(label_text)
            self.weight_sliders[key] = slider_row["slider"]
            weights_layout.addLayout(slider_row["layout"])

        layout.addWidget(self.weights_widget)

        # Prompt input
        prompt_layout = QHBoxLayout()
        prompt_layout.addWidget(QLabel("📝 Opis materiału / prompt (opcjonalne):"))
        self.prompt_input = QLineEdit()
        self.prompt_input.setPlaceholderText("np. funny moments Kai Cenat z Nicki Minaj")
        self.prompt_input.setText(self.config.prompt_text)
        prompt_layout.addWidget(self.prompt_input)
        layout.addLayout(prompt_layout)

        # Language switch
        lang_layout = QHBoxLayout()
        lang_layout.addWidget(QLabel("🌐 Język transkrypcji:"))
        self.language_combo = QComboBox()
        self.language_combo.addItems(["PL", "EN"])
        self.language_combo.setCurrentIndex(0 if self.config.language.lower() == "pl" else 1)
        lang_layout.addWidget(self.language_combo)
        lang_layout.addStretch()
        layout.addLayout(lang_layout)

        # Profile selection
        profile_layout = QHBoxLayout()
        profile_layout.addWidget(QLabel("👤 Profil streamera:"))
        self.profile_combo = QComboBox()

        # Load available profiles
        self.profile_loader = get_profile_loader()
        available_profiles = self.profile_loader.list_profiles()

        # Add profiles to combo box with display names
        self.profile_map = {}
        for profile_key in available_profiles:
            profile = self.profile_loader.get_profile(profile_key)
            if profile:
                display_name = f"{profile.display_name} ({profile.language.upper()})"
                self.profile_combo.addItem(display_name)
                self.profile_map[display_name] = profile_key

        # Set default to Sejm if available
        default_idx = 0
        for idx, (display_name, key) in enumerate(self.profile_map.items()):
            if key == "sejm":
                default_idx = idx
                break
        self.profile_combo.setCurrentIndex(default_idx)

        profile_layout.addWidget(self.profile_combo)

        # Add warning label (hidden by default)
        self.profile_warning = QLabel("⚠️ Detected profile mismatch!")
        self.profile_warning.setStyleSheet("color: orange; font-weight: bold;")
        self.profile_warning.setVisible(False)
        profile_layout.addWidget(self.profile_warning)

        profile_layout.addStretch()
        layout.addLayout(profile_layout)

        # Connect profile change
        self.profile_combo.currentIndexChanged.connect(self.on_profile_changed)

        layout.addStretch()


        # Initialize weight visibility and values
        self.toggle_weight_override(self.override_weights_cb.isChecked(), init=True)
        self._refresh_weight_sliders()
        self._update_chat_controls()
        self._sync_mode_hint()

        # Connect mode change
        self.radio_mode_stream.toggled.connect(self._update_chat_controls)
        self.radio_mode_stream.toggled.connect(self._sync_mode_hint)
        self.radio_mode_sejm.toggled.connect(self._sync_mode_hint)

        return tab

    def _create_weight_slider_row(self, label_text: str):
        """Stwórz wiersz slidera 0.00-1.00."""

        layout = QHBoxLayout()
        label = QLabel(label_text)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(0, 100)
        slider.setSingleStep(1)
        value_label = QLabel("0.00")

        def on_change(val: int):
            value_label.setText(f"{val/100:.2f}")

        slider.valueChanged.connect(on_change)

        layout.addWidget(label)
        layout.addWidget(slider)
        layout.addWidget(value_label)
        return {"layout": layout, "slider": slider, "value_label": value_label}

    def _refresh_weight_sliders(self):
        """Załaduj wagi aktywnego trybu do sliderów."""

        if self.override_weights_cb.isChecked() and self.config.custom_weights:
            weights = self.config.custom_weights
        elif self.radio_mode_stream.isChecked():
            weights = self.config.scoring_weights.stream_mode
        else:
            weights = self.config.scoring_weights.sejm_mode
        mapping = {
            "chat_burst_weight": weights.chat_burst_weight,
            "acoustic_weight": weights.acoustic_weight,
            "semantic_weight": weights.semantic_weight,
        }
        for key, value in mapping.items():
            slider = self.weight_sliders.get(key)
            if slider:
                slider.setValue(int(value * 100))

    def _update_chat_controls(self):
        """Włącz/wyłącz pola czatu zależnie od trybu."""

        is_stream = self.radio_mode_stream.isChecked()
        self.chat_path_edit.setEnabled(is_stream)
        self.chat_browse_btn.setEnabled(is_stream)
        self._refresh_chat_status()

    def _refresh_chat_status(self):
        """Pokaż status chat.json (zielony/ czerwony) i hint o burstach."""

        if not hasattr(self, "chat_status_label"):
            return

        is_stream = self.radio_mode_stream.isChecked()
        chat_path = self.chat_path_edit.text().strip()

        if not is_stream:
            self.chat_status_label.setText("🌐 Tryb Sejm – chat bursts wyłączone")
            self.chat_status_label.setStyleSheet("color: #666; font-weight: bold; padding-left: 4px;")
            return

        if chat_path and Path(chat_path).exists():
            parsed = load_chat_robust(chat_path)
            total_msgs = sum(parsed.values())
            if total_msgs > 50:
                self.chat_status_label.setText("✅ Chat bursts aktywne (chat.json załadowany)")
                self.chat_status_label.setStyleSheet("color: #2e7d32; font-weight: bold; padding-left: 4px;")
                self.log(
                    f"Chat załadowany prawidłowo – {total_msgs} wiadomości, włączono chat burst scoring",
                    "INFO",
                )
            elif total_msgs > 0:
                self.chat_status_label.setText("⚠️ Chat bardzo cichy (<50 msg) – fallback wagi")
                self.chat_status_label.setStyleSheet("color: #f2a600; font-weight: bold; padding-left: 4px;")
                self.log("Chat bardzo cichy (<50 msg) – używamy fallback wag", "WARNING")
            else:
                self.chat_status_label.setText("⚠️ Chat pusty – fallback wagi")
                self.chat_status_label.setStyleSheet("color: #f2a600; font-weight: bold; padding-left: 4px;")
                self.log(
                    "Chat.json pusty lub nieobsługiwany – spróbuj przekonwertować (chat-downloader JSON)",
                    "WARNING",
                )
        elif chat_path:
            self.chat_status_label.setText("❌ Nie znaleziono chat.json – burst score = 0.0")
            self.chat_status_label.setStyleSheet("color: #c62828; font-weight: bold; padding-left: 4px;")
        else:
            self.chat_status_label.setText("⚠️ Brak pliku chat.json – burst score = 0.0")
            self.chat_status_label.setStyleSheet("color: #f57c00; font-weight: bold; padding-left: 4px;")

    def _sync_mode_hint(self):
        """Zaktualizuj podpowiedź w headerze o aktywnym trybie (Sejm/Stream)."""

        if not hasattr(self, "mode_status_label"):
            return

        mode = "STREAM" if self.radio_mode_stream.isChecked() else "SEJM"
        self._apply_mode_defaults()
        chat_hint = "Chat bursts aktywne (chat.json)" if mode == "STREAM" else "Tryb Sejm – bez czatu"
        self.mode_status_label.setText(
            f"Tryb: {mode} • przełącz w zakładce 🛰️ Tryb/Chat ({chat_hint})"
        )

    def toggle_weight_override(self, checked: bool, init: bool = False):
        """Pokaż/ukryj slidery wag."""

        self.weights_widget.setVisible(checked)
        if checked and not init:
            self._refresh_weight_sliders()

    def _apply_mode_defaults(self):
        """Dostosuj domyślne wartości po zmianie trybu (np. krótsze klipy dla Stream)."""

        if not hasattr(self, "min_clip_duration"):
            return

        if self.radio_mode_stream.isChecked() and not self._min_clip_customized:
            self.min_clip_duration.setValue(8)
            self.log("Tryb Stream → min. długość klipu ustawiona na 8s", "INFO")
        elif self.radio_mode_sejm.isChecked() and not self._min_clip_customized:
            # Przywróć bardziej konserwatywne minimum dla Sejmu
            self.min_clip_duration.setValue(max(self.min_clip_duration.value(), 20))

    def browse_chat_file(self):
        """Wybierz plik chat.json."""

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz chat.json",
            "",
            "Chat JSON (*.json);;All Files (*)",
        )
        if file_path:
            self.chat_path_edit.setText(file_path)
            self._refresh_chat_status()

    def _browse_chat_file(self):
        """Browse Chat Render MP4 file for overlay (long videos)."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz Chat Render MP4",
            "",
            "Chat Render MP4 (*.mp4);;All Files (*)",
        )
        if file_path:
            self.chat_file_path.setText(file_path)

    def test_chat_file(self):
        """Przetestuj parsowanie chat.json i pokaż wynik w popupie."""

        chat_path = self.chat_path_edit.text().strip()
        if not chat_path:
            QMessageBox.information(self, "Chat", "Najpierw wskaż plik chat.json.")
            return
        data = load_chat_robust(chat_path)
        total_msgs = sum(data.values())
        if total_msgs > 0:
            msg = f"Znaleziono {total_msgs} wiadomości w {len(data)} sekundach."
            QMessageBox.information(self, "Chat", msg)
        else:
            QMessageBox.warning(
                self,
                "Chat",
                "Nie rozpoznano formatu chat.json – rozważ konwersję innym narzędziem.",
            )
        self._refresh_chat_status()
    
    def create_config_tabs(self) -> QTabWidget:
        """Zakładki z konfiguracją"""
        tabs = QTabWidget()

        # TAB 0: Mode / Stream settings
        tabs.addTab(self.create_mode_tab(), "🛰️ Tryb / Chat")

        # TAB 1: Output Settings
        tabs.addTab(self.create_output_tab(), "📊 Output")

        # TAB 1b: Shorts (dedicated)
        tabs.addTab(self.create_shorts_tab(), "📱 Shorts")

        # TAB 2: Smart Splitter (NOWY!)
        tabs.addTab(self.create_smart_splitter_tab(), "🤖 Smart Splitter")
        
        # TAB 3: Model Settings
        tabs.addTab(self.create_model_tab(), "🧠 AI Models")
        
        # TAB 4: Advanced
        tabs.addTab(self.create_advanced_tab(), "⚙️ Advanced")

        # TAB 5: YouTube (rozszerzony)
        tabs.addTab(self.create_youtube_tab(), "📺 YouTube")

        # TAB 6: Upload Manager
        tabs.addTab(self.create_upload_tab(), "🚀 Upload Manager")

        # TAB 7: Konta / Integracje
        tabs.addTab(self.create_accounts_tab(), "🔑 Konta / Integracje")

        return tabs
    
    def create_output_tab(self) -> QWidget:
        """TAB 1: Output Settings"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Target duration
        dur_layout = QHBoxLayout()
        dur_layout.addWidget(QLabel("🎯 Docelowa długość filmu (minuty):"))
        self.target_duration = QDoubleSpinBox()
        self.target_duration.setRange(10.0, 60.0)  # 10-60 min
        self.target_duration.setSingleStep(1.0)
        self.target_duration.setValue(max(10.0, min(60.0, self.config.selection.target_total_duration / 60)))
        self.target_duration.setSuffix(" min")
        dur_layout.addWidget(self.target_duration)
        dur_layout.addStretch()
        layout.addLayout(dur_layout)

        # Number of clips
        clips_layout = QHBoxLayout()
        clips_layout.addWidget(QLabel("📊 Liczba klipów:"))
        self.num_clips = QSpinBox()
        self.num_clips.setRange(5, 40)
        self.num_clips.setValue(min(40, max(5, self.config.selection.max_clips)))
        clips_layout.addWidget(self.num_clips)
        clips_layout.addStretch()
        layout.addLayout(clips_layout)

        # Min/Max clip duration (sekundy)
        min_clip_layout = QHBoxLayout()
        min_clip_layout.addWidget(QLabel("⏱️ Min. długość klipu (sekundy):"))
        self.min_clip_duration = QDoubleSpinBox()
        self.min_clip_duration.setDecimals(0)
        self.min_clip_duration.setRange(8, 180)
        self.min_clip_duration.setSingleStep(5)
        self.min_clip_duration.setValue(max(8, min(180, self.config.selection.min_clip_duration)))
        self.min_clip_duration.setSuffix(" s")
        self.min_clip_duration.valueChanged.connect(lambda _: setattr(self, "_min_clip_customized", True))
        min_clip_layout.addWidget(self.min_clip_duration)
        min_clip_layout.addStretch()
        layout.addLayout(min_clip_layout)

        max_clip_layout = QHBoxLayout()
        max_clip_layout.addWidget(QLabel("⏱️ Max. długość klipu (sekundy):"))
        self.max_clip_duration = QDoubleSpinBox()
        self.max_clip_duration.setDecimals(0)
        self.max_clip_duration.setRange(30, 600)
        self.max_clip_duration.setSingleStep(10)
        self.max_clip_duration.setValue(max(30, min(600, self.config.selection.max_clip_duration)))
        self.max_clip_duration.setSuffix(" s")
        max_clip_layout.addWidget(self.max_clip_duration)
        max_clip_layout.addStretch()
        layout.addLayout(max_clip_layout)

        # Dynamic scoring threshold
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(QLabel("🎚️ Próg score (0.10-0.80):"))
        self.score_threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.score_threshold_slider.setRange(10, 80)
        default_threshold = int(
            max(
                0.1,
                min(
                    0.8,
                    float(
                        getattr(
                            getattr(self.config, "scoring", None) or self.config.selection,
                            "min_score_slider",
                            getattr(self.config.selection, "min_score_threshold", 0.3),
                        )
                    ),
                ),
            )
            * 100
        )
        self.score_threshold_slider.setValue(max(10, min(80, default_threshold)))
        self.score_threshold_slider.setSingleStep(5)
        threshold_layout.addWidget(self.score_threshold_slider)
        self.score_threshold_label = QLabel(f"{self.score_threshold_slider.value()/100:.2f}")
        self.score_threshold_slider.valueChanged.connect(
            lambda v: self.score_threshold_label.setText(f"{v/100:.2f}")
        )
        threshold_layout.addWidget(self.score_threshold_label)
        layout.addLayout(threshold_layout)

        # Transitions & Hardsub
        self.add_transitions = QCheckBox("✨ Dodaj przejścia między klipami")
        self.add_transitions.setChecked(False)  # Domyślnie wyłączone - fontconfig issue
        layout.addWidget(self.add_transitions)

        self.add_hardsub = QCheckBox("📝 Dodaj napisy (hardsub)")
        self.add_hardsub.setChecked(False)
        layout.addWidget(self.add_hardsub)

        # === CHAT OVERLAY (Simplified - MP4 Render based) ===
        self.chat_overlay_enabled = QCheckBox("💬 Dodaj czat (Chat Render MP4)")
        self.chat_overlay_enabled.setChecked(False)
        layout.addWidget(self.chat_overlay_enabled)

        # Chat file path
        chat_file_row = QHBoxLayout()
        chat_file_row.addWidget(QLabel("Plik:"))
        self.chat_file_path = QLineEdit()
        self.chat_file_path.setPlaceholderText("Chat Render MP4 (700x1200)...")
        chat_file_row.addWidget(self.chat_file_path)

        browse_chat_btn = QPushButton("📂")
        browse_chat_btn.setMaximumWidth(40)
        browse_chat_btn.clicked.connect(self._browse_chat_file)
        chat_file_row.addWidget(browse_chat_btn)
        layout.addLayout(chat_file_row)

        # Position X, Y, Scale in one row (cleaner UI)
        chat_pos_row = QHBoxLayout()

        # X position (horizontal - left to right)
        chat_pos_row.addWidget(QLabel("X:"))
        self.chat_x_slider = QSlider(Qt.Orientation.Horizontal)
        self.chat_x_slider.setRange(0, 100)
        self.chat_x_slider.setValue(64)  # Right side default (good for facecam left)
        chat_pos_row.addWidget(self.chat_x_slider)
        self.chat_x_label = QLabel("64%")
        self.chat_x_label.setMinimumWidth(45)
        self.chat_x_slider.valueChanged.connect(
            lambda v: self.chat_x_label.setText(f"{v}%")
        )
        chat_pos_row.addWidget(self.chat_x_label)

        # Y position (vertical - top to bottom)
        chat_pos_row.addWidget(QLabel("  Y:"))
        self.chat_y_slider = QSlider(Qt.Orientation.Horizontal)
        self.chat_y_slider.setRange(0, 100)
        self.chat_y_slider.setValue(10)  # Top default
        chat_pos_row.addWidget(self.chat_y_slider)
        self.chat_y_label = QLabel("10%")
        self.chat_y_label.setMinimumWidth(45)
        self.chat_y_slider.valueChanged.connect(
            lambda v: self.chat_y_label.setText(f"{v}%")
        )
        chat_pos_row.addWidget(self.chat_y_label)

        # Scale (resize chat render)
        chat_pos_row.addWidget(QLabel("  Skala:"))
        self.chat_scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.chat_scale_slider.setRange(50, 100)
        self.chat_scale_slider.setValue(80)  # 80% of original size
        chat_pos_row.addWidget(self.chat_scale_slider)
        self.chat_scale_label = QLabel("80%")
        self.chat_scale_label.setMinimumWidth(45)
        self.chat_scale_slider.valueChanged.connect(
            lambda v: self.chat_scale_label.setText(f"{v}%")
        )
        chat_pos_row.addWidget(self.chat_scale_label)

        layout.addLayout(chat_pos_row)

        # Transparency controls (second row)
        chat_transparency_row = QHBoxLayout()

        # Transparent background checkbox
        self.chat_transparent_bg = QCheckBox("🎨 Transparentne tło")
        self.chat_transparent_bg.setChecked(True)  # Default: enabled
        self.chat_transparent_bg.setToolTip("Usuń czarne tło chatu (colorkey filter)")
        chat_transparency_row.addWidget(self.chat_transparent_bg)

        chat_transparency_row.addSpacing(20)  # Add space

        # Opacity slider
        chat_transparency_row.addWidget(QLabel("  Opacity:"))
        self.chat_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.chat_opacity_slider.setRange(50, 100)  # 50-100%
        self.chat_opacity_slider.setValue(90)  # Default: 90% (readable but slightly transparent)
        self.chat_opacity_slider.setToolTip("Przezroczystość tekstu i emotek (50-100%)")
        chat_transparency_row.addWidget(self.chat_opacity_slider)
        self.chat_opacity_label = QLabel("90%")
        self.chat_opacity_label.setMinimumWidth(45)
        self.chat_opacity_slider.valueChanged.connect(
            lambda v: self.chat_opacity_label.setText(f"{v}%")
        )
        chat_transparency_row.addWidget(self.chat_opacity_label)

        layout.addLayout(chat_transparency_row)

        layout.addStretch()
        return tab

    def create_shorts_tab(self) -> QWidget:
        """Dedykowany tab dla shortsów (szablony, AI fallback, prędkość)."""

        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.shorts_generate_cb = QCheckBox(self._t("generate_shorts"))
        self.shorts_generate_cb.setChecked(bool(getattr(self.config.shorts, "enabled", True)))
        layout.addWidget(self.shorts_generate_cb)

        template_layout = QHBoxLayout()
        template_layout.addWidget(QLabel(self._t("shorts_template")))
        self.shorts_template_combo = QComboBox()

        # Dynamically load templates from registry
        try:
            from shorts.templates import list_templates
            templates = list_templates()
            self.template_name_map = {}  # Map display name -> internal name
            for internal_name, metadata in templates.items():
                display_name = metadata.display_name
                self.shorts_template_combo.addItem(display_name)
                self.template_name_map[display_name] = internal_name

            # Set current selection
            current_template = getattr(self.config.shorts, "template", "gaming")
            for display_name, internal_name in self.template_name_map.items():
                if internal_name == current_template:
                    idx = self.shorts_template_combo.findText(display_name)
                    if idx >= 0:
                        self.shorts_template_combo.setCurrentIndex(idx)
                    break
        except ImportError:
            # Fallback if shorts module not available
            self.shorts_template_combo.addItems(["Gaming Facecam", "Universal"])
            self.template_name_map = {"Gaming Facecam": "gaming", "Universal": "universal"}

        template_layout.addWidget(self.shorts_template_combo)
        template_layout.addStretch()
        layout.addLayout(template_layout)

        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("📊 Liczba shortsów do wygenerowania:"))
        self.shorts_count_slider = QSlider(Qt.Orientation.Horizontal)
        self.shorts_count_slider.setRange(1, 50)
        shorts_count = int(getattr(self.config.shorts, "num_shorts", getattr(self.config.shorts, "count", 10) or 10))
        self.shorts_count_slider.setValue(shorts_count)
        self.shorts_count_slider.setSingleStep(1)
        count_layout.addWidget(self.shorts_count_slider)
        self.shorts_count_label = QLabel(str(self.shorts_count_slider.value()))
        self.shorts_count_slider.valueChanged.connect(lambda v: self.shorts_count_label.setText(str(v)))
        count_layout.addWidget(self.shorts_count_label)
        layout.addLayout(count_layout)

        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("⚡ Przyspieszenie shortsa (x):"))
        self.shorts_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.shorts_speed_slider.setMinimum(100)
        self.shorts_speed_slider.setMaximum(150)
        self.shorts_speed_slider.setSingleStep(5)
        speedup_val = float(getattr(self.config.shorts, "speedup_factor", getattr(self.config.shorts, "speedup", 1.0)))
        self.shorts_speed_slider.setValue(int(speedup_val * 100))
        speed_layout.addWidget(self.shorts_speed_slider)
        self.shorts_speed_label = QLabel(str(self.shorts_speed_slider.value() / 100))
        self.shorts_speed_slider.valueChanged.connect(lambda v: self.shorts_speed_label.setText(f"{v/100:.2f}"))
        speed_layout.addWidget(self.shorts_speed_label)
        layout.addLayout(speed_layout)

        self.shorts_add_subs_cb = QCheckBox(self._t("add_subtitles"))
        self.shorts_add_subs_cb.setChecked(
            bool(
                getattr(
                    self.config.shorts,
                    "enable_subtitles",
                    getattr(self.config.shorts, "add_subtitles", getattr(self.config.shorts, "subtitles", False)),
                )
            )
        )
        layout.addWidget(self.shorts_add_subs_cb)

        subs_lang_layout = QHBoxLayout()
        subs_lang_layout.addWidget(QLabel("🌐 Język napisów:"))
        self.shorts_subs_lang = QComboBox()
        self.shorts_subs_lang.addItems(["PL", "EN"])
        current_lang = getattr(self.config.shorts, "subtitle_lang", "pl").lower()
        self.shorts_subs_lang.setCurrentIndex(0 if current_lang == "pl" else 1)
        subs_lang_layout.addWidget(self.shorts_subs_lang)
        subs_lang_layout.addStretch()
        layout.addLayout(subs_lang_layout)

        self.shorts_remove_music_cb = QCheckBox(self._t("remove_music"))
        self.shorts_remove_music_cb.setChecked(bool(getattr(self.config.copyright, "enabled", False)))
        layout.addWidget(self.shorts_remove_music_cb)

        template_btn_layout = QHBoxLayout()
        template_btn_layout.addWidget(QLabel("🎨"))
        self.shorts_template_btn = QPushButton("Ustawienia szablonu / facecam")
        self.shorts_template_btn.clicked.connect(self.open_shorts_template_dialog)
        template_btn_layout.addWidget(self.shorts_template_btn)
        template_btn_layout.addStretch()
        layout.addLayout(template_btn_layout)

        layout.addStretch()
        return tab

    def create_upload_tab(self) -> QWidget:
        """Upload Manager tab with queue and scheduling."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        file_row = QHBoxLayout()
        self.upload_file_list = QListWidget()
        self.upload_file_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        file_buttons = QVBoxLayout()
        add_btn = QPushButton("Add files")
        add_btn.clicked.connect(self.add_upload_files)
        file_buttons.addWidget(add_btn)
        refresh_btn = QPushButton("Refresh channels")
        refresh_btn.clicked.connect(self.refresh_channels)
        file_buttons.addWidget(refresh_btn)
        scan_btn = QPushButton("Scan copyright")
        scan_btn.clicked.connect(self.scan_copyright)
        file_buttons.addWidget(scan_btn)
        file_buttons.addStretch()
        file_row.addWidget(self.upload_file_list, 2)
        file_row.addLayout(file_buttons, 1)
        layout.addLayout(file_row)

        yt_group = QGroupBox("YouTube konta")
        yt_layout = QVBoxLayout()

        yt_long_row = QHBoxLayout()
        self.cb_youtube = QCheckBox("YouTube – Długie (16:9)")
        self.cb_youtube.setChecked(True)
        yt_long_row.addWidget(self.cb_youtube)
        self.youtube_long_account_combo = QComboBox()
        self.youtube_long_default_label = QLabel()
        yt_long_row.addWidget(self.youtube_long_account_combo, 1)
        yt_long_row.addWidget(self.youtube_long_default_label)
        yt_layout.addLayout(yt_long_row)

        yt_shorts_row = QHBoxLayout()
        self.cb_youtube_shorts = QCheckBox("YouTube Shorts (9:16)")
        self.cb_youtube_shorts.setChecked(True)
        yt_shorts_row.addWidget(self.cb_youtube_shorts)
        self.youtube_shorts_account_combo = QComboBox()
        self.youtube_shorts_default_label = QLabel()
        yt_shorts_row.addWidget(self.youtube_shorts_account_combo, 1)
        yt_shorts_row.addWidget(self.youtube_shorts_default_label)
        yt_layout.addLayout(yt_shorts_row)

        yt_hint = QLabel(
            "Domyślne konta wybierane są z pola default_for=['long'/'shorts'] w accounts.yml."
        )
        yt_hint.setStyleSheet("color: #666; font-size: 11px;")
        yt_layout.addWidget(yt_hint)

        yt_group.setLayout(yt_layout)
        layout.addWidget(yt_group)

        self._refresh_youtube_account_inputs()

        platforms_layout = QHBoxLayout()
        self.cb_facebook = QCheckBox("Facebook")
        self.cb_instagram = QCheckBox("Instagram Reels")
        self.cb_tiktok = QCheckBox("TikTok")
        for cb in [self.cb_facebook, self.cb_instagram, self.cb_tiktok]:
            cb.setChecked(True)
            platforms_layout.addWidget(cb)
        platforms_layout.addStretch()
        layout.addLayout(platforms_layout)

        self.copyright_cb = QCheckBox("Enable Copyright Protection")
        self.copyright_cb.setChecked(bool(getattr(self.config.copyright, "enable_protection", True)))
        layout.addWidget(self.copyright_cb)
        self.upload_manager.protector = self.copyright_protector if self.copyright_cb.isChecked() else None

        form_layout = QHBoxLayout()
        self.upload_title = QLineEdit()
        self.upload_title.setPlaceholderText("Title")
        self.upload_desc = QTextEdit()
        self.upload_desc.setPlaceholderText("Description")
        form_layout.addWidget(self.upload_title)
        form_layout.addWidget(self.upload_desc)
        layout.addLayout(form_layout)

        schedule_layout = QHBoxLayout()
        self.schedule_picker = QDateTimeEdit()
        self.schedule_picker.setCalendarPopup(True)
        schedule_layout.addWidget(QLabel("Schedule publish (optional):"))
        schedule_layout.addWidget(self.schedule_picker)
        layout.addLayout(schedule_layout)

        enqueue_btn = QPushButton("Enqueue selected")
        enqueue_btn.clicked.connect(self.enqueue_uploads)
        layout.addWidget(enqueue_btn)

        self.upload_progress = QProgressBar()
        layout.addWidget(self.upload_progress)

        self.target_table = QTableWidget(0, 11)
        self.target_table.setHorizontalHeaderLabels(
            [
                "File",
                "Platform",
                "Account",
                "Scheduled",
                "Mode",
                "Status",
                "Result",
                "Link",
                "Open",
                "Copy",
                "Last error",
            ]
        )
        self.target_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.target_table)

        bulk_layout = QGroupBox("Bulk schedule")
        bulk_form = QHBoxLayout()
        self.bulk_start_dt = QDateTimeEdit()
        self.bulk_start_dt.setCalendarPopup(True)
        self.bulk_times_input = QLineEdit("18:00,20:00,22:00")
        self.bulk_interval_spin = QSpinBox()
        self.bulk_interval_spin.setMinimum(1)
        self.bulk_interval_spin.setValue(1)
        self.bulk_tz_input = QLineEdit("Europe/Warsaw")
        self.bulk_apply_btn = QPushButton("Apply to selected/all")
        self.bulk_apply_btn.clicked.connect(self.apply_bulk_schedule)
        self.bulk_presets_combo = QComboBox()
        self.bulk_presets_combo.addItem("-- preset --", userData=None)
        for name in self.scheduling_presets.keys():
            self.bulk_presets_combo.addItem(name, userData=name)
        self.bulk_presets_combo.currentIndexChanged.connect(self.apply_preset)
        bulk_form.addWidget(QLabel("Start"))
        bulk_form.addWidget(self.bulk_start_dt)
        bulk_form.addWidget(QLabel("Times"))
        bulk_form.addWidget(self.bulk_times_input)
        bulk_form.addWidget(QLabel("Interval days"))
        bulk_form.addWidget(self.bulk_interval_spin)
        bulk_form.addWidget(QLabel("Timezone"))
        bulk_form.addWidget(self.bulk_tz_input)
        bulk_form.addWidget(self.bulk_presets_combo)
        bulk_form.addWidget(self.bulk_apply_btn)
        bulk_layout.setLayout(bulk_form)
        layout.addWidget(bulk_layout)

        self.upload_manager.add_callback(self.on_upload_update)
        self.upload_manager.start()
        return tab

    def create_accounts_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        header = QLabel("Status kont i integracji")
        header.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(header)

        desc = QLabel(
            "Lista kont z accounts.yml wraz z walidacją plików/ENV. Skorzystaj z przycisku odśwież, jeśli zmienisz plik lub zmienne ENV."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #555; padding: 6px;")
        layout.addWidget(desc)

        self.accounts_table = QTableWidget(0, 6)
        self.accounts_table.setHorizontalHeaderLabels(
            [
                "Platforma",
                "Account ID",
                "Opis",
                "Status",
                "Wymagane pola",
                "Jak naprawić",
            ]
        )
        self.accounts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.accounts_table)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Odśwież status")
        refresh_btn.clicked.connect(self.reload_accounts_registry)
        docs_btn = QPushButton("Otwórz docs")
        docs_btn.clicked.connect(self.open_accounts_docs)
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(docs_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.populate_accounts_status_table()

        return tab
    
    def create_smart_splitter_tab(self) -> QWidget:
        """TAB 2: Smart Splitter Settings (NOWY!)"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Header
        header = QLabel("🤖 Inteligentny podział długich materiałów")
        header.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(header)
        
        info = QLabel(
            "System automatycznie wykryje długie materiały (>1h) i podzieli je na optymalne części.\n"
            "Każda część otrzyma osobny tytuł, miniaturkę z numerem i schedulowaną premierę."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; padding: 10px; background: #f5f5f5; border-radius: 4px;")
        layout.addWidget(info)
        
        layout.addSpacing(15)
        
        # Enable/Disable
        self.splitter_enabled = QCheckBox("✅ Włącz Smart Splitter")
        self.splitter_enabled.setChecked(False)  # DISABLED by default - has design flaw (splits based on source duration, not selected clips)
        self.splitter_enabled.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(self.splitter_enabled)
        
        layout.addSpacing(10)
        
        # Min duration for split
        min_dur_layout = QHBoxLayout()
        min_dur_layout.addWidget(QLabel("⏱️ Minimalna długość dla podziału:"))
        self.splitter_min_duration = QSpinBox()
        self.splitter_min_duration.setRange(1800, 14400)  # 30min - 4h
        self.splitter_min_duration.setValue(3600)  # 1h default
        self.splitter_min_duration.setSuffix(" s (1h)")
        self.splitter_min_duration.valueChanged.connect(self.update_splitter_label)
        min_dur_layout.addWidget(self.splitter_min_duration)
        min_dur_layout.addStretch()
        layout.addLayout(min_dur_layout)
        
        # Premiere hour
        premiere_layout = QHBoxLayout()
        premiere_layout.addWidget(QLabel("🗓️ Godzina premier:"))
        self.premiere_time = QTimeEdit()
        self.premiere_time.setTime(QTime(18, 0))  # 18:00 default
        self.premiere_time.setDisplayFormat("HH:mm")
        premiere_layout.addWidget(self.premiere_time)
        premiere_layout.addWidget(QLabel("(codziennie o tej samej godzinie)"))
        premiere_layout.addStretch()
        layout.addLayout(premiere_layout)
        
        # First premiere offset
        offset_layout = QHBoxLayout()
        offset_layout.addWidget(QLabel("📅 Pierwsza premiera za:"))
        self.premiere_offset = QSpinBox()
        self.premiere_offset.setRange(0, 7)
        self.premiere_offset.setValue(1)
        self.premiere_offset.setSuffix(" dni")
        offset_layout.addWidget(self.premiere_offset)
        offset_layout.addWidget(QLabel("(0 = dziś, 1 = jutro)"))
        offset_layout.addStretch()
        layout.addLayout(offset_layout)
        
        # Use politicians in titles
        self.use_politicians = QCheckBox("👔 Używaj nazwisk polityków w tytułach (np. TUSK VS KACZYŃSKI)")
        self.use_politicians.setChecked(True)
        layout.addWidget(self.use_politicians)
        
        layout.addSpacing(15)
        
        # Example strategy display
        strategy_group = QGroupBox("📊 Przykładowa strategia podziału")
        strategy_layout = QVBoxLayout()
        
        self.strategy_label = QLabel()
        self.update_strategy_example()
        strategy_layout.addWidget(self.strategy_label)
        
        strategy_group.setLayout(strategy_layout)
        layout.addWidget(strategy_group)
        
        layout.addStretch()
        return tab
    
    def create_model_tab(self) -> QWidget:
        """TAB 3: Model Settings"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Whisper model
        whisper_layout = QHBoxLayout()
        whisper_layout.addWidget(QLabel("🎤 Whisper Model:"))
        self.whisper_model = QComboBox()
        self.whisper_model.addItems(["large-v3 (najlepszy)", "medium (szybszy)", "small (najszybszy)"])
        self.whisper_model.setCurrentIndex(1)  # medium default
        whisper_layout.addWidget(self.whisper_model)
        whisper_layout.addStretch()
        layout.addLayout(whisper_layout)
        
        info = QLabel("⚠️ large-v3 wymaga ~10GB VRAM | medium ~5GB | small ~2GB")
        info.setStyleSheet("color: #FF9800; font-style: italic;")
        layout.addWidget(info)
        
        layout.addStretch()
        return tab
    
    def create_advanced_tab(self) -> QWidget:
        """TAB 4: Advanced Settings"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Output directory
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("📁 Katalog wyjściowy:"))
        self.output_dir = QLineEdit()
        self.output_dir.setText(str(self.config.output_dir))
        dir_layout.addWidget(self.output_dir)
        
        browse_dir_btn = QPushButton("📂")
        browse_dir_btn.clicked.connect(self.browse_output_dir)
        dir_layout.addWidget(browse_dir_btn)
        layout.addLayout(dir_layout)
        
        # Keep intermediate
        self.keep_intermediate = QCheckBox("💾 Zachowaj pliki tymczasowe (do debugowania)")
        self.keep_intermediate.setChecked(False)
        layout.addWidget(self.keep_intermediate)
        
        layout.addStretch()
        return tab
    
    def create_youtube_tab(self) -> QWidget:
        """TAB 5: YouTube Settings (ROZSZERZONY!)"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Enable YouTube upload
        self.youtube_upload = QCheckBox("📺 Upload do YouTube po zakończeniu")
        self.youtube_upload.setChecked(False)
        self.youtube_upload.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(self.youtube_upload)
        
        layout.addSpacing(10)
        
        # Schedule as premiere (NOWE!)
        self.youtube_premiere = QCheckBox("🎬 Scheduluj jako Premiery (zamiast instant publish)")
        self.youtube_premiere.setChecked(True)
        layout.addWidget(self.youtube_premiere)
        
        premiere_info = QLabel(
            "✨ Gdy włączone: każda część będzie premiered w osobnym dniu o określonej godzinie\n"
            "❌ Gdy wyłączone: wszystkie części zostaną opublikowane natychmiast"
        )
        premiere_info.setWordWrap(True)
        premiere_info.setStyleSheet("color: #666; font-size: 9pt; padding-left: 25px;")
        layout.addWidget(premiere_info)
        
        layout.addSpacing(10)
        
        # Privacy status
        privacy_layout = QHBoxLayout()
        privacy_layout.addWidget(QLabel("🔒 Status prywatności (dla non-premiere):"))
        self.youtube_privacy = QComboBox()
        self.youtube_privacy.addItems(["Unlisted", "Private", "Public"])
        self.youtube_privacy.setCurrentIndex(0)
        privacy_layout.addWidget(self.youtube_privacy)
        privacy_layout.addStretch()
        layout.addLayout(privacy_layout)
        
        layout.addSpacing(10)
        
        # Credentials path
        cred_layout = QHBoxLayout()
        cred_layout.addWidget(QLabel("🔑 Client Secret JSON:"))
        self.youtube_creds = QLineEdit()
        self.youtube_creds.setText("client_secret.json")
        self.youtube_creds.setPlaceholderText("client_secret.json")
        cred_layout.addWidget(self.youtube_creds)
        layout.addLayout(cred_layout)
        
        cred_info = QLabel("📘 Pobierz z: Google Cloud Console → APIs & Services → Credentials")
        cred_info.setStyleSheet("color: #2196F3; font-style: italic; padding-left: 25px;")
        layout.addWidget(cred_info)

        layout.addSpacing(20)

        # === STREAMER PROFILE DETECTION (NEW!) ===
        profile_group = QGroupBox("🎭 Streamer Profile")
        profile_layout = QVBoxLayout()

        # Info label
        self.profile_info_label = QLabel("Detecting...")
        self.profile_info_label.setWordWrap(True)
        self.profile_info_label.setStyleSheet("padding: 8px; background-color: #f5f5f5; border-radius: 4px;")
        profile_layout.addWidget(self.profile_info_label)

        # Buttons
        button_layout = QHBoxLayout()

        self.change_profile_btn = QPushButton("🔄 Change Profile")
        self.change_profile_btn.clicked.connect(self.show_profile_selector)
        button_layout.addWidget(self.change_profile_btn)

        self.refresh_detection_btn = QPushButton("🔍 Refresh")
        self.refresh_detection_btn.clicked.connect(self.detect_streamer)
        button_layout.addWidget(self.refresh_detection_btn)

        button_layout.addStretch()
        profile_layout.addLayout(button_layout)

        profile_group.setLayout(profile_layout)
        layout.addWidget(profile_group)

        # Initialize current_profile
        self.current_profile = None

        layout.addStretch()
        return tab
    
    # ... (reszta metod create_control_section, create_progress_panel, create_log_panel, create_results_section bez zmian)
    
    def create_control_section(self) -> QGroupBox:
        """Sekcja kontroli przetwarzania"""
        group = QGroupBox("🎮 Processing Control")
        layout = QHBoxLayout()
        
        self.start_btn = QPushButton("▶️ Start Processing")
        self.start_btn.setEnabled(False)
        self.start_btn.setMinimumHeight(50)
        self.start_btn.clicked.connect(self.start_processing)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background: #4CAF50;
                color: white;
                font-size: 14pt;
                font-weight: bold;
                border-radius: 6px;
            }
            QPushButton:hover {
                background: #45a049;
            }
            QPushButton:disabled {
                background: #ccc;
            }
        """)
        layout.addWidget(self.start_btn, stretch=3)
        
        self.cancel_btn = QPushButton("⏹️ Abort Processing")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setMinimumHeight(50)
        self.cancel_btn.clicked.connect(self.cancel_processing)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background: #F44336;
                color: white;
                font-size: 14pt;
                font-weight: bold;
                border-radius: 6px;
            }
            QPushButton:hover {
                background: #da190b;
            }
        """)
        layout.addWidget(self.cancel_btn, stretch=1)
        
        group.setLayout(layout)
        return group
    
    def create_progress_panel(self) -> QGroupBox:
        """Panel postępu"""
        group = QGroupBox("📊 Progress")
        layout = QVBoxLayout()
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimumHeight(30)
        layout.addWidget(self.progress_bar)
        
        # Current stage label
        self.progress_label = QLabel("Gotowy")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_label.setStyleSheet("font-size: 11pt; color: #555;")
        layout.addWidget(self.progress_label)
        
        # Stats list
        stats_label = QLabel("📈 Completed Stages:")
        layout.addWidget(stats_label)
        
        self.stats_list = QListWidget()
        self.stats_list.setMaximumHeight(200)
        layout.addWidget(self.stats_list)
        
        group.setLayout(layout)
        return group
    
    def create_log_panel(self) -> QGroupBox:
        """Panel logów"""
        group = QGroupBox("📝 Processing Logs")
        layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("font-family: 'Consolas', monospace; font-size: 9pt;")
        layout.addWidget(self.log_text)
        
        group.setLayout(layout)
        return group
    
    def create_results_section(self) -> QGroupBox:
        """Sekcja wyników"""
        group = QGroupBox("🎉 Results")
        layout = QVBoxLayout()
        
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        self.results_text.setMaximumHeight(200)
        layout.addWidget(self.results_text)
        
        # Action buttons
        btn_layout = QHBoxLayout()
        
        open_folder_btn = QPushButton("📂 Otwórz folder")
        open_folder_btn.clicked.connect(self.open_output_folder)
        btn_layout.addWidget(open_folder_btn)
        
        play_video_btn = QPushButton("▶️ Odtwórz film")
        play_video_btn.clicked.connect(self.play_output_video)
        btn_layout.addWidget(play_video_btn)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
        
        group.setLayout(layout)
        return group
    def download_from_url(self):
        """Download video from URL"""
        url = self.url_input.text().strip()
        
        if not url:
            QMessageBox.warning(self, "Błąd", "Proszę podać URL video!")
            return
        
        # Disable button during download
        self.download_btn.setEnabled(False)
        self.download_progress.setVisible(True)
        self.download_status.setVisible(True)
        self.download_status.setText("Inicjalizacja...")
        
        # Start download thread
        self.download_thread = DownloadThread(url, download_dir="downloads")
        
        # Connect signals
        self.download_thread.progress_updated.connect(self.on_download_progress)
        self.download_thread.info_retrieved.connect(self.on_video_info)
        self.download_thread.download_completed.connect(self.on_download_complete)
        self.download_thread.download_failed.connect(self.on_download_failed)
        
        self.download_thread.start()

    def on_download_progress(self, percent: int, message: str):
        """Update download progress"""
        self.download_progress.setValue(percent)
        self.download_status.setText(message)

    def on_video_info(self, info: dict):
        """Display video info"""
        duration_str = self.format_duration(info['duration'])
        info_text = f"📹 {info['title']}\n⏱️ Długość: {duration_str} | 👤 {info['uploader']}"
        self.download_status.setText(info_text)

    def on_download_complete(self, file_path: str):
        """Handle successful download"""
        self.downloaded_file_path = file_path
        
        # Update UI
        self.download_btn.setEnabled(True)
        self.download_progress.setValue(100)
        self.download_status.setText("✅ Pobrano pomyślnie!")
        
        # Show file info
        self.video_info_label.setText(f"📁 Pobrany plik: {Path(file_path).name}")
        self.video_info_label.setVisible(True)
        
        # Auto-load to file path label (for processing)
        self.file_path_label.setText(file_path)
        
        # Show info in log
        self.log(f"✅ Pobrano: {Path(file_path).name}", "SUCCESS")
        
        # Enable start button
        self.start_btn.setEnabled(True)
        
        QMessageBox.information(
            self,
            "Sukces",
            f"Video pobrane pomyślnie!\n\n{Path(file_path).name}\n\nMożesz teraz rozpocząć processing."
        )

    def on_download_failed(self, error: str):
        """Handle download failure"""
        self.download_btn.setEnabled(True)
        self.download_progress.setVisible(False)
        self.download_status.setText(f"❌ Błąd: {error}")
        
        self.log(f"❌ Błąd pobierania: {error}", "ERROR")
        
        QMessageBox.critical(
            self,
            "Błąd pobierania",
            f"Nie udało się pobrać video:\n\n{error}\n\nSprawdź URL i spróbuj ponownie."
        )

    def format_duration(self, seconds: int) -> str:
        """Format duration for display"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"
    
    def setup_styles(self):
        """Ustaw globalne style"""
        self.setStyleSheet("""
            QMainWindow {
                background: #fafafa;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #ddd;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
            QPushButton {
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QSpinBox, QDoubleSpinBox, QComboBox, QLineEdit, QTimeEdit {
                padding: 6px;
                border: 1px solid #ccc;
                border-radius: 4px;
                min-width: 120px;
            }
        """)
    
    # === EVENT HANDLERS ===
    def on_profile_changed(self):
        """Handle profile selection change"""
        if not hasattr(self, 'profile_combo'):
            return

        display_name = self.profile_combo.currentText()
        profile_key = self.profile_map.get(display_name)

        if profile_key:
            profile = self.profile_loader.get_profile(profile_key)
            if profile:
                self.log(f"✓ User confirmed profile: {profile_key}", "INFO")
                self.config.language = profile.language
                self.config.asr.language = profile.language

                if profile.data.get('features', {}).get('keywords_file'):
                    self.config.features.keywords_file = profile.data['features']['keywords_file']

                if profile.data.get('features', {}).get('spacy_model'):
                    self.config.features.spacy_model = profile.data['features']['spacy_model']

                if profile.channel_id:
                    self.config.youtube.channel_id = profile.channel_id
                    self.log(f"  Updated config.youtube.channel_id to: {profile.channel_id}", "INFO")

                # ✅ FIX: Store streamer_id in config for Stage 7 AI metadata generation
                self.config.streamer_id = profile.streamer_id
                self.log(f"  Updated config.streamer_id to: {profile.streamer_id}", "INFO")

                lang_idx = 0 if profile.language == "pl" else 1
                self.language_combo.setCurrentIndex(lang_idx)
                self.log(f"  Updated GUI language to: {profile.language.upper()}", "INFO")

                if hasattr(self, 'profile_warning'):
                    self.profile_warning.setVisible(False)

    def auto_detect_profile(self, video_path: str):
        """Auto-detect profile based on video filename"""
        filename = Path(video_path).name
        detected_profile = self.profile_loader.auto_detect_profile(filename)

        if detected_profile:
            self.log(f"🔍 Auto-detected profile: {detected_profile.display_name}", "INFO")
            target_display_name = f"{detected_profile.display_name} ({detected_profile.language.upper()})"
            for idx in range(self.profile_combo.count()):
                if self.profile_combo.itemText(idx) == target_display_name:
                    current_selection = self.profile_combo.currentText()
                    if current_selection != target_display_name:
                        if hasattr(self, 'profile_warning'):
                            self.profile_warning.setText(
                                f"⚠️ Detected {detected_profile.display_name} but you selected {current_selection.split(' ')[0]}"
                            )
                            self.profile_warning.setVisible(True)
                        self.log(
                            f"⚠️ Profile mismatch! Detected: {detected_profile.display_name}, "
                            f"Selected: {current_selection.split(' ')[0]}",
                            "WARNING"
                        )
                    else:
                        if hasattr(self, 'profile_warning'):
                            self.profile_warning.setVisible(False)
                    break
        else:
            self.log(f"ℹ️ Could not auto-detect profile from filename: {filename}", "INFO")

    def browse_file(self):
        """Wybór pliku MP4"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz transmisję Sejmu",
            str(Path.home()),
            "Video Files (*.mp4 *.mkv *.avi)"
        )
        
        if file_path:
            self.file_path_label.setText(file_path)
            self.start_btn.setEnabled(True)
            
            # Pokaż info o pliku
            file_size = Path(file_path).stat().st_size / (1024**3)  # GB
            self.file_info_label.setText(
                f"📊 Rozmiar: {file_size:.2f} GB | Naciśnij 'Start Processing' aby rozpocząć"
            )
            self.file_info_label.setVisible(True)

            # Auto-detect profile from filename
            if hasattr(self, 'profile_loader'):
                self.auto_detect_profile(file_path)

            self.log(f"Wybrano plik: {Path(file_path).name}", "INFO")
            
            # Detect file duration and suggest split strategy
            self.detect_and_suggest_strategy(file_path)
    
    def detect_and_suggest_strategy(self, file_path: str):
        """Wykryj długość pliku i zasugeruj strategię"""
        try:
            import subprocess
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
                capture_output=True, text=True, timeout=10
            )
            
            duration = float(result.stdout.strip())
            hours = duration / 3600
            
            if duration >= self.splitter_min_duration.value():
                # Material długi - zasugeruj split
                if duration < 7200:  # < 2h
                    parts = 2
                elif duration < 14400:  # < 4h
                    parts = 3
                elif duration < 21600:  # < 6h
                    parts = 4
                else:
                    parts = 5
                
                self.log(
                    f"🤖 Smart Splitter: Wykryto {hours:.1f}h materiału → "
                    f"Zostanie podzielony na {parts} części (~15min każda)",
                    "INFO"
                )
            else:
                self.log(
                    f"ℹ️ Materiał {hours:.1f}h < 1h → Pojedynczy film bez podziału",
                    "INFO"
                )
        except:
            pass  # Ignore errors
    
    def browse_output_dir(self):
        """Wybór folderu wyjściowego"""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Wybierz folder wyjściowy",
            self.output_dir.text()
        )
        if dir_path:
            self.output_dir.setText(dir_path)
    
    def start_processing(self):
        """Rozpocznij przetwarzanie"""
        # === OCHRONA PRZED WIELOKROTNYM URUCHOMIENIEM ===
        if self.processing_thread and self.processing_thread.isRunning():
            self.log("⚠️ Pipeline już działa! Ignoruję kolejne kliknięcie Start.", "WARNING")
            QMessageBox.warning(
                self,
                "Pipeline już działa",
                "Przetwarzanie jest już w toku.\n\nProszę poczekać na zakończenie lub kliknąć Cancel."
            )
            return

        # CRITICAL: Aktualizuj config z GUI PRZED startem
        self.update_config_from_gui()

        # Log config values
        self.log(f"Config - Whisper model: {self.config.asr.model}", "INFO")
        self.log(
            f"Config - Target duration: {self.config.selection.target_total_duration/60:.1f} min",
            "INFO",
        )
        self.log(f"Config - Smart Splitter: {self.config.splitter.enabled}", "INFO")

        # Disable controls
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.results_widget.setVisible(False)

        # Reset progress
        self.progress_bar.setValue(0)
        self.stats_list.clear()

        # Start thread
        if self.downloaded_file_path:
            input_file = self.downloaded_file_path
        else:
            input_file = self.file_path_label.text()

        if not input_file or input_file == "Nie wybrano pliku":
            QMessageBox.warning(self, "Błąd", "Proszę wybrać plik wejściowy lub pobrać video z URL!")
            self.start_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            return

        if self.config.mode.lower() == "stream":
            if self.config.chat_json_path and not self.config.chat_json_path.exists():
                self.log(f"Nie znaleziono chat.json pod: {self.config.chat_json_path}", "WARNING")
            elif not self.config.chat_json_path:
                self.log("Tryb Stream bez chat.json → chat_burst_score będzie 0.0", "WARNING")

        self.processing_thread = ProcessingThread(input_file, self.config)

        # Connect signals
        self.processing_thread.progress_updated.connect(self.on_progress_update)
        self.processing_thread.stage_completed.connect(self.on_stage_completed)
        self.processing_thread.log_message.connect(self.log)
        self.processing_thread.processing_completed.connect(self.on_processing_completed)
        self.processing_thread.processing_failed.connect(self.on_processing_failed)

        self.processing_thread.start()
        self.log("🚀 Rozpoczęto przetwarzanie...", "INFO")
    
    def cancel_processing(self):
        """Anuluj przetwarzanie"""
        if self.processing_thread:
            self.log("Anulowanie...", "WARNING")
            self.processing_thread.stop()
            self.processing_thread.wait()
            self.reset_ui_after_processing()
    
    def on_progress_update(self, percent: int, message: str):
        """Update progress bar"""
        self.progress_bar.setValue(percent)
        self.progress_label.setText(message)
    
    def on_stage_completed(self, stage: str, stats: dict):
        """Stage zakończony"""
        time_taken = stats.get('time', 'N/A')
        self.stats_list.addItem(f"✅ {stage} - {time_taken}")
    
    def on_processing_completed(self, results: dict):
        """Przetwarzanie zakończone pomyślnie"""
        self.current_results = results

        export_results = results.get('export_results') or []
        primary_output = results.get('output_file')
        if not primary_output and export_results:
            primary_output = export_results[0].get('output_file')

        if primary_output and self.copyright_cb.isChecked() and self.copyright_protector:
            fixed_path, status = self.copyright_protector.scan_and_fix(primary_output)
            self.log(f"Copyright scan for main output: {status}", "INFO")
            primary_output = fixed_path
            for item in export_results:
                if item.get('output_file') == results.get('output_file'):
                    item['output_file'] = fixed_path

        if not export_results and not primary_output:
            warn_msg = results.get('message', 'Brak wygenerowanych klipów – dostosuj próg score lub parametry.')
            self.log(warn_msg, "WARNING")
            QMessageBox.information(self, "Brak klipów", warn_msg)
            self.reset_ui_after_processing()
            return

        if getattr(self.config.shorts, 'enabled', False):
            generator_cls, segment_cls = self.shorts_generator_cls, self.segment_cls

            if generator_cls is None or segment_cls is None:
                msg = self.shorts_import_error or "Moduł shorts jest niedostępny."
                self.log(msg, "ERROR")
                QMessageBox.warning(
                    self,
                    "Shorts not available",
                    f"Nie można uruchomić generatora shortsów. {msg}"
                )
                return

            try:
                generator = generator_cls(
                    output_dir=Path(self.config.output_dir) / "shorts",
                    face_regions=self.config.shorts.face_regions,
                )
                raw_segments = results.get('segments', [])
                segments = [
                    segment_cls(
                        start=float(seg.get('start', 0)),
                        end=float(seg.get('end', 0)),
                        score=float(seg.get('score', 0)),
                        subtitles=seg.get('subtitles'),
                    )
                    for seg in raw_segments
                ]
                video_path = Path(primary_output or results.get('input_file'))
                copyright_processor = None
                try:
                    if getattr(self.config.copyright, "enable_protection", True):
                        copyright_processor = self.copyright_protector
                except Exception as exc:
                    self.log(f"Nie udało się zainicjalizować modułu copyright: {exc}", "WARNING")

                shorts_paths = generator.generate(
                    video_path,
                    segments,
                    template=self.config.shorts.template,
                    count=getattr(self.config.shorts, "num_shorts", getattr(self.config.shorts, "count", 5)),
                    speedup=getattr(self.config.shorts, "speedup_factor", getattr(self.config.shorts, "speedup", 1.0)),
                    enable_subtitles=getattr(
                        self.config.shorts,
                        "enable_subtitles",
                        getattr(self.config.shorts, "add_subtitles", getattr(self.config.shorts, "subtitles", False)),
                    ),
                    subtitle_lang=self.config.shorts.subtitle_lang,
                    copyright_processor=copyright_processor,
                )
                for short in shorts_paths:
                    self.upload_file_list.addItem(str(short))
            except Exception as exc:
                self.log("Shorts generation failed: %s" % exc, "ERROR")

        # Show results
        self.results_widget.setVisible(True)
        
        # Check if multi-part
        if results.get('parts_metadata'):
            # Multi-part results
            parts = results['parts_metadata']
            summary = f"""
✅ Przetwarzanie zakończone - MULTI-PART!

📊 Wygenerowano {len(parts)} części:
"""
            for part in parts:
                summary += f"\n  Część {part['part_number']}/{part['total_parts']}:"
                summary += f"\n  📺 {part['title']}"
                summary += f"\n  🗓️ Premiera: {part['premiere_datetime'][:16]}"
                summary += f"\n  ⏱️ Długość: {part['duration']:.0f}s ({part['num_clips']} klipów)"
                
                if results.get('youtube_results') and len(results['youtube_results']) >= part['part_number']:
                    yt = results['youtube_results'][part['part_number']-1]
                    if yt and yt.get('success'):  # Sprawdzenie czy yt nie jest None
                        summary += f"\n  🔗 {yt['video_url']}"
                summary += "\n"
            
        else:
            # Single file results
            summary = f"""
✅ Przetwarzanie zakończone!

📊 Podsumowanie:
- Plik wejściowy: {results['input_file']}
- Długość oryginału: {results.get('original_duration', 'N/A')}
- Liczba wybranych klipów: {results.get('num_clips', 'N/A')}
- Długość finalna: {results.get('output_duration', 'N/A')}
- Plik wyjściowy: {results.get('output_file', 'N/A')}

⏱️ Czasy przetwarzania:
{self._format_timing_stats(results.get('timing', {}))}
"""
        
        self.results_text.setText(summary)
        self.log("✅ Gotowe!", "SUCCESS")
        self.reset_ui_after_processing()
    
    def on_processing_failed(self, error: str):
        """Przetwarzanie zakończone błędem"""
        QMessageBox.critical(self, "Error", f"Błąd przetwarzania:\n{error}")
        self.reset_ui_after_processing()
    
    def reset_ui_after_processing(self):
        """Reset UI po zakończeniu"""
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Gotowy")

    def add_upload_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Select files to upload")
        for path in files:
            self.upload_file_list.addItem(path)

    def scan_copyright(self):
        protector = self.copyright_protector if self.copyright_cb.isChecked() else None
        if protector is None:
            QMessageBox.information(self, "Copyright", "Protection disabled w GUI.")
            return
        items = self.upload_file_list.selectedItems() or list(self.upload_file_list.findItems("*", Qt.MatchFlag.MatchWildcard))
        for item in items:
            fixed_path, status = protector.scan_and_fix(item.text())
            if fixed_path != item.text():
                item.setText(fixed_path)
            self.log(f"Status copyright dla {fixed_path}: {status}", "INFO")
        QMessageBox.information(self, "Copyright", "Scan completed. Zaktualizowano statusy w tabeli.")

    def refresh_channels(self):
        QMessageBox.information(self, "Channels", "Refreshed channel tokens (placeholder)")

    def enqueue_uploads(self):
        selected_items = self.upload_file_list.selectedItems() or list(self.upload_file_list.findItems("*", Qt.MatchFlag.MatchWildcard))
        if not selected_items:
            QMessageBox.warning(self, "Upload", "No files selected")
            return
        scheduled_at = parse_scheduled_at(self.schedule_picker.dateTime().toString(Qt.DateFormat.ISODate))
        protection_enabled = self.copyright_cb.isChecked()
        for item in selected_items:
            targets: list[UploadTarget] = []
            platform_choices = [
                ("youtube_long", self.cb_youtube, "long", self.youtube_long_account_combo),
                ("youtube_shorts", self.cb_youtube_shorts, "shorts", self.youtube_shorts_account_combo),
                ("facebook", self.cb_facebook, None, None),
                ("instagram", self.cb_instagram, None, None),
                ("tiktok", self.cb_tiktok, None, None),
            ]
            for platform, checkbox, kind, combo in platform_choices:
                if not checkbox.isChecked():
                    continue
                account_id = combo.currentData() if combo else None
                if not account_id:
                    account_id = self._default_account(platform, kind if platform.startswith("youtube") else None)
                if not account_id:
                    self.log(
                        f"Brak skonfigurowanego konta dla {platform}. Dodaj je w accounts.yml",
                        "ERROR",
                    )
                    QMessageBox.warning(self, "Upload", f"Brak konta dla platformy {platform}")
                    continue
                mode = "NATIVE_SCHEDULE" if platform.startswith("youtube") else "LOCAL_SCHEDULE"
                targets.append(
                    UploadTarget(
                        platform=platform,
                        account_id=account_id,
                        scheduled_at=scheduled_at,
                        mode=mode,
                        kind=kind,
                    )
                )
            if not targets:
                QMessageBox.warning(self, "Upload", "No platforms selected")
                return
            job = UploadJob(
                file_path=Path(item.text()),
                title=self.upload_title.text() or Path(item.text()).stem,
                description=self.upload_desc.toPlainText(),
                targets=targets,
            )
            job.copyright_status = "pending" if protection_enabled else "skipped"
            job.original_path = job.file_path
            self.upload_manager.enqueue(job)
            for target in job.targets:
                self._add_or_update_target_row(job, target)

    def _account_options_for_platform(self, platform: str, kind: str | None = None) -> list[tuple[str, str]]:
        specs = self.accounts_registry.list(platform) if hasattr(self, "accounts_registry") else []
        options: list[tuple[str, str]] = []
        for spec in specs:
            label = spec.label(kind)
            options.append((spec.account_id, label))
        return options

    def _default_account(self, platform: str, kind: str | None = None) -> str | None:
        if not hasattr(self, "accounts_registry"):
            return None
        return self.accounts_registry.default_account(platform, kind)

    def _refresh_youtube_account_inputs(self):
        if not hasattr(self, "youtube_long_account_combo"):
            return

        combos = [
            (self.youtube_long_account_combo, self.youtube_long_default_label, "youtube_long", "long"),
            (self.youtube_shorts_account_combo, self.youtube_shorts_default_label, "youtube_shorts", "shorts"),
        ]
        for combo, label, platform, kind in combos:
            combo.blockSignals(True)
            combo.clear()
            label.setText("")
            options = self._account_options_for_platform(platform, kind)
            default_acc = self._default_account(platform, kind)
            if not options:
                combo.addItem("Brak kont YouTube", userData=None)
                combo.setEnabled(False)
                label.setText("Dodaj wpis w accounts.yml")
                label.setStyleSheet("color: #c0392b; font-size: 11px;")
            else:
                combo.setEnabled(True)
                for account_id, option_label in options:
                    combo.addItem(option_label, userData=account_id)
                if default_acc is not None:
                    idx = combo.findData(default_acc)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                        label.setText(f"Domyślne: {default_acc}")
                if not label.text():
                    label.setText("Wybierz konto")
                label.setStyleSheet("color: #555; font-size: 11px;")
            combo.blockSignals(False)

    def reload_accounts_registry(self):
        self.upload_manager.refresh_accounts()
        self.accounts_registry = self.upload_manager.accounts_registry
        self.accounts_config = self.upload_manager.accounts_config or {}
        self._refresh_youtube_account_inputs()
        self.populate_accounts_status_table()

    def populate_accounts_status_table(self):
        if not hasattr(self, "accounts_table"):
            return
        self.accounts_table.setRowCount(0)
        platforms = ["youtube", "facebook", "instagram", "tiktok"]
        for platform in platforms:
            for spec in self.accounts_registry.list(platform):
                row = self.accounts_table.rowCount()
                self.accounts_table.insertRow(row)
                self.accounts_table.setItem(row, 0, QTableWidgetItem(platform))
                self.accounts_table.setItem(row, 1, QTableWidgetItem(spec.account_id))
                description = spec.config.get("description") or spec.config.get("name") or "—"
                self.accounts_table.setItem(row, 2, QTableWidgetItem(str(description)))
                status_item = QTableWidgetItem(spec.status)
                color = "#27ae60" if spec.status == STATUS_OK else "#c0392b"
                if spec.status == STATUS_MISSING_ENV:
                    color = "#d35400"
                elif spec.status == STATUS_MANUAL_REQUIRED:
                    color = "#f39c12"
                status_item.setForeground(Qt.GlobalColor.black)
                status_item.setBackground(QColor(color))
                self.accounts_table.setItem(row, 3, status_item)
                self.accounts_table.setItem(row, 4, QTableWidgetItem(self._account_requirements(spec)))
                self.accounts_table.setItem(row, 5, QTableWidgetItem(self._account_diagnosis(spec)))

    def open_accounts_docs(self):
        docs_path = Path("docs/accounts_setup.md").resolve()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(docs_path)))

    def _account_requirements(self, spec):
        if spec.platform == "youtube":
            return "client_secret_path, credential_profile, (optional) expected_channel_id"
        if spec.platform == "facebook":
            return "page_id, access_token_env"
        if spec.platform == "instagram":
            return "ig_user_id, page_id, access_token_env"
        if spec.platform == "tiktok":
            return "mode, advertiser_id (opcjonalnie), access_token_env dla OFFICIAL_API"
        return "—"

    def _account_diagnosis(self, spec):
        cfg = spec.config or {}
        access_env = cfg.get("access_token_env")
        if spec.platform == "youtube":
            if spec.status == STATUS_OK:
                return "Konto gotowe. Zaloguj/zweryfikuj w UI, aby odświeżyć token."
            if spec.status == STATUS_INVALID_CONFIG:
                secret_path = cfg.get("client_secret_path") or "secrets/youtube_client_secret.json"
                return f"Umieść plik client_secret pod {secret_path} i ustaw credential_profile."
            if spec.status == STATUS_MISSING_ENV:
                return "Ustaw brakujące zmienne środowiskowe przed startem."
        if spec.platform in {"facebook", "instagram"}:
            if spec.status == STATUS_MISSING_ENV:
                return f"Dodaj token do ENV: export {access_env}=<PAGE_TOKEN> albo wpisz w .env."
            if spec.status == STATUS_INVALID_CONFIG:
                return "Uzupełnij page_id/ig_user_id i access_token_env w accounts.yml."
        if spec.platform == "tiktok":
            if spec.status == STATUS_MANUAL_REQUIRED:
                return "Tryb MANUAL_ONLY – zaloguj ręcznie i podaj advertiser_id/username w accounts.yml."
            if spec.status == STATUS_MISSING_ENV:
                return f"OFFICIAL_API wymaga tokena w ENV: export {access_env}=<TOKEN>."
        return spec.message or "Sprawdź konfigurację"

    def _target_url(self, target: UploadTarget) -> str | None:
        if target.result_url:
            return target.result_url
        if not target.result_id:
            return None
        cfg = None
        normalized = "youtube" if target.platform.startswith("youtube") else target.platform
        if self.accounts_config:
            cfg = (self.accounts_config.get(normalized) or {}).get(target.account_id)
        return build_public_url(target.platform, target.result_id, cfg)

    def _open_target_link(self, target: UploadTarget):
        url = self._target_url(target)
        if url:
            QDesktopServices.openUrl(QUrl(url))
        else:
            QMessageBox.information(
                self,
                "Brak linku",
                "Brak publicznego linku — platforma nie zwróciła URL. Sprawdź materiał w panelu danej platformy.",
            )

    def _copy_target_link(self, target: UploadTarget):
        url = self._target_url(target)
        text = url or (target.result_id or "")
        if not text:
            QMessageBox.information(self, "Copy", "Brak danych do skopiowania")
            return
        QApplication.clipboard().setText(text)
        if url:
            self.log(f"Skopiowano link do {target.platform}", "INFO")
        else:
            self.log("Skopiowano tylko result_id (brak URL)", "INFO")

    def _add_or_update_target_row(self, job: UploadJob, target: UploadTarget):
        row = self.target_row_map.get(target.target_id)
        if row is None:
            row = self.target_table.rowCount()
            self.target_table.insertRow(row)
            self.target_row_map[target.target_id] = row
        self.target_lookup[target.target_id] = (job, target)

        file_item = QTableWidgetItem(str(job.file_path))
        file_item.setData(Qt.ItemDataRole.UserRole, target.target_id)
        self.target_table.setItem(row, 0, file_item)
        self.target_table.setItem(row, 1, QTableWidgetItem(target.platform))

        # Account dropdown
        account_combo = QComboBox()
        for account_id, label in self._account_options_for_platform(target.platform, target.kind):
            account_combo.addItem(label, userData=account_id)
        if target.account_id:
            idx = account_combo.findData(target.account_id)
            if idx >= 0:
                account_combo.setCurrentIndex(idx)
        else:
            default_acc = self._default_account(target.platform, target.kind)
            if default_acc is not None:
                idx = account_combo.findData(default_acc)
                if idx >= 0:
                    account_combo.setCurrentIndex(idx)
        account_combo.currentIndexChanged.connect(
            lambda _, j=job, t=target, combo=account_combo: self._on_account_changed(
                j, t, combo.currentData()
            )
        )
        self.target_table.setCellWidget(row, 2, account_combo)

        # Scheduled picker
        sched_picker = QDateTimeEdit()
        sched_picker.setCalendarPopup(True)
        dt_value = target.scheduled_at or datetime.now()
        if dt_value.tzinfo:
            sched_picker.setDateTime(QDateTime.fromSecsSinceEpoch(int(dt_value.timestamp())))
        else:
            sched_picker.setDateTime(QDateTime.fromString(dt_value.isoformat(), Qt.DateFormat.ISODate))
        sched_picker.dateTimeChanged.connect(lambda value, j=job, t=target: self._on_schedule_changed(j, t, value))
        self.target_table.setCellWidget(row, 3, sched_picker)

        mode_combo = QComboBox()
        mode_combo.addItems(["LOCAL_SCHEDULE", "NATIVE_SCHEDULE"])
        idx = mode_combo.findText(target.mode)
        if idx >= 0:
            mode_combo.setCurrentIndex(idx)
        mode_combo.currentTextChanged.connect(lambda value, j=job, t=target: self._on_mode_changed(j, t, value))
        self.target_table.setCellWidget(row, 4, mode_combo)

        self.target_table.setItem(row, 5, QTableWidgetItem(target.state))

        url = self._target_url(target)
        result_widget = QLabel()
        if url:
            result_widget.setText(f"<a href='{url}'>{target.result_id}</a>")
            result_widget.setTextFormat(Qt.TextFormat.RichText)
            result_widget.setOpenExternalLinks(True)
        else:
            result_widget.setText(target.result_id or "-")
        self.target_table.setCellWidget(row, 6, result_widget)

        self.target_table.setItem(row, 7, QTableWidgetItem(url or ""))

        open_btn = QPushButton("Open")
        open_btn.clicked.connect(lambda _, t=target: self._open_target_link(t))
        self.target_table.setCellWidget(row, 8, open_btn)

        copy_btn = QPushButton("Copy")
        copy_btn.clicked.connect(lambda _, t=target: self._copy_target_link(t))
        self.target_table.setCellWidget(row, 9, copy_btn)

        self.target_table.setItem(row, 10, QTableWidgetItem(target.last_error or ""))

    def _on_account_changed(self, job: UploadJob, target: UploadTarget, value: str):
        if not value:
            return
        self.upload_manager.update_target_configuration(job, target, account_id=value)
        self.log(f"Zapisano konto {value} dla {target.platform}", "INFO")

    def _on_schedule_changed(self, job: UploadJob, target: UploadTarget, qdatetime: QDateTime):
        py_dt = qdatetime.toPyDateTime()
        if py_dt.tzinfo is None:
            py_dt = py_dt.replace(tzinfo=ZoneInfo("Europe/Warsaw"))
        self.upload_manager.update_target_configuration(job, target, scheduled_at=py_dt)
        self.log(f"Zmieniono termin na {py_dt.isoformat()} dla {target.platform}", "INFO")

    def _on_mode_changed(self, job: UploadJob, target: UploadTarget, value: str):
        self.upload_manager.update_target_configuration(job, target, mode=value)

    def _get_target_by_row(self, row: int):
        item = self.target_table.item(row, 0)
        if not item:
            return None
        target_id = item.data(Qt.ItemDataRole.UserRole)
        return self.target_lookup.get(target_id)

    def apply_bulk_schedule(self):
        rows = {index.row() for index in self.target_table.selectedIndexes()}
        if not rows:
            rows = set(range(self.target_table.rowCount()))
        selected = [self._get_target_by_row(row) for row in rows]
        selected = [(j, t) for j, t in selected if j and t]
        if not selected:
            QMessageBox.warning(self, "Bulk schedule", "Brak wybranych targetów")
            return
        tz = self.bulk_tz_input.text() or "Europe/Warsaw"
        start_dt = parse_scheduled_at(self.bulk_start_dt.dateTime().toString(Qt.DateFormat.ISODate), tz)
        times = parse_times_list(self.bulk_times_input.text().split(","))
        interval_days = self.bulk_interval_spin.value()
        schedule = distribute_targets([t for _, t in selected], start_dt, times_of_day=times, interval_days=interval_days, tz=tz)
        for (job, target), sched in zip(selected, schedule):
            self.upload_manager.update_target_configuration(job, target, scheduled_at=sched)
            self._add_or_update_target_row(job, target)
            if sched < datetime.now(tz=sched.tzinfo):
                self.log(f"{target.platform} ustawiony w przeszłości → due now", "WARNING")
        self.log(f"Bulk schedule applied to {len(selected)} targets", "INFO")

    def apply_preset(self):
        preset_key = self.bulk_presets_combo.currentData()
        if not preset_key:
            return
        preset = self.scheduling_presets.get(preset_key, {})
        times = preset.get("times")
        if times:
            self.bulk_times_input.setText(",".join(times))
        tz = preset.get("timezone") or "Europe/Warsaw"
        self.bulk_tz_input.setText(tz)
        offset_days = preset.get("start_offset_days", 0)
        start = datetime.now(tz=ZoneInfo(tz)) + timedelta(days=offset_days)
        self.bulk_start_dt.setDateTime(QDateTime.fromSecsSinceEpoch(int(start.timestamp())))

    def _load_scheduling_presets(self):
        config_path = Path("config.yml")
        if not config_path.exists():
            return {}
        try:
            with open(config_path, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            return data.get("scheduling_presets", {}) or {}
        except Exception:
            self.logger.exception("Failed to load scheduling presets from config.yml")
            return {}

    def on_upload_update(self, event: str, job: UploadJob, target: UploadTarget | None = None):
        if event == "jobs_restored":
            self.log(
                f"Restored job {job.job_id} with {len(job.targets)} targets from persistence",
                "INFO",
            )
            for t in job.targets:
                self._add_or_update_target_row(job, t)
            return
        if target:
            self._add_or_update_target_row(job, target)
        if event == "target_retry_scheduled" and target:
            self.log(
                f"Retry scheduled for {target.platform}/{target.account_id} at {target.next_retry_at}",
                "WARNING",
            )
        if event == "target_manual_required" and target:
            self.log(f"Manual publish required: {target.last_error}", "ERROR")
    
    def update_config_from_gui(self):
        """Aktualizuj obiekt Config wartościami z GUI"""
        # Apply selected profile settings first
        if hasattr(self, 'profile_combo') and hasattr(self, 'profile_map'):
            display_name = self.profile_combo.currentText()
            profile_key = self.profile_map.get(display_name)
            if profile_key:
                profile = self.profile_loader.get_profile(profile_key)
                if profile:
                    profile.apply_to_config(self.config)
                    self.log(f"🌐 Language: {self.config.language.upper()} (from profile)", "INFO")
                    self.log(f"📚 Keywords file: {self.config.features.keywords_file}", "INFO")
        from pathlib import Path  # Import at method start to avoid UnboundLocalError


        # Selection settings
        self.config.selection.target_total_duration = float(self.target_duration.value()) * 60.0
        self.config.selection.max_clips = int(self.num_clips.value())
        # Wymuszamy minimalnie 8s, niezależnie od wcześniejszych ustawień
        self.config.selection.min_clip_duration = max(8.0, float(self.min_clip_duration.value()))
        self.config.selection.max_clip_duration = float(self.max_clip_duration.value())
        self.config.selection.min_score_threshold = float(self.score_threshold_slider.value()) / 100.0

        # Export settings
        self.config.export.add_transitions = bool(self.add_transitions.isChecked())
        self.config.export.generate_hardsub = bool(self.add_hardsub.isChecked())

        # Chat overlay settings (Chat Render MP4 based)
        self.config.export.chat_overlay_enabled = bool(self.chat_overlay_enabled.isChecked())
        self.config.export.chat_overlay_path = self.chat_file_path.text().strip() or None
        self.config.export.chat_x_percent = int(self.chat_x_slider.value())
        self.config.export.chat_y_percent = int(self.chat_y_slider.value())
        self.config.export.chat_scale_percent = int(self.chat_scale_slider.value())
        self.config.export.chat_transparent_bg = bool(self.chat_transparent_bg.isChecked())
        self.config.export.chat_opacity_percent = int(self.chat_opacity_slider.value())

        # Shorts settings
        if hasattr(self.config, 'shorts'):
            enabled = bool(self.shorts_generate_cb.isChecked()) if hasattr(self, 'shorts_generate_cb') else False
            self.config.shorts.enabled = enabled
            self.config.shorts.generate_shorts = enabled

            # Get template from combo box using mapping
            if hasattr(self, 'template_name_map'):
                display_name = self.shorts_template_combo.currentText()
                self.config.shorts.template = self.template_name_map.get(display_name, 'gaming')
            else:
                # Fallback for backward compat
                self.config.shorts.template = 'gaming' if self.shorts_template_combo.currentIndex() == 0 else 'universal'
            self.config.shorts.default_template = self.config.shorts.template

            self.config.shorts.enable_subtitles = bool(self.shorts_add_subs_cb.isChecked())
            self.config.shorts.add_subtitles = bool(self.shorts_add_subs_cb.isChecked())
            self.config.shorts.subtitles = bool(self.shorts_add_subs_cb.isChecked())
            self.config.shorts.speedup_factor = float(self.shorts_speed_slider.value()) / 100.0
            self.config.shorts.speedup = self.config.shorts.speedup_factor
            self.config.shorts.num_shorts = int(self.shorts_count_slider.value())
            self.config.shorts.count = self.config.shorts.num_shorts
            self.config.shorts.subtitle_lang = 'pl' if self.shorts_subs_lang.currentIndex() == 0 else 'en'

        if hasattr(self.config, 'copyright'):
            self.config.copyright.enabled = bool(self.shorts_remove_music_cb.isChecked())
            self.config.copyright.enable_protection = bool(self.copyright_cb.isChecked()) if hasattr(self, 'copyright_cb') else True
            if hasattr(self, 'copyright_protector'):
                self.copyright_protector.settings.enable_protection = self.config.copyright.enable_protection
                self.copyright_protector.settings.audd_api_key = getattr(self.config.copyright, 'audd_api_key', '')
                self.copyright_protector.settings.music_detection_threshold = getattr(self.config.copyright, 'music_detection_threshold', 0.7)
                self.copyright_protector.settings.royalty_free_folder = getattr(self.config.copyright, 'royalty_free_folder', Path('assets/royalty_free'))
                self.upload_manager.protector = self.copyright_protector if self.config.copyright.enable_protection else None

        # Whisper model
        whisper_idx = self.whisper_model.currentIndex()
        whisper_map = {0: "large-v3", 1: "medium", 2: "small"}
        self.config.asr.model = whisper_map.get(whisper_idx, "medium")

        # Mode & chat
        self.config.mode = "stream" if self.radio_mode_stream.isChecked() else "sejm"
        chat_path = self.chat_path_edit.text().strip()
        self.config.chat_json_path = Path(chat_path).expanduser() if chat_path else None
        self.config.prompt_text = self.prompt_input.text().strip()
        self.config.override_weights = bool(self.override_weights_cb.isChecked())
        if self.config.override_weights:
            self.config.custom_weights = CompositeWeights(
                chat_burst_weight=self.weight_sliders['chat_burst_weight'].value() / 100,
                acoustic_weight=self.weight_sliders['acoustic_weight'].value() / 100,
                semantic_weight=self.weight_sliders['semantic_weight'].value() / 100,
            )

        # Language switch updates Whisper + spaCy
        self.config.language = "pl" if self.language_combo.currentIndex() == 0 else "en"
        self.config.asr.language = self.config.language
        self.config.features.spacy_model = "pl_core_news_lg" if self.config.language == "pl" else "en_core_web_sm"

        # AUTO-DETECT LANGUAGE FROM STREAMER PROFILE (overrides GUI if different)
        if hasattr(self, 'current_profile') and self.current_profile:
            try:
                profile_lang = self.current_profile.primary_language
                gui_lang = self.config.language

                if profile_lang != gui_lang:
                    self.log(f"🌐 Auto-detected language from profile: {profile_lang.upper()}", "INFO")
                    self.log(f"   Overriding GUI language ({gui_lang.upper()}) → {profile_lang.upper()}", "INFO")

                    # Override language settings
                    self.config.language = profile_lang
                    self.config.asr.language = profile_lang
                    self.config.features.keywords_file = f"models/keywords_{profile_lang}.csv"
                    self.config.features.spacy_model = (
                        "pl_core_news_lg" if profile_lang == "pl" else "en_core_web_sm"
                    )

                    self.log(f"   ✓ ASR language: {profile_lang}", "INFO")
                    self.log(f"   ✓ Keywords file: keywords_{profile_lang}.csv", "INFO")
                    self.log(f"   ✓ NLP model: {self.config.features.spacy_model}", "INFO")
                else:
                    # Language matches GUI, but still need to ensure keywords_file uses language-specific file
                    self.log(f"🌐 Language: {profile_lang.upper()} (from profile, matches GUI)", "INFO")

                    # CRITICAL FIX: Update keywords_file even when language matches
                    self.config.features.keywords_file = f"models/keywords_{profile_lang}.csv"
                    self.config.features.spacy_model = (
                        "pl_core_news_lg" if profile_lang == "pl" else "en_core_web_sm"
                    )
            except AttributeError as e:
                self.log(f"⚠️ Could not auto-detect language from profile: {e}", "WARNING")
                self.log(f"   Using GUI setting: {self.config.language.upper()}", "WARNING")

        # SMART WARNING: Check if profile might be wrong based on input filename
        if hasattr(self, 'current_profile') and self.current_profile and hasattr(self, 'input_file') and self.input_file:
            try:
                input_filename = Path(self.input_file.text()).name.lower()
                profile_id = self.current_profile.streamer_id

                # Known streamer keywords in filenames
                streamer_hints = {
                    'asmongold': ['asmongold', 'asmon', 'zackrawrr', 'zack'],
                    'sejm': ['sejm', 'parlament', 'obrady']
                }

                # Check if filename suggests different streamer
                for expected_id, keywords in streamer_hints.items():
                    if any(kw in input_filename for kw in keywords):
                        if expected_id != profile_id:
                            self.log(f"⚠️ WARNING: Profile mismatch detected!", "WARNING")
                            self.log(f"   Current profile: {profile_id} ({self.current_profile.name})", "WARNING")
                            self.log(f"   Filename suggests: {expected_id}", "WARNING")
                            filename_display = Path(self.input_file.text()).name
                            if len(filename_display) > 80:
                                filename_display = filename_display[:80] + "..."
                            self.log(f"   Filename: {filename_display}", "WARNING")
                            self.log(f"   → If this is wrong, click 'Change Profile' to select correct one!", "WARNING")
                            break
            except Exception as e:
                # Silently ignore errors in profile mismatch detection
                pass

        # Smart Splitter settings (NOWE!)
        if hasattr(self.config, 'splitter'):
            self.config.splitter.enabled = bool(self.splitter_enabled.isChecked())
            self.config.splitter.min_duration_for_split = float(self.splitter_min_duration.value())
            self.config.splitter.premiere_hour = int(self.premiere_time.time().hour())
            self.config.splitter.premiere_minute = int(self.premiere_time.time().minute())
            self.config.splitter.first_premiere_days_offset = int(self.premiere_offset.value())
            self.config.splitter.use_politicians_in_titles = bool(self.use_politicians.isChecked())
        
        # YouTube settings (ROZSZERZONE!)
        # Safe access - widgets may be deleted during profile changes
        if hasattr(self.config, 'youtube'):
            if hasattr(self, 'youtube_upload') and self.youtube_upload is not None:
                try:
                    self.config.youtube.enabled = bool(self.youtube_upload.isChecked())
                except RuntimeError:
                    pass  # Widget deleted by Qt

            if hasattr(self, 'youtube_premiere') and self.youtube_premiere is not None:
                try:
                    self.config.youtube.schedule_as_premiere = bool(self.youtube_premiere.isChecked())
                except RuntimeError:
                    pass  # Widget deleted by Qt

            if hasattr(self, 'youtube_privacy') and self.youtube_privacy is not None:
                try:
                    privacy_map = {0: "unlisted", 1: "private", 2: "public"}
                    self.config.youtube.privacy_status = privacy_map.get(
                        self.youtube_privacy.currentIndex(), "unlisted"
                    )
                except RuntimeError:
                    pass  # Widget deleted by Qt

            if hasattr(self, 'youtube_creds') and self.youtube_creds is not None:
                try:
                    if self.youtube_creds.text():
                        self.config.youtube.credentials_path = Path(self.youtube_creds.text())
                except RuntimeError:
                    pass  # Widget deleted by Qt
        
        # Advanced settings
        # Safe access - widgets may be deleted during profile changes
        if hasattr(self, 'output_dir') and self.output_dir is not None:
            try:
                self.config.output_dir = Path(self.output_dir.text())
                # Ensure paths exist
                self.config.output_dir.mkdir(parents=True, exist_ok=True)
            except RuntimeError:
                pass  # Widget deleted by Qt

        if hasattr(self, 'keep_intermediate') and self.keep_intermediate is not None:
            try:
                self.config.keep_intermediate = bool(self.keep_intermediate.isChecked())
            except RuntimeError:
                pass  # Widget deleted by Qt
    
    def update_splitter_label(self):
        """Aktualizuj label z czasem w godzinach"""
        seconds = self.splitter_min_duration.value()
        hours = seconds / 3600
        self.splitter_min_duration.setSuffix(f" s ({hours:.1f}h)")
        self.update_strategy_example()
    
    def update_strategy_example(self):
        """Aktualizuj przykładową strategię podziału"""
        if not hasattr(self, 'strategy_label'):
            return
        
        # Example dla 5h materiału
        example_duration = 5 * 3600
        min_split = self.splitter_min_duration.value() if hasattr(self, 'splitter_min_duration') else 3600
        
        if example_duration >= min_split:
            # Oblicz części
            if example_duration < 7200:
                parts = 2
            elif example_duration < 14400:
                parts = 3
            elif example_duration < 21600:
                parts = 4
            else:
                parts = 5
            
            strategy_text = f"""
<b>Przykład: 5h live z Sejmu</b><br>
<span style='color: #4CAF50'>✓</span> Material > {min_split/3600:.1f}h → Podział aktywny<br>
<br>
<b>Strategia:</b><br>
• Liczba części: <b>{parts}</b><br>
• Czas na część: ~<b>15 minut</b><br>
• Score threshold: <b>7.0</b> (wyższy niż standard 6.5)<br>
• Kompresja: ~<b>9%</b> (45min z 5h)<br>
<br>
<b>Premiery:</b><br>
• Część 1: Jutro 18:00<br>
• Część 2: Pojutrze 18:00<br>
• Część 3: Za 3 dni 18:00
"""
        else:
            strategy_text = f"""
<b>Przykład: 5h live z Sejmu</b><br>
<span style='color: #F44336'>✗</span> Material < {min_split/3600:.1f}h → Brak podziału<br>
<br>
<i>Zwiększ "Minimalna długość" aby włączyć podział</i>
"""
        
        self.strategy_label.setText(strategy_text)
    
    def log(self, message: str, level: str = "INFO"):
        """Dodaj wiadomość do loga"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        color_map = {
            "INFO": "#2196F3",
            "SUCCESS": "#4CAF50",
            "WARNING": "#FF9800",
            "ERROR": "#F44336"
        }

        color = color_map.get(level, "#000000")

        html = f'<span style="color: gray;">[{timestamp}]</span> <span style="color: {color}; font-weight: bold;">[{level}]</span> {message}'

        self.log_text.append(html)
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)

        # Persist to file logger as well
        # Persist to file logger as well
        self.logger.log(getattr(logging, level, logging.INFO), message)
    
    def open_output_folder(self):
        """Otwórz folder z wynikami"""
        if self.current_results:
            # Check if multi-part
            if self.current_results.get('export_results'):
                output_path = Path(self.current_results['export_results'][0]['output_file']).parent
            else:
                output_path = Path(self.current_results['output_file']).parent
            
            import os
            import platform
            
            if platform.system() == "Windows":
                os.startfile(output_path)
            elif platform.system() == "Darwin":  # macOS
                os.system(f"open '{output_path}'")
            else:  # Linux
                os.system(f"xdg-open '{output_path}'")
    
    def play_output_video(self):
        """Odtwórz wygenerowany film"""
        if self.current_results:
            import os
            import platform
            
            # Get first video file
            if self.current_results.get('export_results'):
                video_file = self.current_results['export_results'][0]['output_file']
            else:
                video_file = self.current_results['output_file']
            
            if platform.system() == "Windows":
                os.startfile(video_file)
            elif platform.system() == "Darwin":  # macOS
                os.system(f"open '{video_file}'")
            else:  # Linux
                os.system(f"xdg-open '{video_file}'")
    
    def _format_timing_stats(self, timing: dict) -> str:
        """Formatuj statystyki czasu"""
        lines = []
        for stage, time in timing.items():
            lines.append(f"  • {stage}: {time}")
        return "\n".join(lines)

    def open_shorts_template_dialog(self):
        """Otwórz dialog wyboru szablonu Shorts"""
        dialog = ShortsTemplateDialog(self, self.config)
        if dialog.exec():
            # User clicked OK - get selected template
            self.shorts_template_selection = dialog.get_selected_template()
            # Update config with dialog values
            dialog.apply_to_config(self.config)
            self.log(f"Shorts template: {self.shorts_template_selection}", "INFO")

    def detect_streamer(self):
        """Auto-detect streamer from config"""
        try:
            from pipeline.streamers import get_manager
            manager = get_manager()

            # Get channel_id from config
            channel_id = self.config.youtube.channel_id if hasattr(self.config, 'youtube') else None

            if not channel_id:
                self.profile_info_label.setText("⚠️ No YouTube channel_id in config.yml")
                self.profile_info_label.setStyleSheet("padding: 8px; background-color: #fff3e0; border-radius: 4px;")
                self.current_profile = None
                return

            # Try auto-detection
            profile = manager.detect_from_youtube(channel_id)

            if profile:
                # Success
                self.profile_info_label.setText(
                    f"✅ Detected: {profile.name}\n"
                    f"Language: {profile.primary_language.upper()} | "
                    f"Type: {profile.channel_type.title()}"
                )
                self.profile_info_label.setStyleSheet("padding: 8px; background-color: #e8f5e9; border-radius: 4px;")
                self.current_profile = profile
                logger.info(f"Auto-detected streamer: {profile.streamer_id}")
            else:
                # Not found
                self.profile_info_label.setText(
                    f"⚠️ No profile found for channel: {channel_id}\n"
                    f"Click 'Change Profile' to select one."
                )
                self.profile_info_label.setStyleSheet("padding: 8px; background-color: #fff3e0; border-radius: 4px;")
                self.current_profile = None
                logger.warning(f"No profile found for channel_id: {channel_id}")

        except ImportError:
            # StreamerManager not available
            self.profile_info_label.setText("ℹ️ Streamer profiles not available (legacy mode)")
            self.profile_info_label.setStyleSheet("padding: 8px; background-color: #e3f2fd; border-radius: 4px;")
            self.current_profile = None

        except Exception as e:
            self.profile_info_label.setText(f"❌ Error detecting profile: {e}")
            self.profile_info_label.setStyleSheet("padding: 8px; background-color: #ffebee; border-radius: 4px;")
            self.current_profile = None
            logger.error(f"Profile detection error: {e}", exc_info=True)

    def show_profile_selector(self):
        """Show enhanced profile selection dialog with context and warnings"""
        try:
            from pipeline.streamers import get_manager
            from PyQt6.QtWidgets import QInputDialog
            manager = get_manager()

            profiles = manager.list_all()

            if not profiles:
                QMessageBox.warning(
                    self,
                    "No Profiles",
                    "No streamer profiles found.\n\n"
                    "Create one in: pipeline/streamers/profiles/\n"
                    "Use _TEMPLATE.yaml as starting point."
                )
                return

            # Enhanced selection dialog with more context
            items = []
            for p in profiles:
                # Show name, language, and content type
                lang_flag = "🇵🇱" if p.primary_language == "pl" else "🇺🇸" if p.primary_language == "en" else "🌐"
                type_emoji = "🏛️" if p.streamer_id == "sejm" else "🎮"
                items.append(f"{type_emoji} {p.name} ({p.streamer_id}) {lang_flag} {p.primary_language.upper()}")

            selected, ok = QInputDialog.getItem(
                self,
                "🔄 Select Streamer Profile",
                "⚠️  IMPORTANT: Profile determines language & AI metadata style!\n\n"
                "Choose profile that matches your content:\n"
                "• 🏛️ Sejm = Polish political content (formal)\n"
                "• 🎮 Asmongold/Streamers = English gaming/react content (casual)\n\n"
                "Profile:",
                items,
                0,
                False
            )

            if ok and selected:
                # Extract streamer_id from selection
                streamer_id = selected.split('(')[1].split(')')[0].strip()
                profile = manager.get(streamer_id)

                if profile:
                    # Show confirmation with profile details
                    confirm = QMessageBox.question(
                        self,
                        "Confirm Profile Selection",
                        f"Selected Profile: {profile.name}\n\n"
                        f"This will:\n"
                        f"• Use {profile.primary_language.upper()} for AI metadata\n"
                        f"• Use {profile.primary_language.upper()} keywords for clip detection\n"
                        f"• Apply {profile.channel_type} content style\n\n"
                        f"Is this correct for your content?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )

                    if confirm == QMessageBox.StandardButton.Yes:
                        self.current_profile = profile
                        self.profile_info_label.setText(
                            f"✅ Selected: {profile.name}\n"
                            f"Language: {profile.primary_language.upper()} | "
                            f"Type: {profile.channel_type.title()}"
                        )
                        self.profile_info_label.setStyleSheet("padding: 8px; background-color: #e8f5e9; border-radius: 4px;")
                        logger.info(f"User confirmed profile: {streamer_id}")

                        # CRITICAL: Update config.youtube.channel_id to match selected profile
                        # This ensures Stage 7 (AI metadata) uses the correct profile
                        if hasattr(self.config, 'youtube') and hasattr(profile, 'platforms'):
                            youtube_platform = profile.platforms.get('youtube')
                            if youtube_platform and hasattr(youtube_platform, 'channel_id'):
                                self.config.youtube.channel_id = youtube_platform.channel_id
                                logger.info(f"Updated config.youtube.channel_id to: {youtube_platform.channel_id}")
                            else:
                                logger.warning(f"Profile {streamer_id} has no YouTube channel_id")

                        # Update GUI language dropdown to match profile
                        if hasattr(profile, 'primary_language'):
                            lang_index = 0 if profile.primary_language == "pl" else 1
                            self.language_combo.setCurrentIndex(lang_index)
                            logger.info(f"Updated GUI language to: {profile.primary_language.upper()}")

                        # Show success message with reminder
                        QMessageBox.information(
                            self,
                            "✅ Profile Updated",
                            f"Profile set to: {profile.name}\n\n"
                            f"⚠️  REMINDER: Make sure this matches your input video!\n"
                            f"Wrong profile = wrong language = gibberish transcripts!"
                        )

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load profiles: {e}")
            logger.error(f"Profile selector error: {e}", exc_info=True)


class ShortsTemplateDialog(QDialog):
    """
    Dialog do wyboru szablonu YouTube Shorts
    Profesjonalne layouty dla streamów (gaming + IRL)
    """

    def __init__(self, parent, config: Config):
        super().__init__(parent)
        self.config = config
        self.selected_template = getattr(config.shorts, 'template', 'gaming')

        self.setWindowTitle("🎨 Shorts Template Settings - Profesjonalne layouty dla streamów")
        self.setMinimumWidth(700)
        self.setMinimumHeight(600)

        self.init_ui()

    def init_ui(self):
        """Inicjalizacja UI"""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("🎬 Wybierz szablon layoutu dla YouTube Shorts")
        header.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header)

        info = QLabel(
            "Automatyczna detekcja kamerki streamera + 4 profesjonalne szablony\n"
            "⚠️ Dla materiałów z Sejmu (bez kamerki) używany jest prosty crop 9:16"
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet("color: #666; padding: 10px; background: #f5f5f5; border-radius: 4px;")
        layout.addWidget(info)

        layout.addSpacing(20)

        # === TEMPLATE SELECTION ===
        template_group = QGroupBox("📱 Wybór szablonu")
        template_layout = QVBoxLayout()

        self.template_buttons = QButtonGroup(self)

        # Auto-detect (recommended)
        self.radio_auto = QRadioButton("🤖 AUTO (Zalecane) - Automatyczna detekcja na podstawie kamerki")
        self.radio_auto.setChecked(True)
        self.radio_auto.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.template_buttons.addButton(self.radio_auto, 0)
        template_layout.addWidget(self.radio_auto)

        auto_desc = QLabel(
            "   System wykryje pozycję kamerki i automatycznie wybierze najlepszy szablon.\n"
            "   Używa MediaPipe Face Detection."
        )
        auto_desc.setStyleSheet("color: #666; font-size: 9pt; padding-left: 25px;")
        template_layout.addWidget(auto_desc)

        template_layout.addSpacing(10)

        # Simple (backward compatibility)
        self.radio_simple = QRadioButton("📐 SIMPLE - Prosty crop 9:16 (dla Sejmu)")
        self.template_buttons.addButton(self.radio_simple, 1)
        template_layout.addWidget(self.radio_simple)

        simple_desc = QLabel("   Standardowy crop do formatu pionowego. Brak detekcji kamerki.")
        simple_desc.setStyleSheet("color: #666; font-size: 9pt; padding-left: 25px;")
        template_layout.addWidget(simple_desc)

        template_layout.addSpacing(10)

        # Classic Gaming
        self.radio_gaming = QRadioButton("🎮 CLASSIC GAMING - Kamerka na dole + gameplay u góry")
        self.template_buttons.addButton(self.radio_gaming, 2)
        template_layout.addWidget(self.radio_gaming)

        gaming_desc = QLabel(
            "   Layout:\n"
            "   • Tytuł u góry (220px)\n"
            "   • Gameplay wyżej (65% ekranu, max 15% crop z boków)\n"
            "   • Kamerka na dole (pełna szerokość, 33% wysokości)\n"
            "   • Napisy pod kamerką (safe zone)"
        )
        gaming_desc.setStyleSheet("color: #666; font-size: 9pt; padding-left: 25px;")
        template_layout.addWidget(gaming_desc)

        template_layout.addSpacing(10)

        # PIP Modern
        self.radio_pip = QRadioButton("📺 PIP MODERN - Mała kamerka w rogu (Picture-in-Picture)")
        self.template_buttons.addButton(self.radio_pip, 3)
        template_layout.addWidget(self.radio_pip)

        pip_desc = QLabel(
            "   Layout:\n"
            "   • Cały stream skalowany do 9:16 (max 15% crop)\n"
            "   • Kamerka jako mały PIP w prawym dolnym rogu\n"
            "   • Zaokrąglone rogi + lekki cień (drop shadow)\n"
            "   • Napisy w środkowej safe zone"
        )
        pip_desc.setStyleSheet("color: #666; font-size: 9pt; padding-left: 25px;")
        template_layout.addWidget(pip_desc)

        template_layout.addSpacing(10)

        # IRL Full-face
        self.radio_irl = QRadioButton("🙋 IRL FULL-FACE - Pełna twarz (zoom + crop)")
        self.template_buttons.addButton(self.radio_irl, 4)
        template_layout.addWidget(self.radio_irl)

        irl_desc = QLabel(
            "   Layout:\n"
            "   • Zoom 1.2x na twarz\n"
            "   • Delikatny crop 12% z boków\n"
            "   • Brak PIP - tylko główna twarz\n"
            "   • Napisy w bezpiecznej strefie"
        )
        irl_desc.setStyleSheet("color: #666; font-size: 9pt; padding-left: 25px;")
        template_layout.addWidget(irl_desc)

        template_layout.addSpacing(10)

        # Dynamic Speaker Tracker
        self.radio_speaker = QRadioButton("👥 DYNAMIC SPEAKER TRACKER - Tracking mówiącego (2+ osoby)")
        self.template_buttons.addButton(self.radio_speaker, 5)
        template_layout.addWidget(self.radio_speaker)

        speaker_desc = QLabel(
            "   Layout (zaawansowany):\n"
            "   • Automatyczne wykrywanie mówiącego (word-level timestamps)\n"
            "   • Płynne przejścia co 3-5 sekund\n"
            "   • Zoom na aktualnie mówiącego\n"
            "   ⚠️ Wymaga 2+ twarzy w kadrze"
        )
        speaker_desc.setStyleSheet("color: #666; font-size: 9pt; padding-left: 25px;")
        template_layout.addWidget(speaker_desc)

        template_group.setLayout(template_layout)
        layout.addWidget(template_group)

        layout.addSpacing(20)

        # === ADVANCED SETTINGS ===
        advanced_group = QGroupBox("⚙️ Zaawansowane ustawienia")
        advanced_layout = QVBoxLayout()

        # Face detection enable/disable
        self.face_detection_cb = QCheckBox("🔍 Włącz wykrywanie twarzy (MediaPipe)")
        self.face_detection_cb.setChecked(self.config.shorts.face_detection)
        self.face_detection_cb.setToolTip(
            "Automatyczne wykrywanie regionu kamerki za pomocą MediaPipe Face Detection.\n"
            "Wyłącz jeśli chcesz zaoszczędzić zasoby CPU."
        )
        advanced_layout.addWidget(self.face_detection_cb)

        # Confidence threshold slider
        conf_layout = QHBoxLayout()
        conf_layout.addWidget(QLabel("   Próg pewności (confidence):"))
        self.confidence_slider = QSlider(Qt.Orientation.Horizontal)
        self.confidence_slider.setRange(30, 90)
        self.confidence_slider.setValue(int(self.config.shorts.webcam_detection_confidence * 100))
        self.confidence_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.confidence_slider.setTickInterval(10)
        conf_layout.addWidget(self.confidence_slider)
        self.confidence_label = QLabel(f"{self.confidence_slider.value()}%")
        self.confidence_slider.valueChanged.connect(
            lambda v: self.confidence_label.setText(f"{v}%")
        )
        conf_layout.addWidget(self.confidence_label)
        advanced_layout.addLayout(conf_layout)

        advanced_group.setLayout(advanced_layout)
        layout.addWidget(advanced_group)

        layout.addStretch()

        # === BUTTONS ===
        btn_layout = QHBoxLayout()

        cancel_btn = QPushButton("❌ Anuluj")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setMinimumWidth(120)
        btn_layout.addWidget(cancel_btn)

        btn_layout.addStretch()

        ok_btn = QPushButton("✅ Zastosuj")
        ok_btn.clicked.connect(self.accept)
        ok_btn.setMinimumWidth(120)
        ok_btn.setStyleSheet("""
            QPushButton {
                background: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 10px;
            }
            QPushButton:hover {
                background: #45a049;
            }
        """)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

    def get_selected_template(self) -> str:
        """Pobierz wybrany szablon"""
        selected_id = self.template_buttons.checkedId()

        template_map = {
            0: "auto",
            1: "simple",
            2: "classic_gaming",
            3: "pip_modern",
            4: "irl_fullface",
            5: "dynamic_speaker"
        }

        return template_map.get(selected_id, "auto")

    def apply_to_config(self, config: Config):
        """Zastosuj ustawienia do obiektu Config"""
        config.shorts.template = self.get_selected_template()
        if hasattr(config.shorts, 'face_detection'):
            config.shorts.face_detection = self.face_detection_cb.isChecked()
        if hasattr(config.shorts, 'webcam_detection_confidence'):
            config.shorts.webcam_detection_confidence = self.confidence_slider.value() / 100.0


def main():
    """Entry point"""
    app = QApplication(sys.argv)
    
    # Ustaw global font
    app.setFont(QFont("Segoe UI", 10))
    
    window = SejmHighlightsApp()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()