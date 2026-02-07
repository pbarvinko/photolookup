from __future__ import annotations

from typing import Optional, Tuple

from PIL import Image
from perception.hashers.image import PHash

BBox = Tuple[int, int, int, int]

HASH_TYPE = "phash"
HASH_VERSION = 1
HASH_SIZE = 16
HASH_FORMAT = "hex"

_PHASH = PHash(hash_size=HASH_SIZE)


def compute_distance(hash_a: str, hash_b: str) -> float:
    """Compute distance between two hashes produced by this engine."""
    return float(_PHASH.compute_distance(hash_a, hash_b, hash_format=HASH_FORMAT))


def get_hash_meta() -> dict[str, object]:
    return {
        "type": HASH_TYPE,
        "version": HASH_VERSION,
        "hash_size": HASH_SIZE,
        "hash_format": HASH_FORMAT,
    }


def _sanitize_bbox(bbox: BBox, width: int, height: int) -> BBox:
    x0, y0, x1, y1 = bbox
    x0 = max(0, min(x0, width - 1))
    y0 = max(0, min(y0, height - 1))
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    if x1 < x0 or y1 < y0:
        raise ValueError(f"Invalid bbox after clamp: {(x0, y0, x1, y1)}")
    return x0, y0, x1, y1


def _prepare_image(pil_image: Image.Image) -> Image.Image:
    if pil_image.mode == "RGBA":
        bg = Image.new("RGBA", pil_image.size, (255, 255, 255, 255))
        return Image.alpha_composite(bg, pil_image).convert("RGB")
    return pil_image.convert("RGB")


def create_hash(
    pil_image: Image.Image,
    bbox: Optional[BBox] = None,
) -> str | list[str] | None:
    """Create a perceptual hash (pHash) for the image or a bbox region.

    The bbox is expected to be (x0, y0, x1, y1) with inclusive x1/y1,
    matching detect_main_image()'s output. If bbox is None, use the full image.
    """
    image = pil_image
    if bbox is not None:
        x0, y0, x1, y1 = _sanitize_bbox(bbox, image.width, image.height)
        # PIL crop uses exclusive right/bottom bounds.
        image = image.crop((x0, y0, x1 + 1, y1 + 1))

    image = _prepare_image(image)
    return _PHASH.compute(image, hash_format=HASH_FORMAT)
