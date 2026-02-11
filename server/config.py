from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field

DEFAULT_TOP_K = 3
DEFAULT_INCLUDE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"]
DEFAULT_BUILD_WORKERS = 0  # 0 = auto (cpu_count - 1), 1 = sequential, N = parallel with N workers


@dataclass(frozen=True)
class AppConfig:
    data_dir: str
    image_library_dirs: list[str] = field(default_factory=list)
    index_path: str = ""  # Derived from data_dir, not user-configurable
    top_k_default: int = DEFAULT_TOP_K
    include_extensions: list[str] = field(default_factory=lambda: list(DEFAULT_INCLUDE_EXTENSIONS))
    debug_dir: str = ""  # Defaults to data_dir/debug, but overridable in config
    build_workers: int = DEFAULT_BUILD_WORKERS


def _normalize_extensions(exts: Iterable[str]) -> list[str]:
    normalized = []
    for ext in exts:
        if not ext:
            continue
        ext = ext.lower()
        if not ext.startswith("."):
            ext = "." + ext
        normalized.append(ext)
    return normalized


def load_config(data_dir: str | None = None) -> AppConfig:
    """Load configuration from PHOTOLOOKUP_DATA_DIR.

    Args:
        data_dir: Optional override for data directory. If None, uses PHOTOLOOKUP_DATA_DIR env var.

    Returns:
        AppConfig with paths derived from data_dir.

    Raises:
        RuntimeError: If PHOTOLOOKUP_DATA_DIR is not set and data_dir is not provided.
    """
    if data_dir is None:
        data_dir = os.environ.get("PHOTOLOOKUP_DATA_DIR")
        if not data_dir:
            raise RuntimeError(
                "PHOTOLOOKUP_DATA_DIR environment variable is required but not set. "
                "Please set it to the directory containing config.json and index.json."
            )
    config_path = os.path.join(data_dir, "config.json")

    # Default values
    image_library_dirs = []
    top_k_default = DEFAULT_TOP_K
    include_extensions = list(DEFAULT_INCLUDE_EXTENSIONS)
    debug_dir = os.path.join(data_dir, "debug")  # Default to data_dir/debug
    build_workers = DEFAULT_BUILD_WORKERS

    # Load config file if it exists
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as f:
            raw = json.load(f)

        image_library_dirs = raw.get("image_library_dirs") or raw.get("image_library_paths") or []
        top_k_default = int(raw.get("top_k_default", DEFAULT_TOP_K))
        include_extensions = _normalize_extensions(
            raw.get("include_extensions", DEFAULT_INCLUDE_EXTENSIONS)
        )
        build_workers = int(raw.get("build_workers", DEFAULT_BUILD_WORKERS))

        # debug_dir can be overridden in config, otherwise defaults to data_dir/debug
        if "debug_dir" in raw and raw["debug_dir"]:
            debug_dir = raw["debug_dir"]

    # index_path is always derived from data_dir (not configurable)
    index_path = os.path.join(data_dir, "index.json")

    return AppConfig(
        data_dir=data_dir,
        image_library_dirs=list(image_library_dirs),
        index_path=index_path,
        top_k_default=top_k_default,
        include_extensions=include_extensions,
        debug_dir=debug_dir,
        build_workers=build_workers,
    )
