"""
Upload Queue Dialog - UI dla zarządzania kolejką uploadów
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel, QMessageBox, QMenu,
    QLineEdit, QComboBox, QTextEdit, QGroupBox, QDateTimeEdit,
    QProgressBar, QWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDateTime
from PyQt6.QtGui import QColor, QFont, QAction
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from pipeline.upload_queue import UploadQueue, QueueItem, UploadStatus
from pipeline.config import Config


class UploadWorker(QThread):
    """Worker thread dla uploadu z kolejki"""

    progress = pyqtSignal(str, int, str)  # (item_id, percent, message)
    completed = pyqtSignal(str, dict)  # (item_id, result)
    failed = pyqtSignal(str, str)  # (item_id, error)

    def __init__(self, queue: UploadQueue, config: Config):
        super().__init__()
        self.queue = queue
        self.config = config
        self._is_running = True
        self.current_item_id = None

    def run(self):
        """Process queue items"""
        while self._is_running:
            # Get next pending item
            pending_items = self.queue.get_pending()

            if not pending_items:
                break

            item = pending_items[0]
            self.current_item_id = item.id

            try:
                self.queue.mark_uploading(item.id)
                self.progress.emit(item.id, 0, "Rozpoczynam upload...")

                # Import YouTube stage
                from pipeline.stage_09_youtube import YouTubeStage

                # Create YouTube stage with profile
                youtube_stage = YouTubeStage(self.config, profile_name=item.profile_name)
                youtube_stage.authorize()

                self.progress.emit(item.id, 20, "Uploading video...")

                # Upload video
                upload_result = youtube_stage.upload_video(
                    video_file=item.video_file,
                    thumbnail_file=item.thumbnail_file,
                    title=item.title,
                    description=item.description,
                    tags=item.tags
                )

                if upload_result.get('success'):
                    self.progress.emit(item.id, 100, "Upload zakończony!")

                    # Add to playlist if specified
                    settings = youtube_stage.get_profile_settings(item.video_type)
                    if settings.get('playlist_id'):
                        youtube_stage.playlist_manager.add_video_to_playlist(
                            settings['playlist_id'],
                            upload_result['video_id']
                        )

                    self.queue.mark_completed(
                        item.id,
                        upload_result['video_url'],
                        upload_result['video_id']
                    )
                    self.completed.emit(item.id, upload_result)
                else:
                    raise Exception(upload_result.get('error', 'Unknown error'))

            except Exception as e:
                error_msg = str(e)
                self.queue.mark_failed(item.id, error_msg)
                self.failed.emit(item.id, error_msg)
                self.progress.emit(item.id, 0, f"Błąd: {error_msg}")

        self.current_item_id = None

    def stop(self):
        """Stop worker"""
        self._is_running = False


class UploadQueueDialog(QDialog):
    """Dialog dla zarządzania Upload Queue"""

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.queue = UploadQueue()
        self.upload_worker = None

        self.init_ui()
        self.refresh_table()

    def init_ui(self):
        """Initialize UI"""
        self.setWindowTitle("📤 Upload Queue Manager")
        self.setGeometry(150, 150, 1200, 700)

        layout = QVBoxLayout(self)

        # Header with stats
        header = self.create_header()
        layout.addWidget(header)

        # Main table
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "ID", "Title", "Profile", "Type", "Status", "Progress",
            "YouTube URL", "Error", "Actions"
        ])

        # Set column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)

        self.table.setColumnWidth(5, 100)

        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)

        layout.addWidget(self.table)

        # Bottom controls
        controls = self.create_controls()
        layout.addWidget(controls)

    def create_header(self) -> QWidget:
        """Create header with stats"""
        header = QWidget()
        layout = QHBoxLayout(header)

        title = QLabel("📤 Upload Queue")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        layout.addStretch()

        # Stats labels
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("padding: 8px; background: #f0f0f0; border-radius: 4px;")
        layout.addWidget(self.stats_label)

        self.update_stats()

        return header

    def create_controls(self) -> QWidget:
        """Create bottom controls"""
        controls = QWidget()
        layout = QHBoxLayout(controls)

        # Left side - actions
        self.start_btn = QPushButton("▶️ Start Batch Upload")
        self.start_btn.clicked.connect(self.start_batch_upload)
        self.start_btn.setStyleSheet("padding: 10px; font-weight: bold; background: #4CAF50; color: white;")
        layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏸️ Stop")
        self.stop_btn.clicked.connect(self.stop_batch_upload)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("padding: 10px; font-weight: bold;")
        layout.addWidget(self.stop_btn)

        layout.addSpacing(20)

        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self.refresh_table)
        layout.addWidget(refresh_btn)

        clear_completed_btn = QPushButton("🧹 Clear Completed")
        clear_completed_btn.clicked.connect(self.clear_completed)
        layout.addWidget(clear_completed_btn)

        layout.addStretch()

        close_btn = QPushButton("✖️ Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        return controls

    def refresh_table(self):
        """Refresh table with queue items"""
        items = self.queue.get_all()
        self.table.setRowCount(len(items))

        for row, item in enumerate(items):
            # ID (shortened)
            id_short = item.id.split('_')[-1] if '_' in item.id else item.id
            self.table.setItem(row, 0, QTableWidgetItem(id_short))

            # Title
            title_item = QTableWidgetItem(item.title[:50])
            title_item.setToolTip(item.title)
            self.table.setItem(row, 1, title_item)

            # Profile
            self.table.setItem(row, 2, QTableWidgetItem(item.profile_name))

            # Type
            type_icon = "📱" if item.video_type == "shorts" else "🎬"
            self.table.setItem(row, 3, QTableWidgetItem(f"{type_icon} {item.video_type}"))

            # Status
            status_item = self.create_status_item(item.status)
            self.table.setItem(row, 4, status_item)

            # Progress bar
            progress = QProgressBar()
            if item.status == UploadStatus.COMPLETED.value:
                progress.setValue(100)
            elif item.status == UploadStatus.UPLOADING.value:
                progress.setValue(50)  # Will be updated by worker
            else:
                progress.setValue(0)
            self.table.setCellWidget(row, 5, progress)

            # YouTube URL
            url_item = QTableWidgetItem(item.youtube_url or "")
            if item.youtube_url:
                url_item.setForeground(QColor(33, 150, 243))
            self.table.setItem(row, 6, url_item)

            # Error
            error_item = QTableWidgetItem(item.error_message or "")
            if item.error_message:
                error_item.setForeground(QColor(244, 67, 54))
                error_item.setToolTip(item.error_message)
            self.table.setItem(row, 7, error_item)

            # Actions button
            actions_btn = QPushButton("⋮")
            actions_btn.clicked.connect(lambda checked, r=row: self.show_item_actions(r))
            self.table.setCellWidget(row, 8, actions_btn)

        self.update_stats()

    def create_status_item(self, status: str) -> QTableWidgetItem:
        """Create status item with color"""
        item = QTableWidgetItem(status.upper())

        if status == UploadStatus.PENDING.value:
            item.setBackground(QColor(158, 158, 158))
        elif status == UploadStatus.UPLOADING.value:
            item.setBackground(QColor(33, 150, 243))
        elif status == UploadStatus.COMPLETED.value:
            item.setBackground(QColor(76, 175, 80))
        elif status == UploadStatus.FAILED.value:
            item.setBackground(QColor(244, 67, 54))
        elif status == UploadStatus.SCHEDULED.value:
            item.setBackground(QColor(255, 193, 7))
        elif status == UploadStatus.CANCELLED.value:
            item.setBackground(QColor(96, 96, 96))

        item.setForeground(QColor(255, 255, 255))
        font = QFont()
        font.setBold(True)
        item.setFont(font)

        return item

    def update_stats(self):
        """Update statistics label"""
        stats = self.queue.get_stats()
        self.stats_label.setText(
            f"📊 Total: {stats['total']} | "
            f"⏳ Pending: {stats['pending']} | "
            f"▶️ Uploading: {stats['uploading']} | "
            f"✅ Completed: {stats['completed']} | "
            f"❌ Failed: {stats['failed']} | "
            f"🕐 Scheduled: {stats['scheduled']}"
        )

    def show_context_menu(self, position):
        """Show context menu on right-click"""
        row = self.table.rowAt(position.y())
        if row < 0:
            return

        items = self.queue.get_all()
        if row >= len(items):
            return

        item = items[row]

        menu = QMenu(self)

        # View details
        view_action = QAction("👁️ View Details", self)
        view_action.triggered.connect(lambda: self.view_item_details(item))
        menu.addAction(view_action)

        # Edit
        edit_action = QAction("✏️ Edit", self)
        edit_action.triggered.connect(lambda: self.edit_item(item))
        menu.addAction(edit_action)

        menu.addSeparator()

        # Retry (if failed)
        if item.can_retry():
            retry_action = QAction("🔄 Retry", self)
            retry_action.triggered.connect(lambda: self.retry_item(item.id))
            menu.addAction(retry_action)

        # Schedule
        schedule_action = QAction("🕐 Schedule", self)
        schedule_action.triggered.connect(lambda: self.schedule_item(item))
        menu.addAction(schedule_action)

        # Cancel
        if item.status in [UploadStatus.PENDING.value, UploadStatus.SCHEDULED.value]:
            cancel_action = QAction("⏹️ Cancel", self)
            cancel_action.triggered.connect(lambda: self.cancel_item(item.id))
            menu.addAction(cancel_action)

        menu.addSeparator()

        # Remove
        remove_action = QAction("🗑️ Remove from Queue", self)
        remove_action.triggered.connect(lambda: self.remove_item(item.id))
        menu.addAction(remove_action)

        menu.exec(self.table.viewport().mapToGlobal(position))

    def show_item_actions(self, row: int):
        """Show actions for item"""
        items = self.queue.get_all()
        if row >= len(items):
            return

        item = items[row]
        self.show_context_menu(self.table.visualItemRect(self.table.item(row, 0)).bottomLeft())

    def view_item_details(self, item: QueueItem):
        """Show item details dialog"""
        details = f"""
