"""
Centralized logging module for Sejm Highlights
Replaces print statements with structured logging
"""
import logging
import sys
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime
from enum import Enum


class LogLevel(Enum):
    """Log levels with emoji indicators for GUI"""
    DEBUG = ('DEBUG', '🔍', logging.DEBUG)
    INFO = ('INFO', 'ℹ️', logging.INFO)
    SUCCESS = ('SUCCESS', '✅', logging.INFO)
    WARNING = ('WARNING', '⚠️', logging.WARNING)
    ERROR = ('ERROR', '❌', logging.ERROR)
    CRITICAL = ('CRITICAL', '🔥', logging.CRITICAL)


class SejmLogger:
    """
    Custom logger for Sejm Highlights with GUI callback support

    Features:
    - File logging with rotation
    - Console logging with colors
    - GUI callback for real-time updates
    - Stage-based logging
    - Progress tracking
    """

    def __init__(
        self,
        name: str = "SejmHighlights",
        log_dir: Optional[Path] = None,
        console_level: int = logging.INFO,
        file_level: int = logging.DEBUG,
        gui_callback: Optional[Callable] = None
    ):
        """
        Initialize logger

        Args:
            name: Logger name
            log_dir: Directory for log files (None = no file logging)
            console_level: Minimum level for console output
            file_level: Minimum level for file output
            gui_callback: Optional callback for GUI updates (text, level)
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()

        self.gui_callback = gui_callback
        self.current_stage = None
        self.progress_callback = None

        # Console handler with colors
        self._add_console_handler(console_level)

        # File handler with rotation
        if log_dir:
            self._add_file_handler(log_dir, file_level)

    def _add_console_handler(self, level: int):
        """Add console handler with color formatting"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)

        # Color formatter for console
        formatter = ColoredFormatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def _add_file_handler(self, log_dir: Path, level: int):
        """Add file handler with rotation"""
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        # Create log file with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = log_dir / f'sejm_highlights_{timestamp}.log'

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)

        # Detailed formatter for file
        formatter = logging.Formatter(
            '%(asctime)s | %(name)s | %(levelname)-8s | %(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

        self.info(f"📝 Logging to: {log_file}")

    def set_gui_callback(self, callback: Callable):
        """Set GUI callback for real-time updates"""
        self.gui_callback = callback

    def set_progress_callback(self, callback: Callable):
        """Set progress callback for progress bar updates"""
        self.progress_callback = callback

    def set_stage(self, stage: str):
        """Set current pipeline stage"""
        self.current_stage = stage

    def _log(self, level: LogLevel, message: str, *args, **kwargs):
        """Internal logging method with GUI callback"""
        # Format message with args
        if args:
            message = message % args

        # Add stage prefix if set
        if self.current_stage:
            message = f"[{self.current_stage}] {message}"

        # Log to standard logging
        log_method = getattr(self.logger, level.value[0].lower())
        if level == LogLevel.SUCCESS:
            log_method = self.logger.info  # SUCCESS uses INFO level
        log_method(message, **kwargs)

        # Send to GUI callback if set
        if self.gui_callback:
            emoji = level.value[1]
            gui_message = f"{emoji} {message}"
            self.gui_callback(gui_message, level.value[0])

    def debug(self, message: str, *args, **kwargs):
        """Debug level logging"""
        self._log(LogLevel.DEBUG, message, *args, **kwargs)

    def info(self, message: str, *args, **kwargs):
        """Info level logging"""
        self._log(LogLevel.INFO, message, *args, **kwargs)

    def success(self, message: str, *args, **kwargs):
        """Success level logging (INFO with ✅)"""
        self._log(LogLevel.SUCCESS, message, *args, **kwargs)

    def warning(self, message: str, *args, **kwargs):
        """Warning level logging"""
        self._log(LogLevel.WARNING, message, *args, **kwargs)

    def error(self, message: str, *args, **kwargs):
        """Error level logging"""
        self._log(LogLevel.ERROR, message, *args, **kwargs)

    def critical(self, message: str, *args, **kwargs):
        """Critical level logging"""
        self._log(LogLevel.CRITICAL, message, *args, **kwargs)

    def exception(self, message: str, *args, **kwargs):
        """Log exception with traceback"""
        self.logger.exception(message, *args, **kwargs)
        if self.gui_callback:
            self.gui_callback(f"❌ {message}", "ERROR")

    def progress(self, current: int, total: int, message: str = ""):
        """Update progress"""
        percentage = int((current / total) * 100) if total > 0 else 0
        progress_msg = f"Progress: {current}/{total} ({percentage}%)"
        if message:
            progress_msg += f" - {message}"

        self.debug(progress_msg)

        if self.progress_callback:
            self.progress_callback(current, total, message)

    def stage_start(self, stage_name: str, description: str = ""):
        """Log stage start"""
        self.set_stage(stage_name)
        header = f"{'=' * 60}"
        self.info(header)
        self.info(f"🚀 STAGE: {stage_name}")
        if description:
            self.info(f"   {description}")
        self.info(header)

    def stage_end(self, stage_name: str, stats: Optional[dict] = None):
        """Log stage completion"""
        self.success(f"Stage {stage_name} completed")
        if stats:
            for key, value in stats.items():
                self.info(f"   {key}: {value}")
        self.set_stage(None)


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output"""

    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[37m',       # White
        'SUCCESS': '\033[32m',    # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }

    def format(self, record):
        # Add color to level name
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"

        return super().format(record)


# Global logger instance
_global_logger: Optional[SejmLogger] = None


def get_logger(
    name: str = "SejmHighlights",
    log_dir: Optional[Path] = None,
    gui_callback: Optional[Callable] = None
) -> SejmLogger:
    """
    Get or create global logger instance

    Args:
        name: Logger name
        log_dir: Directory for log files
        gui_callback: Optional callback for GUI updates

    Returns:
        SejmLogger instance
    """
    global _global_logger

    if _global_logger is None:
        _global_logger = SejmLogger(
            name=name,
            log_dir=log_dir,
            gui_callback=gui_callback
        )

    return _global_logger


def set_gui_callback(callback: Callable):
    """Set GUI callback on global logger"""
    if _global_logger:
        _global_logger.set_gui_callback(callback)


def set_progress_callback(callback: Callable):
    """Set progress callback on global logger"""
    if _global_logger:
        _global_logger.set_progress_callback(callback)


# Convenience functions using global logger
def debug(message: str, *args, **kwargs):
    """Debug log"""
    logger = get_logger()
    logger.debug(message, *args, **kwargs)


def info(message: str, *args, **kwargs):
    """Info log"""
    logger = get_logger()
    logger.info(message, *args, **kwargs)


def success(message: str, *args, **kwargs):
    """Success log"""
    logger = get_logger()
    logger.success(message, *args, **kwargs)


def warning(message: str, *args, **kwargs):
    """Warning log"""
    logger = get_logger()
    logger.warning(message, *args, **kwargs)


def error(message: str, *args, **kwargs):
    """Error log"""
    logger = get_logger()
    logger.error(message, *args, **kwargs)


def critical(message: str, *args, **kwargs):
    """Critical log"""
    logger = get_logger()
    logger.critical(message, *args, **kwargs)


def exception(message: str, *args, **kwargs):
    """Exception log"""
    logger = get_logger()
    logger.exception(message, *args, **kwargs)
