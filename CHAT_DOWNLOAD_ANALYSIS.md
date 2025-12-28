# Chat Download Analysis: Multi-Platform Support

## Problem Statement

**User needs to:**
1. Get chat data for videos from YouTube, Twitch, Kick
2. Either download automatically OR upload manually
3. Support different chat formats per platform
4. Integrate with GUI for easy workflow

---

## Platform-Specific Chat Formats

### 1. YouTube Live Chat

**Tool:** `yt-dlp` (already in requirements.txt!)

**Download Command:**
```bash
yt-dlp \
  --write-subs \
  --sub-lang live_chat \
  --skip-download \
  --output "%(id)s" \
  "https://youtube.com/watch?v=VIDEO_ID"

# Output: VIDEO_ID.live_chat.json
```

**Format:**
```json
{
  "replayChatItemAction": {
    "actions": [{
      "addChatItemAction": {
        "item": {
          "liveChatTextMessageRenderer": {
            "message": {"runs": [{"text": "Hello!"}]},
            "authorName": {"simpleText": "Username"},
            "timestampUsec": "1642345678123456"
          }
        }
      }
    }],
    "videoOffsetTimeMsec": "123456"  // ← KEY: Offset from video start!
  }
}
```

**Key Fields:**
- `videoOffsetTimeMsec` - milliseconds from video start (THIS IS WHAT WE NEED!)
- `timestampUsec` - absolute timestamp (backup)
- `message.runs[0].text` - message content
- `authorName.simpleText` - username

**Parser Code:**
```python
def parse_youtube_chat(json_path: str) -> List[Dict]:
    """Parse YouTube live_chat.json format"""

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    messages = []

    for action in data.get('replayChatItemAction', {}).get('actions', []):
        if 'addChatItemAction' in action:
            item = action['addChatItemAction']['item']

            if 'liveChatTextMessageRenderer' in item:
                renderer = item['liveChatTextMessageRenderer']

                # Get video offset in seconds
                offset_ms = int(action.get('videoOffsetTimeMsec', 0))
                offset_seconds = offset_ms / 1000.0

                # Extract message text
                message_text = ''.join(
                    run.get('text', '')
                    for run in renderer.get('message', {}).get('runs', [])
                )

                # Extract author
                author = renderer.get('authorName', {}).get('simpleText', 'Unknown')

                messages.append({
                    'time_in_seconds': offset_seconds,
                    'author': author,
                    'message': message_text,
                    'platform': 'youtube'
                })

    return messages
```

**Pros:**
- ✅ yt-dlp already installed
- ✅ videoOffsetTimeMsec is PERFECT for syncing
- ✅ Works for VODs (if chat replay available)

**Cons:**
- ⚠️ Only works if chat replay is available
- ⚠️ Some old streams don't have chat saved

---

### 2. Twitch VOD Chat

**Tool:** `TwitchDownloaderCLI`

**Installation:**
```bash
# Download from: https://github.com/lay295/TwitchDownloader/releases
# Or via chocolatey (Windows):
choco install twitchdownloader-cli

# Linux/Mac:
wget https://github.com/lay295/TwitchDownloader/releases/download/VERSION/TwitchDownloaderCLI-Linux-x64
chmod +x TwitchDownloaderCLI-Linux-x64
```

**Download Command:**
```bash
TwitchDownloaderCLI chatdownload \
  --id 1234567890 \
  --output chat.json \
  --embed-images false \
  --timestamp-format Relative  # ← IMPORTANT!

# Or with VOD URL:
TwitchDownloaderCLI chatdownload \
  -u "https://twitch.tv/videos/1234567890" \
  -o chat.json
```

**Format:**
```json
{
  "comments": [
    {
      "content_offset_seconds": 123.45,  // ← KEY: Offset from VOD start!
      "message": {
        "body": "PogChamp",
        "fragments": [{"text": "PogChamp"}]
      },
      "commenter": {
        "display_name": "Username",
        "_id": "12345"
      }
    }
  ],
  "video": {
    "start": 1642345678,
    "end": 1642349278,
    "length": 3600
  }
}
```

