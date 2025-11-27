"""
Upload Queue Manager - Zarządzanie kolejką uploadów YouTube
Obsługuje preview, scheduling, retry, batch operations
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum


class UploadStatus(Enum):
    """Status uploadu w kolejce"""
    PENDING = "pending"
    UPLOADING = "uploading"
    COMPLETED = "completed"
    FAILED = "failed"
    SCHEDULED = "scheduled"
    CANCELLED = "cancelled"


@dataclass
class QueueItem:
    """Pojedynczy item w kolejce uploadów"""
    id: str  # Unique ID
    video_file: str
    title: str
    description: str
    tags: List[str]
    profile_name: str  # sejm, stream, etc.
    video_type: str  # "main" or "shorts"

    # Status & metadata
    status: str = UploadStatus.PENDING.value
    thumbnail_file: Optional[str] = None
    scheduled_time: Optional[str] = None  # ISO format datetime

    # Results & errors
    youtube_url: Optional[str] = None
    video_id: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

    # Timestamps
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    # Additional metadata
    duration: Optional[float] = None
    file_size: Optional[int] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        """Convert to dict for JSON serialization"""
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict) -> 'QueueItem':
        """Create from dict"""
        return QueueItem(**data)

    def can_retry(self) -> bool:
        """Check if can retry"""
        return self.retry_count < self.max_retries and self.status == UploadStatus.FAILED.value

    def is_ready_to_upload(self) -> bool:
        """Check if ready to upload (pending or scheduled time passed)"""
        if self.status == UploadStatus.PENDING.value:
            return True

        if self.status == UploadStatus.SCHEDULED.value and self.scheduled_time:
            scheduled = datetime.fromisoformat(self.scheduled_time)
            return datetime.now() >= scheduled

        return False


class UploadQueue:
    """Manager for upload queue"""

    def __init__(self, queue_file: Path = Path("upload_queue.json")):
        self.queue_file = queue_file
        self.items: List[QueueItem] = []
        self.load()

    def load(self):
        """Load queue from file"""
        if self.queue_file.exists():
            try:
                with open(self.queue_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.items = [QueueItem.from_dict(item) for item in data]
            except Exception as e:
                print(f"Error loading queue: {e}")
                self.items = []
        else:
            self.items = []

    def save(self):
        """Save queue to file"""
        try:
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump([item.to_dict() for item in self.items], f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving queue: {e}")

    def add(self, item: QueueItem) -> str:
        """Add item to queue, returns item ID"""
        if not item.id:
            item.id = f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.items)}"

        self.items.append(item)
        self.save()
        return item.id

    def get(self, item_id: str) -> Optional[QueueItem]:
        """Get item by ID"""
        for item in self.items:
            if item.id == item_id:
                return item
        return None

    def update(self, item_id: str, **kwargs):
        """Update item fields"""
        item = self.get(item_id)
        if item:
            for key, value in kwargs.items():
                if hasattr(item, key):
                    setattr(item, key, value)
            self.save()

    def remove(self, item_id: str):
        """Remove item from queue"""
        self.items = [item for item in self.items if item.id != item_id]
        self.save()

    def get_all(self, status: Optional[str] = None) -> List[QueueItem]:
        """Get all items, optionally filtered by status"""
        if status:
            return [item for item in self.items if item.status == status]
        return self.items

    def get_pending(self) -> List[QueueItem]:
        """Get all pending items ready to upload"""
        return [item for item in self.items if item.is_ready_to_upload()]

    def get_failed(self) -> List[QueueItem]:
        """Get all failed items that can be retried"""
        return [item for item in self.items if item.can_retry()]

    def mark_uploading(self, item_id: str):
        """Mark item as uploading"""
        self.update(item_id, status=UploadStatus.UPLOADING.value, started_at=datetime.now().isoformat())

    def mark_completed(self, item_id: str, youtube_url: str, video_id: str):
        """Mark item as completed"""
        self.update(
            item_id,
            status=UploadStatus.COMPLETED.value,
            youtube_url=youtube_url,
            video_id=video_id,
            completed_at=datetime.now().isoformat()
        )

    def mark_failed(self, item_id: str, error_message: str):
        """Mark item as failed and increment retry count"""
        item = self.get(item_id)
        if item:
            item.status = UploadStatus.FAILED.value
            item.error_message = error_message
            item.retry_count += 1
            self.save()

    def retry(self, item_id: str):
        """Reset item for retry"""
        item = self.get(item_id)
        if item and item.can_retry():
            item.status = UploadStatus.PENDING.value
            item.error_message = None
            item.started_at = None
            self.save()
            return True
        return False

    def schedule(self, item_id: str, scheduled_time: datetime):
        """Schedule item for later upload"""
        self.update(
            item_id,
            status=UploadStatus.SCHEDULED.value,
            scheduled_time=scheduled_time.isoformat()
        )

    def cancel(self, item_id: str):
        """Cancel upload"""
        self.update(item_id, status=UploadStatus.CANCELLED.value)

    def clear_completed(self):
        """Remove all completed items from queue"""
        self.items = [item for item in self.items if item.status != UploadStatus.COMPLETED.value]
        self.save()

    def clear_all(self):
        """Clear entire queue"""
        self.items = []
        self.save()

    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics"""
        stats = {
            'total': len(self.items),
            'pending': 0,
            'uploading': 0,
            'completed': 0,
            'failed': 0,
            'scheduled': 0,
            'cancelled': 0
        }

        for item in self.items:
            if item.status == UploadStatus.PENDING.value:
                stats['pending'] += 1
            elif item.status == UploadStatus.UPLOADING.value:
                stats['uploading'] += 1
            elif item.status == UploadStatus.COMPLETED.value:
                stats['completed'] += 1
            elif item.status == UploadStatus.FAILED.value:
                stats['failed'] += 1
            elif item.status == UploadStatus.SCHEDULED.value:
                stats['scheduled'] += 1
            elif item.status == UploadStatus.CANCELLED.value:
                stats['cancelled'] += 1

        return stats

    def batch_add(self, items: List[QueueItem]) -> List[str]:
        """Add multiple items at once"""
        item_ids = []
        for item in items:
            item_id = self.add(item)
            item_ids.append(item_id)
        return item_ids

    def batch_retry(self, item_ids: List[str]) -> int:
        """Retry multiple items, returns count of successfully retried"""
        count = 0
        for item_id in item_ids:
            if self.retry(item_id):
                count += 1
        return count
