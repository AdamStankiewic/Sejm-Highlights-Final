"""
Stream Highlights App - Streaming content UI
Part of Highlights AI Platform

Usage:
    python -m apps.stream_app
    or
    python apps/stream_app.py
"""
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QProgressBar, QTextEdit,
    QSpinBox, QGroupBox, QComboBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from modules.streaming.pipeline import StreamingPipeline
from modules.streaming.config import StreamingConfig


class ProcessingThread(QThread):
    """Background thread for processing"""
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, pipeline, input_file, output_dir):
        super().__init__()
        self.pipeline = pipeline
        self.input_file = input_file
        self.output_dir = output_dir

    def run(self):
        try:
            self.pipeline.set_progress_callback(
                lambda p, m: self.progress.emit(p, m)
            )
            result = self.pipeline.process(self.input_file, self.output_dir)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class StreamHighlightsApp(QMainWindow):
    """Main application window for Stream Highlights"""

    def __init__(self):
        super().__init__()
        self.config = StreamingConfig()
        self.pipeline = None
        self.processing_thread = None
        self.vod_file = None
        self.chat_file = None

        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Stream Highlights AI v1.0")
        self.setMinimumSize(700, 500)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Title
        title = QLabel("Stream Highlights AI")
        title.setStyleSheet("font-size: 24px; font-weight: bold; margin: 10px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Automatyczne wycinanie najlepszych momentow z VOD na podstawie aktywnosci czatu")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        # VOD selection
        vod_group = QGroupBox("VOD (Video)")
        vod_layout = QHBoxLayout(vod_group)

        self.vod_label = QLabel("Nie wybrano pliku VOD")
        vod_layout.addWidget(self.vod_label, stretch=1)

        self.vod_btn = QPushButton("Wybierz VOD")
        self.vod_btn.clicked.connect(self.select_vod)
        vod_layout.addWidget(self.vod_btn)

        layout.addWidget(vod_group)

        # Chat selection
        chat_group = QGroupBox("Chat (JSON)")
        chat_layout = QVBoxLayout(chat_group)

        chat_row = QHBoxLayout()
        self.chat_label = QLabel("Nie wybrano pliku czatu")
        chat_row.addWidget(self.chat_label, stretch=1)

        self.chat_btn = QPushButton("Wybierz chat JSON")
        self.chat_btn.clicked.connect(self.select_chat)
        chat_row.addWidget(self.chat_btn)
        chat_layout.addLayout(chat_row)

        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("Format:"))
        self.format_combo = QComboBox()
        self.format_combo.addItems(["Twitch (TwitchDownloader)", "YouTube Live Chat"])
        format_row.addWidget(self.format_combo)
        format_row.addStretch()
        chat_layout.addLayout(format_row)

        # Chat stats
        self.chat_stats_label = QLabel("")
        chat_layout.addWidget(self.chat_stats_label)

        # Preview spikes button
        preview_row = QHBoxLayout()
        self.preview_btn = QPushButton("Preview Chat Spikes")
        self.preview_btn.clicked.connect(self.preview_chat_spikes)
        self.preview_btn.setEnabled(False)
        preview_row.addWidget(self.preview_btn)
        preview_row.addStretch()
        chat_layout.addLayout(preview_row)

        layout.addWidget(chat_group)

        # Settings
        settings_group = QGroupBox("Ustawienia")
        settings_layout = QHBoxLayout(settings_group)

        settings_layout.addWidget(QLabel("Docelowa dlugosc (min):"))
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 30)
        self.duration_spin.setValue(10)
        settings_layout.addWidget(self.duration_spin)

        settings_layout.addWidget(QLabel("Max klipow:"))
        self.clips_spin = QSpinBox()
        self.clips_spin.setRange(5, 50)
        self.clips_spin.setValue(20)
        settings_layout.addWidget(self.clips_spin)

        settings_layout.addStretch()

        layout.addWidget(settings_group)

        # Progress
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Gotowy - wybierz VOD i plik czatu")
        layout.addWidget(self.status_label)

        # Log (bigger for more info)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(200)
        self.log_text.setStyleSheet("font-family: monospace; font-size: 11px;")
        layout.addWidget(self.log_text)

        # Buttons
        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton("Generuj Highlights")
        self.start_btn.clicked.connect(self.start_processing)
        self.start_btn.setEnabled(False)
        self.start_btn.setStyleSheet("font-size: 16px; padding: 10px;")
        btn_layout.addWidget(self.start_btn)

        self.cancel_btn = QPushButton("Anuluj")
        self.cancel_btn.clicked.connect(self.cancel_processing)
        self.cancel_btn.setEnabled(False)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

    def select_vod(self):
        """Select VOD file"""
        file, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz VOD",
            "",
            "Video Files (*.mp4 *.mkv *.avi *.mov *.webm *.ts)"
        )

        if file:
            self.vod_file = file
            self.vod_label.setText(Path(file).name)
            self.log(f"VOD: {Path(file).name}")
            self._check_ready()

    def select_chat(self):
        """Select chat JSON file"""
        file, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz plik czatu",
            "",
            "JSON Files (*.json)"
        )

        if file:
            self.chat_file = file
            self.chat_label.setText(Path(file).name)
            self.log(f"Chat: {Path(file).name}")

            # Try to load and show stats
            try:
                format_type = "twitch" if self.format_combo.currentIndex() == 0 else "youtube"
                pipeline = StreamingPipeline(self.config)
                count = pipeline.load_chat_from_file(file, format_type)
                stats = pipeline.get_chat_stats()

                self.chat_stats_label.setText(
                    f"Zaladowano {count:,} wiadomosci | "
                    f"{stats.get('unique_users', 0):,} uzytkownikow | "
                    f"{stats.get('messages_per_minute', 0):.1f} msg/min"
                )
                self.log(f"Chat zaladowany: {count} wiadomosci")

                # Store pipeline for preview
                self._chat_pipeline = pipeline
                self.preview_btn.setEnabled(True)

            except Exception as e:
                self.chat_stats_label.setText(f"Blad ladowania: {e}")
                self.log(f"Blad: {e}")

            self._check_ready()

    def _check_ready(self):
        """Check if ready to process"""
        if self.vod_file and self.chat_file:
            self.start_btn.setEnabled(True)

    def start_processing(self):
        """Start processing"""
        if not self.vod_file:
            return

        # Update config
        self.config.target_duration = self.duration_spin.value() * 60
        self.config.max_clips = self.clips_spin.value()

        # Create pipeline with chat
        self.pipeline = StreamingPipeline(self.config)

        if self.chat_file:
            format_type = "twitch" if self.format_combo.currentIndex() == 0 else "youtube"
            self.pipeline.load_chat_from_file(self.chat_file, format_type)

        # Output directory
        vod_path = Path(self.vod_file)
        output_dir = vod_path.parent / f"{vod_path.stem}_highlights"
        output_dir.mkdir(exist_ok=True)

        # Start thread
        self.processing_thread = ProcessingThread(
            self.pipeline,
            self.vod_file,
            str(output_dir)
        )
        self.processing_thread.progress.connect(self.on_progress)
        self.processing_thread.finished.connect(self.on_finished)
        self.processing_thread.error.connect(self.on_error)
        self.processing_thread.start()

        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.log("Rozpoczeto przetwarzanie...")

    def cancel_processing(self):
        """Cancel processing"""
        if self.pipeline:
            self.pipeline.cancel()
            self.log("Anulowanie...")

    def on_progress(self, progress: float, message: str):
        """Update progress"""
        self.progress_bar.setValue(int(progress * 100))
        self.status_label.setText(message)

    def on_finished(self, result: dict):
        """Processing finished"""
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setValue(100)

        if result.get('cancelled'):
            self.status_label.setText("Anulowano")
        else:
            num_clips = result.get('num_clips', 0)
            self.status_label.setText(f"Zakonczone! Wybrano {num_clips} klipow")
            self.log(f"Gotowe! {num_clips} klipow do eksportu")

    def on_error(self, error: str):
        """Handle error"""
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.status_label.setText("Blad!")
        self.log(f"BLAD: {error}")

    def log(self, message: str):
        """Add to log"""
        self.log_text.append(message)

    def preview_chat_spikes(self):
        """Preview top chat activity moments"""
        if not hasattr(self, '_chat_pipeline') or not self._chat_pipeline.scorer:
            self.log("Najpierw zaladuj chat!")
            return

        self.log("\n=== TOP CHAT SPIKES ===")

        spikes = self._chat_pipeline.scorer.get_top_chat_spikes(top_n=15)

        if not spikes:
            self.log("Nie znaleziono spike'ow (za malo danych)")
            return

        for i, spike in enumerate(spikes, 1):
            self.log(
                f"{i:2d}. {spike['timestamp_str']} | "
                f"activity={spike['activity']:.0f} msg | "
                f"emotes={spike['emotes']}"
            )

        self.log("======================\n")
        self.log("Te timestampy maja najwieksza aktywnosc czatu")
        self.log("Mozesz sprawdzic VOD w tych momentach")


def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    window = StreamHighlightsApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