**Key Fields:**
- `content_offset_seconds` - seconds from VOD start (PERFECT!)
- `message.body` - message text
- `commenter.display_name` - username

**Parser Code:**
```python
def parse_twitch_chat(json_path: str) -> List[Dict]:
    """Parse TwitchDownloader JSON format"""

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    messages = []

    for comment in data.get('comments', []):
        offset = comment.get('content_offset_seconds', 0)

        message_text = comment.get('message', {}).get('body', '')
        author = comment.get('commenter', {}).get('display_name', 'Unknown')

        messages.append({
            'time_in_seconds': offset,
            'author': author,
            'message': message_text,
            'platform': 'twitch'
        })

    return messages
```

**Pros:**
- ✅ Official tool, reliable
- ✅ content_offset_seconds is PERFECT
- ✅ Works for all Twitch VODs

**Cons:**
- ❌ Requires separate tool installation
- ⚠️ Not in Python (external CLI binary)

---

### 3. Kick VOD Chat

**Tool:** ❌ **NO official tool!**

**Options:**

#### Option A: Manual Export (if Kick provides it)
- Check if Kick has chat export feature
- Format unknown

#### Option B: API Scraping (complex)
```python
# Hypothetical - would need reverse engineering
import requests

def download_kick_chat(vod_id: str):
    # Kick API endpoint (need to find)
    url = f"https://kick.com/api/v2/channels/{channel}/chatroom/messages"

    # Would need authentication, pagination, etc.
    # Complex and fragile
```

#### Option C: Browser Extension
- Chrome extension to export chat
- User exports manually
- We parse the format

**Current Status:** ⚠️ **Not implemented** (low priority - Kick is smaller platform)

**Recommendation:**
- Start with YouTube + Twitch (90% of use cases)
- Add Kick later if needed

---

## Unified Chat Parser

### Universal Parser (handles all formats)

```python
# utils/chat_downloader.py

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def auto_detect_format(json_path: Path) -> str:
    """Auto-detect chat format from JSON structure"""

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # YouTube format
    if 'replayChatItemAction' in data:
        return 'youtube'

    # Twitch format
    if 'comments' in data and isinstance(data['comments'], list):
        if data['comments'] and 'content_offset_seconds' in data['comments'][0]:
            return 'twitch'

    # Generic format (from our utils/chat_parser.py)
    if isinstance(data, list) and data and 'time_in_seconds' in data[0]:
        return 'generic'

    return 'unknown'


def parse_youtube_live_chat(json_path: Path) -> List[Dict]:
    """Parse YouTube live_chat.json"""
    # ... (code from above)


def parse_twitch_vod_chat(json_path: Path) -> List[Dict]:
    """Parse TwitchDownloader JSON"""
    # ... (code from above)


def parse_chat_universal(json_path: Path) -> List[Dict]:
    """
    Universal chat parser - auto-detects format

    Args:
        json_path: Path to chat JSON file

    Returns:
        List of {time_in_seconds, author, message, platform}
        Sorted by time_in_seconds
    """

    if not json_path.exists():
        logger.error(f"Chat file not found: {json_path}")
        return []

    # Auto-detect format
    format_type = auto_detect_format(json_path)
    logger.info(f"Detected chat format: {format_type}")

    # Parse based on format
    if format_type == 'youtube':
        messages = parse_youtube_live_chat(json_path)
    elif format_type == 'twitch':
        messages = parse_twitch_vod_chat(json_path)
    elif format_type == 'generic':
        # Already in our format
        with open(json_path, 'r', encoding='utf-8') as f:
            messages = json.load(f)
    else:
        logger.warning(f"Unknown chat format: {json_path}")
        return []

    # Sort by time
    messages = sorted(messages, key=lambda m: m.get('time_in_seconds', 0))

    logger.info(f"Loaded {len(messages)} chat messages")
    return messages
```

---

## GUI Integration

### Option 1: Manual Upload Only (SIMPLEST)

