from __future__ import annotations

from PIL import Image
import numpy as np
import cv2

MAX_DIM = 1000
BLUR_KERNEL = (5, 5)
SMOOTH_KERNEL = 11

BORDER_FRACTION = 0.05
TOP_SEARCH_FRACTION = 0.35
BOTTOM_SEARCH_START = 0.65

THRESH_BLEND = 0.5
TOP_GRAD_GUARD_MIN_FRAC = 0.02

MAIN_IMAGE_MIN_AREA_RATIO = 0.6
TOP_AREA_MAX_RATIO = 0.85
TOP_AREA_TARGET_RATIO = 0.72
LEFT_SEGMENT_RATIO_THRESHOLD = 0.55
BOTTOM_VAR_RATIO_THRESHOLD = 0.5


def _smooth_1d(values: np.ndarray, k: int = SMOOTH_KERNEL) -> np.ndarray:
    k = max(3, int(k))
    kernel = np.ones(k, dtype=np.float32) / float(k)
    return np.convolve(values, kernel, mode="same")


def _threshold(border_med: float, interior_med: float) -> float:
    return border_med + THRESH_BLEND * (interior_med - border_med)


def _first_last_above(scores: np.ndarray, threshold: float, max_idx: int) -> tuple[int, int]:
    # Scan within the edge band to find the earliest and latest threshold crossings.
    first = None
    last = None
    for i in range(1, max_idx):
        if scores[i] >= threshold:
            if first is None:
                first = i
            last = i
    if first is None:
        idx = int(np.argmax(scores[1:max_idx])) + 1
        return idx, idx
    if last is None:
        last = first
    return first, last


def _best_segment_end(scores: np.ndarray, threshold: float, max_idx: int) -> int:
    # Pick the end of the longest above-threshold segment in the edge band.
    best_end = None
    best_len = 0
    start = None
    for i in range(max_idx):
        if scores[i] >= threshold:
            if start is None:
                start = i
        elif start is not None:
            length = i - start
            if length > best_len:
                best_len = length
                best_end = i - 1
            start = None
    if start is not None:
        length = max_idx - start
        if length > best_len:
            best_len = length
            best_end = max_idx - 1
    if best_end is None:
        return int(np.argmax(scores[1:max_idx])) + 1
    return best_end


def _max_grad_index(scores: np.ndarray, max_idx: int) -> int:
    # Strongest local rise in the edge band.
    grad = scores[1:] - scores[:-1]
    return int(np.argmax(grad[: max(1, max_idx - 1)]))


def _max_grad_index_from_right(scores: np.ndarray, max_idx: int) -> int:
    # Strongest local rise measured from the right edge inward.
    grad = scores[1:] - scores[:-1]
    rev_grad = grad[::-1]
    idx = int(np.argmax(rev_grad[: max(1, max_idx - 1)]))
    return (scores.shape[0] - 2) - idx


def _segments_above(scores: np.ndarray, threshold: float, max_idx: int) -> list[tuple[int, int]]:
    # Return contiguous above-threshold segments within the edge band.
    segments: list[tuple[int, int]] = []
    start = None
    for i in range(max_idx):
        if scores[i] >= threshold:
            if start is None:
                start = i
        elif start is not None:
            segments.append((start, i - 1))
            start = None
    if start is not None:
        segments.append((start, max_idx - 1))
    return segments


def _find_top(
    row_diff: np.ndarray,
    height: int,
    top_max: int,
    border_rows: int,
    interior_rows: tuple[int, int],
) -> int:
    # Top edge: use border vs interior contrast, then guard against tiny early crossings.
    border_med = float(np.median(row_diff[:border_rows]))
    interior_med = float(np.median(row_diff[interior_rows[0] : interior_rows[1]]))
    thr = _threshold(border_med, interior_med)

    first, last = _first_last_above(row_diff, thr, top_max)

    if border_med > interior_med:
        return _best_segment_end(row_diff, thr, top_max)
    if first < int(TOP_GRAD_GUARD_MIN_FRAC * height):
        return _max_grad_index(row_diff, top_max)
    return first


def _find_bottom(
    row_diff: np.ndarray,
    height: int,
    bottom_min: int,
    border_rows: int,
    interior_rows: tuple[int, int],
) -> int:
    # Bottom edge: scan inward from bottom for first strong contrast.
    border_med = float(np.median(row_diff[-border_rows:]))
    interior_med = float(np.median(row_diff[interior_rows[0] : interior_rows[1]]))
    thr = _threshold(border_med, interior_med)

    for i in range(height - 2, bottom_min - 1, -1):
        if row_diff[i] >= thr:
            return i
    return int(np.argmax(row_diff[bottom_min : height - 1])) + bottom_min


def _find_left(
    col_diff: np.ndarray,
    width: int,
    left_max: int,
    border_cols: int,
    interior_cols: tuple[int, int],
) -> int:
    # Left edge: scan inward from left for first strong contrast.
    border_med = float(np.median(col_diff[:border_cols]))
    interior_med = float(np.median(col_diff[interior_cols[0] : interior_cols[1]]))
    thr = _threshold(border_med, interior_med)

    if border_med > interior_med:
        return _max_grad_index(col_diff, left_max)

    for i in range(1, left_max):
        if col_diff[i] >= thr:
            # If the first segment is weak vs later ones, prefer the strongest segment.
            segments = _segments_above(col_diff, thr, left_max)
            if len(segments) > 1:
                means = [float(col_diff[s : e + 1].mean()) for s, e in segments]
                if means and (means[0] / max(means)) < LEFT_SEGMENT_RATIO_THRESHOLD:
                    best_idx = int(np.argmax(means))
                    return segments[best_idx][1]
            return i
    return int(np.argmax(col_diff[1:left_max])) + 1


