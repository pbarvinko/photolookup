"""Shared image processing utilities for index building."""

from __future__ import annotations

from PIL import Image, ImageOps


def load_image(path: str) -> Image.Image:
    """Load image and apply EXIF transpose."""
    return ImageOps.exif_transpose(Image.open(path))