📋 Upload Details

ID: {item.id}
Title: {item.title}
Profile: {item.profile_name}
Type: {item.video_type}
Status: {item.status}

📁 File: {item.video_file}
🖼️ Thumbnail: {item.thumbnail_file or 'None'}

📝 Description:
{item.description}

🏷️ Tags: {', '.join(item.tags)}

🔗 YouTube URL: {item.youtube_url or 'Not uploaded yet'}
🆔 Video ID: {item.video_id or 'N/A'}

⏱️ Created: {item.created_at}
⏱️ Started: {item.started_at or 'N/A'}
⏱️ Completed: {item.completed_at or 'N/A'}

🔄 Retry Count: {item.retry_count}/{item.max_retries}
❌ Error: {item.error_message or 'None'}
        """.strip()

        QMessageBox.information(self, f"Details - {item.id}", details)

    def edit_item(self, item: QueueItem):
        """Edit item (simple version - can be expanded)"""
        # For now just show a message - can be expanded to full edit dialog
        QMessageBox.information(
            self,
            "Edit Item",
            "Funkcja edycji będzie dostępna w rozszerzonej wersji.\n"
            "Aktualnie możesz edytować tylko poprzez usunięcie i dodanie ponownie."
        )

    def retry_item(self, item_id: str):
        """Retry failed item"""
        if self.queue.retry(item_id):
            QMessageBox.information(self, "Retry", "Item został dodany ponownie do kolejki")
            self.refresh_table()
        else:
            QMessageBox.warning(self, "Retry", "Nie można ponowić - osiągnięto max retry count")

    def schedule_item(self, item: QueueItem):
        """Schedule item for later"""
        # Create simple schedule dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Schedule Upload")
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel("Wybierz datę i czas uploadu:"))

        datetime_edit = QDateTimeEdit()
        datetime_edit.setDateTime(QDateTime.currentDateTime().addSecs(3600))  # +1 hour
        datetime_edit.setCalendarPopup(True)
        layout.addWidget(datetime_edit)

        buttons = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        buttons.addWidget(ok_btn)
        buttons.addWidget(cancel_btn)
        layout.addLayout(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            scheduled_time = datetime_edit.dateTime().toPyDateTime()
            self.queue.schedule(item.id, scheduled_time)
            QMessageBox.information(
                self,
                "Scheduled",
                f"Upload zaplanowany na: {scheduled_time.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            self.refresh_table()

    def cancel_item(self, item_id: str):
        """Cancel item"""
        self.queue.cancel(item_id)
        self.refresh_table()

    def remove_item(self, item_id: str):
        """Remove item from queue"""
        reply = QMessageBox.question(
            self,
            "Remove Item",
            "Czy na pewno chcesz usunąć ten item z kolejki?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.queue.remove(item_id)
            self.refresh_table()

    def clear_completed(self):
        """Clear all completed items"""
        reply = QMessageBox.question(
            self,
            "Clear Completed",
            "Usunąć wszystkie zakończone uploady z kolejki?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.queue.clear_completed()
            self.refresh_table()

    def start_batch_upload(self):
        """Start batch upload of pending items"""
        pending = self.queue.get_pending()

        if not pending:
            QMessageBox.information(self, "No Items", "Brak items do uploadu w kolejce")
            return

        reply = QMessageBox.question(
            self,
            "Start Batch Upload",
            f"Rozpocząć upload {len(pending)} items?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.upload_worker = UploadWorker(self.queue, self.config)
            self.upload_worker.progress.connect(self.on_upload_progress)
            self.upload_worker.completed.connect(self.on_upload_completed)
            self.upload_worker.failed.connect(self.on_upload_failed)
            self.upload_worker.finished.connect(self.on_batch_finished)

            self.upload_worker.start()

            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)

    def stop_batch_upload(self):
        """Stop batch upload"""
        if self.upload_worker:
            self.upload_worker.stop()
            self.upload_worker.wait()

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

    def on_upload_progress(self, item_id: str, percent: int, message: str):
        """Handle upload progress"""
        # Update progress bar for this item
        items = self.queue.get_all()
        for row, item in enumerate(items):
            if item.id == item_id:
                widget = self.table.cellWidget(row, 5)
                if isinstance(widget, QProgressBar):
                    widget.setValue(percent)
                break

    def on_upload_completed(self, item_id: str, result: dict):
        """Handle upload completed"""
        self.refresh_table()

    def on_upload_failed(self, item_id: str, error: str):
        """Handle upload failed"""
        self.refresh_table()

    def on_batch_finished(self):
        """Handle batch upload finished"""
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.refresh_table()

        QMessageBox.information(self, "Batch Complete", "Batch upload zakończony!")
