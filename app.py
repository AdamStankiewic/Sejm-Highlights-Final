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
from typing import TYPE_CHECKING, Optional, Tuple
from video_downloader import VideoDownloader
from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QTextEdit, QFileDialog,
    QGroupBox, QSpinBox, QDoubleSpinBox, QComboBox, QListWidget,
    QSplitter, QMessageBox, QTabWidget, QCheckBox, QLineEdit, QTimeEdit,
    QDialog, QRadioButton, QButtonGroup, QSlider, QTableWidget,
    QTableWidgetItem, QDateTimeEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QTime
from PyQt6.QtGui import QFont, QTextCursor, QPixmap

# Import pipeline modules
from pipeline.processor import PipelineProcessor
from pipeline.config import CompositeWeights, Config
from shorts.generator import ShortsGenerator, Segment
from uploader.manager import UploadManager, UploadJob


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
        self.processing_thread = None
        self.current_results = None
        self.download_thread = None
        self.downloaded_file_path = None
        self.upload_manager = UploadManager()
        self.translations = {
            "pl": {
                "generate_shorts": "Generuj shortsy z najlepszych segmentów",
                "shorts_template": "Szablon shortsa",
                "speedup": "Przyspieszenie",
                "add_subtitles": "Dodaj napisy",
            },
            "en": {
                "generate_shorts": "Generate shorts from top segments",
                "shorts_template": "Shorts template",
                "speedup": "Speed up",
                "add_subtitles": "Add subtitles",
            },
        }

        self.init_ui()
        self.setup_styles()

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
        self.chat_browse_btn = QPushButton("📂")
        self.chat_browse_btn.clicked.connect(self.browse_chat_file)
        chat_layout.addWidget(self.chat_path_edit)
        chat_layout.addWidget(self.chat_browse_btn)
        chat_group.setLayout(chat_layout)
        layout.addWidget(chat_group)

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
            ("prompt_boost_weight", "Prompt boost weight"),
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
            "prompt_boost_weight": weights.prompt_boost_weight,
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

    def _sync_mode_hint(self):
        """Zaktualizuj podpowiedź w headerze o aktywnym trybie (Sejm/Stream)."""

        if not hasattr(self, "mode_status_label"):
            return

        mode = "STREAM" if self.radio_mode_stream.isChecked() else "SEJM"
        chat_hint = "Chat bursts aktywne (chat.json)" if mode == "STREAM" else "Tryb Sejm – bez czatu"
        self.mode_status_label.setText(
            f"Tryb: {mode} • przełącz w zakładce 🛰️ Tryb/Chat ({chat_hint})"
        )

    def toggle_weight_override(self, checked: bool, init: bool = False):
        """Pokaż/ukryj slidery wag."""

        self.weights_widget.setVisible(checked)
        if checked and not init:
            self._refresh_weight_sliders()

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
        self.num_clips.setRange(5, 50)
        self.num_clips.setValue(min(50, max(5, self.config.selection.max_clips)))
        clips_layout.addWidget(self.num_clips)
        clips_layout.addStretch()
        layout.addLayout(clips_layout)

        # Min/Max clip duration
        min_clip_layout = QHBoxLayout()
        min_clip_layout.addWidget(QLabel("⏱️ Min. długość klipu (minuty):"))
        self.min_clip_duration = QDoubleSpinBox()
        self.min_clip_duration.setDecimals(2)
        self.min_clip_duration.setRange(0.33, 5.0)  # 20s - 5 min
        self.min_clip_duration.setSingleStep(0.05)
        self.min_clip_duration.setValue(max(0.33, min(5.0, self.config.selection.min_clip_duration / 60)))
        self.min_clip_duration.setSuffix(" min")
        self.min_clip_duration.valueChanged.connect(lambda _: setattr(self, "_min_clip_customized", True))
        min_clip_layout.addWidget(self.min_clip_duration)
        min_clip_layout.addStretch()
        layout.addLayout(min_clip_layout)

        max_clip_layout = QHBoxLayout()
        max_clip_layout.addWidget(QLabel("⏱️ Max. długość klipu (minuty):"))
        self.max_clip_duration = QDoubleSpinBox()
        self.max_clip_duration.setDecimals(2)
        self.max_clip_duration.setRange(0.5, 10.0)
        self.max_clip_duration.setSingleStep(0.1)
        self.max_clip_duration.setValue(max(0.5, min(10.0, self.config.selection.max_clip_duration / 60)))
        self.max_clip_duration.setSuffix(" min")
        max_clip_layout.addWidget(self.max_clip_duration)
        max_clip_layout.addStretch()
        layout.addLayout(max_clip_layout)

        # Dynamic scoring threshold
        threshold_layout = QHBoxLayout()
        threshold_layout.addWidget(QLabel("🎚️ Próg score (0.10-0.80):"))
        self.score_threshold_slider = QSlider(Qt.Orientation.Horizontal)
        self.score_threshold_slider.setRange(10, 80)
        default_threshold = int(getattr(self.config.selection, "min_score_threshold", 0.3) * 100)
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
        self.shorts_template_combo.addItems(["Gaming Facecam", "Universal"])
        current_template = getattr(self.config.shorts, "template", "gaming")
        self.shorts_template_combo.setCurrentIndex(0 if current_template == "gaming" else 1)
        template_layout.addWidget(self.shorts_template_combo)
        template_layout.addStretch()
        layout.addLayout(template_layout)

        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("📊 Liczba shortsów do wygenerowania:"))
        self.shorts_count_slider = QSlider(Qt.Orientation.Horizontal)
        self.shorts_count_slider.setRange(1, 50)
        self.shorts_count_slider.setValue(int(getattr(self.config.shorts, "count", 10) or 10))
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
        self.shorts_speed_slider.setValue(int(float(getattr(self.config.shorts, "speedup", 1.0)) * 100))
        speed_layout.addWidget(self.shorts_speed_slider)
        self.shorts_speed_label = QLabel(str(self.shorts_speed_slider.value() / 100))
        self.shorts_speed_slider.valueChanged.connect(lambda v: self.shorts_speed_label.setText(f"{v/100:.2f}"))
        speed_layout.addWidget(self.shorts_speed_label)
        layout.addLayout(speed_layout)

        self.shorts_add_subs_cb = QCheckBox(self._t("add_subtitles"))
        self.shorts_add_subs_cb.setChecked(bool(getattr(self.config.shorts, "subtitles", False)))
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

        # Store template selection (domyślnie z configu)
        self.shorts_template_selection = getattr(self.config.shorts, "template", "gaming")

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
        self.shorts_template_combo.addItems(["Gaming Facecam", "Universal"])
        current_template = getattr(self.config.shorts, "template", "gaming")
        self.shorts_template_combo.setCurrentIndex(0 if current_template == "gaming" else 1)
        template_layout.addWidget(self.shorts_template_combo)
        template_layout.addStretch()
        layout.addLayout(template_layout)

        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel(self._t("speedup")))
        self.shorts_speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.shorts_speed_slider.setMinimum(100)
        self.shorts_speed_slider.setMaximum(150)
        self.shorts_speed_slider.setSingleStep(5)
        self.shorts_speed_slider.setValue(int(float(getattr(self.config.shorts, "speedup_factor", 1.0)) * 100))
        speed_layout.addWidget(self.shorts_speed_slider)
        self.shorts_speed_label = QLabel(str(self.shorts_speed_slider.value() / 100))
        self.shorts_speed_slider.valueChanged.connect(lambda v: self.shorts_speed_label.setText(f"{v/100:.2f}"))
        speed_layout.addWidget(self.shorts_speed_label)
        layout.addLayout(speed_layout)

        self.shorts_add_subs_cb = QCheckBox(self._t("add_subtitles"))
        self.shorts_add_subs_cb.setChecked(bool(getattr(self.config.shorts, "add_subtitles", False)))
        layout.addWidget(self.shorts_add_subs_cb)

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
        file_buttons.addStretch()
        file_row.addWidget(self.upload_file_list, 2)
        file_row.addLayout(file_buttons, 1)
        layout.addLayout(file_row)

        platforms_layout = QHBoxLayout()
        self.cb_youtube = QCheckBox("YouTube")
        self.cb_youtube_shorts = QCheckBox("YouTube Shorts")
        self.cb_facebook = QCheckBox("Facebook")
        self.cb_instagram = QCheckBox("Instagram Reels")
        self.cb_tiktok = QCheckBox("TikTok")
        for cb in [self.cb_youtube, self.cb_youtube_shorts, self.cb_facebook, self.cb_instagram, self.cb_tiktok]:
            cb.setChecked(True)
            platforms_layout.addWidget(cb)
        platforms_layout.addStretch()
        layout.addLayout(platforms_layout)

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

        self.upload_table = QTableWidget(0, 3)
        self.upload_table.setHorizontalHeaderLabels(["File", "Status", "Result IDs"])
        layout.addWidget(self.upload_table)

        self.upload_manager.add_callback(self.on_upload_update)
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
        self.splitter_enabled.setChecked(True)
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
        self.log("Rozpoczęto przetwarzanie...", "INFO")
    
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

        if getattr(self.config.shorts, 'enabled', False):
            try:
                generator = ShortsGenerator(
                    output_dir=Path(self.config.output_dir) / "shorts",
                    face_regions=self.config.shorts.face_regions,
                )
                raw_segments = results.get('segments', [])
                segments = [
                    Segment(
                        start=float(seg.get('start', 0)),
                        end=float(seg.get('end', 0)),
                        score=float(seg.get('score', 0)),
                        subtitles=seg.get('subtitles'),
                    )
                    for seg in raw_segments
                ]
                video_path = Path(results.get('output_file') or results.get('input_file'))
                shorts_paths = generator.generate(
                    video_path,
                    segments,
                    template=self.config.shorts.template,
                    max_shorts=self.config.shorts.max_shorts_count,
                    speedup=self.config.shorts.speedup_factor,
                    add_subtitles=self.config.shorts.add_subtitles,
                    subtitle_lang=self.config.shorts.subtitle_lang,
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

    def refresh_channels(self):
        QMessageBox.information(self, "Channels", "Refreshed channel tokens (placeholder)")

    def enqueue_uploads(self):
        selected_items = self.upload_file_list.selectedItems() or list(self.upload_file_list.findItems("*", Qt.MatchFlag.MatchWildcard))
        if not selected_items:
            QMessageBox.warning(self, "Upload", "No files selected")
            return
        platforms = {
            "youtube_long": self.cb_youtube.isChecked(),
            "youtube_shorts": self.cb_youtube_shorts.isChecked(),
            "facebook": self.cb_facebook.isChecked(),
            "instagram": self.cb_instagram.isChecked(),
            "tiktok": self.cb_tiktok.isChecked(),
        }
        schedule = self.schedule_picker.dateTime().toString(Qt.DateFormat.ISODate)
        for item in selected_items:
            job = UploadJob(
                file_path=Path(item.text()),
                title=self.upload_title.text() or Path(item.text()).stem,
                description=self.upload_desc.toPlainText(),
                platforms=platforms,
                schedule=schedule,
            )
            self.upload_manager.enqueue(job)
            row = self.upload_table.rowCount()
            self.upload_table.insertRow(row)
            self.upload_table.setItem(row, 0, QTableWidgetItem(item.text()))
            self.upload_table.setItem(row, 1, QTableWidgetItem(job.status))
            self.upload_table.setItem(row, 2, QTableWidgetItem("-"))

    def on_upload_update(self, job: UploadJob):
        for row in range(self.upload_table.rowCount()):
            file_item = self.upload_table.item(row, 0)
            if file_item and file_item.text() == str(job.file_path):
                self.upload_table.setItem(row, 1, QTableWidgetItem(job.status))
                self.upload_table.setItem(row, 2, QTableWidgetItem(str(job.result_ids)))
        self.upload_progress.setValue(min(100, self.upload_progress.value() + 20))
    
    def update_config_from_gui(self):
        """Aktualizuj obiekt Config wartościami z GUI"""
        # Selection settings
        self.config.selection.target_total_duration = float(self.target_duration.value()) * 60.0
        self.config.selection.max_clips = int(self.num_clips.value())
        self.config.selection.min_clip_duration = float(self.min_clip_duration.value()) * 60.0
        self.config.selection.max_clip_duration = float(self.max_clip_duration.value()) * 60.0
        self.config.selection.min_score_threshold = float(self.score_threshold_slider.value()) / 100.0

        # Export settings
        self.config.export.add_transitions = bool(self.add_transitions.isChecked())
        self.config.export.generate_hardsub = bool(self.add_hardsub.isChecked())

        # Shorts settings
        if hasattr(self.config, 'shorts'):
            enabled = bool(self.shorts_generate_cb.isChecked()) if hasattr(self, 'shorts_generate_cb') else False
            self.config.shorts.enabled = enabled
            self.config.shorts.template = 'gaming' if self.shorts_template_combo.currentIndex() == 0 else 'universal'
            self.config.shorts.add_subtitles = bool(self.shorts_add_subs_cb.isChecked())
            self.config.shorts.speedup_factor = float(self.shorts_speed_slider.value()) / 100.0
        
        # Whisper model
        whisper_idx = self.whisper_model.currentIndex()
        whisper_map = {0: "large-v3", 1: "medium", 2: "small"}
        self.config.asr.model = whisper_map.get(whisper_idx, "medium")

        # Mode & chat
        self.config.mode = "stream" if self.radio_mode_stream.isChecked() else "sejm"
        chat_path = self.chat_path_edit.text().strip()
        self.config.chat_json_path = Path(chat_path) if chat_path else None
        self.config.prompt_text = self.prompt_input.text().strip()
        self.config.override_weights = bool(self.override_weights_cb.isChecked())
        if self.config.override_weights:
            self.config.custom_weights = CompositeWeights(
                chat_burst_weight=self.weight_sliders['chat_burst_weight'].value() / 100,
                acoustic_weight=self.weight_sliders['acoustic_weight'].value() / 100,
                semantic_weight=self.weight_sliders['semantic_weight'].value() / 100,
                prompt_boost_weight=self.weight_sliders['prompt_boost_weight'].value() / 100,
            )

        # Language switch updates Whisper + spaCy
        self.config.language = "pl" if self.language_combo.currentIndex() == 0 else "en"
        self.config.asr.language = self.config.language
        self.config.features.spacy_model = "pl_core_news_lg" if self.config.language == "pl" else "en_core_web_sm"
        
        # Smart Splitter settings (NOWE!)
        if hasattr(self.config, 'splitter'):
            self.config.splitter.enabled = bool(self.splitter_enabled.isChecked())
            self.config.splitter.min_duration_for_split = float(self.splitter_min_duration.value())
            self.config.splitter.premiere_hour = int(self.premiere_time.time().hour())
            self.config.splitter.premiere_minute = int(self.premiere_time.time().minute())
            self.config.splitter.first_premiere_days_offset = int(self.premiere_offset.value())
            self.config.splitter.use_politicians_in_titles = bool(self.use_politicians.isChecked())
        
        # YouTube settings (ROZSZERZONE!)
        if hasattr(self.config, 'youtube'):
            self.config.youtube.enabled = bool(self.youtube_upload.isChecked())
            self.config.youtube.schedule_as_premiere = bool(self.youtube_premiere.isChecked())
            
            privacy_map = {0: "unlisted", 1: "private", 2: "public"}
            self.config.youtube.privacy_status = privacy_map.get(
                self.youtube_privacy.currentIndex(), "unlisted"
            )
            
            if self.youtube_creds.text():
                self.config.youtube.credentials_path = Path(self.youtube_creds.text())
        
        # Advanced settings
        self.config.output_dir = Path(self.output_dir.text())
        self.config.keep_intermediate = bool(self.keep_intermediate.isChecked())
        
        # Ensure paths exist
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
    
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
        logging.getLogger("app").log(getattr(logging, level, logging.INFO), message)
    
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