# ============================================================================
# SNIPPET DO DODANIA W app.py
# Integracja pobierania video z URL (yt-dlp)
# ============================================================================

"""
INSTRUKCJA:
1. Dodaj ten kod na początku app.py (po importach)
2. Zmień metodę create_input_section() (patrz niżej)
3. Dodaj nowe metody (patrz niżej)
"""

# ============================================================================
# CZĘŚĆ 1: Dodaj do importów (górna część app.py, linia ~25)
# ============================================================================

# Dodaj ten import po istniejących importach:
from video_downloader import VideoDownloader


# ============================================================================
# CZĘŚĆ 2: Dodaj DownloadThread class (po ProcessingThread, linia ~78)
# ============================================================================

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


# ============================================================================
# CZĘŚĆ 3: Dodaj do __init__ klasy SejmHighlightsApp (linia ~87)
# ============================================================================

# Dodaj te linie w __init__ (po istniejących):
        self.download_thread = None
        self.downloaded_file_path = None


# ============================================================================
# CZĘŚĆ 4: ZASTĄP metodę create_input_section() (linia ~164)
# ============================================================================

def create_input_section(self) -> QGroupBox:
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


# ============================================================================
# CZĘŚĆ 5: Dodaj nowe metody (na końcu klasy SejmHighlightsApp, przed setup_styles)
# ============================================================================

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


# ============================================================================
# CZĘŚĆ 6: Zaktualizuj metodę start_processing() (linia ~728)
# ============================================================================

# Znajdź linię:
#     input_file = self.file_path_label.text()

# I ZASTĄP ją tym:
        # Get input file (either downloaded or selected locally)
        if self.downloaded_file_path:
            input_file = self.downloaded_file_path
        else:
            input_file = self.file_path_label.text()
        
        if not input_file or input_file == "Nie wybrano pliku":
            QMessageBox.warning(self, "Błąd", "Proszę wybrać plik wejściowy lub pobrać video z URL!")
            return


# ============================================================================
# KONIEC SNIPPETU
# ============================================================================

"""
PODSUMOWANIE ZMIAN:

1. Import VideoDownloader
2. Dodaj DownloadThread class
3. Dodaj self.download_thread i self.downloaded_file_path do __init__
4. Zastąp create_input_section() nową wersją z tabs
5. Dodaj 5 nowych metod:
   - download_from_url()
   - on_download_progress()
   - on_video_info()
   - on_download_complete()
   - on_download_failed()
   - format_duration()
6. Zaktualizuj start_processing() aby używał downloaded_file_path

TESTOWANIE:
1. python app.py
2. Przejdź do tab "Pobierz z URL"
3. Wklej: https://www.youtube.com/watch?v=dQw4w9WgXcQ
4. Kliknij "Pobierz i załaduj"
5. Poczekaj ~30 sekund
6. Kliknij "Start Processing"
"""
