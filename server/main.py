from __future__ import annotations

import json
import logging
import os
import random
import string
from io import BytesIO
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
from pydantic import BaseModel

from . import hasher
from .config import AppConfig, load_config
from .image_detection_engine import detect_main_image
from .index_builder_coordinator import IndexBuilderCoordinator
from .index_store import IndexStore

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


app = FastAPI(title="PhotoLookup", version="0.1.0")

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
VERSION_FILE = os.path.join(os.path.dirname(__file__), "..", "VERSION")


def _read_version() -> str:
    """Read version from VERSION file."""
    try:
        with open(VERSION_FILE, encoding="utf-8") as f:
            return f.read().strip()
    except Exception as exc:
        logger.warning(f"Failed to read VERSION file: {exc}")
        return "unknown"


_VERSION = _read_version()


class NoCacheStaticFiles(StaticFiles):
    def set_stat_headers(self, response, path, stat_result):  # type: ignore[override]
        super().set_stat_headers(response, path, stat_result)
        response.headers["Cache-Control"] = "no-store"


app.mount("/assets", NoCacheStaticFiles(directory=WEB_DIR), name="assets")


class LookupResponse(BaseModel):
    query_hash: str
    matches: list[dict[str, Any]]
    count: int
    index_meta: dict[str, Any]


class BBoxResponse(BaseModel):
    bbox: tuple[int, int, int, int]


def _load_app_config() -> AppConfig:
    data_dir = os.environ.get("PHOTOLOOKUP_DATA_DIR")
    return load_config(data_dir)


_CONFIG = _load_app_config()
_INDEX_STORE = IndexStore(_CONFIG)
_INDEX_COORDINATOR = IndexBuilderCoordinator(_INDEX_STORE)


@app.on_event("startup")
def _load_index_on_startup() -> None:
    logger.info("Loading index on startup...")
    _INDEX_STORE.init()
    if _INDEX_STORE.is_loaded():
        logger.info(f"Index loaded successfully: {_INDEX_STORE.get_count()} images")
    else:
        logger.warning("No index found. Build index to enable lookups.")


@app.on_event("shutdown")
def _shutdown() -> None:
    logger.info("Shutting down server...")
    # Wait for build to complete with 30 second timeout
    if _INDEX_COORDINATOR.wait_for_completion(timeout=30):
        logger.info("Build completed before shutdown")
    else:
        logger.warning("Build did not complete within timeout, shutting down anyway")


def _open_uploaded_image(file: UploadFile) -> Image.Image:
    try:
        data = file.file.read()
        image = Image.open(BytesIO(data))
        return ImageOps.exif_transpose(image)
    except Exception as exc:
        logger.error(f"Failed to open uploaded image: {exc}")
        raise HTTPException(status_code=400, detail=f"Invalid image: {exc}") from exc


def _parse_bbox(bbox: str | None) -> tuple[int, int, int, int] | None:
    if not bbox:
        return None
    try:
        parts = [int(part.strip()) for part in bbox.split(",")]
        if len(parts) != 4:
            raise ValueError("Expected 4 integers.")
        return (parts[0], parts[1], parts[2], parts[3])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid bbox: {exc}") from exc


def _random_id(length: int = 8) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


@app.get("/")
def web_index() -> FileResponse:
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/index/status")
def index_status() -> dict[str, Any]:
    """Get index status and current build progress if any."""
    # Get build status
    build_progress = _INDEX_COORDINATOR.get_status()
    build_status = None
    if build_progress:
        build_status = {
            "operation": build_progress.operation,
            "status": build_progress.status.value,
            "progress": build_progress.progress,
            "total": build_progress.total,
            "started_at": build_progress.started_at,
            "completed_at": build_progress.completed_at,
            "error": build_progress.error,
        }

    # Get index status
    if not _INDEX_STORE.is_loaded():
        return {
            "exists": False,
            "index_path": _CONFIG.index_path,
            "build_status": build_status,
        }

    data = _INDEX_STORE.get_index()
    return {
        "exists": True,
        "index_path": _CONFIG.index_path,
        "count": _INDEX_STORE.get_count(),
        "meta": data.meta,
        "build_status": build_status,
    }


