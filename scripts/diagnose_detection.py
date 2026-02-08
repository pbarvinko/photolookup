"""Diagnostic tool to analyze bbox detection behavior."""
from __future__ import annotations

import sys
from pathlib import Path
import numpy as np
import cv2
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.image_detection_engine import detect_main_image


def analyze_edge_profiles(image_path: Path) -> None:
    """Analyze and display edge detection profiles for an image."""
    with Image.open(image_path) as im:
        im_upright = ImageOps.exif_transpose(im)

    # Replicate the detection preprocessing
    image = im_upright.convert("RGB")
    arr = np.array(image)
    height, width = arr.shape[:2]

    MAX_DIM = 1000
    scale = 1.0
    if max(height, width) > MAX_DIM:
        scale = MAX_DIM / max(height, width)
        arr = cv2.resize(arr, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)

    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)

    # Compute edge profiles
    row_diff = np.mean(np.abs(gray[1:, :].astype(np.float32) - gray[:-1, :].astype(np.float32)), axis=1)
    col_diff = np.mean(np.abs(gray[:, 1:].astype(np.float32) - gray[:, :-1].astype(np.float32)), axis=0)

    # Smooth
    SMOOTH_KERNEL = 11
    k = max(3, int(SMOOTH_KERNEL))
    kernel = np.ones(k, dtype=np.float32) / float(k)
    row_diff = np.convolve(row_diff, kernel, mode="same")
    col_diff = np.convolve(col_diff, kernel, mode="same")

    # Get detected bbox
    bbox = detect_main_image(im_upright)

    print(f"\n{'='*60}")
    print(f"Image: {image_path.name}")
    print(f"Size: {width}x{height} (original), {arr.shape[1]}x{arr.shape[0]} (scaled)")
    print(f"Detected bbox: {bbox}")
    print(f"{'='*60}")

    # Analyze each edge
    diff_height = row_diff.shape[0]
    diff_width = col_diff.shape[0]

    # Top edge analysis
    top_search = int(diff_height * 0.35)
    top_peaks = []
    for i in range(1, top_search):
        if row_diff[i] > row_diff[i-1] and row_diff[i] > row_diff[i+1]:
            top_peaks.append((i, row_diff[i]))
    top_peaks.sort(key=lambda x: x[1], reverse=True)

    print(f"\nTop edge (search band: 0-{top_search}):")
    print(f"  Top 5 peaks: {top_peaks[:5]}")
    scaled_y0 = int(bbox[1] * scale) if scale != 1.0 else bbox[1]
    print(f"  Detected: y0={bbox[1]} (scaled: {scaled_y0})")

    # Left edge analysis
    left_search = int(diff_width * 0.35)
    left_peaks = []
    for i in range(1, left_search):
        if col_diff[i] > col_diff[i-1] and col_diff[i] > col_diff[i+1]:
            left_peaks.append((i, col_diff[i]))
    left_peaks.sort(key=lambda x: x[1], reverse=True)

    print(f"\nLeft edge (search band: 0-{left_search}):")
    print(f"  Top 5 peaks: {left_peaks[:5]}")
    scaled_x0 = int(bbox[0] * scale) if scale != 1.0 else bbox[0]
    print(f"  Detected: x0={bbox[0]} (scaled: {scaled_x0})")

    # Compute variance in different regions to check inner vs outer edge
    diff_y0 = scaled_y0 - 1 if scale != 1.0 else bbox[1] - 1
    diff_x0 = scaled_x0 - 1 if scale != 1.0 else bbox[0] - 1

    # For top edge: compare variance just above and just below detected edge
    if diff_y0 > 20:
        above_var = gray[max(0, diff_y0-10):diff_y0, :].var()
        below_var = gray[diff_y0:min(arr.shape[0], diff_y0+20), :].var()
        print(f"  Variance above detected top edge: {above_var:.2f}")
        print(f"  Variance below detected top edge: {below_var:.2f}")
        print(f"  {'  -> Likely INNER edge (good)' if below_var > above_var else '  -> Likely OUTER edge (bad!)'}")

    # For left edge: compare variance just left and just right of detected edge
    if diff_x0 > 20:
        left_var = gray[:, max(0, diff_x0-10):diff_x0].var()
        right_var = gray[:, diff_x0:min(arr.shape[1], diff_x0+20)].var()
        print(f"\nLeft edge variance analysis:")
        print(f"  Variance left of detected edge: {left_var:.2f}")
        print(f"  Variance right of detected edge: {right_var:.2f}")
        print(f"  {'  -> Likely INNER edge (good)' if right_var > left_var else '  -> Likely OUTER edge (bad!)'}")


if __name__ == "__main__":
    debug_dir = ROOT / "tests" / "debug"

    # Analyze failure cases
    failure_cases = ["g4htdhe4.jpg", "s9usry82.jpg", "ztevon2q.jpg"]

    for fname in failure_cases:
        analyze_edge_profiles(debug_dir / fname)

    # Analyze one success case for comparison
    print("\n\n" + "="*60)
    print("SUCCESS CASE FOR COMPARISON:")
    print("="*60)
    analyze_edge_profiles(debug_dir / "860rlc6k.jpg")
