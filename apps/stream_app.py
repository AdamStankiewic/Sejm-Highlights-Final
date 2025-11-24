"""
Stream Highlights AI - Aplikacja GUI dla streamów
Wersja: 1.0.0 - INITIAL RELEASE
Python 3.11+ | PyQt6 | CUDA

Automatyczne generowanie najlepszych momentów ze streamów Twitch/YouTube
Bazuje na aktywności czatu, emote spamie i reakcjach widzów
"""

import sys
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QTextEdit, QFileDialog,
    QGroupBox, QSpinBox, QDoubleSpinBox, QComboBox,
    QMessageBox, QTabWidget, QCheckBox, QLineEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

# Pipeline imports (currently using same pipeline, will be refactored)
from pipeline.processor import PipelineProcessor
from pipeline.config import Config


class StreamHighlightsApp(QMainWindow):
    """
    Aplikacja do generowania highlights ze streamów
    Uproszczona wersja - focus na UX dla streamerów
    """

    def __init__(self):
        super().__init__()

        # Config
        self.config = Config.load_default()
        self.vod_path = None
        self.chat_path = None
        self.chat_data = None

        self.init_ui()

    def init_ui(self):
        """Initialize UI"""
        self.setWindowTitle("Stream Highlights AI v1.0 🎮")
        self.setGeometry(100, 100, 900, 700)

        # Main widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # === HEADER ===
        header = QLabel("🎮 Stream Highlights Generator")
        header.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header.setStyleSheet("color: #9146FF; padding: 10px;")  # Twitch purple
        layout.addWidget(header)

        info = QLabel(
            "Automatycznie znajduje najlepsze momenty ze streamu bazując na:\n"
            "• Aktywności czatu (spam, KEKW, PogChamp)\n"
            "• Reakcjach emote\n"
            "• Głośności audio"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; padding: 5px; margin-bottom: 10px;")
        layout.addWidget(info)

        # === FILE SELECTION ===
        file_group = QGroupBox("📁 Pliki")
        file_layout = QVBoxLayout()

        # VOD file
        vod_layout = QHBoxLayout()
        self.vod_btn = QPushButton("📹 Wybierz Stream VOD")
        self.vod_btn.clicked.connect(self.select_vod)
        self.vod_btn.setStyleSheet("padding: 10px; font-weight: bold;")
        vod_layout.addWidget(self.vod_btn)

        self.vod_label = QLabel("Nie wybrano pliku")
        self.vod_label.setStyleSheet("color: #999;")
        vod_layout.addWidget(self.vod_label)
        file_layout.addLayout(vod_layout)

        # Chat file (optional)
        chat_layout = QHBoxLayout()
        self.chat_btn = QPushButton("💬 Wybierz Chat JSON (opcjonalne)")
        self.chat_btn.clicked.connect(self.select_chat)
        self.chat_btn.setStyleSheet("padding: 10px;")
        chat_layout.addWidget(self.chat_btn)

        self.chat_label = QLabel("Opcjonalne - zwiększa accuracy")
        self.chat_label.setStyleSheet("color: #999;")
        chat_layout.addWidget(self.chat_label)
        file_layout.addLayout(chat_layout)

        # Chat help
        chat_help = QLabel(
            "💡 Tip: Pobierz chat używając 'Twitch Downloader' lub 'yt-dlp --write-subs'"
        )
        chat_help.setStyleSheet("color: #FF9800; font-style: italic; font-size: 9pt; padding: 5px;")
        file_layout.addWidget(chat_help)

        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # === SETTINGS ===
        settings_group = QGroupBox("⚙️ Ustawienia")
        settings_layout = QVBoxLayout()

        # Target clips
        clips_layout = QHBoxLayout()
        clips_layout.addWidget(QLabel("🎯 Liczba klipów:"))
        self.num_clips = QSpinBox()
        self.num_clips.setRange(5, 30)
        self.num_clips.setValue(10)
        clips_layout.addWidget(self.num_clips)
        clips_layout.addWidget(QLabel("(najlepsze momenty)"))
        clips_layout.addStretch()
        settings_layout.addLayout(clips_layout)

        # Clip duration
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("⏱️ Długość klipu:"))
        self.clip_duration = QSpinBox()
        self.clip_duration.setRange(30, 180)
        self.clip_duration.setValue(60)
        self.clip_duration.setSuffix(" s")
        duration_layout.addWidget(self.clip_duration)
        duration_layout.addStretch()
        settings_layout.addLayout(duration_layout)

        # Shorts
        self.generate_shorts = QCheckBox("📱 Generuj też Shorts (9:16, max 60s)")
        self.generate_shorts.setChecked(True)
        settings_layout.addWidget(self.generate_shorts)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # === PROCESSING ===
        process_group = QGroupBox("🚀 Przetwarzanie")
        process_layout = QVBoxLayout()

        # Start button
        self.start_btn = QPushButton("▶️ Generuj Highlights")
        self.start_btn.clicked.connect(self.start_processing)
        self.start_btn.setEnabled(False)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #9146FF;
                color: white;
                padding: 15px;
                font-size: 14pt;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #772CE8;
            }
            QPushButton:disabled {
                background-color: #CCC;
            }
        """)
        process_layout.addWidget(self.start_btn)

        # Progress
        self.progress_bar = QProgressBar()
        process_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("Gotowy")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        process_layout.addWidget(self.progress_label)

        process_group.setLayout(process_layout)
        layout.addWidget(process_group)

        # === LOGS ===
        log_group = QGroupBox("📋 Logi")
        log_layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        self.log_text.setStyleSheet("font-family: 'Consolas', monospace; font-size: 9pt;")
        log_layout.addWidget(self.log_text)

        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        layout.addStretch()

    def select_vod(self):
        """Select stream VOD file"""
        file, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz Stream VOD",
            "",
            "Video Files (*.mp4 *.mkv *.flv *.mov);;All Files (*)"
        )

        if file:
            self.vod_path = file
            filename = Path(file).name
            self.vod_label.setText(f"✅ {filename}")
            self.vod_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
            self.log(f"VOD selected: {filename}", "INFO")
            self._check_ready()

    def select_chat(self):
        """Select chat JSON file (optional)"""
        file, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz Chat JSON",
            "",
            "JSON Files (*.json);;All Files (*)"
        )

        if file:
            self.chat_path = file
            filename = Path(file).name
            self.chat_label.setText(f"✅ {filename}")
            self.chat_label.setStyleSheet("color: #4CAF50; font-weight: bold;")

            # Parse chat (basic validation)
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    self.chat_data = json.load(f)

                self.log(f"Chat loaded: {len(self.chat_data)} messages", "INFO")

            except Exception as e:
                self.log(f"Chat parse error: {e}", "ERROR")
                self.chat_label.setText(f"❌ Invalid JSON")
                self.chat_label.setStyleSheet("color: #F44336;")
                self.chat_data = None

    def _check_ready(self):
        """Enable process button when VOD is selected"""
        if self.vod_path:
            self.start_btn.setEnabled(True)

    def start_processing(self):
        """Start processing (placeholder)"""
        self.log("🚀 Starting processing...", "INFO")
        self.log("⚠️ Streaming module not yet implemented - using Sejm pipeline", "WARNING")
        self.log("📌 TODO: Implement streaming scorer with chat analysis", "INFO")

        # Update config
        self.config.selection.max_clips = self.num_clips.value()
        self.config.selection.max_clip_duration = float(self.clip_duration.value())
        self.config.shorts.enabled = self.generate_shorts.isChecked()

        QMessageBox.information(
            self,
            "Coming Soon",
            "🚧 Streaming module is under development!\n\n"
            "Currently this app uses the same pipeline as Sejm app.\n"
            "Streaming-specific features (chat analysis, emote detection) "
            "will be added in v1.1.\n\n"
            "For now, use 'sejm_app.py' for processing."
        )

    def log(self, message: str, level: str = "INFO"):
        """Add log message"""
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Color by level
        colors = {
            "INFO": "#2196F3",
            "SUCCESS": "#4CAF50",
            "WARNING": "#FF9800",
            "ERROR": "#F44336"
        }
        color = colors.get(level, "#666")

        formatted = f'<span style="color: {color};">[{timestamp}] {level}: {message}</span>'
        self.log_text.append(formatted)


def main():
    """Main entry point"""
    app = QApplication(sys.argv)

    # Set app style
    app.setStyle("Fusion")

    window = StreamHighlightsApp()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
