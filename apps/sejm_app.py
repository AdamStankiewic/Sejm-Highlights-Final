"""
Sejm Highlights App - Political content UI
Part of Highlights AI Platform

Usage:
    python -m apps.sejm_app
    or
    python apps/sejm_app.py
"""
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QProgressBar, QTextEdit,
    QSpinBox, QDoubleSpinBox, QGroupBox, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from modules.politics.pipeline import PoliticsPipeline
from modules.politics.config import PoliticsConfig


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


class SejmHighlightsApp(QMainWindow):
    """Main application window for Sejm Highlights"""

    def __init__(self):
        super().__init__()
        self.config = PoliticsConfig()
        self.pipeline = None
        self.processing_thread = None
        self.input_file = None

        self.init_ui()

    def init_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("Sejm Highlights AI v2.0 - Modular Edition")
        self.setMinimumSize(800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # Title
        title = QLabel("Sejm Highlights AI")
        title.setStyleSheet("font-size: 24px; font-weight: bold; margin: 10px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Automatyczne wycinanie najciekawszych momentow z debat sejmowych")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        # File selection
        file_group = QGroupBox("Plik wejsciowy")
        file_layout = QHBoxLayout(file_group)

        self.file_label = QLabel("Nie wybrano pliku")
        file_layout.addWidget(self.file_label, stretch=1)

        self.file_btn = QPushButton("Wybierz video")
        self.file_btn.clicked.connect(self.select_file)
        file_layout.addWidget(self.file_btn)

        layout.addWidget(file_group)

        # Settings
        settings_group = QGroupBox("Ustawienia")
        settings_layout = QVBoxLayout(settings_group)

        # Target duration
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Docelowa dlugosc (min):"))
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(5, 60)
        self.duration_spin.setValue(15)
        duration_layout.addWidget(self.duration_spin)
        duration_layout.addStretch()
        settings_layout.addLayout(duration_layout)

        # GPT scoring
        self.gpt_check = QCheckBox("Uzyj GPT do analizy semantycznej")
        self.gpt_check.setChecked(True)
        settings_layout.addWidget(self.gpt_check)

        layout.addWidget(settings_group)

        # Progress
        progress_group = QGroupBox("Postep")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_bar = QProgressBar()
        progress_layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Gotowy")
        progress_layout.addWidget(self.status_label)

        layout.addWidget(progress_group)

        # Log
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        log_layout.addWidget(self.log_text)

        layout.addWidget(log_group)

        # Buttons
        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.start_processing)
        self.start_btn.setEnabled(False)
        self.start_btn.setStyleSheet("font-size: 16px; padding: 10px;")
        btn_layout.addWidget(self.start_btn)

        self.cancel_btn = QPushButton("Anuluj")
        self.cancel_btn.clicked.connect(self.cancel_processing)
        self.cancel_btn.setEnabled(False)
        btn_layout.addWidget(self.cancel_btn)

        layout.addLayout(btn_layout)

        # Stretch
        layout.addStretch()

    def select_file(self):
        """Select input video file"""
        file, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz plik video",
            "",
            "Video Files (*.mp4 *.mkv *.avi *.mov *.webm)"
        )

        if file:
            self.input_file = file
            self.file_label.setText(Path(file).name)
            self.start_btn.setEnabled(True)
            self.log("Wybrano plik: " + Path(file).name)

    def start_processing(self):
        """Start processing pipeline"""
        if not self.input_file:
            return

        # Update config from UI
        self.config.target_duration = self.duration_spin.value() * 60
        self.config.use_gpt_scoring = self.gpt_check.isChecked()

        # Create pipeline
        self.pipeline = PoliticsPipeline(self.config)

        # Output directory
        input_path = Path(self.input_file)
        output_dir = input_path.parent / f"{input_path.stem}_highlights"
        output_dir.mkdir(exist_ok=True)

        # Start processing thread
        self.processing_thread = ProcessingThread(
            self.pipeline,
            self.input_file,
            str(output_dir)
        )
        self.processing_thread.progress.connect(self.on_progress)
        self.processing_thread.finished.connect(self.on_finished)
        self.processing_thread.error.connect(self.on_error)
        self.processing_thread.start()

        # Update UI
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.file_btn.setEnabled(False)
        self.log("Rozpoczeto przetwarzanie...")

    def cancel_processing(self):
        """Cancel processing"""
        if self.pipeline:
            self.pipeline.cancel()
            self.log("Anulowanie...")

    def on_progress(self, progress: float, message: str):
        """Update progress bar"""
        self.progress_bar.setValue(int(progress * 100))
        self.status_label.setText(message)

    def on_finished(self, result: dict):
        """Processing finished"""
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.file_btn.setEnabled(True)
        self.progress_bar.setValue(100)

        if result.get('cancelled'):
            self.status_label.setText("Anulowano")
            self.log("Przetwarzanie anulowane")
        else:
            self.status_label.setText("Zakonczone!")
            num_clips = result.get('num_clips', 0)
            self.log(f"Zakonczone! Wybrano {num_clips} klipow")

    def on_error(self, error: str):
        """Handle error"""
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.file_btn.setEnabled(True)
        self.status_label.setText("Blad!")
        self.log(f"BLAD: {error}")

    def log(self, message: str):
        """Add message to log"""
        self.log_text.append(message)


def main():
    """Main entry point"""
    app = QApplication(sys.argv)
    window = SejmHighlightsApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