def _find_right(
    col_diff: np.ndarray,
    width: int,
    right_max: int,
    right_min: int,
    border_cols: int,
    interior_cols: tuple[int, int],
) -> int:
    # Right edge: scan inward from right for first strong contrast.
    border_med = float(np.median(col_diff[-border_cols:]))
    interior_med = float(np.median(col_diff[interior_cols[0] : interior_cols[1]]))
    thr = _threshold(border_med, interior_med)

    if border_med > interior_med:
        return _max_grad_index_from_right(col_diff, right_max)

    for i in range(width - 2, right_min - 1, -1):
        if col_diff[i] >= thr:
            return i
    return int(np.argmax(col_diff[right_min : width - 1])) + right_min


def detect_main_image(pil_image: Image.Image) -> tuple[int, int, int, int]:
    """Detect main image rectangle and return (x0, y0, x1, y1) inclusive."""
    image = pil_image.convert("RGB")
    arr = np.array(image)
    height, width = arr.shape[:2]

    scale = 1.0
    if max(height, width) > MAX_DIM:
        # Downscale for speed; scale back later.
        scale = MAX_DIM / max(height, width)
        arr = cv2.resize(arr, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)

    # Edge contrast per row/col highlights border-to-image transitions.
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, BLUR_KERNEL, 0)

    row_diff = np.mean(np.abs(gray[1:, :].astype(np.float32) - gray[:-1, :].astype(np.float32)), axis=1)
    col_diff = np.mean(np.abs(gray[:, 1:].astype(np.float32) - gray[:, :-1].astype(np.float32)), axis=0)

    row_diff = _smooth_1d(row_diff, SMOOTH_KERNEL)
    col_diff = _smooth_1d(col_diff, SMOOTH_KERNEL)

    diff_height = row_diff.shape[0]
    diff_width = col_diff.shape[0]

    border_rows = max(5, int(diff_height * BORDER_FRACTION))
    border_cols = max(5, int(diff_width * BORDER_FRACTION))
    interior_rows = (int(diff_height * 0.3), int(diff_height * 0.7))
    interior_cols = (int(diff_width * 0.3), int(diff_width * 0.7))

    top_max = max(2, int(diff_height * TOP_SEARCH_FRACTION))
    bottom_min = int(diff_height * BOTTOM_SEARCH_START)
    left_max = max(2, int(diff_width * TOP_SEARCH_FRACTION))
    right_min = int(diff_width * BOTTOM_SEARCH_START)
    right_max = left_max

    # Find candidate edges within outer bands.
    y0 = _find_top(row_diff, diff_height, top_max, border_rows, interior_rows) + 1
    y1 = _find_bottom(row_diff, diff_height, bottom_min, border_rows, interior_rows) + 1
    x0 = _find_left(col_diff, diff_width, left_max, border_cols, interior_cols) + 1
    x1 = _find_right(col_diff, diff_width, right_max, right_min, border_cols, interior_cols) + 1

    # Bottom refinement: when border is noisy and variance drops sharply, use variance for bottom edge.
    bottom_border_med = float(np.median(row_diff[-border_rows:]))
    bottom_interior_med = float(np.median(row_diff[interior_rows[0] : interior_rows[1]]))
    row_var = _smooth_1d(gray.var(axis=1), SMOOTH_KERNEL)
    bottom_border_var = float(np.median(row_var[-border_rows:]))
    bottom_interior_var = float(np.median(row_var[interior_rows[0] : interior_rows[1]]))
    if bottom_border_med > bottom_interior_med and bottom_border_var < bottom_interior_var * BOTTOM_VAR_RATIO_THRESHOLD:
        var_thr = _threshold(bottom_border_var, bottom_interior_var)
        for i in range(diff_height - 2, bottom_min - 1, -1):
            if row_var[i] >= var_thr:
                y1 = i + 1
                break

    # Top refinement: if the box is too large, choose a later top segment to shrink it.
    area_ratio = ((x1 - x0 + 1) * (y1 - y0 + 1)) / float(diff_width * diff_height)
    top_border_med = float(np.median(row_diff[:border_rows]))
    top_interior_med = float(np.median(row_diff[interior_rows[0] : interior_rows[1]]))
    if area_ratio > TOP_AREA_MAX_RATIO and top_border_med < top_interior_med:
        top_thr = _threshold(top_border_med, top_interior_med)
        segments = _segments_above(row_diff, top_thr, top_max)
        if len(segments) > 1:
            best_idx = None
            best_score = None
            for start, end in segments:
                cand_y0 = end + 1
                cand_area = ((x1 - x0 + 1) * (y1 - cand_y0 + 1)) / float(diff_width * diff_height)
                if cand_area <= area_ratio:
                    score = abs(cand_area - TOP_AREA_TARGET_RATIO)
                    if best_score is None or score < best_score:
                        best_score = score
                        best_idx = end
            if best_idx is not None:
                y0 = best_idx + 1

    if scale != 1.0:
        # Back to full-resolution coordinates.
        x0 = int(x0 / scale)
        x1 = int(x1 / scale)
        y0 = int(y0 / scale)
        y1 = int(y1 / scale)

    # Clamp and guardrail to full image if the bbox is invalid or too small.
    x0 = max(0, min(x0, width - 1))
    x1 = max(0, min(x1, width - 1))
    y0 = max(0, min(y0, height - 1))
    y1 = max(0, min(y1, height - 1))

    if x1 <= x0 or y1 <= y0:
        return (0, 0, width - 1, height - 1)

    area_ratio = ((x1 - x0 + 1) * (y1 - y0 + 1)) / float(width * height)
    if area_ratio < MAIN_IMAGE_MIN_AREA_RATIO:
        return (0, 0, width - 1, height - 1)

    return (x0, y0, x1, y1)
