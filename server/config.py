from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Iterable


DEFAULT_CONFIG_PATH = os.environ.get(
    "PHOTOLOOKUP_CONFIG",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "config.json"),
)
DEFAULT_TOP_K = 3
DEFAULT_INDEX_PATH = "config/index.json"
DEFAULT_INCLUDE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"]
DEFAULT_DEBUG_DIR = ""
DEFAULT_BUILD_WORKERS = 0  # 0 = auto (cpu_count - 1), 1 = sequential, N = parallel with N workers


@dataclass(frozen=True)
class AppConfig:
    image_library_dirs: list[str] = field(default_factory=list)
    index_path: str = DEFAULT_INDEX_PATH
    top_k_default: int = DEFAULT_TOP_K
    include_extensions: list[str] = field(default_factory=lambda: list(DEFAULT_INCLUDE_EXTENSIONS))
    debug_dir: str = DEFAULT_DEBUG_DIR
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


def load_config(path: str | None = None) -> AppConfig:
    cfg_path = path or DEFAULT_CONFIG_PATH
    if not os.path.exists(cfg_path):
        return AppConfig()

    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    image_library_dirs = raw.get("image_library_dirs") or raw.get("image_library_paths") or []
    index_path = raw.get("index_path", DEFAULT_INDEX_PATH)
    top_k_default = int(raw.get("top_k_default", DEFAULT_TOP_K))
    include_extensions = _normalize_extensions(raw.get("include_extensions", DEFAULT_INCLUDE_EXTENSIONS))
    debug_dir = raw.get("debug_dir", DEFAULT_DEBUG_DIR)
    build_workers = int(raw.get("build_workers", DEFAULT_BUILD_WORKERS))

    return AppConfig(
        image_library_dirs=list(image_library_dirs),
        index_path=index_path,
        top_k_default=top_k_default,
        include_extensions=include_extensions,
        debug_dir=debug_dir,
        build_workers=build_workers,
    )
