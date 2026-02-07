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


def relative_errors(
    actual: tuple[int, int, int, int],
    expected: tuple[int, int, int, int],
    width: int,
    height: int,
) -> tuple[float, float, float, float]:
    x0, y0, x1, y1 = actual
    ex0, ey0, ex1, ey1 = expected
    dx0 = abs(x0 - ex0) / width
    dx1 = abs(x1 - ex1) / width
    dy0 = abs(y0 - ey0) / height
    dy1 = abs(y1 - ey1) / height
    return dx0, dx1, dy0, dy1


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate main image detection against expected bounds.")
    parser.add_argument(
        "--data-dir",
        default=ROOT / "tests" / "debug",
        type=Path,
        help="Directory containing image files and matching JSON metadata",
    )
    parser.add_argument(
        "--tolerance",
        default=0.05,
        type=float,
        help="Max allowed relative error per side (fraction of width/height)",
    )
    args = parser.parse_args()

    total = 0
    failures = 0

    json_paths = sorted(args.data_dir.glob("*.json"))
    if not json_paths:
        print(f"No JSON metadata files found in {args.data_dir}")
        return 1

    image_exts = (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff")

    for json_path in json_paths:
        with json_path.open("r", encoding="utf-8") as handle:
            metadata = json.load(handle)
        if "bbox" not in metadata:
            print(f"[SKIP] {json_path.name} missing bbox")
            continue

        bbox = metadata["bbox"]
        if isinstance(bbox, list) and len(bbox) == 4:
            expected = tuple(int(v) for v in bbox)
        elif isinstance(bbox, dict):
            expected = (
                int(bbox["x0"]),
                int(bbox["y0"]),
                int(bbox["x1"]),
                int(bbox["y1"]),
            )
        else:
            print(f"[SKIP] {json_path.name} invalid bbox format")
            continue

        image_path = None
        for ext in image_exts:
            candidate = json_path.with_suffix(ext)
            if candidate.exists():
                image_path = candidate
                break

        if image_path is None:
            print(f"[MISSING] {json_path.stem} (no matching image)")
            failures += 1
            total += 1
            continue

        with Image.open(image_path) as im:
            im_upright = ImageOps.exif_transpose(im)
            actual = detect_main_image(im_upright)
            width, height = im_upright.size

        errors = relative_errors(actual, expected, width, height)
        max_error = max(errors)
        ok = max_error <= args.tolerance
        status = "OK" if ok else "FAIL"
        print(
            f"[{status}] {image_path.name} actual={actual} "
            f"expected=({expected[0]},{expected[1]},{expected[2]},{expected[3]}) "
            f"max_error={max_error:.3f} tol={args.tolerance:.3f}"
        )

        total += 1
        if not ok:
            failures += 1

    print(f"Done. {total - failures}/{total} passed.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
