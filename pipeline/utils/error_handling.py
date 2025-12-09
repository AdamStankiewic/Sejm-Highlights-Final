"""
Enhanced Error Handling
- Custom exceptions
- Error recovery strategies
- User-friendly error messages
"""
from typing import Optional, Callable, Any
from functools import wraps
import traceback
from ..logger import get_logger

logger = get_logger()


# Custom Exceptions
class SejmHighlightsError(Exception):
    """Base exception for Sejm Highlights application"""
    def __init__(self, message: str, details: Optional[str] = None):
        self.message = message
        self.details = details
        super().__init__(self.message)


class VideoProcessingError(SejmHighlightsError):
    """Error during video processing"""
    pass


class AudioExtractionError(SejmHighlightsError):
    """Error during audio extraction"""
    pass


class TranscriptionError(SejmHighlightsError):
    """Error during transcription"""
    pass


class FeatureExtractionError(SejmHighlightsError):
    """Error during feature extraction"""
    pass


class ScoringError(SejmHighlightsError):
    """Error during scoring"""
    pass


class SelectionError(SejmHighlightsError):
    """Error during clip selection"""
    pass


class ExportError(SejmHighlightsError):
    """Error during video export"""
    pass


class ConfigurationError(SejmHighlightsError):
    """Error in configuration"""
    pass


class ValidationError(SejmHighlightsError):
    """Error during validation"""
    pass


