"""
Caching System for Transcriptions and Intermediate Results
- Pickle-based caching
- Cache invalidation
- Storage optimization
"""
import pickle
import hashlib
import json
from pathlib import Path
from typing import Any, Optional, Dict
from datetime import datetime, timedelta
from ..logger import get_logger

logger = get_logger()


class CacheManager:
    """
    Manages caching of expensive operations (transcription, features, etc.)

    Features:
    - Pickle serialization
    - Hash-based cache keys
    - Automatic expiration
    - Cache size management
    """

    def __init__(
        self,
        cache_dir: Path,
        max_age_days: int = 30,
        max_size_gb: float = 10.0
    ):
        """
        Initialize cache manager

        Args:
            cache_dir: Directory for cache files
            max_age_days: Maximum cache age in days
            max_size_gb: Maximum cache size in GB
        """
        self.cache_dir = Path(cache_dir)
        self.max_age_days = max_age_days
        self.max_size_gb = max_size_gb

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"💾 Cache directory: {self.cache_dir}")

    def _get_cache_key(self, identifier: str, params: Optional[Dict] = None) -> str:
        """
        Generate cache key from identifier and parameters

        Args:
            identifier: Base identifier (e.g., video file path)
            params: Optional parameters that affect the result

        Returns:
            Cache key hash
        """
        # Combine identifier with sorted params
        cache_string = identifier

        if params:
            # Sort params for consistent hashing
            sorted_params = json.dumps(params, sort_keys=True)
            cache_string += sorted_params

        # Generate SHA256 hash
        hash_obj = hashlib.sha256(cache_string.encode('utf-8'))
        return hash_obj.hexdigest()[:16]  # First 16 chars

    def _get_cache_path(self, cache_key: str, cache_type: str) -> Path:
        """Get cache file path"""
        filename = f"{cache_type}_{cache_key}.pkl"
        return self.cache_dir / filename

    def _get_metadata_path(self, cache_key: str, cache_type: str) -> Path:
        """Get metadata file path"""
        filename = f"{cache_type}_{cache_key}.meta"
        return self.cache_dir / filename

    def has_cache(self, identifier: str, cache_type: str, params: Optional[Dict] = None) -> bool:
        """
        Check if cache exists and is valid

        Args:
            identifier: Cache identifier
            cache_type: Type of cache (e.g., 'transcription', 'features')
            params: Optional parameters

        Returns:
            True if valid cache exists
        """
        cache_key = self._get_cache_key(identifier, params)
        cache_path = self._get_cache_path(cache_key, cache_type)
        meta_path = self._get_metadata_path(cache_key, cache_type)

        if not cache_path.exists() or not meta_path.exists():
            return False

        # Check expiration
        try:
            with open(meta_path, 'r') as f:
                metadata = json.load(f)

            created_at = datetime.fromisoformat(metadata['created_at'])
            age = datetime.now() - created_at

            if age > timedelta(days=self.max_age_days):
                logger.debug(f"Cache expired: {cache_key} (age: {age.days} days)")
                return False

            return True

        except Exception as e:
            logger.warning(f"Failed to read cache metadata: {e}")
            return False

    def get(self, identifier: str, cache_type: str, params: Optional[Dict] = None) -> Optional[Any]:
        """
        Retrieve cached data

        Args:
            identifier: Cache identifier
            cache_type: Type of cache
            params: Optional parameters

        Returns:
            Cached data or None
        """
        if not self.has_cache(identifier, cache_type, params):
            return None

        cache_key = self._get_cache_key(identifier, params)
        cache_path = self._get_cache_path(cache_key, cache_type)

        try:
            with open(cache_path, 'rb') as f:
                data = pickle.load(f)

            logger.success(f"✓ Cache hit: {cache_type}/{cache_key}")
            return data

        except Exception as e:
            logger.error(f"Failed to load cache: {e}")
            return None

    def set(
        self,
        identifier: str,
        cache_type: str,
        data: Any,
        params: Optional[Dict] = None,
        metadata: Optional[Dict] = None
    ):
        """
        Save data to cache

        Args:
            identifier: Cache identifier
            cache_type: Type of cache
            data: Data to cache
            params: Optional parameters
            metadata: Optional additional metadata
        """
        cache_key = self._get_cache_key(identifier, params)
        cache_path = self._get_cache_path(cache_key, cache_type)
        meta_path = self._get_metadata_path(cache_key, cache_type)

        try:
            # Save data
            with open(cache_path, 'wb') as f:
                pickle.dump(data, f, protocol=pickle.HIGHEST_PROTOCOL)

            # Save metadata
            meta_data = {
                'created_at': datetime.now().isoformat(),
                'identifier': identifier,
                'cache_type': cache_type,
                'params': params or {},
                'file_size_mb': cache_path.stat().st_size / (1024 * 1024)
            }

            if metadata:
                meta_data.update(metadata)

            with open(meta_path, 'w') as f:
                json.dump(meta_data, f, indent=2)

            logger.success(f"💾 Cached {cache_type}: {cache_key} ({meta_data['file_size_mb']:.2f} MB)")

            # Check cache size and cleanup if needed
            self._cleanup_if_needed()

        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def invalidate(self, identifier: str, cache_type: str, params: Optional[Dict] = None):
        """
        Invalidate (delete) cache

        Args:
            identifier: Cache identifier
            cache_type: Type of cache
            params: Optional parameters
        """
        cache_key = self._get_cache_key(identifier, params)
        cache_path = self._get_cache_path(cache_key, cache_type)
        meta_path = self._get_metadata_path(cache_key, cache_type)

        try:
            if cache_path.exists():
                cache_path.unlink()
            if meta_path.exists():
                meta_path.unlink()

            logger.info(f"🗑️  Cache invalidated: {cache_type}/{cache_key}")

        except Exception as e:
            logger.error(f"Failed to invalidate cache: {e}")

    def _cleanup_if_needed(self):
        """Cleanup old cache files if size exceeds limit"""
        total_size_gb = self._get_total_size()

        if total_size_gb > self.max_size_gb:
            logger.warning(f"Cache size ({total_size_gb:.2f} GB) exceeds limit ({self.max_size_gb} GB)")
            self._cleanup_old_caches()

    def _get_total_size(self) -> float:
        """Get total cache size in GB"""
        total_bytes = sum(f.stat().st_size for f in self.cache_dir.glob('*.pkl'))
        return total_bytes / (1024**3)

    def _cleanup_old_caches(self):
        """Remove oldest caches until size is under limit"""
        # Get all cache files with their metadata
        cache_files = []

        for cache_path in self.cache_dir.glob('*.pkl'):
            meta_path = cache_path.with_suffix('.meta')

            if meta_path.exists():
                try:
                    with open(meta_path, 'r') as f:
                        metadata = json.load(f)

                    created_at = datetime.fromisoformat(metadata['created_at'])
                    cache_files.append((cache_path, meta_path, created_at))

                except Exception:
                    pass

        # Sort by creation time (oldest first)
        cache_files.sort(key=lambda x: x[2])

        # Remove oldest files until size is acceptable
        removed_count = 0
        for cache_path, meta_path, _ in cache_files:
            cache_path.unlink()
            meta_path.unlink()
            removed_count += 1

            if self._get_total_size() <= self.max_size_gb * 0.8:  # 80% of limit
                break

        logger.info(f"🗑️  Cleaned up {removed_count} old cache files")

    def get_stats(self) -> Dict:
        """Get cache statistics"""
        cache_files = list(self.cache_dir.glob('*.pkl'))
        total_size = self._get_total_size()

        # Count by type
        types = {}
        for f in cache_files:
            cache_type = f.stem.split('_')[0]
            types[cache_type] = types.get(cache_type, 0) + 1

        return {
            'total_files': len(cache_files),
            'total_size_gb': total_size,
            'by_type': types,
            'cache_dir': str(self.cache_dir)
        }

    def clear_all(self):
        """Clear all cache"""
        count = 0
        for f in self.cache_dir.glob('*'):
            f.unlink()
            count += 1

        logger.warning(f"🗑️  Cleared all cache ({count} files)")


# Global cache manager
_cache_manager: Optional[CacheManager] = None


def get_cache_manager(cache_dir: Optional[Path] = None) -> CacheManager:
    """Get or create global cache manager"""
    global _cache_manager

    if _cache_manager is None:
        if cache_dir is None:
            cache_dir = Path.cwd() / 'cache'

        _cache_manager = CacheManager(cache_dir)

    return _cache_manager
