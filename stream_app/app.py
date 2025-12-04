"""
Stream Highlights AI - Aplikacja GUI dla streamów
Wersja: 1.2.1 - CHAT-BASED SCORING WITH DELAY OFFSET
Python 3.11+ | PyQt6 | CUDA

Automatyczne generowanie najlepszych momentów ze streamów Twitch/YouTube/Kick
Bazuje na aktywności czatu, emote spamie i reakcjach widzów

v1.2: Chat scoring replaces GPT - real streaming highlights!
v1.2.1: Added delay offset - accounts for stream delay (action before chat reaction)
"""

import sys
import json
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QTextEdit, QFileDialog,
    QGroupBox, QSpinBox, QDoubleSpinBox, QComboBox,
    QMessageBox, QTabWidget, QCheckBox, QLineEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

# Pipeline imports
from pipeline.processor import PipelineProcessor
from pipeline.config import Config

# Streaming module imports
from modules.streaming import create_scorer_from_chat, ChatAnalyzer


class StreamingProcessingThread(QThread):
    """Worker thread for streaming video processing"""

    # Signals
    progress_updated = pyqtSignal(int, str)  # (percent, message)
    stage_completed = pyqtSignal(str, dict)  # (stage_name, stats)
    log_message = pyqtSignal(str, str)  # (level, message)
    processing_completed = pyqtSignal(dict)  # (results)
    processing_failed = pyqtSignal(str)  # (error_message)

    def __init__(self, input_file: str, config: Config, chat_data: dict = None, chat_path: str = None):
        super().__init__()
        self.input_file = input_file
        self.config = config
        self.chat_data = chat_data
        self.chat_path = chat_path
        self.processor = None
        self.chat_scorer = None
        self._is_running = True

    def run(self):
        """Main processing loop with streaming scorer"""
        try:
            self.log_message.emit("INFO", f"🚀 Starting: {Path(self.input_file).name}")

            # Initialize chat scorer if chat provided
            if self.chat_path:
                try:
                    self.log_message.emit("INFO", "📊 Initializing chat analyzer...")

                    # Get delay offset from config (default: 10s)
                    delay_offset = self.config.streaming.chat_delay_offset

                    self.chat_scorer = create_scorer_from_chat(
                        chat_json_path=self.chat_path,
                        vod_duration=0,  # Will be updated after video inspection
                        chat_delay_offset=delay_offset
                    )

                    stats = self.chat_scorer.chat_analyzer.get_statistics()
                    self.log_message.emit("SUCCESS",
                        f"✅ Chat loaded: {stats['total_messages']} messages, "
                        f"{stats['unique_chatters']} chatters, "
                        f"baseline: {stats['baseline_msg_rate']:.2f} msg/s"
                    )
                    self.log_message.emit("INFO", f"📱 Platform: {stats['platform'].upper()}")
                    self.log_message.emit("INFO", f"⏱️ Delay offset: {delay_offset:.1f}s (accounts for stream delay)")

                except Exception as e:
                    self.log_message.emit("WARNING", f"⚠️ Chat analysis failed: {e}")
                    self.log_message.emit("INFO", "Falling back to audio-only scoring")
                    self.chat_scorer = None
            else:
                self.log_message.emit("INFO", "No chat file provided - using audio-only scoring")

            # Initialize processor
            self.processor = PipelineProcessor(self.config)

            # Progress callback
            def progress_callback(stage: str, percent: int, message: str):
                if self._is_running:
                    self.progress_updated.emit(percent, f"{stage}: {message}")
                    self.log_message.emit("INFO", f"[{stage}] {message}")

            self.processor.set_progress_callback(progress_callback)

            # OVERRIDE Stage 5: Use streaming scorer instead of GPT
            if self.chat_scorer:
                self.log_message.emit("INFO", "🎮 Using streaming chat-based scoring")
                from pipeline.stage_05_scoring_streaming import StreamingScoringStage
                self.processor.stages['scoring'] = StreamingScoringStage(
                    self.config,
                    chat_scorer=self.chat_scorer
                )
            else:
                self.log_message.emit("INFO", "🔊 Using audio-only scoring (no chat)")
                from pipeline.stage_05_scoring_streaming import StreamingScoringStage
                self.processor.stages['scoring'] = StreamingScoringStage(
                    self.config,
                    chat_scorer=None
                )

            # Run pipeline with custom scoring
            result = self.processor.process(self.input_file)

            if self._is_running:
                self.log_message.emit("SUCCESS", "✅ Processing completed!")
                self.processing_completed.emit(result)

        except Exception as e:
            if self._is_running:
                import traceback
                error_details = traceback.format_exc()
                self.log_message.emit("ERROR", f"❌ Error: {str(e)}")
                self.log_message.emit("ERROR", error_details)
                self.processing_failed.emit(str(e))

    def stop(self):
        """Stop processing"""
        self._is_running = False
        if self.processor:
            self.processor.cancel()


