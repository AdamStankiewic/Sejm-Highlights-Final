"""
Parallel Processing Utilities
- Multi-process support for CPU-intensive tasks
- Thread pools for I/O operations
- Progress tracking
"""
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from typing import Callable, List, Any, Optional, Dict
from functools import partial
from tqdm import tqdm
from ..logger import get_logger

logger = get_logger()


class ParallelProcessor:
    """
    Parallel processing manager for pipeline stages

    Features:
    - Process pools for CPU-intensive tasks (VAD, features)
    - Thread pools for I/O tasks (file operations)
    - Progress tracking
    - Error handling and recovery
    """

    def __init__(
        self,
        max_workers: Optional[int] = None,
        use_processes: bool = True
    ):
        """
        Initialize parallel processor

        Args:
            max_workers: Number of workers (None = CPU count)
            use_processes: Use processes (True) or threads (False)
        """
        if max_workers is None:
            max_workers = max(1, mp.cpu_count() - 1)  # Leave 1 core free

        self.max_workers = max_workers
        self.use_processes = use_processes

        logger.info(f"⚙️  Parallel processor initialized")
        logger.info(f"   Workers: {max_workers}")
        logger.info(f"   Mode: {'Processes' if use_processes else 'Threads'}")

    def map(
        self,
        func: Callable,
        items: List[Any],
        desc: str = "Processing",
        show_progress: bool = True,
        chunk_size: int = 1,
        **kwargs
    ) -> List[Any]:
        """
        Apply function to items in parallel

        Args:
            func: Function to apply
            items: List of items to process
            desc: Progress bar description
            show_progress: Show progress bar
            chunk_size: Chunk size for batching
            **kwargs: Additional arguments to pass to func

        Returns:
            List of results (in order)
        """
        if not items:
            return []

        # Use partial to bind kwargs to function
        if kwargs:
            func = partial(func, **kwargs)

        # Choose executor
        ExecutorClass = ProcessPoolExecutor if self.use_processes else ThreadPoolExecutor

        results = []

        try:
            with ExecutorClass(max_workers=self.max_workers) as executor:
                # Submit all tasks
                futures = {executor.submit(func, item): i for i, item in enumerate(items)}

                # Collect results with progress bar
                if show_progress:
                    with tqdm(total=len(items), desc=desc) as pbar:
                        for future in as_completed(futures):
                            idx = futures[future]
                            try:
                                result = future.result()
                                results.append((idx, result))
                                pbar.update(1)
                            except Exception as e:
                                logger.error(f"Task {idx} failed: {e}")
                                results.append((idx, None))
                                pbar.update(1)
                else:
                    for future in as_completed(futures):
                        idx = futures[future]
                        try:
                            result = future.result()
                            results.append((idx, result))
                        except Exception as e:
                            logger.error(f"Task {idx} failed: {e}")
                            results.append((idx, None))

        except Exception as e:
            logger.error(f"Parallel processing failed: {e}")
            return []

        # Sort results by original index
        results.sort(key=lambda x: x[0])
        return [r[1] for r in results]

    def map_batch(
        self,
        func: Callable,
        items: List[Any],
        batch_size: int,
        desc: str = "Processing batches",
        show_progress: bool = True,
        **kwargs
    ) -> List[Any]:
        """
        Apply function to batches of items in parallel

        Args:
            func: Function to apply (receives list of items)
            items: List of items to process
            batch_size: Size of each batch
            desc: Progress bar description
            show_progress: Show progress bar
            **kwargs: Additional arguments to pass to func

        Returns:
            Flattened list of results
        """
        # Create batches
        batches = [items[i:i + batch_size] for i in range(0, len(items), batch_size)]

        logger.debug(f"Created {len(batches)} batches of size {batch_size}")

        # Process batches in parallel
        batch_results = self.map(
            func=func,
            items=batches,
            desc=desc,
            show_progress=show_progress,
            chunk_size=1,
            **kwargs
        )

        # Flatten results
        results = []
        for batch_result in batch_results:
            if batch_result:
                if isinstance(batch_result, list):
                    results.extend(batch_result)
                else:
                    results.append(batch_result)

        return results


