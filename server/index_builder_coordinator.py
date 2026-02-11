from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from .index_store import IndexStore

logger = logging.getLogger(__name__)


class BuildStatus(str, Enum):
    """Status of an index build task."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class BuildProgress:
    """Progress information for an index build task."""

    operation: str  # "build" | "update"
    status: BuildStatus
    progress: int  # files processed so far
    total: int | None  # total files (None if unknown during streaming)
    started_at: str  # ISO timestamp
    completed_at: str | None = None
    error: str | None = None
    result: dict | None = None  # final IndexData meta on completion


class IndexBuilderCoordinator:
    """
    Manages async index building operations.

    Ensures only one build runs at a time and provides progress tracking.
    """

    def __init__(self, index_store: IndexStore) -> None:
        self._index_store = index_store
        self._current_task: BuildProgress | None = None
        self._task_lock = threading.Lock()
        self._background_thread: threading.Thread | None = None

    def start_build(self, rebuild: bool) -> BuildProgress:
        """
        Start an async index build or update operation.

        Args:
            rebuild: If True, rebuild from scratch. If False, incremental update.

        Returns:
            BuildProgress with initial state

        Raises:
            RuntimeError: If a build is already in progress
        """
        with self._task_lock:
            # Check if build already running
            if self._current_task is not None and self._current_task.status == BuildStatus.RUNNING:
                raise RuntimeError("Build already in progress")

            # Create new task
            operation = "build" if rebuild else "update"
            task = BuildProgress(
                operation=operation,
                status=BuildStatus.RUNNING,
                progress=0,
                total=None,
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            self._current_task = task

            # Start background thread
            self._background_thread = threading.Thread(
                target=self._run_build_task,
                args=(rebuild,),
                daemon=False,
            )
            self._background_thread.start()

            return task

    def get_status(self) -> BuildProgress | None:
        """
        Get current build status.

        Returns:
            BuildProgress if a task exists (running or completed), None otherwise
        """
        with self._task_lock:
            return self._current_task

    def _run_build_task(self, rebuild: bool) -> None:
        """
        Background thread function that runs the actual build.

        Args:
            rebuild: If True, rebuild from scratch. If False, incremental update.
        """
        try:
            logger.info(f"Background build started: {'rebuild' if rebuild else 'update'}")

            # Progress callback
            def on_progress(count: int) -> None:
                with self._task_lock:
                    if self._current_task:
                        self._current_task.progress = count

            # Run build or update
            if rebuild:
                result = self._index_store.build(progress_callback=on_progress)
            else:
                result = self._index_store.update(progress_callback=on_progress)

            # Mark as completed
            with self._task_lock:
                if self._current_task:
                    self._current_task.status = BuildStatus.COMPLETED
                    self._current_task.completed_at = datetime.now(timezone.utc).isoformat()
                    self._current_task.total = self._index_store.get_count()
                    self._current_task.progress = self._current_task.total
                    self._current_task.result = result.meta

            logger.info(f"Background build completed: {self._index_store.get_count()} images")

        except Exception as exc:
            logger.error(f"Background build failed: {exc}", exc_info=True)

            # Mark as failed
            with self._task_lock:
                if self._current_task:
                    self._current_task.status = BuildStatus.FAILED
                    self._current_task.completed_at = datetime.now(timezone.utc).isoformat()
                    self._current_task.error = str(exc)

    def wait_for_completion(self, timeout: float | None = None) -> bool:
        """
        Wait for current build to complete (for graceful shutdown).

        Args:
            timeout: Maximum time to wait in seconds, None for no timeout

        Returns:
            True if build completed within timeout, False otherwise
        """
        if self._background_thread is None:
            return True

        self._background_thread.join(timeout=timeout)
        return not self._background_thread.is_alive()