```python
# In app.py - Long Video Settings

chat_group = QGroupBox("💬 Chat Overlay (Optional)")
chat_layout = QVBoxLayout()

# Chat file browse
file_layout = QHBoxLayout()
file_layout.addWidget(QLabel("Chat File:"))

self.chat_file_path = QLineEdit()
self.chat_file_path.setPlaceholderText("Browse for chat.json...")
file_layout.addWidget(self.chat_file_path)

self.chat_browse_btn = QPushButton("📂 Browse")
self.chat_browse_btn.clicked.connect(self.browse_chat_file)
file_layout.addWidget(self.chat_browse_btn)

chat_layout.addLayout(file_layout)

# Info label
info = QLabel(
    "Supported formats:\n"
    "  • YouTube live_chat.json (from yt-dlp)\n"
    "  • Twitch chat.json (from TwitchDownloaderCLI)\n"
    "  • Generic {time_in_seconds, author, message}"
)
info.setStyleSheet("color: #666; font-size: 9pt;")
chat_layout.addWidget(info)

# Enable overlay checkbox
self.chat_overlay_enabled = QCheckBox("Enable Chat Overlay")
self.chat_overlay_enabled.setChecked(False)
chat_layout.addWidget(self.chat_overlay_enabled)

# Position
position_layout = QHBoxLayout()
position_layout.addWidget(QLabel("Position:"))
self.chat_position = QComboBox()
self.chat_position.addItems([
    "Top-Right",
    "Top-Left",
    "Bottom-Right",
    "Bottom-Left"
])
position_layout.addWidget(self.chat_position)
chat_layout.addLayout(position_layout)

chat_group.setLayout(chat_layout)
```

**Browse Handler:**
```python
def browse_chat_file(self):
    """Browse for chat JSON file"""

    file_path, _ = QFileDialog.getOpenFileName(
        self,
        "Select Chat File",
        "",
        "JSON Files (*.json);;All Files (*.*)"
    )

    if file_path:
        self.chat_file_path.setText(file_path)

        # Validate and show preview
        try:
            from utils.chat_downloader import parse_chat_universal

            messages = parse_chat_universal(Path(file_path))

            if messages:
                QMessageBox.information(
                    self,
                    "Chat Loaded",
                    f"✅ Loaded {len(messages)} messages\n"
                    f"Duration: {messages[-1]['time_in_seconds']/60:.1f} minutes\n"
                    f"Format: Auto-detected"
                )
            else:
                QMessageBox.warning(
                    self,
                    "Invalid Chat",
                    "❌ No messages found in file\n"
                    "Check format or file content"
                )

        except Exception as e:
            QMessageBox.warning(
                self,
                "Parse Error",
                f"❌ Failed to parse chat file:\n{e}"
            )
```

**Pros:**
- ✅ Simple implementation
- ✅ No external dependencies
- ✅ User has full control

**Cons:**
- ⚠️ User must download chat separately
- ⚠️ Extra step in workflow

---

### Option 2: Automatic Download (ADVANCED)

```python
# In app.py - Chat Download Section

chat_download_group = QGroupBox("💬 Chat Download")
download_layout = QVBoxLayout()

# URL input
url_layout = QHBoxLayout()
url_layout.addWidget(QLabel("Video URL:"))

self.chat_video_url = QLineEdit()
self.chat_video_url.setPlaceholderText("https://youtube.com/watch?v=... or https://twitch.tv/videos/...")
url_layout.addWidget(self.chat_video_url)

download_layout.addLayout(url_layout)

# Platform auto-detect
platform_layout = QHBoxLayout()
platform_layout.addWidget(QLabel("Platform:"))

self.chat_platform_label = QLabel("Auto-detect")
platform_layout.addWidget(self.chat_platform_label)
platform_layout.addStretch()

download_layout.addLayout(platform_layout)

# Download button
self.download_chat_btn = QPushButton("⬇️ Download Chat")
self.download_chat_btn.clicked.connect(self.download_chat)
download_layout.addWidget(self.download_chat_btn)

# Status
self.chat_status_label = QLabel("No chat loaded")
self.chat_status_label.setStyleSheet("color: #666;")
download_layout.addWidget(self.chat_status_label)

chat_download_group.setLayout(download_layout)
```