@app.post("/api/index", status_code=202)
def build_index_endpoint(rebuild: bool = Query(False)) -> dict[str, Any]:
    """
    Start an async build or update of the image index.

    Query params:
        rebuild: If True, rebuild from scratch. If False (default), incrementally update.

    Returns:
        202 Accepted with build task status

    Raises:
        409 Conflict if a build is already in progress
    """
    try:
        progress = _INDEX_COORDINATOR.start_build(rebuild)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "operation": progress.operation,
        "status": progress.status.value,
        "progress": progress.progress,
        "total": progress.total,
        "started_at": progress.started_at,
    }


@app.post("/api/lookup", response_model=LookupResponse)
async def lookup_image(
    file: UploadFile = File(...),
    top_k: int = Query(None, ge=1, le=100),
    bbox: str | None = Query(
        None,
        description="Optional bbox as 'x0,y0,x1,y1' (inclusive).",
    ),
) -> LookupResponse:
    if not _INDEX_STORE.is_loaded():
        raise HTTPException(status_code=400, detail="Index not loaded. Build index first.")
    data = _INDEX_STORE.get_index()

    effective_top_k = top_k if top_k is not None else _CONFIG.top_k_default

    image = _open_uploaded_image(file)
    query_hash = hasher.hash_image(image, bbox=_parse_bbox(bbox))

    matches = _INDEX_STORE.lookup_matches(query_hash, effective_top_k)

    return LookupResponse(
        query_hash=query_hash,
        matches=matches,
        count=_INDEX_STORE.get_count(),
        index_meta=data.meta,
    )


@app.post("/api/bbox", response_model=BBoxResponse)
async def detect_bbox(file: UploadFile = File(...)) -> BBoxResponse:
    image = _open_uploaded_image(file)
    bbox = detect_main_image(image)
    return BBoxResponse(bbox=bbox)


@app.get("/api/image")
def get_image(image_id: str = Query(..., alias="id")) -> Response:
    blob = _INDEX_STORE.get_image_blob(image_id)
    if blob is None:
        logger.warning(f"Image not found: {image_id}")
        raise HTTPException(status_code=404, detail="Image not found.")
    data, media_type = blob
    return Response(content=data, media_type=media_type)


@app.get("/api/config")
def get_config() -> JSONResponse:
    return JSONResponse(
        {
            "version": _VERSION,
            "image_library_dirs": _CONFIG.image_library_dirs,
            "index_path": _CONFIG.index_path,
            "top_k_default": _CONFIG.top_k_default,
            "include_extensions": _CONFIG.include_extensions,
            "hash_meta": hasher.get_metadata(),
            "debug_dir": _CONFIG.debug_dir,
        }
    )


@app.post("/api/debug")
async def debug_image(
    file: UploadFile = File(...),
    detected_bbox: str | None = Form(None),
    bbox: str | None = Form(None),
) -> dict[str, str | None]:
    if not _CONFIG.debug_dir:
        raise HTTPException(status_code=400, detail="Debug directory is not configured.")
    image = _open_uploaded_image(file)
    os.makedirs(_CONFIG.debug_dir, exist_ok=True)
    image_id = _random_id()
    image_path = os.path.join(_CONFIG.debug_dir, f"{image_id}.jpg")
    json_path = os.path.join(_CONFIG.debug_dir, f"{image_id}.json")

    if image.mode != "RGB":
        image = image.convert("RGB")
    image.save(image_path, "JPEG", quality=90)

    payload = {
        "detected_bbox": _parse_bbox(detected_bbox),
        "bbox": _parse_bbox(bbox),
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)

    return {"id": image_id, "image": image_path, "meta": json_path}
