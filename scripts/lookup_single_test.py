from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.image_detection_engine import detect_main_image
from server.phash_engine import compute_distance, create_hash, get_hash_meta

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic"}


def _iter_images(directory: Path) -> list[Path]:
    return sorted(
        [p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
    )


def _load_upright(path: Path) -> Image.Image:
    with Image.open(path) as image:
        upright = ImageOps.exif_transpose(image)
        upright.load()
    return upright


def _hash_cache_path(originals_dir: Path) -> Path:
    return originals_dir.with_name(f"{originals_dir.name}_hashes.json")


def _load_hash_cache(
    cache_path: Path, expected_meta: dict[str, object]
) -> dict[str, dict[str, str]] | None:
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if payload.get("meta") != expected_meta:
        return None
    hashes = payload.get("hashes")
    return hashes if isinstance(hashes, dict) else None


def _save_hash_cache(
    cache_path: Path, meta: dict[str, object], hashes: dict[str, dict[str, str]]
) -> None:
    payload = {"meta": meta, "hashes": hashes}
    cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _build_original_hashes(
    originals_dir: Path,
    hash_format: str,
) -> dict[str, tuple[Path, str]]:
    originals: dict[str, tuple[Path, str]] = {}
    for path in _iter_images(originals_dir):
        image = _load_upright(path)
        try:
            hash_value = create_hash(image, bbox=None, hash_format=hash_format)
        finally:
            image.close()
        originals[path.stem] = (path, hash_value)
    return originals


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare lookup images to originals using pHash and print top matches."
    )
    parser.add_argument("originals_dir", help="Directory containing original images")
    parser.add_argument("lookup_dir", help="Single lookup directory (tests/lookup/<name>)")
    parser.add_argument(
        "--hash-format",
        choices=("hex", "base64"),
        default="hex",
        help="Hash string format passed to Perception (default: hex)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=3,
        help="Number of top matches to print (default: 3)",
    )
    args = parser.parse_args()

    originals_dir = Path(args.originals_dir)
    lookup_dir = Path(args.lookup_dir)
    if not originals_dir.is_dir():
        raise SystemExit(f"Originals directory not found: {originals_dir}")
    if not lookup_dir.is_dir():
        raise SystemExit(f"Lookup directory not found: {lookup_dir}")

    cache_path = _hash_cache_path(originals_dir)
    expected_meta = get_hash_meta(hash_format=args.hash_format)
    cached_hashes = _load_hash_cache(cache_path, expected_meta)

    if cached_hashes is None:
        originals = _build_original_hashes(originals_dir, args.hash_format)
        _save_hash_cache(
            cache_path,
            expected_meta,
            {stem: {"filename": p.name, "hash": h} for stem, (p, h) in originals.items()},
        )
    else:
        originals = {
            stem: (originals_dir / payload["filename"], payload["hash"])
            for stem, payload in cached_hashes.items()
        }
    if not originals:
        raise SystemExit(f"No images found in originals directory: {originals_dir}")

    expected_stem = lookup_dir.name if not lookup_dir.name.startswith("0") else None

    lookup_files = _iter_images(lookup_dir)
    if not lookup_files:
        raise SystemExit(f"No images found in lookup directory: {lookup_dir}")

    for path in lookup_files:
        image = _load_upright(path)
        try:
            bbox = detect_main_image(image)
            lookup_hash = create_hash(image, bbox=bbox, hash_format=args.hash_format)
        finally:
            image.close()

        scored: list[tuple[float, str, Path]] = []
        for stem, (orig_path, orig_hash) in originals.items():
            dist = compute_distance(lookup_hash, orig_hash, hash_format=args.hash_format)
            scored.append((dist, stem, orig_path))

        scored.sort(key=lambda x: x[0])
        top_matches = scored[: args.top]

        print(f"{path.name} (expected: {expected_stem or 'NONE'})")
        for rank, (dist, _stem, orig_path) in enumerate(top_matches, start=1):
            confidence = 1.0 - dist
            print(f"  {rank}) {orig_path.name} dist={dist:.6f} confidence={confidence:.6f}")

        if expected_stem is not None:
            ok = top_matches and top_matches[0][1] == expected_stem
            print("  OK" if ok else "  MISS")
        else:
            print("  NO-EXPECTED")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