**Download Handler:**
```python
def download_chat(self):
    """Download chat from video URL"""

    url = self.chat_video_url.text().strip()

    if not url:
        QMessageBox.warning(self, "No URL", "Please enter video URL")
        return

    # Detect platform
    if 'youtube.com' in url or 'youtu.be' in url:
        platform = 'youtube'
    elif 'twitch.tv' in url:
        platform = 'twitch'
    elif 'kick.com' in url:
        platform = 'kick'
    else:
        QMessageBox.warning(self, "Unknown Platform", "URL not recognized")
        return

    self.chat_platform_label.setText(platform.title())

    # Start download in background thread
    self.download_chat_btn.setEnabled(False)
    self.chat_status_label.setText(f"⏳ Downloading chat from {platform}...")

    # Create download thread
    from PyQt6.QtCore import QThread

    class ChatDownloadThread(QThread):
        finished = pyqtSignal(str)  # Path to downloaded file
        failed = pyqtSignal(str)    # Error message

        def __init__(self, url, platform):
            super().__init__()
            self.url = url
            self.platform = platform

        def run(self):
            try:
                if self.platform == 'youtube':
                    output_path = self.download_youtube_chat(self.url)
                elif self.platform == 'twitch':
                    output_path = self.download_twitch_chat(self.url)
                else:
                    self.failed.emit(f"{self.platform} not supported yet")
                    return

                self.finished.emit(output_path)

            except Exception as e:
                self.failed.emit(str(e))

        def download_youtube_chat(self, url):
            """Download YouTube chat using yt-dlp"""
            import subprocess
            import tempfile

            output_dir = Path(tempfile.gettempdir())
            output_template = str(output_dir / "%(id)s")

            cmd = [
                "yt-dlp",
                "--write-subs",
                "--sub-lang", "live_chat",
                "--skip-download",
                "--output", output_template,
                url
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise Exception(f"yt-dlp failed: {result.stderr}")

            # Find generated file
            video_id = url.split('v=')[1].split('&')[0]
            chat_file = output_dir / f"{video_id}.live_chat.json"

            if not chat_file.exists():
                raise Exception("Chat file not found - may not be available")

            return str(chat_file)

        def download_twitch_chat(self, url):
            """Download Twitch chat using TwitchDownloaderCLI"""
            import subprocess
            import tempfile

            output_file = Path(tempfile.gettempdir()) / "twitch_chat.json"

            cmd = [
                "TwitchDownloaderCLI",
                "chatdownload",
                "-u", url,
                "-o", str(output_file),
                "--timestamp-format", "Relative"
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                raise Exception(f"TwitchDownloader failed: {result.stderr}")

            return str(output_file)

    # Connect signals
    self.chat_download_thread = ChatDownloadThread(url, platform)
    self.chat_download_thread.finished.connect(self.on_chat_downloaded)
    self.chat_download_thread.failed.connect(self.on_chat_download_failed)
    self.chat_download_thread.start()

def on_chat_downloaded(self, file_path):
    """Handle successful chat download"""

    self.download_chat_btn.setEnabled(True)
    self.chat_file_path.setText(file_path)
    self.chat_status_label.setText(f"✅ Chat downloaded: {Path(file_path).name}")

    # Validate
    try:
        from utils.chat_downloader import parse_chat_universal
        messages = parse_chat_universal(Path(file_path))

        QMessageBox.information(
            self,
            "Chat Downloaded",
            f"✅ Successfully downloaded {len(messages)} messages"
        )

    except Exception as e:
        QMessageBox.warning(self, "Parse Error", f"Downloaded but failed to parse: {e}")

def on_chat_download_failed(self, error):
    """Handle failed chat download"""

    self.download_chat_btn.setEnabled(True)
    self.chat_status_label.setText("❌ Download failed")

    QMessageBox.critical(
        self,
        "Download Failed",
        f"Failed to download chat:\n{error}\n\n"
        f"Make sure tools are installed:\n"
        f"  • YouTube: yt-dlp (pip install yt-dlp)\n"
        f"  • Twitch: TwitchDownloaderCLI"
    )
```

**Pros:**
- ✅ One-click workflow
- ✅ Auto-detects platform
- ✅ User-friendly