def parallel_vad_segments(
    audio_segments: List[Dict],
    vad_model: Any,
    sample_rate: int = 16000
) -> List[Dict]:
    """
    Process VAD segments in parallel

    Args:
        audio_segments: List of audio segment dicts with 'audio' and 'offset'
        vad_model: VAD model instance
        sample_rate: Audio sample rate

    Returns:
        List of VAD results
    """

    def process_segment(segment: Dict) -> Dict:
        """Process single segment through VAD"""
        try:
            audio = segment['audio']
            offset = segment['offset']

            # Run VAD
            speech_timestamps = vad_model(audio, sample_rate)

            # Adjust timestamps by offset
            for ts in speech_timestamps:
                ts['start'] += offset
                ts['end'] += offset

            return {
                'offset': offset,
                'timestamps': speech_timestamps,
                'success': True
            }

        except Exception as e:
            logger.error(f"VAD failed for segment at {segment['offset']}: {e}")
            return {
                'offset': segment['offset'],
                'timestamps': [],
                'success': False
            }

    # Process in parallel
    processor = ParallelProcessor(use_processes=True)
    results = processor.map(
        func=process_segment,
        items=audio_segments,
        desc="VAD Processing",
        show_progress=True
    )

    return results


def parallel_feature_extraction(
    segments: List[Dict],
    feature_extractor: Callable,
    audio_data: Any,
    sample_rate: int = 16000
) -> List[Dict]:
    """
    Extract features from segments in parallel

    Args:
        segments: List of segment dicts
        feature_extractor: Feature extraction function
        audio_data: Audio data array
        sample_rate: Sample rate

    Returns:
        List of segments with features
    """

    def extract_for_segment(segment: Dict) -> Dict:
        """Extract features for single segment"""
        try:
            features = feature_extractor(
                segment=segment,
                audio=audio_data,
                sr=sample_rate
            )

            return {**segment, 'features': features}

        except Exception as e:
            logger.error(f"Feature extraction failed for segment: {e}")
            return segment

    # Process in parallel
    processor = ParallelProcessor(use_processes=True)
    enriched_segments = processor.map(
        func=extract_for_segment,
        items=segments,
        desc="Feature Extraction",
        show_progress=True
    )

    return enriched_segments


def parallel_video_chunks(
    video_path: str,
    chunks: List[Dict],
    processing_func: Callable
) -> List[Any]:
    """
    Process video chunks in parallel

    Args:
        video_path: Path to video file
        chunks: List of chunk dicts with 'start' and 'end' times
        processing_func: Function to process each chunk

    Returns:
        List of processing results
    """

    def process_chunk(chunk: Dict) -> Any:
        """Process single video chunk"""
        try:
            result = processing_func(
                video_path=video_path,
                start_time=chunk['start'],
                end_time=chunk['end']
            )
            return result

        except Exception as e:
            logger.error(f"Chunk processing failed ({chunk['start']}-{chunk['end']}): {e}")
            return None

    # Process in parallel
    processor = ParallelProcessor(use_processes=True)
    results = processor.map(
        func=process_chunk,
        items=chunks,
        desc="Processing video chunks",
        show_progress=True
    )

    return results


def get_optimal_worker_count(task_type: str = "cpu") -> int:
    """
    Get optimal number of workers for task type

    Args:
        task_type: 'cpu', 'io', or 'mixed'

    Returns:
        Recommended worker count
    """
    cpu_count = mp.cpu_count()

    if task_type == "cpu":
        # CPU-bound: Use CPU count - 1
        return max(1, cpu_count - 1)
    elif task_type == "io":
        # I/O-bound: Can use more workers
        return cpu_count * 2
    else:
        # Mixed: Use CPU count
        return cpu_count