# Error Handler Decorator
def handle_stage_errors(stage_name: str, recovery_strategy: Optional[Callable] = None):
    """
    Decorator for handling errors in pipeline stages

    Args:
        stage_name: Name of the stage
        recovery_strategy: Optional function to attempt recovery
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)

            except SejmHighlightsError as e:
                # Custom exception - already formatted
                logger.error(f"❌ {stage_name} failed: {e.message}")
                if e.details:
                    logger.error(f"   Details: {e.details}")

                # Attempt recovery if strategy provided
                if recovery_strategy:
                    logger.info("🔄 Attempting recovery...")
                    try:
                        return recovery_strategy(*args, **kwargs)
                    except Exception as recovery_error:
                        logger.error(f"❌ Recovery failed: {recovery_error}")

                raise

            except FileNotFoundError as e:
                error_msg = f"File not found in {stage_name}"
                logger.error(f"❌ {error_msg}: {e}")
                raise SejmHighlightsError(error_msg, str(e))

            except MemoryError as e:
                error_msg = f"Out of memory in {stage_name}"
                logger.error(f"❌ {error_msg}")
                logger.error("   Try: Close other applications, use smaller video, or enable Smart Splitter")
                raise SejmHighlightsError(error_msg, "Insufficient RAM")

            except KeyboardInterrupt:
                logger.warning(f"⚠️ {stage_name} interrupted by user")
                raise

            except Exception as e:
                # Unexpected error
                error_msg = f"Unexpected error in {stage_name}"
                logger.error(f"❌ {error_msg}: {type(e).__name__}: {e}")
                logger.debug(f"Traceback: {traceback.format_exc()}")
                raise SejmHighlightsError(error_msg, str(e))

        return wrapper
    return decorator


def safe_execute(
    func: Callable,
    error_message: str,
    default_return: Any = None,
    raise_on_error: bool = False
) -> Any:
    """
    Safely execute a function with error handling

    Args:
        func: Function to execute
        error_message: Error message to log
        default_return: Value to return on error
        raise_on_error: Whether to raise exception on error

    Returns:
        Function result or default_return on error
    """
    try:
        return func()
    except Exception as e:
        logger.error(f"❌ {error_message}: {e}")
        if raise_on_error:
            raise
        return default_return


def get_user_friendly_error_message(error: Exception) -> str:
    """
    Convert technical error to user-friendly message

    Args:
        error: Exception object

    Returns:
        User-friendly error message
    """
    error_type = type(error).__name__
    error_str = str(error)

    # Common error patterns
    if "CUDA out of memory" in error_str:
        return (
            "Brak pamięci GPU. Spróbuj:\n"
            "• Użyj mniejszego modelu Whisper (small zamiast large-v3)\n"
            "• Zmniejsz batch size\n"
            "• Zamknij inne aplikacje używające GPU"
        )

    elif "No such file" in error_str or isinstance(error, FileNotFoundError):
        return f"Nie znaleziono pliku: {error_str}"

    elif "ffmpeg" in error_str.lower():
        return (
            "Błąd FFmpeg. Sprawdź:\n"
            "• Czy FFmpeg jest zainstalowany\n"
            "• Czy plik wideo nie jest uszkodzony\n"
            "• Czy masz uprawnienia do zapisu"
        )

    elif "OPENAI_API_KEY" in error_str:
        return (
            "Brak klucza API OpenAI. Dodaj OPENAI_API_KEY do pliku .env\n"
            "Lub wyłącz GPT scoring w konfiguracji"
        )

    elif isinstance(error, MemoryError):
        return (
            "Brak pamięci RAM. Spróbuj:\n"
            "• Zamknij inne aplikacje\n"
            "• Użyj krótszego wideo\n"
            "• Włącz Smart Splitter dla długich materiałów"
        )

    elif "spacy" in error_str.lower():
        return (
            "Błąd spaCy. Zainstaluj model polskiego:\n"
            "python -m spacy download pl_core_news_lg"
        )

    elif "timeout" in error_str.lower():
        return "Operacja przekroczyła limit czasu. Spróbuj ponownie lub użyj mniejszego pliku."

    else:
        # Generic message
        return f"Wystąpił błąd: {error_type}\n{error_str}"


class ErrorRecovery:
    """Strategies for error recovery"""

    @staticmethod
    def retry_with_smaller_batch(func: Callable, max_retries: int = 3) -> Any:
        """
        Retry function with progressively smaller batch sizes

        Args:
            func: Function to retry (should accept batch_size kwarg)
            max_retries: Maximum retry attempts

        Returns:
            Function result
        """
        batch_sizes = [10, 5, 2, 1]

        for i, batch_size in enumerate(batch_sizes[:max_retries]):
            try:
                logger.info(f"🔄 Retry {i+1}/{max_retries} with batch_size={batch_size}")
                return func(batch_size=batch_size)
            except Exception as e:
                if i == max_retries - 1:
                    raise
                logger.warning(f"⚠️ Failed with batch_size={batch_size}: {e}")
                continue

    @staticmethod
    def fallback_to_cpu(func: Callable) -> Any:
        """
        Retry function with CPU instead of GPU

        Args:
            func: Function to retry (should accept device kwarg)

        Returns:
            Function result
        """
        try:
            return func(device='cuda')
        except Exception as e:
            logger.warning(f"⚠️ GPU failed: {e}")
            logger.info("🔄 Retrying with CPU...")
            return func(device='cpu')

    @staticmethod
    def skip_and_continue(items: list, process_func: Callable) -> list:
        """
        Process items, skipping failures

        Args:
            items: List of items to process
            process_func: Function to process each item

        Returns:
            List of successful results
        """
        results = []
        failed_count = 0

        for i, item in enumerate(items):
            try:
                result = process_func(item)
                results.append(result)
            except Exception as e:
                logger.warning(f"⚠️ Item {i} failed: {e}. Skipping...")
                failed_count += 1

        if failed_count > 0:
            logger.warning(f"⚠️ {failed_count}/{len(items)} items failed")

        return results


def create_error_report(error: Exception, context: dict) -> dict:
    """
    Create detailed error report for debugging

    Args:
        error: Exception object
        context: Context dictionary (config, stage, etc.)

    Returns:
        Error report dict
    """
    return {
        'error_type': type(error).__name__,
        'error_message': str(error),
        'traceback': traceback.format_exc(),
        'context': context,
        'user_friendly_message': get_user_friendly_error_message(error)
    }
