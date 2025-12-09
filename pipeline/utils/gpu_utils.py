"""
GPU Acceleration Utilities
- CUDA detection and fallback logic
- GPU memory management
- Model device placement
"""
import torch
import platform
from typing import Tuple, Optional
from ..logger import get_logger

logger = get_logger()


class GPUManager:
    """
    Manages GPU acceleration with automatic CPU fallback

    Features:
    - CUDA availability detection
    - GPU memory monitoring
    - Automatic fallback to CPU
    - Device selection for models
    """

    def __init__(self):
        self.device = None
        self.cuda_available = False
        self.gpu_name = None
        self.gpu_memory = None

        self._detect_gpu()

    def _detect_gpu(self):
        """Detect GPU and initialize device"""
        self.cuda_available = torch.cuda.is_available()

        if self.cuda_available:
            try:
                self.device = torch.device('cuda:0')
                self.gpu_name = torch.cuda.get_device_name(0)
                self.gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)  # GB

                logger.success(f"🎮 GPU Detected: {self.gpu_name}")
                logger.info(f"   Memory: {self.gpu_memory:.1f} GB")
                logger.info(f"   CUDA Version: {torch.version.cuda}")

                # Test GPU with simple operation
                test_tensor = torch.zeros(1).cuda()
                del test_tensor
                torch.cuda.empty_cache()

                logger.success("   GPU test passed ✓")

            except Exception as e:
                logger.warning(f"GPU detected but failed to initialize: {e}")
                logger.warning("Falling back to CPU")
                self.cuda_available = False
                self.device = torch.device('cpu')
        else:
            self.device = torch.device('cpu')
            logger.info("🖥️  No GPU detected, using CPU")

    def get_device(self) -> torch.device:
        """Get current device (cuda or cpu)"""
        return self.device

    def is_available(self) -> bool:
        """Check if GPU is available"""
        return self.cuda_available

    def get_device_name(self) -> str:
        """Get device name"""
        if self.cuda_available:
            return self.gpu_name or "Unknown GPU"
        return f"CPU ({platform.processor()})"

    def get_memory_info(self) -> Optional[dict]:
        """Get GPU memory information"""
        if not self.cuda_available:
            return None

        try:
            allocated = torch.cuda.memory_allocated(0) / (1024**3)  # GB
            reserved = torch.cuda.memory_reserved(0) / (1024**3)  # GB
            total = self.gpu_memory

            return {
                'allocated_gb': allocated,
                'reserved_gb': reserved,
                'total_gb': total,
                'free_gb': total - reserved,
                'utilization_pct': (reserved / total) * 100 if total > 0 else 0
            }
        except Exception as e:
            logger.error(f"Failed to get GPU memory info: {e}")
            return None

    def clear_cache(self):
        """Clear GPU cache"""
        if self.cuda_available:
            torch.cuda.empty_cache()
            logger.debug("GPU cache cleared")

    def get_optimal_batch_size(self, base_batch_size: int = 10) -> int:
        """
        Get optimal batch size based on available GPU memory

        Args:
            base_batch_size: Default batch size

        Returns:
            Recommended batch size
        """
        if not self.cuda_available:
            return base_batch_size

        mem_info = self.get_memory_info()
        if not mem_info:
            return base_batch_size

        free_gb = mem_info['free_gb']

        # Heuristic: adjust batch size based on available memory
        # Whisper large-v3 needs ~10GB VRAM for batch_size=1
        if free_gb < 8:
            return max(1, base_batch_size // 2)
        elif free_gb > 16:
            return base_batch_size * 2
        else:
            return base_batch_size

    def recommend_whisper_model(self) -> Tuple[str, str]:
        """
        Recommend Whisper model based on available hardware

        Returns:
            (model_name, device_type)
        """
        if not self.cuda_available:
            logger.info("💡 Recommendation: Use 'small' or 'base' model for CPU")
            return "small", "cpu"

        mem_info = self.get_memory_info()
        if not mem_info:
            return "medium", "cuda"

        free_gb = mem_info['free_gb']

        # Whisper model VRAM requirements:
        # - large-v3: ~10GB
        # - medium: ~5GB
        # - small: ~2GB
        # - base: ~1GB

        if free_gb >= 10:
            logger.info("💡 Recommendation: 'large-v3' model fits in GPU memory")
            return "large-v3", "cuda"
        elif free_gb >= 5:
            logger.info("💡 Recommendation: 'medium' model for GPU")
            return "medium", "cuda"
        elif free_gb >= 2:
            logger.info("💡 Recommendation: 'small' model for GPU")
            return "small", "cuda"
        else:
            logger.warning("⚠️ Low GPU memory, falling back to CPU")
            return "small", "cpu"

    def monitor_memory(self):
        """Log current GPU memory usage"""
        mem_info = self.get_memory_info()
        if mem_info:
            logger.debug(
                f"GPU Memory: {mem_info['allocated_gb']:.2f}GB allocated, "
                f"{mem_info['free_gb']:.2f}GB free ({mem_info['utilization_pct']:.1f}% used)"
            )


# Global GPU manager instance
_gpu_manager: Optional[GPUManager] = None


def get_gpu_manager() -> GPUManager:
    """Get or create global GPU manager"""
    global _gpu_manager
    if _gpu_manager is None:
        _gpu_manager = GPUManager()
    return _gpu_manager


def is_cuda_available() -> bool:
    """Check if CUDA is available"""
    return get_gpu_manager().is_available()


def get_device() -> torch.device:
    """Get current device"""
    return get_gpu_manager().get_device()


def get_optimal_device(use_gpu: bool = True) -> str:
    """
    Get optimal device string for models

    Args:
        use_gpu: Whether to prefer GPU (from config)

    Returns:
        'cuda' or 'cpu'
    """
    if not use_gpu:
        return 'cpu'

    manager = get_gpu_manager()
    return 'cuda' if manager.is_available() else 'cpu'


def check_spacy_gpu() -> bool:
    """
    Check if spaCy can use GPU

    Returns:
        True if GPU is available for spaCy
    """
    try:
        import spacy
        has_gpu = spacy.prefer_gpu()
        if has_gpu:
            logger.success("🧠 spaCy GPU acceleration enabled")
        else:
            logger.info("🧠 spaCy using CPU")
        return has_gpu
    except ImportError:
        logger.warning("spaCy not installed")
        return False
    except Exception as e:
        logger.warning(f"Failed to enable spaCy GPU: {e}")
        return False
