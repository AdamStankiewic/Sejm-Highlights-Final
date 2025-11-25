"""
Sejm Highlights Desktop - Aplikacja GUI dla treści politycznych
Wersja: 2.0.0 - MODULAR EDITION
Python 3.11+ | PyQt6 | CUDA

Automatyczne generowanie najlepszych momentów z transmisji Sejmu
+ Inteligentny podział długich materiałów na części z auto-premiering
"""

import sys
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from video_downloader import VideoDownloader
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QTextEdit, QFileDialog,
    QGroupBox, QSpinBox, QDoubleSpinBox, QComboBox, QListWidget,
    QSplitter, QMessageBox, QTabWidget, QCheckBox, QLineEdit, QTimeEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QTime
from PyQt6.QtGui import QFont, QTextCursor, QPixmap

# Import pipeline modules
from pipeline.processor import PipelineProcessor
from pipeline.config import Config


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
        
        self.init_ui()
        self.setup_styles()
    
    def init_ui(self):
        """Inicjalizacja interfejsu użytkownika"""
        self.setWindowTitle("Sejm Highlights AI - Automated Video Compiler v2.0")
        self.setGeometry(100, 100, 1400, 950)  # Zwiększona wysokość
        
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
    
    def create_config_tabs(self) -> QTabWidget:
        """Zakładki z konfiguracją"""
        tabs = QTabWidget()

        # TAB 1: Output Settings
        tabs.addTab(self.create_output_tab(), "📊 Output")

        # TAB 2: Smart Splitter
        tabs.addTab(self.create_smart_splitter_tab(), "🤖 Smart Splitter")

        # TAB 3: Scoring & Selection (NOWY!)
        tabs.addTab(self.create_scoring_tab(), "🎯 Scoring & Selection")

        # TAB 4: Model Settings
        tabs.addTab(self.create_model_tab(), "🧠 AI Models")

        # TAB 5: Advanced
        tabs.addTab(self.create_advanced_tab(), "⚙️ Advanced")

        # TAB 6: YouTube
        tabs.addTab(self.create_youtube_tab(), "📺 YouTube")

        return tabs
    
    def create_output_tab(self) -> QWidget:
        """TAB 1: Output Settings"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Target duration
        dur_layout = QHBoxLayout()
        dur_layout.addWidget(QLabel("🎯 Docelowa długość filmu (sekundy):"))
        self.target_duration = QSpinBox()
        self.target_duration.setRange(600, 2400)  # 10-40 min
        self.target_duration.setValue(900)  # 15 min default
        self.target_duration.setSuffix(" s")
        dur_layout.addWidget(self.target_duration)
        dur_layout.addStretch()
        layout.addLayout(dur_layout)
        
        # Number of clips
        clips_layout = QHBoxLayout()
        clips_layout.addWidget(QLabel("📊 Liczba klipów:"))
        self.num_clips = QSpinBox()
        self.num_clips.setRange(5, 20)
        self.num_clips.setValue(12)
        clips_layout.addWidget(self.num_clips)
        clips_layout.addStretch()
        layout.addLayout(clips_layout)
        
        # Min/Max clip duration
        min_clip_layout = QHBoxLayout()
        min_clip_layout.addWidget(QLabel("⏱️ Min. długość klipu (s):"))
        self.min_clip_duration = QSpinBox()
        self.min_clip_duration.setRange(60, 180)
        self.min_clip_duration.setValue(90)
        min_clip_layout.addWidget(self.min_clip_duration)
        min_clip_layout.addStretch()
        layout.addLayout(min_clip_layout)
        
        max_clip_layout = QHBoxLayout()
        max_clip_layout.addWidget(QLabel("⏱️ Max. długość klipu (s):"))
        self.max_clip_duration = QSpinBox()
        self.max_clip_duration.setRange(90, 300)
        self.max_clip_duration.setValue(180)
        max_clip_layout.addWidget(self.max_clip_duration)
        max_clip_layout.addStretch()
        layout.addLayout(max_clip_layout)
        
        # Transitions & Hardsub
        self.add_transitions = QCheckBox("✨ Dodaj przejścia między klipami")
        self.add_transitions.setChecked(False)  # Domyślnie wyłączone - fontconfig issue
        layout.addWidget(self.add_transitions)
        
        self.add_hardsub = QCheckBox("📝 Dodaj napisy (hardsub)")
        self.add_hardsub.setChecked(False)
        layout.addWidget(self.add_hardsub)
        
        # === YouTube Shorts Settings ===
        layout.addSpacing(20)
        shorts_header = QLabel("📱 YouTube Shorts")
        shorts_header.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        layout.addWidget(shorts_header)
        
        self.shorts_enabled = QCheckBox("Generuj YouTube Shorts z najlepszych momentów")
        self.shorts_enabled.setChecked(False)
        self.shorts_enabled.setToolTip(
            "Automatycznie wybiera krótkie (15-60s) momenty i konwertuje do formatu 9:16 pionowego.\n"
            "Shorts używają tej samej analizy GPT co długi film - bez dodatkowych kosztów!"
        )
        layout.addWidget(self.shorts_enabled)
        
        shorts_count_layout = QHBoxLayout()
        shorts_count_layout.addWidget(QLabel("   📊 Liczba Shorts do wygenerowania:"))
        self.shorts_count = QSpinBox()
        self.shorts_count.setRange(5, 20)
        self.shorts_count.setValue(10)
        self.shorts_count.setSuffix(" Shorts")
        self.shorts_count.setEnabled(False)  # Disabled by default
        shorts_count_layout.addWidget(self.shorts_count)
        shorts_count_layout.addStretch()
        layout.addLayout(shorts_count_layout)
        
        # Connect checkbox to enable/disable spinner
        self.shorts_enabled.toggled.connect(self.shorts_count.setEnabled)
        
        shorts_info = QLabel(
            "   ℹ️ Shorts: 15-60s, format 9:16, duże napisy, automatyczne tytuły z emoji"
        )
        shorts_info.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(shorts_info)
        
        layout.addStretch()
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

    def create_scoring_tab(self) -> QWidget:
        """TAB 3: Scoring & Selection Settings (NOWY!)"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # === SEKCJA 1: Scoring Weights ===
        scoring_header = QLabel("⚖️ Scoring Weights")
        scoring_header.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(scoring_header)

        info = QLabel("Wagi wpływające na final score. Większa waga = większy wpływ na wybór klipów.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; padding: 5px; font-size: 9pt;")
        layout.addWidget(info)

        # Weight Semantic (GPT)
        semantic_layout = QHBoxLayout()
        semantic_label = QLabel("🤖 GPT Semantic:")
        semantic_label.setMinimumWidth(160)
        semantic_layout.addWidget(semantic_label)
        self.weight_semantic = QDoubleSpinBox()
        self.weight_semantic.setRange(0.0, 1.0)
        self.weight_semantic.setSingleStep(0.05)
        self.weight_semantic.setValue(0.70)  # Default from config
        self.weight_semantic.setDecimals(2)
        self.weight_semantic.setFixedWidth(80)
        semantic_layout.addWidget(self.weight_semantic)
        semantic_layout.addWidget(QLabel("(największy wpływ)"))
        semantic_layout.addStretch()
        layout.addLayout(semantic_layout)

        # Weight Acoustic
        acoustic_layout = QHBoxLayout()
        acoustic_label = QLabel("🔊 Acoustic (głośność):")
        acoustic_label.setMinimumWidth(160)
        acoustic_layout.addWidget(acoustic_label)
        self.weight_acoustic = QDoubleSpinBox()
        self.weight_acoustic.setRange(0.0, 1.0)
        self.weight_acoustic.setSingleStep(0.05)
        self.weight_acoustic.setValue(0.10)
        self.weight_acoustic.setDecimals(2)
        self.weight_acoustic.setFixedWidth(80)
        acoustic_layout.addWidget(self.weight_acoustic)
        acoustic_layout.addStretch()
        layout.addLayout(acoustic_layout)

        # Weight Keyword
        keyword_layout = QHBoxLayout()
        keyword_label = QLabel("🔑 Keywords:")
        keyword_label.setMinimumWidth(160)
        keyword_layout.addWidget(keyword_label)
        self.weight_keyword = QDoubleSpinBox()
        self.weight_keyword.setRange(0.0, 1.0)
        self.weight_keyword.setSingleStep(0.05)
        self.weight_keyword.setValue(0.10)
        self.weight_keyword.setDecimals(2)
        self.weight_keyword.setFixedWidth(80)
        keyword_layout.addWidget(self.weight_keyword)
        keyword_layout.addStretch()
        layout.addLayout(keyword_layout)

        # Weight Speaker Change
        speaker_layout = QHBoxLayout()
        speaker_label = QLabel("👥 Speaker Change:")
        speaker_label.setMinimumWidth(160)
        speaker_layout.addWidget(speaker_label)
        self.weight_speaker_change = QDoubleSpinBox()
        self.weight_speaker_change.setRange(0.0, 1.0)
        self.weight_speaker_change.setSingleStep(0.05)
        self.weight_speaker_change.setValue(0.10)
        self.weight_speaker_change.setDecimals(2)
        self.weight_speaker_change.setFixedWidth(80)
        speaker_layout.addWidget(self.weight_speaker_change)
        speaker_layout.addStretch()
        layout.addLayout(speaker_layout)

        # Sum info
        weights_sum_label = QLabel("💡 Suma wag powinna = 1.0")
        weights_sum_label.setStyleSheet("color: #2196F3; font-size: 9pt; padding: 5px;")
        layout.addWidget(weights_sum_label)

        layout.addSpacing(15)

        # === SEKCJA 2: Pre-filtering ===
        prefilter_header = QLabel("🔍 Pre-filtering")
        prefilter_header.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(prefilter_header)

        prefilter_info = QLabel(
            "Ile segmentów przejdzie do GPT scoring. Dla długich materiałów (>6h) zwiększ do 150-200."
        )
        prefilter_info.setWordWrap(True)
        prefilter_info.setStyleSheet("color: #666; padding: 5px; font-size: 9pt;")
        layout.addWidget(prefilter_info)

        # Prefilter top N
        prefilter_layout = QHBoxLayout()
        prefilter_label = QLabel("📊 Prefilter Top N:")
        prefilter_label.setMinimumWidth(160)
        prefilter_layout.addWidget(prefilter_label)
        self.prefilter_top_n = QSpinBox()
        self.prefilter_top_n.setRange(20, 300)
        self.prefilter_top_n.setSingleStep(10)
        self.prefilter_top_n.setValue(100)  # Default from config
        self.prefilter_top_n.setFixedWidth(80)
        prefilter_layout.addWidget(self.prefilter_top_n)
        prefilter_layout.addWidget(QLabel("segmentów"))
        prefilter_layout.addStretch()
        layout.addLayout(prefilter_layout)

        layout.addSpacing(15)

        # === SEKCJA 3: Selection Advanced ===
        selection_header = QLabel("⚙️ Selection Advanced")
        selection_header.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(selection_header)

        # Min time gap
        gap_layout = QHBoxLayout()
        gap_label = QLabel("⏱️ Min gap między klipami:")
        gap_label.setMinimumWidth(200)
        gap_layout.addWidget(gap_label)
        self.min_time_gap = QSpinBox()
        self.min_time_gap.setRange(0, 60)
        self.min_time_gap.setValue(20)  # Default
        self.min_time_gap.setSuffix(" s")
        self.min_time_gap.setFixedWidth(80)
        gap_layout.addWidget(self.min_time_gap)
        gap_layout.addStretch()
        layout.addLayout(gap_layout)

        # Smart merge gap
        merge_layout = QHBoxLayout()
        merge_label = QLabel("🔗 Smart merge gap:")
        merge_label.setMinimumWidth(200)
        merge_layout.addWidget(merge_label)
        self.smart_merge_gap = QDoubleSpinBox()
        self.smart_merge_gap.setRange(0.0, 30.0)
        self.smart_merge_gap.setValue(5.0)
        self.smart_merge_gap.setSuffix(" s")
        self.smart_merge_gap.setFixedWidth(80)
        merge_layout.addWidget(self.smart_merge_gap)
        merge_layout.addWidget(QLabel("(łączy bliskie klipy)"))
        merge_layout.addStretch()
        layout.addLayout(merge_layout)

        # Position bins
        bins_layout = QHBoxLayout()
        bins_label = QLabel("📦 Position bins:")
        bins_label.setMinimumWidth(200)
        bins_layout.addWidget(bins_label)
        self.position_bins = QSpinBox()
        self.position_bins.setRange(3, 10)
        self.position_bins.setValue(5)
        self.position_bins.setFixedWidth(80)
        bins_layout.addWidget(self.position_bins)
        bins_layout.addWidget(QLabel("(równomierne pokrycie)"))
        bins_layout.addStretch()
        layout.addLayout(bins_layout)

        # Max clips per bin
        max_per_bin_layout = QHBoxLayout()
        max_per_bin_label = QLabel("📊 Max clips per bin:")
        max_per_bin_label.setMinimumWidth(200)
        max_per_bin_layout.addWidget(max_per_bin_label)
        self.max_clips_per_bin = QSpinBox()
        self.max_clips_per_bin.setRange(2, 10)
        self.max_clips_per_bin.setValue(5)
        self.max_clips_per_bin.setFixedWidth(80)
        max_per_bin_layout.addWidget(self.max_clips_per_bin)
        max_per_bin_layout.addStretch()
        layout.addLayout(max_per_bin_layout)

        layout.addStretch()
        return tab

    def create_model_tab(self) -> QWidget:
        """TAB 4: Model Settings"""
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
        
        self.cancel_btn = QPushButton("⏹️ Cancel")
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
        self.log(f"Config - Target duration: {self.config.selection.target_total_duration}s", "INFO")
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
    
    def update_config_from_gui(self):
        """Aktualizuj obiekt Config wartościami z GUI"""
        # Selection settings
        self.config.selection.target_total_duration = float(self.target_duration.value())
        self.config.selection.max_clips = int(self.num_clips.value())
        self.config.selection.min_clip_duration = float(self.min_clip_duration.value())
        self.config.selection.max_clip_duration = float(self.max_clip_duration.value())

        # Selection Advanced (NOWE!)
        if hasattr(self, 'min_time_gap'):
            self.config.selection.min_time_gap = float(self.min_time_gap.value())
        if hasattr(self, 'smart_merge_gap'):
            self.config.selection.smart_merge_gap = float(self.smart_merge_gap.value())
        if hasattr(self, 'position_bins'):
            self.config.selection.position_bins = int(self.position_bins.value())
        if hasattr(self, 'max_clips_per_bin'):
            self.config.selection.max_clips_per_bin = int(self.max_clips_per_bin.value())

        # Scoring Weights (NOWE!)
        if hasattr(self, 'weight_semantic'):
            self.config.scoring.weight_semantic = float(self.weight_semantic.value())
        if hasattr(self, 'weight_acoustic'):
            self.config.scoring.weight_acoustic = float(self.weight_acoustic.value())
        if hasattr(self, 'weight_keyword'):
            self.config.scoring.weight_keyword = float(self.weight_keyword.value())
        if hasattr(self, 'weight_speaker_change'):
            self.config.scoring.weight_speaker_change = float(self.weight_speaker_change.value())

        # Scoring Pre-filter (NOWE!)
        if hasattr(self, 'prefilter_top_n'):
            self.config.scoring.prefilter_top_n = int(self.prefilter_top_n.value())

        # Export settings
        self.config.export.add_transitions = bool(self.add_transitions.isChecked())
        self.config.export.generate_hardsub = bool(self.add_hardsub.isChecked())
        
        # Shorts settings
        if hasattr(self.config, 'shorts'):
            self.config.shorts.enabled = bool(self.shorts_enabled.isChecked())
            self.config.shorts.max_shorts_count = int(self.shorts_count.value())
        
        # Whisper model
        whisper_idx = self.whisper_model.currentIndex()
        whisper_map = {0: "large-v3", 1: "medium", 2: "small"}
        self.config.asr.model = whisper_map.get(whisper_idx, "medium")
        
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