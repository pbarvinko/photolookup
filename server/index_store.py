from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from PIL import Image, ImageOps

from .config import AppConfig
from .phash_engine import compute_distance, create_hash, get_hash_meta

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageInfo:
    image_id: str
    path: str
    hash: str


class IndexStore:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._index_path = config.index_path
        self._meta: dict[str, object] | None = None
        self._items: dict[str, dict[str, str]] | None = None

    def init(self) -> None:
        if self._items is None:
            self._load()

    def is_loaded(self) -> bool:
        return self._items is not None and self._meta is not None

    def build(self) -> IndexData:
        """Build the image index using parallel or sequential processing based on config."""
        # Log each top-level directory
        for lib_dir in self._config.image_library_dirs:
            logger.info(f"Processing directory: {lib_dir}")

        # Choose between parallel and sequential based on config
        if self._config.build_workers == 1:
            logger.info("Using sequential processing (build_workers=1)")
            items, errors = self._build_sequential()
        else:
            try:
                from .index_builder import build_index_parallel

                paths = _iter_image_files(
                    self._config.image_library_dirs,
                    self._config.include_extensions
                )
                items, errors = build_index_parallel(
                    paths,
                    workers=self._config.build_workers
                )
            except Exception as exc:
                logger.warning(f"Parallel processing failed ({exc}), falling back to sequential")
                items, errors = self._build_sequential()

        # Log total
        logger.info(f"Index building complete: {len(items)} files processed, {len(errors)} errors")
        if errors:
            logger.warning(f"Encountered {len(errors)} errors during indexing")

        # Create metadata
        meta = {
            "hash": get_hash_meta(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "library_dirs": list(self._config.image_library_dirs),
            "errors": errors,
        }

        self._meta = meta
        self._items = items
        self._save()
        return self.get_index()

    def _build_sequential(self) -> tuple[dict[str, dict[str, str]], list[str]]:
        """Sequential implementation of index building (original algorithm)."""
        items: dict[str, dict[str, str]] = {}
        errors: list[str] = []
        processed_count = 0

        for path in _iter_image_files(self._config.image_library_dirs, self._config.include_extensions):
            try:
                image = _load_image(path)
                image_id = hashlib.sha256(path.encode("utf-8")).hexdigest()
                items[image_id] = {
                    "path": path,
                    "hash": _hash_image(image),
                }
                processed_count += 1

                # Log progress every 100 files
                if processed_count % 100 == 0:
                    logger.info(f"Processed {processed_count} files...")

            except Exception as exc:
                error_msg = f"{path}: {exc}"
                errors.append(error_msg)
                logger.error(f"Failed to process image: {error_msg}")

        return items, errors

    def get_index(self) -> "IndexData":
        if not self.is_loaded():
            raise ValueError("Index not loaded.")
        return IndexData(meta=self._meta or {}, items=self._items or {})

    def get_image_info(self, image_id: str) -> ImageInfo | None:
        if not self.is_loaded():
            return None
        item = self._items.get(image_id) if self._items else None
        if item is None:
            return None
        return ImageInfo(image_id=image_id, path=item["path"], hash=item["hash"])

    def get_count(self) -> int:
        return len(self._items) if self._items is not None else 0

    def lookup_matches(self, query_hash: str, top_k: int) -> list[dict[str, object]]:
        if not self.is_loaded():
            return []
        results: list[dict[str, object]] = []
        for image_id, item in (self._items or {}).items():
            hash_value = item["hash"]
            distance = compute_distance(query_hash, hash_value)
            results.append({"id": image_id, "path": item["path"], "distance": distance})

        results.sort(key=lambda item: item["distance"])
        return results[:top_k]

    def get_image_blob(self, image_id: str) -> tuple[bytes, str] | None:
        info = self.get_image_info(image_id)
        if info is None:
            return None
        if not os.path.exists(info.path):
            logger.warning(f"Image file not found: {info.path} (id: {image_id})")
            return None
        try:
            media_type = mimetypes.guess_type(info.path)[0] or "application/octet-stream"
            with open(info.path, "rb") as f:
                return f.read(), media_type
        except Exception as exc:
            logger.error(f"Failed to read image file {info.path}: {exc}")
            return None

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._index_path) or ".", exist_ok=True)
            payload = {"meta": self._meta or {}, "items": self._items or {}}
            with open(self._index_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, sort_keys=True)
            logger.info(f"Saved index to {self._index_path}")
        except Exception as exc:
            logger.error(f"Failed to save index to {self._index_path}: {exc}")
            raise

    def _load(self) -> None:
        if not os.path.exists(self._index_path):
            logger.info(f"Index file not found: {self._index_path}")
            return
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            self._meta = payload.get("meta", {})
            self._items = payload.get("items", {})
            logger.info(f"Loaded index with {len(self._items)} images from {self._index_path}")
        except Exception as exc:
            logger.error(f"Failed to load index from {self._index_path}: {exc}")
            raise


def _iter_image_files(paths: Iterable[str], extensions: Iterable[str]) -> Iterable[str]:
    ext_set = {ext.lower() for ext in extensions}
    for base in paths:
        if not base:
            continue
        base = os.path.expanduser(base)
        if os.path.isfile(base):
            _, ext = os.path.splitext(base)
            if ext.lower() in ext_set:
                yield base
            continue
        for root, _, files in os.walk(base):
            for name in files:
                _, ext = os.path.splitext(name)
                if ext.lower() not in ext_set:
                    continue
                yield os.path.join(root, name)


def _load_image(path: str) -> Image.Image:
    return ImageOps.exif_transpose(Image.open(path))


def _hash_image(image: Image.Image) -> str:
    return create_hash(image, bbox=None)


@dataclass(frozen=True)
class IndexData:
    meta: dict[str, object]
    items: dict[str, dict[str, str]]
