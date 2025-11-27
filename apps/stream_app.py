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

# Pipeline imports
from pipeline.processor import PipelineProcessor
from pipeline.config import Config

# Streaming module imports
from modules.streaming import create_scorer_from_chat, ChatAnalyzer
from modules.streaming.context_detector import (
    parse_stream_context, ContentType, Language, format_context_summary
)


class StreamingProcessingThread(QThread):
    """Worker thread for streaming video processing"""

    # Signals
    progress_updated = pyqtSignal(int, str)  # (percent, message)
    stage_completed = pyqtSignal(str, dict)  # (stage_name, stats)
    log_message = pyqtSignal(str, str)  # (level, message)
    processing_completed = pyqtSignal(dict)  # (results)
    processing_failed = pyqtSignal(str)  # (error_message)

    def __init__(
        self,
        input_file: str,
        config: Config,
        chat_data: dict = None,
        chat_path: str = None,
        language: str = "pl",
        stream_context: dict = None
    ):
        super().__init__()
        self.input_file = input_file
        self.config = config
        self.chat_data = chat_data
        self.chat_path = chat_path
        self.language = language
        self.stream_context = stream_context or {}
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
                    delay_offset = self.config.streaming.get('chat_delay_offset', 10.0)

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

            # Override language from GUI
            if self.language:
                self.config.asr.language = self.language
                self.log_message.emit("INFO", f"🌍 ASR Language: {Language.get_name(self.language)} ({self.language})")

            # Initialize processor
            self.processor = PipelineProcessor(self.config)

            # Set stream context on export stage for context-aware titles
            if self.stream_context:
                self.processor.stages['export'].stream_context = self.stream_context
                self.log_message.emit("INFO", "📋 Context-aware title generation enabled")

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

        # Stream context (language + content)
        self.language = Language.POLISH  # Default
        self.streamer_name = ""
        self.content_type = ContentType.VARIETY
        self.activity = ""
        self.stream_title = ""

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

        # === LANGUAGE SELECTION ===
        lang_group = QGroupBox("🌍 Język / Language")
        lang_layout = QVBoxLayout()

        lang_info = QLabel("Wybierz język dla: transkrypcji, tytułów, opisów")
        lang_info.setStyleSheet("color: #666; font-size: 9pt; margin-bottom: 5px;")
        lang_layout.addWidget(lang_info)

        # Language buttons layout
        lang_buttons = QHBoxLayout()

        self.lang_pl = QPushButton("🇵🇱 Polski")
        self.lang_pl.setCheckable(True)
        self.lang_pl.setChecked(True)
        self.lang_pl.clicked.connect(lambda: self.set_language(Language.POLISH))
        self.lang_pl.setStyleSheet("""
            QPushButton {
                padding: 10px;
                font-weight: bold;
                border: 2px solid #9146FF;
                border-radius: 5px;
            }
            QPushButton:checked {
                background-color: #9146FF;
                color: white;
            }
        """)
        lang_buttons.addWidget(self.lang_pl)

        self.lang_en = QPushButton("🇬🇧 English")
        self.lang_en.setCheckable(True)
        self.lang_en.clicked.connect(lambda: self.set_language(Language.ENGLISH))
        self.lang_en.setStyleSheet("""
            QPushButton {
                padding: 10px;
                font-weight: bold;
                border: 2px solid #9146FF;
                border-radius: 5px;
            }
            QPushButton:checked {
                background-color: #9146FF;
                color: white;
            }
        """)
        lang_buttons.addWidget(self.lang_en)

        self.lang_de = QPushButton("🇩🇪 Deutsch")
        self.lang_de.setCheckable(True)
        self.lang_de.clicked.connect(lambda: self.set_language(Language.GERMAN))
        self.lang_de.setStyleSheet("""
            QPushButton {
                padding: 10px;
                font-weight: bold;
                border: 2px solid #9146FF;
                border-radius: 5px;
            }
            QPushButton:checked {
                background-color: #9146FF;
                color: white;
            }
        """)
        lang_buttons.addWidget(self.lang_de)

        lang_layout.addLayout(lang_buttons)
        lang_group.setLayout(lang_layout)
        layout.addWidget(lang_group)

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

        # === CONTENT CONTEXT ===
        context_group = QGroupBox("🎮 Kontekst Contentu")
        context_layout = QVBoxLayout()

        # Streamer name
        streamer_layout = QHBoxLayout()
        streamer_layout.addWidget(QLabel("Streamer:"))
        self.streamer_field = QLineEdit()
        self.streamer_field.setPlaceholderText("np. Gucio, LVNDMARK, xQc (auto-detect z pliku)")
        self.streamer_field.textChanged.connect(lambda text: setattr(self, 'streamer_name', text))
        streamer_layout.addWidget(self.streamer_field)
        context_layout.addLayout(streamer_layout)

        # Content type
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Typ contentu:"))
        self.content_type_combo = QComboBox()
        self.content_type_combo.addItems([
            ContentType.GAMING,
            ContentType.IRL,
            ContentType.EVENT,
            ContentType.JUST_CHATTING,
            ContentType.VARIETY
        ])
        self.content_type_combo.setCurrentText(ContentType.VARIETY)
        self.content_type_combo.currentTextChanged.connect(lambda text: setattr(self, 'content_type', text))
        type_layout.addWidget(self.content_type_combo)
        type_layout.addStretch()
        context_layout.addLayout(type_layout)

        # Activity/Game
        activity_layout = QHBoxLayout()
        activity_layout.addWidget(QLabel("Aktywność/Gra:"))
        self.activity_field = QLineEdit()
        self.activity_field.setPlaceholderText("np. Tarkov, CS2, Mixed, IRL Warszawa (opcjonalne)")
        self.activity_field.textChanged.connect(lambda text: setattr(self, 'activity', text))
        activity_layout.addWidget(self.activity_field)
        context_layout.addLayout(activity_layout)

        # Stream title
        title_layout = QHBoxLayout()
        title_layout.addWidget(QLabel("Tytuł streamu:"))
        self.title_field = QLineEdit()
        self.title_field.setPlaceholderText("Tytuł z pliku (opcjonalne)")
        self.title_field.textChanged.connect(lambda text: setattr(self, 'stream_title', text))
        title_layout.addWidget(self.title_field)
        context_layout.addLayout(title_layout)

        # Context help
        context_help = QLabel(
            "💡 Pola wypełnią się automatycznie po wybraniu VOD. Możesz je edytować."
        )
        context_help.setStyleSheet("color: #FF9800; font-style: italic; font-size: 9pt; padding: 5px;")
        context_layout.addWidget(context_help)

        context_group.setLayout(context_layout)
        layout.addWidget(context_group)

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

    def set_language(self, lang_code: str):
        """Set language and update UI"""
        self.language = lang_code

        # Update button states
        self.lang_pl.setChecked(lang_code == Language.POLISH)
        self.lang_en.setChecked(lang_code == Language.ENGLISH)
        self.lang_de.setChecked(lang_code == Language.GERMAN)

        lang_name = Language.get_name(lang_code)
        self.log(f"Language set to: {lang_name} ({lang_code})", "INFO")

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

            # Auto-detect stream context
            context = parse_stream_context(file)

            # Update context fields
            self.streamer_field.setText(context['streamer'])
            self.content_type_combo.setCurrentText(context['content_type'])
            self.activity_field.setText(context['activity'])
            self.title_field.setText(context['stream_title'])

            # Update language if detected differently
            detected_lang = context['language']
            if detected_lang != self.language:
                self.set_language(detected_lang)

            # Log detected context
            self.log("📋 Auto-detected context:", "INFO")
            for line in format_context_summary(context).split('\n'):
                self.log(f"   {line}", "INFO")

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

            # DEBUG: Print to console
            print(f"🔍 DEBUG: Chat path set to: {self.chat_path}")

            # Parse chat (basic validation)
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    self.chat_data = json.load(f)

                self.log(f"Chat loaded: {len(self.chat_data)} messages", "INFO")
                print(f"🔍 DEBUG: Chat data type: {type(self.chat_data)}")

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
        """Start streaming highlight processing"""
        # Validate input
        if not self.vod_path:
            QMessageBox.warning(self, "Error", "Please select a VOD file!")
            return

        # Update config from GUI
        self.config.selection.max_clips = self.num_clips.value()
        self.config.selection.max_clip_duration = float(self.clip_duration.value())
        self.config.shorts.enabled = self.generate_shorts.isChecked()

        # Log configuration
        self.log(f"🎬 VOD: {Path(self.vod_path).name}", "INFO")

        # DEBUG: Print chat_path value
        print(f"🔍 DEBUG: start_processing() - chat_path = {self.chat_path}")
        print(f"🔍 DEBUG: start_processing() - chat_data = {type(self.chat_data) if self.chat_data else None}")

        if self.chat_path:
            self.log(f"💬 Chat: {Path(self.chat_path).name}", "INFO")
        else:
            self.log("⚠️ No chat file - using audio-only scoring", "WARNING")

        # Log language and content context
        self.log(f"🌍 Language: {Language.get_name(self.language)} ({self.language})", "INFO")
        self.log(f"🎮 Streamer: {self.streamer_name or 'Unknown'}", "INFO")
        self.log(f"📋 Content Type: {self.content_type}", "INFO")
        if self.activity:
            self.log(f"🎯 Activity: {self.activity}", "INFO")

        self.log(f"⚙️ Target clips: {self.num_clips.value()}", "INFO")
        self.log(f"⚙️ Clip duration: {self.clip_duration.value()}s", "INFO")

        # Prepare stream context dict
        stream_context = {
            'streamer': self.streamer_name,
            'content_type': self.content_type,
            'activity': self.activity,
            'stream_title': self.stream_title,
            'language': self.language
        }

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
            chat_path=self.chat_path,
            language=self.language,
            stream_context=stream_context
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
