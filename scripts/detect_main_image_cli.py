from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.image_detection_engine import detect_main_image


def _is_image_path(path: Path) -> bool:
    return path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


def _process_image(src_path: Path) -> Path:
    dst_path = src_path.with_name(f"{src_path.stem}_detected{src_path.suffix}")
    with Image.open(src_path) as im:
        im_upright = ImageOps.exif_transpose(im)
        rect = detect_main_image(im_upright)
        preview = im_upright.copy()
        draw = ImageDraw.Draw(preview)
        draw.rectangle(rect, outline=(255, 0, 0), width=5)
        preview.save(dst_path)
    return dst_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Detect main image region in a photo.")
    parser.add_argument("path", help="Path to an image file or a directory of images")
    args = parser.parse_args()

    src_path = Path(args.path)
    if not src_path.exists():
        raise SystemExit(f"Input path not found: {src_path}")

    outputs = []
    if src_path.is_dir():
        for entry in sorted(src_path.iterdir()):
            if entry.is_file() and _is_image_path(entry):
                outputs.append(_process_image(entry))
    else:
        if not _is_image_path(src_path):
            raise SystemExit(f"Unsupported file type: {src_path.suffix}")
        outputs.append(_process_image(src_path))

    for out_path in outputs:
        print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