**Cons:**
- ❌ Requires external tools (yt-dlp, TwitchDownloaderCLI)
- ❌ More complex code
- ⚠️ Can fail if tools not installed

---

### Option 3: HYBRID (RECOMMENDED!)

Combine both approaches:

```
┌─ Chat Overlay ───────────────────────────────┐
│                                              │
│ ○ Download from URL                          │
│   URL: [paste YouTube/Twitch URL]            │
│   [⬇️ Download Chat]                         │
│                                              │
│ ○ Upload file manually                       │
│   [📂 Browse...] chat.json                   │
│                                              │
│ Status: ✅ Chat loaded (1,234 messages)      │
│         Duration: 45.5 minutes               │
│                                              │
│ ☑ Enable Chat Overlay                       │
│ Position: [Top-Right    ▼]                   │
│                                              │
└──────────────────────────────────────────────┘
```

**Benefits:**
- ✅ Flexible workflow
- ✅ Fallback if download fails
- ✅ Advanced users can provide custom formats

---

## Implementation Recommendations

### Phase 1: Manual Upload Only (SIMPLE MVP)

**Why:**
- ✅ No external dependencies
- ✅ Works immediately
- ✅ User can use any tool to get chat

**User workflow:**
```bash
# YouTube
yt-dlp --write-subs --sub-lang live_chat --skip-download URL

# Twitch
TwitchDownloaderCLI chatdownload -u URL -o chat.json

# Then upload to GUI
```

**Implementation:** 2 hours

### Phase 2: Add YouTube Auto-Download

**Why:**
- ✅ yt-dlp already installed
- ✅ Most common use case
- ✅ Easy to implement

**Implementation:** +2 hours

### Phase 3: Add Twitch Auto-Download

**Why:**
- Requires TwitchDownloaderCLI installation
- Document installation steps
- Test on Windows/Linux/Mac

**Implementation:** +2 hours

### Phase 4: Add Kick (if needed)

**Only if users request it**

---

## Required Files

### 1. Chat Downloader Module
```
utils/chat_downloader.py
├── auto_detect_format()
├── parse_youtube_live_chat()
├── parse_twitch_vod_chat()
└── parse_chat_universal()
```

### 2. GUI Integration
```
app.py (modifications)
├── Chat file browser
├── Chat download section (optional)
├── Chat overlay controls
└── Validation & preview
```

### 3. Chat Overlay Renderer
```
pipeline/chat_overlay.py
├── ChatOverlayRenderer class
├── render_chat_overlay()
└── _render_chat_text()
```

---

## Format Summary Table

| Platform | Tool | Output Format | Key Field | Status |
|----------|------|---------------|-----------|--------|
| **YouTube** | yt-dlp | live_chat.json | videoOffsetTimeMsec | ✅ Ready |
| **Twitch** | TwitchDownloaderCLI | chat.json | content_offset_seconds | ✅ Ready |
| **Kick** | ??? | ??? | ??? | ❌ Unknown |

---

## Final Recommendation

### START WITH:

1. **Manual Upload** (Phase 1)
   - Browse button for chat.json
   - Auto-detect format (YouTube/Twitch/Generic)
   - Show preview (message count, duration)

2. **Documentation** for users:
   ```markdown
   # How to Get Chat Files

   ## YouTube:
   yt-dlp --write-subs --sub-lang live_chat --skip-download URL

   ## Twitch:
   TwitchDownloaderCLI chatdownload -u URL -o chat.json

   Then upload to GUI via Browse button.
   ```

3. **Add auto-download LATER** if users request it

**Why this order:**
- ✅ Fast to implement (2 hours)
- ✅ Works for all platforms (user brings file)
- ✅ No external tool dependencies
- ✅ Can add auto-download later without breaking

---

## Next Steps

**Before I implement, confirm:**

1. **Start with manual upload only?** (Simplest, 2 hours)
   - OR add YouTube auto-download? (+2 hours)

2. **Which platforms do you actually use?**
   - YouTube? ✅ / ❌
   - Twitch? ✅ / ❌
   - Kick? ✅ / ❌

3. **Do you have sample chat files?**
   - Can you share one for testing?

**Answer and I'll implement!** 🚀