class StreamHighlightsApp(QMainWindow):
    """
    Aplikacja do generowania highlights ze streamów
    Chat-based scoring dla Twitch/YouTube/Kick
    """

    def __init__(self):
        super().__init__()

        # Config
        self.config = Config.load_default()
        self.vod_path = None
        self.chat_path = None
        self.chat_data = None

        # Processing thread
        self.processing_thread = None

        self.init_ui()

    def init_ui(self):
        """Initialize UI"""
        self.setWindowTitle("Stream Highlights AI v1.2 🎮")
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
        self.generate_shorts.stateChanged.connect(self._toggle_shorts_fields)
        settings_layout.addWidget(self.generate_shorts)

        # Shorts template selector
        template_layout = QHBoxLayout()
        template_layout.addWidget(QLabel("  📐 Szablon:"))
        self.shorts_template = QComboBox()
        self.shorts_template.addItems([
            "auto (wykryj automatycznie)",
            "classic_gaming (webcam dół)",
            "pip_modern (PIP w rogu)",
            "irl_fullface (zoom na twarz)",
            "simple (prosty crop)"
        ])
        self.shorts_template.setCurrentIndex(0)  # Default: auto
        self.shorts_template.setToolTip("Auto wykrywa layout na podstawie kamerki w streamie")
        template_layout.addWidget(self.shorts_template)
        template_layout.addStretch()
        settings_layout.addLayout(template_layout)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # === COPYRIGHT DETECTION ===
        copyright_group = QGroupBox("🎵 Copyright Detection (DMCA Protection)")
        copyright_layout = QVBoxLayout()

        # Info about .env API key
        env_info = QLabel("💡 API Key: Ustaw AUDD_API_KEY w pliku .env (raz i działa zawsze)")
        env_info.setStyleSheet("color: #666; font-style: italic; font-size: 9pt; margin-bottom: 5px;")
        copyright_layout.addWidget(env_info)

        # Enable copyright detection checkbox
        self.enable_copyright = QCheckBox("🛡️ Włącz wykrywanie muzyki chronionej")
        self.enable_copyright.setChecked(True)  # Default ON
        self.enable_copyright.stateChanged.connect(self._toggle_copyright_fields)
        copyright_layout.addWidget(self.enable_copyright)

        # Max music percentage slider
        music_threshold_layout = QHBoxLayout()
        music_threshold_layout.addWidget(QLabel("🎚️ Max muzyki:"))
        self.max_music_percentage = QSpinBox()
        self.max_music_percentage.setRange(0, 100)
        self.max_music_percentage.setValue(30)
        self.max_music_percentage.setSuffix("%")
        self.max_music_percentage.setToolTip("Klipy z >30% muzyki zostaną pominięte")
        music_threshold_layout.addWidget(self.max_music_percentage)
        music_threshold_layout.addWidget(QLabel("(pomiń jeśli więcej)"))
        music_threshold_layout.addStretch()
        copyright_layout.addLayout(music_threshold_layout)

        # Vocal isolation method selector
        method_layout = QHBoxLayout()
        method_layout.addWidget(QLabel("🔊 Vocal isolation:"))
        self.vocal_method = QComboBox()
        self.vocal_method.addItems([
            "highpass (usuwa <300Hz - bass/beat)",
            "bandpass (zachowuje 300-3400Hz - głos)"
        ])
        self.vocal_method.setCurrentIndex(0)  # Default: highpass
        method_layout.addWidget(self.vocal_method)
        method_layout.addStretch()
        copyright_layout.addLayout(method_layout)

        # Help text
        copyright_help = QLabel(
            "💡 Skanuje wybrane klipy i automatycznie usuwa muzykę w tle.\n"
            "   Workflow: Pre-scan → Vocal isolation (jeśli wykryto muzykę)"
        )
        copyright_help.setStyleSheet("color: #FF9800; font-style: italic; font-size: 9pt; padding: 5px;")
        copyright_help.setWordWrap(True)
        copyright_layout.addWidget(copyright_help)

        copyright_group.setLayout(copyright_layout)
        layout.addWidget(copyright_group)

        # === PROCESSING ===
        process_group = QGroupBox("🚀 Przetwarzanie")
        process_layout = QVBoxLayout()

        # Buttons layout
        buttons_layout = QHBoxLayout()

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
        buttons_layout.addWidget(self.start_btn)

        # Cancel button
        self.cancel_btn = QPushButton("⏹️ Anuluj")
        self.cancel_btn.clicked.connect(self.cancel_processing)
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #F44336;
                color: white;
                padding: 15px;
                font-size: 14pt;
                font-weight: bold;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #D32F2F;
            }
            QPushButton:disabled {
                background-color: #CCC;
            }
        """)
        buttons_layout.addWidget(self.cancel_btn)

        process_layout.addLayout(buttons_layout)

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

                # Note: chat_data might be a dict with 'comments' key (Twitch Downloader format)
                # The actual parsing is done in ChatAnalyzer
                if isinstance(self.chat_data, dict):
                    # Check for Twitch Downloader format
                    if 'comments' in self.chat_data:
                        msg_count = len(self.chat_data.get('comments', []))
                        self.log(f"Chat file loaded: {msg_count} messages", "INFO")
                    else:
                        self.log(f"Chat file loaded (format: dict with {len(self.chat_data)} keys)", "INFO")
                elif isinstance(self.chat_data, list):
                    self.log(f"Chat file loaded: {len(self.chat_data)} messages", "INFO")
                else:
                    self.log(f"Chat file loaded: {type(self.chat_data)}", "INFO")

            except Exception as e:
                self.log(f"Chat parse error: {e}", "ERROR")
                self.chat_label.setText(f"❌ Invalid JSON")
                self.chat_label.setStyleSheet("color: #F44336;")
                self.chat_data = None

    def _check_ready(self):
        """Enable process button when VOD is selected"""
        if self.vod_path:
            self.start_btn.setEnabled(True)

    def _toggle_shorts_fields(self, state):
        """Enable/disable shorts template selector based on checkbox"""
        enabled = state == Qt.CheckState.Checked.value
        self.shorts_template.setEnabled(enabled)

    def _toggle_copyright_fields(self, state):
        """Enable/disable copyright detection fields based on checkbox"""
        enabled = state == Qt.CheckState.Checked.value
        self.max_music_percentage.setEnabled(enabled)
        self.vocal_method.setEnabled(enabled)

    def start_processing(self):
        """Start streaming highlight processing"""
        # Validate input
        if not self.vod_path:
            QMessageBox.warning(self, "Error", "Please select a VOD file!")
            return

        # Update config from GUI
        self.config.selection.max_clips = self.num_clips.value()
        self.config.selection.max_clip_duration = float(self.clip_duration.value())
        self.config.shorts.enabled = self.generate_shorts.isChecked()

        # COPYRIGHT DETECTION SETTINGS (from GUI)
        # Note: API key is loaded from .env automatically in config.__post_init__
        if self.enable_copyright.isChecked() and self.config.streaming.audd_api_key:
            self.config.streaming.enable_copyright_detection = True
            self.config.streaming.max_music_percentage = self.max_music_percentage.value() / 100.0
            self.config.streaming.auto_vocal_isolation = True  # Always ON for streaming

            # Map GUI selection to config value
            method_text = self.vocal_method.currentText()
            if "bandpass" in method_text:
                self.config.streaming.vocal_isolation_method = "bandpass"
            else:
                self.config.streaming.vocal_isolation_method = "highpass"
        elif self.enable_copyright.isChecked() and not self.config.streaming.audd_api_key:
            # User wants copyright detection but no API key in .env
            self.log("⚠️ Copyright detection enabled but no AUDD_API_KEY in .env - DISABLED", "WARNING")
            self.config.streaming.enable_copyright_detection = False
        else:
            # User unchecked the checkbox
            self.config.streaming.enable_copyright_detection = False

        # STREAMING-SPECIFIC: Lower min_clip_duration for gaming streams
        # Gaming streamers speak in short bursts (15-40s), not long speeches like Sejm
        self.config.selection.min_clip_duration = 20.0  # Changed from 45s to 20s for streams

        # STREAMING-SPECIFIC: Optimize smart merge for streams
        # Merge closely related moments (e.g., reaction + outcome of game action)
        self.config.selection.smart_merge_gap = 8.0  # Increased from 5.0s to merge more aggressively
        self.config.selection.smart_merge_min_score = 0.45  # Lowered from 0.5 to merge more clips

        # Log configuration
        self.log(f"🎬 VOD: {Path(self.vod_path).name}", "INFO")

        if self.chat_path:
            self.log(f"💬 Chat: {Path(self.chat_path).name}", "INFO")
        else:
            self.log("⚠️ No chat file - using audio-only scoring", "WARNING")

        self.log(f"⚙️ Target clips: {self.num_clips.value()}", "INFO")
        self.log(f"⚙️ Clip duration: {self.clip_duration.value()}s", "INFO")

        # Log copyright detection settings
        if self.config.streaming.enable_copyright_detection:
            self.log("🛡️ Copyright detection: ENABLED", "SUCCESS")
            self.log(f"   Max music: {int(self.config.streaming.max_music_percentage * 100)}%", "INFO")
            self.log(f"   Vocal isolation: {self.config.streaming.vocal_isolation_method}", "INFO")
        else:
            self.log("🎵 Copyright detection: DISABLED", "INFO")

        # Disable controls
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)

        # Reset progress
        self.progress_bar.setValue(0)
        self.log_text.clear()

        # Create and start processing thread
        self.processing_thread = StreamingProcessingThread(
            input_file=self.vod_path,
            config=self.config,
            chat_data=self.chat_data,
            chat_path=self.chat_path
        )

        # Connect signals
        self.processing_thread.progress_updated.connect(self.on_progress_update)
        self.processing_thread.log_message.connect(self.log)
        self.processing_thread.processing_completed.connect(self.on_processing_completed)
        self.processing_thread.processing_failed.connect(self.on_processing_failed)

        # Start processing
        self.processing_thread.start()
        self.log("🚀 Processing started!", "SUCCESS")

    def cancel_processing(self):
        """Cancel ongoing processing"""
        if self.processing_thread and self.processing_thread.isRunning():
            self.log("⏹️ Cancelling...", "WARNING")
            self.processing_thread.stop()
            self.processing_thread.wait(5000)  # Wait 5s max

            self.start_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self.log("❌ Processing cancelled", "WARNING")

    def on_progress_update(self, percent: int, message: str):
        """Update progress bar and label"""
        self.progress_bar.setValue(percent)

    def on_processing_completed(self, result: dict):
        """Handle successful completion"""
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setValue(100)

        # Show results
        clips = result.get('clips', [])
        shorts = result.get('shorts', [])

        self.log(f"\n{'='*50}", "SUCCESS")
        self.log(f"✅ PROCESSING COMPLETE!", "SUCCESS")
        self.log(f"{'='*50}", "SUCCESS")
        self.log(f"📊 Generated {len(clips)} clips", "SUCCESS")
        if shorts:
            self.log(f"📱 Generated {len(shorts)} Shorts", "SUCCESS")

        # Show output folder
        if clips:
            output_dir = Path(clips[0]['file']).parent
            self.log(f"📁 Output: {output_dir}", "INFO")

            QMessageBox.information(
                self,
                "Success!",
                f"✅ Processing complete!\n\n"
                f"Generated:\n"
                f"• {len(clips)} clips\n"
                f"• {len(shorts)} Shorts\n\n"
                f"Output folder:\n{output_dir}"
            )

    def on_processing_failed(self, error: str):
        """Handle processing failure"""
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

        QMessageBox.critical(
            self,
            "Processing Failed",
            f"❌ Error during processing:\n\n{error}\n\n"
            f"Check the logs for details."
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
