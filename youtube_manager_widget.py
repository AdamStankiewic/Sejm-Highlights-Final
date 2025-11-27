"""
YouTube Manager Widget - Reusable component for multi-channel upload management
Can be used in both sejm_app.py and stream_app.py
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QComboBox, QLineEdit, QGroupBox, QCheckBox, QMessageBox
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal
from pathlib import Path
from typing import Optional

from pipeline.config import Config


class YouTubeManagerWidget(QWidget):
    """
    Reusable YouTube Manager Widget

    Features:
    - Profile selector (sejm/stream/custom)
    - Playlist management (main + shorts)
    - Upload Queue button
    - Profile info display
    - Refresh playlists from YouTube API

    Signals:
    - profile_changed(str) - emitted when profile selection changes
    """

    profile_changed = pyqtSignal(str)  # profile_name

    def __init__(self, config: Config, default_profile: str = "sejm", parent=None):
        """
        Initialize YouTube Manager Widget

        Args:
            config: Pipeline configuration
            default_profile: Default profile to select ("sejm" or "stream")
            parent: Parent widget
        """
        super().__init__(parent)
        self.config = config
        self.default_profile = default_profile

        self.init_ui()

    def init_ui(self):
        """Initialize UI components"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Main checkboxes
        self.youtube_upload = QCheckBox("📺 Upload do YouTube po zakończeniu")
        self.youtube_upload.setChecked(False)
        self.youtube_upload.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        layout.addWidget(self.youtube_upload)

        self.youtube_use_queue = QCheckBox("📋 Dodaj do kolejki zamiast natychmiastowego uploadu")
        self.youtube_use_queue.setChecked(False)
        self.youtube_use_queue.setToolTip(
            "Gdy włączone: filmy zostaną dodane do Upload Queue\n"
            "Gdy wyłączone: filmy będą uploaded natychmiast po przetworzeniu"
        )
        layout.addWidget(self.youtube_use_queue)

        layout.addSpacing(10)

        # Upload Profile Group
        profile_group = QGroupBox("🎯 Upload Profile (Multi-channel)")
        profile_layout = QVBoxLayout()

        # Profile selector (compact)
        profile_select_layout = QHBoxLayout()
        profile_label = QLabel("📋 Profil:")
        profile_label.setMinimumWidth(100)
        profile_select_layout.addWidget(profile_label)

        self.youtube_profile = QComboBox()
        self.youtube_profile.setMinimumWidth(150)

        # Load profiles from config
        profile_names = self.config.list_upload_profiles() if hasattr(self.config, 'list_upload_profiles') else []
        if profile_names:
            self.youtube_profile.addItems(profile_names)
            # Set default profile
            if self.default_profile in profile_names:
                self.youtube_profile.setCurrentText(self.default_profile)
        else:
            self.youtube_profile.addItems(["sejm", "stream"])
            self.youtube_profile.setCurrentText(self.default_profile)

        self.youtube_profile.currentIndexChanged.connect(self.on_profile_changed)
        profile_select_layout.addWidget(self.youtube_profile)
        profile_select_layout.addStretch()
        profile_layout.addLayout(profile_select_layout)

        # Profile info display (compact)
        self.profile_info_label = QLabel()
        self.profile_info_label.setStyleSheet(
            "color: #555; font-size: 8pt; padding: 6px; background: #f9f9f9; "
            "border-radius: 3px; border: 1px solid #e0e0e0;"
        )
        self.profile_info_label.setWordWrap(True)
        self.profile_info_label.setMaximumHeight(60)
        profile_layout.addWidget(self.profile_info_label)

        layout.addSpacing(5)

        # Playlist section (aligned labels)
        playlist_main_layout = QHBoxLayout()
        playlist_main_label = QLabel("📂 Main:")
        playlist_main_label.setMinimumWidth(100)
        playlist_main_layout.addWidget(playlist_main_label)
        self.youtube_main_playlist = QLineEdit()
        self.youtube_main_playlist.setPlaceholderText("Playlist ID (opcjonalne)")
        playlist_main_layout.addWidget(self.youtube_main_playlist)
        profile_layout.addLayout(playlist_main_layout)

        playlist_shorts_layout = QHBoxLayout()
        playlist_shorts_label = QLabel("📱 Shorts:")
        playlist_shorts_label.setMinimumWidth(100)
        playlist_shorts_layout.addWidget(playlist_shorts_label)
        self.youtube_shorts_playlist = QLineEdit()
        self.youtube_shorts_playlist.setPlaceholderText("Playlist ID (opcjonalne)")
        playlist_shorts_layout.addWidget(self.youtube_shorts_playlist)
        profile_layout.addLayout(playlist_shorts_layout)

        # Buttons row (both in one line)
        buttons_layout = QHBoxLayout()
        buttons_layout.addStretch()

        self.refresh_playlists_btn = QPushButton("🔄 Odśwież")
        self.refresh_playlists_btn.clicked.connect(self.refresh_playlists)
        self.refresh_playlists_btn.setEnabled(False)
        self.refresh_playlists_btn.setMaximumWidth(120)
        buttons_layout.addWidget(self.refresh_playlists_btn)

        buttons_layout.addSpacing(10)

        self.upload_queue_btn = QPushButton("📤 Upload Queue")
        self.upload_queue_btn.clicked.connect(self.open_upload_queue)
        self.upload_queue_btn.setStyleSheet(
            "padding: 8px 16px; font-weight: bold; background: #FF6B35; color: white; border-radius: 4px;"
        )
        self.upload_queue_btn.setMaximumWidth(150)
        buttons_layout.addWidget(self.upload_queue_btn)

        profile_layout.addLayout(buttons_layout)

        profile_group.setLayout(profile_layout)
        layout.addWidget(profile_group)

        # Update profile info on load
        self.on_profile_changed(0)

    def on_profile_changed(self, index: int):
        """Update profile info when profile selection changes"""
        try:
            profile_name = self.youtube_profile.currentText()
            profile = self.config.get_upload_profile(profile_name)

            if profile:
                # Display profile information
                info_text = (
                    f"📺 Kanał: {profile.name} | "
                    f"🆔 {profile.channel_id[:20]}... | "
                    f"🔑 {profile.token_file}\n"
                    f"📋 Main: {profile.main_videos.privacy_status} "
                    f"({'Premiere' if profile.main_videos.schedule_as_premiere else 'Direct'}) | "
                    f"📱 Shorts: {profile.shorts.privacy_status}"
                )
                self.profile_info_label.setText(info_text)

                # Update playlist fields from profile
                self.youtube_main_playlist.setText(profile.main_videos.playlist_id or "")
                self.youtube_shorts_playlist.setText(profile.shorts.playlist_id or "")

                # Enable refresh button
                self.refresh_playlists_btn.setEnabled(True)
            else:
                self.profile_info_label.setText(f"⚠️ Profil '{profile_name}' nie znaleziony w config.yml")
                self.refresh_playlists_btn.setEnabled(False)

            # Emit signal
            self.profile_changed.emit(profile_name)

        except Exception as e:
            self.profile_info_label.setText(f"❌ Błąd ładowania profilu: {str(e)}")
            self.refresh_playlists_btn.setEnabled(False)

    def refresh_playlists(self):
        """Refresh playlists from YouTube for selected profile"""
        try:
            profile_name = self.youtube_profile.currentText()

            # Import here to avoid circular imports
            from pipeline.stage_09_youtube import YouTubeStage

            # Create YouTube stage with selected profile
            youtube_stage = YouTubeStage(self.config, profile_name=profile_name)
            youtube_stage.authorize()

            # Get playlists
            if youtube_stage.playlist_manager:
                playlists = youtube_stage.playlist_manager.list_playlists()

                if playlists:
                    playlist_names = [f"{p['title']} ({p['id']})" for p in playlists[:10]]
                    playlist_info = "\n".join(playlist_names)
                    QMessageBox.information(
                        self,
                        f"Playlisty - {profile_name}",
                        f"Znaleziono {len(playlists)} playlist:\n\n{playlist_info}\n\n"
                        f"Możesz skopiować ID i wkleić w pole Playlist powyżej."
                    )
                else:
                    QMessageBox.information(self, "Playlisty", "Nie znaleziono żadnych playlist")
            else:
                QMessageBox.warning(self, "Błąd", "Nie udało się zainicjalizować Playlist Manager")

        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się pobrać playlist:\n{str(e)}")

    def open_upload_queue(self):
        """Open Upload Queue Manager dialog"""
        try:
            from upload_queue_dialog import UploadQueueDialog

            dialog = UploadQueueDialog(self.config, parent=self)
            dialog.exec()

        except Exception as e:
            QMessageBox.critical(self, "Błąd", f"Nie udało się otworzyć Upload Queue:\n{str(e)}")

    # Public API methods for parent apps

    def get_selected_profile(self) -> Optional[str]:
        """Get currently selected profile name"""
        if self.youtube_upload.isChecked():
            return self.youtube_profile.currentText()
        return None

    def is_upload_enabled(self) -> bool:
        """Check if YouTube upload is enabled"""
        return self.youtube_upload.isChecked()

    def is_queue_mode(self) -> bool:
        """Check if queue mode is enabled"""
        return self.youtube_use_queue.isChecked()

    def get_playlist_ids(self) -> dict:
        """Get playlist IDs for main and shorts"""
        return {
            'main': self.youtube_main_playlist.text().strip(),
            'shorts': self.youtube_shorts_playlist.text().strip()
        }

    def update_config(self):
        """Update config with current widget values"""
        if hasattr(self.config, 'youtube'):
            self.config.youtube.enabled = self.is_upload_enabled()

        # Update playlist IDs in selected profile
        profile_name = self.youtube_profile.currentText()
        profile = self.config.get_upload_profile(profile_name)
        if profile:
            playlists = self.get_playlist_ids()
            if playlists['main']:
                profile.main_videos.playlist_id = playlists['main']
            if playlists['shorts']:
                profile.shorts.playlist_id = playlists['shorts']
