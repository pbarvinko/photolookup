"""Image hashing abstraction for perceptual similarity matching."""

from __future__ import annotations

from PIL import Image

from . import phash_engine

BBox = tuple[int, int, int, int]


class ImageHasher:
    """Encapsulates image hashing and similarity operations.

    Provides a clean interface for hashing images and computing similarity,
    abstracting away the specific hashing algorithm implementation.
    """

    def hash_image(self, image: Image.Image, bbox: BBox | None = None) -> str:
        """Create perceptual hash for an image.

        Args:
            image: PIL Image to hash
            bbox: Optional bounding box (x0, y0, x1, y1) to hash a region

        Returns:
            Hash string
        """
        return phash_engine.create_hash(image, bbox=bbox)

    def compute_distance(self, hash_a: str, hash_b: str) -> float:
        """Compute normalized distance between two hashes.

        Args:
            hash_a: First hash string
            hash_b: Second hash string

        Returns:
            Distance value (0.0 = identical, 1.0 = completely different)
        """
        return phash_engine.compute_distance(hash_a, hash_b)

    def get_metadata(self) -> dict[str, object]:
        """Get hash algorithm metadata.

        Returns:
            Dictionary with algorithm type, version, and parameters
        """
        return phash_engine.get_hash_meta()


# Module-level singleton for convenience
_default_hasher = ImageHasher()


def hash_image(image: Image.Image, bbox: BBox | None = None) -> str:
    """Create perceptual hash for an image (convenience function).

    Args:
        image: PIL Image to hash
        bbox: Optional bounding box (x0, y0, x1, y1) to hash a region

    Returns:
        Hash string
    """
    return _default_hasher.hash_image(image, bbox)


def compute_distance(hash_a: str, hash_b: str) -> float:
    """Compute normalized distance between two hashes (convenience function).

    Args:
        hash_a: First hash string
        hash_b: Second hash string

    Returns:
        Distance value (0.0 = identical, 1.0 = completely different)
    """
    return _default_hasher.compute_distance(hash_a, hash_b)


def get_metadata() -> dict[str, object]:
    """Get hash algorithm metadata (convenience function).

    Returns:
        Dictionary with algorithm type, version, and parameters
    """
    return _default_hasher.get_metadata()
