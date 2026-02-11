from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor, as_completed

from . import hasher
from .image_utils import load_image

logger = logging.getLogger(__name__)

# Default batch size for worker processing
BATCH_SIZE = 20


def _process_image_batch(paths: list[str]) -> tuple[list[dict[str, str]], list[str]]:
    """
    Process a batch of image paths in a worker process.

    Args:
        paths: List of file paths to process

    Returns:
        Tuple of (results, errors) where:
        - results: List of dicts with image_id, path, and hash
        - errors: List of error messages for failed images
    """
    results = []
    errors = []

    for path in paths:
        try:
            image = load_image(path)
            image_id = hashlib.sha256(path.encode("utf-8")).hexdigest()
            hash_value = hasher.hash_image(image)
            results.append(
                {
                    "image_id": image_id,
                    "path": path,
                    "hash": hash_value,
                }
            )
        except Exception as exc:
            error_msg = f"{path}: {exc}"
            errors.append(error_msg)

    return results, errors


def _iter_batches(paths: Iterable[str], batch_size: int) -> Iterator[list[str]]:
    """
    Yield batches of paths as they're discovered.

    Args:
        paths: Iterable of file paths
        batch_size: Number of paths per batch

    Yields:
        Lists of paths, each containing up to batch_size items
    """
    batch = []
    for path in paths:
        batch.append(path)
        if len(batch) >= batch_size:
            yield batch
            batch = []

    # Don't forget final partial batch
    if batch:
        yield batch


def build_index_parallel(
    paths: Iterable[str],
    workers: int = 0,
    batch_size: int = BATCH_SIZE,
) -> tuple[dict[str, dict[str, str]], list[str]]:
    """
    Build image index using parallel processing.

    Args:
        paths: Iterable of image file paths to process
        workers: Number of worker processes (0 = auto detect)
        batch_size: Number of files per batch

    Returns:
        Tuple of (items, errors) where:
        - items: Dict mapping image_id to {path, hash}
        - errors: List of error messages
    """
    # Determine worker count
    max_workers = max(1, (os.cpu_count() or 2) - 1)

    if workers <= 0:
        # Auto-detect: use cpu_count - 1
        workers = max_workers
    else:
        # Always cap at cpu_count - 1, regardless of config
        workers = min(workers, max_workers)

    logger.info(f"Building index with {workers} worker processes (max available: {max_workers})")

    items: dict[str, dict[str, str]] = {}
    all_errors: list[str] = []
    processed_count = 0
    last_logged = 0

    with ProcessPoolExecutor(max_workers=workers) as executor:
        # Submit batches progressively as paths are discovered
        futures = []
        for batch in _iter_batches(paths, batch_size):
            future = executor.submit(_process_image_batch, batch)
            futures.append(future)

        # Collect results as they complete
        for future in as_completed(futures):
            try:
                results, errors = future.result(timeout=300)  # 5 min timeout per batch

                # Aggregate results
                for result in results:
                    image_id = result["image_id"]
                    items[image_id] = {
                        "path": result["path"],
                        "hash": result["hash"],
                    }

                all_errors.extend(errors)
                processed_count += len(results) + len(errors)

                # Log progress every 100 files
                if processed_count // 100 > last_logged:
                    logger.info(f"Processed {processed_count} files...")
                    last_logged = processed_count // 100

            except TimeoutError:
                logger.error("Batch processing timed out")
                all_errors.append("Batch timeout error")
            except Exception as exc:
                logger.error(f"Worker process error: {exc}")
                all_errors.append(f"Worker error: {exc}")

    return items, all_errors
