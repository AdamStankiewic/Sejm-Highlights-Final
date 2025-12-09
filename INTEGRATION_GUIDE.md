# Integration Guide - Using New Optimization Features

This guide shows how to integrate the new optimization features into your existing Sejm Highlights pipeline.

## 1. Logging Integration

### Replace print statements with structured logging:

**Before:**
```python
print("🔍 Processing segments...")
print(f"   Found {len(segments)} segments")
```

**After:**
```python
from pipeline.logger import get_logger

logger = get_logger()
logger.info("🔍 Processing segments...")
logger.info(f"   Found {len(segments)} segments")
```

### For GUI integration:

```python
from pipeline.logger import get_logger, set_gui_callback

# In your GUI init
logger = get_logger(log_dir=Path("logs"))

# Set callback to update GUI
def gui_log_callback(message: str, level: str):
    self.log_text.append(f"[{level}] {message}")

set_gui_callback(gui_log_callback)
```

## 2. GPU Acceleration

### Add GPU detection to pipeline stages:

```python
from pipeline.utils.gpu_utils import get_gpu_manager, get_optimal_device

# Initialize GPU manager
gpu = get_gpu_manager()

if gpu.is_available():
    logger.success(f"GPU: {gpu.get_device_name()}")
else:
    logger.info("Using CPU")

# Get optimal device for models
device = get_optimal_device(use_gpu=config.asr.use_gpu)

# For Whisper
model = WhisperModel(
    model_size,
    device=device,
    compute_type="float16" if device == "cuda" else "int8"
)

# For spaCy
from pipeline.utils.gpu_utils import check_spacy_gpu
check_spacy_gpu()  # Automatically enables GPU if available
```

## 3. Transcription Caching

### Cache expensive transcription results:

```python
from pipeline.utils.cache_manager import get_cache_manager

cache = get_cache_manager(cache_dir=Path("cache"))

# Check cache before transcription
cache_params = {
    'model': config.asr.model_size,
    'language': config.asr.language
}

cached_transcript = cache.get(
    identifier=str(audio_file),
    cache_type='transcription',
    params=cache_params
)

if cached_transcript:
    logger.success("✓ Using cached transcription")
    segments = cached_transcript['segments']
else:
    # Run transcription
    segments = transcribe_audio(audio_file)

    # Cache result
    cache.set(
        identifier=str(audio_file),
        cache_type='transcription',
        data={'segments': segments},
        params=cache_params
    )
```

## 4. Parallel Processing

### Speed up VAD and feature extraction:

```python
from pipeline.utils.parallel_processor import ParallelProcessor, parallel_feature_extraction

# For feature extraction
processor = ParallelProcessor(use_processes=True)

enriched_segments = parallel_feature_extraction(
    segments=segments,
    feature_extractor=self._extract_segment_features,
    audio_data=audio,
    sample_rate=sr
)
```

## 5. Input Validation

### Validate video files before processing:

```python
from pipeline.utils.validators import validate_video_file
from PyQt6.QtWidgets import QMessageBox

# In GUI before processing
is_valid, error_msg, metadata = validate_video_file(video_path)

if not is_valid:
    QMessageBox.critical(self, "Błąd walidacji", error_msg)
    return

# Show warnings for long videos
if metadata['duration_seconds'] > 7200:  # 2 hours
    reply = QMessageBox.question(
        self,
        "Długi film",
        "Film jest dłuższy niż 2 godziny. Przetwarzanie może zająć kilka godzin.\n"
        "Czy włączyć Smart Splitter?",
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
    )
    if reply == QMessageBox.StandardButton.Yes:
        config.smart_splitter.enabled = True
```

## 6. Enhanced Error Handling

### Use error handlers for pipeline stages:

```python
from pipeline.utils.error_handling import (
    handle_stage_errors,
    ErrorRecovery,
    get_user_friendly_error_message
)

class MyStage:
    @handle_stage_errors("Stage 3: Transcription")
    def process(self, audio_file: str) -> dict:
        # Your processing code
        result = transcribe(audio_file)
        return result
```

### With recovery strategies:

```python
from pipeline.utils.error_handling import ErrorRecovery

def transcribe_with_retry(audio_file):
    """Transcribe with automatic batch size reduction on OOM"""
    return ErrorRecovery.retry_with_smaller_batch(
        lambda batch_size: transcribe(audio_file, batch_size=batch_size),
        max_retries=3
    )
```

### User-friendly errors in GUI:

```python
from pipeline.utils.error_handling import get_user_friendly_error_message

try:
    result = self.process_video(video_path)
except Exception as e:
    user_msg = get_user_friendly_error_message(e)
    QMessageBox.critical(self, "Błąd", user_msg)
```

## 7. Auto-Save Configuration

### Save config when user changes settings:

```python
# In your GUI config change handlers
def on_whisper_model_changed(self, model_name: str):
    self.config.asr.model_size = model_name

    # Auto-save config
    try:
        self.config.save_to_yaml("config.yml")
        logger.debug(f"Config auto-saved: Whisper model = {model_name}")
    except Exception as e:
        logger.warning(f"Failed to auto-save config: {e}")
```

### Add auto-save timer (save every 30 seconds if changes detected):

```python
from PyQt6.QtCore import QTimer

class SejmHighlightsApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config_changed = False

        # Setup auto-save timer
        self.autosave_timer = QTimer()
        self.autosave_timer.timeout.connect(self.autosave_config)
        self.autosave_timer.start(30000)  # 30 seconds

    def mark_config_changed(self):
        """Mark that config has been modified"""
        self.config_changed = True

    def autosave_config(self):
        """Auto-save config if changes detected"""
        if self.config_changed:
            try:
                self.config.save_to_yaml("config.yml")
                logger.debug("Config auto-saved")
                self.config_changed = False
            except Exception as e:
                logger.error(f"Auto-save failed: {e}")
```

## 8. Video Preview Enhancement

### Add better video preview with player selection:

```python
def play_output_video(self):
    """Enhanced video preview with player selection"""
    if not self.current_results:
        return

    import subprocess
    import platform

    # Get video file
    video_file = self._get_output_video_path()

    system = platform.system()

    try:
        if system == "Windows":
            # Try VLC first, fallback to default
            try:
                subprocess.Popen(['vlc', video_file])
            except FileNotFoundError:
                os.startfile(video_file)

        elif system == "Darwin":  # macOS
            subprocess.call(['open', video_file])

        else:  # Linux
            # Try multiple players
            for player in ['vlc', 'mpv', 'ffplay', 'xdg-open']:
                try:
                    subprocess.Popen([player, video_file])
                    break
                except FileNotFoundError:
                    continue

        logger.info(f"Opening video: {Path(video_file).name}")

    except Exception as e:
        logger.error(f"Failed to open video: {e}")
        QMessageBox.warning(
            self,
            "Błąd",
            f"Nie udało się otworzyć video:\n{e}\n\n"
            f"Otwórz ręcznie: {video_file}"
        )
```

## 9. Complete Pipeline Integration Example

Here's a complete example integrating all optimizations:

```python
from pathlib import Path
from pipeline.logger import get_logger
from pipeline.utils.gpu_utils import get_gpu_manager
from pipeline.utils.cache_manager import get_cache_manager
from pipeline.utils.validators import validate_video_file
from pipeline.utils.error_handling import handle_stage_errors, get_user_friendly_error_message

class OptimizedPipelineProcessor:
    def __init__(self, config):
        self.config = config
        self.logger = get_logger(log_dir=Path("logs"))
        self.gpu = get_gpu_manager()
        self.cache = get_cache_manager(cache_dir=Path("cache"))

    @handle_stage_errors("Video Processing")
    def process(self, video_path: str) -> dict:
        # 1. Validate input
        is_valid, error, metadata = validate_video_file(video_path)
        if not is_valid:
            raise ValueError(error)

        # 2. Check GPU
        if self.gpu.is_available():
            self.logger.info(f"Using GPU: {self.gpu.get_device_name()}")

        # 3. Check cache
        cache_key = str(video_path)
        cached = self.cache.get(cache_key, 'transcription')

        if cached:
            self.logger.success("Using cached transcription")
            return cached

        # 4. Process video
        result = self._process_video_internal(video_path)

        # 5. Cache result
        self.cache.set(cache_key, 'transcription', result)

        # 6. Auto-save config
        self.config.save_to_yaml("config.yml")

        return result
```

## Testing

Run the test suite to ensure everything works:

```bash
# All tests
pytest

# Specific modules
pytest tests/test_config.py
pytest tests/test_features.py
pytest tests/test_scoring.py
pytest tests/test_selection.py

# With coverage
pytest --cov=pipeline --cov-report=html
```

## Performance Monitoring

```python
from pipeline.utils.gpu_utils import get_gpu_manager

gpu = get_gpu_manager()

# Monitor memory during processing
gpu.monitor_memory()  # Logs current usage

# Get optimal batch size
batch_size = gpu.get_optimal_batch_size(base_batch_size=10)

# Clear cache when needed
gpu.clear_cache()
```

## Troubleshooting

### GPU not detected
```bash
# Check CUDA installation
python -c "import torch; print(torch.cuda.is_available())"
```

### Cache issues
```python
from pipeline.utils.cache_manager import get_cache_manager

cache = get_cache_manager()
cache.clear_all()  # Clear all cache
stats = cache.get_stats()  # Get cache statistics
```

### Logging issues
Check log files in `logs/` directory for detailed error traces.
