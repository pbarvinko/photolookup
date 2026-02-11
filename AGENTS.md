# PhotoLookup - Technical Documentation

## Application Overview

### Purpose
Photo lookup application to detect whether a newly taken photo of a paper photobook image matches an existing image in the photo library. This helps decide if a photobook photo needs to be scanned and added to the digital library.

- **Digital library**: ~6000 photos (jpg, tiff, png, webp, etc.)
- **Storage**: Multiple folders with potential duplicates (e.g., original tiff + post-processed jpg)

### Architecture: Two Main Operations

PhotoLookup performs two distinct operations:

1. **Bounding Box Detection** (Optional preprocessing)
   - Helper operation for newly taken photos
   - Detects the main image area within a photo of a photobook page
   - Removes borders, backgrounds, and edge artifacts
   - Improves lookup accuracy by cropping to actual image content

2. **Image Lookup via Perceptual Hashing** (Core algorithm)
   - Primary lookup mechanism
   - Uses perceptual hashing (PHash) to find similar images
   - Builds index of all library images
   - Returns top-k matches ranked by hash distance

---

# Bounding Box Detection

## Purpose
Optional preprocessing step for newly captured photos. When photographing a photobook page, the image typically includes:
- The actual photo (what we want to match)
- White/colored borders around the photo
- Background (table, wall, etc.)

The bbox detection algorithm isolates just the photo content, improving lookup accuracy.

## Detection Pipeline (Current)

- Input must be **upright** already (EXIF transpose applied on the server for all uploads).
- Downscale to max 1000px on the longer side for speed.
- Convert to grayscale and blur lightly to suppress noise.
- Compute per-row/col edge contrast (mean abs diff between adjacent rows/cols), then smooth 1D signals.
- Use border vs interior medians to build a threshold; scan within outer bands to find edges.
- **NEW: Inner edge refinement** - After initial detection, check each edge for "outer edge" characteristics (low variance on image side). If detected, search inward for the "inner edge" (border→image transition) using variance analysis. This fixes the common issue where the algorithm picks the background→border edge instead of the border→image edge.
- Top edge uses a gradient guard to avoid tiny early crossings when the border is quiet.
- Left edge prefers a later segment when the first segment is weak vs a stronger later one; inner edge refinement is slightly relaxed here (most common leftover image issue).
- Bottom edge falls back to variance when the border is noisy but variance drops sharply.
- If the detected box is too large (>77% area), pick a later top segment to shrink it toward ~72% area.
- Guardrail: if bbox is invalid or area < 60% of image, fallback to full image bounds.

## Inner Edge Refinement (Implementation Details)

- **Key insight**: Borders create two edges - outer (background→border) and inner (border→image). We want the inner edge.
- **Detection method**: Compare variance on both sides of detected edge. Inner edges have higher variance on the image side.
- **Refinement strategy**:
  - Check if detected edge is "outer" (variance on image side < 0.6-0.8× variance on border side)
  - If outer edge detected, search inward (up to 50 pixels) for a better edge
  - Candidate edge must have: (1) reasonable edge strength (≥0.6-0.7× original), (2) strong inner edge signal (variance ratio >2.0-2.5×)
- **Edge-specific tuning**:
  - Top/bottom: Very conservative (avoid horizon/sky confusion)
  - Left: Slightly relaxed (most common leftover image issue)
  - Right: Moderate
- **Implementation**: `_refine_to_inner_edge()` in `server/image_detection_engine.py`

## Known Hard Cases / Potential Future Improvements

- ✅ **FIXED: Outer vs inner edge detection** - Algorithm now reliably distinguishes border→image edges from background→border edges using variance analysis.
- ✅ **FIXED: Leftover images on sides** - Inner edge refinement successfully ignores small leftover image fragments near edges.
- ✅ **IMPROVED: Low-contrast borders** - Refinement helps by looking for variance changes rather than just edge strength.
- ❌ **Remaining challenge: Multiple stacked images** - When multiple complete images are stacked vertically/horizontally (e.g., `ztevon2q.jpg`), the algorithm may include more than one. Would require sophisticated multi-region detection to solve.
- **Design philosophy**: Conservative refinement thresholds prevent false positives on images with internal structure (horizons, architectural details, etc.). Better to slightly under-crop than to aggressively crop into image content.

## Test Images & Performance

- Debug samples live in `tests/debug` with per-image JSON sidecars containing `bbox`.
- Test runner uses a 5% per-side tolerance against those sidecars.
- **Current performance: 13/14 passing (92.9%)** - significant improvement from baseline 11/14 (78.6%).
- Remaining failure: `ztevon2q.jpg` (5.6% error) - exceptional edge case with multiple stacked images.

## Tests & Tools

- **Test runner**: `scripts/detect_main_image_test.py`
- **Default data**: `tests/debug` (image + JSON sidecar with `bbox`)
- **Default tolerance**: 5% per side
- **CLI preview**: `scripts/detect_main_image_cli.py` (draws rectangle on EXIF-transposed image)
- **Diagnostic tool**: `scripts/diagnose_detection.py` (analyzes edge profiles and variance for debugging)

## Contract to Remember

- `detect_main_image()` expects **upright pixels** (EXIF-transposed upstream).
- Returns `(x0, y0, x1, y1)` in the same orientation as input pixels.

---

# Image Lookup & Perceptual Hashing

## Purpose
Core lookup algorithm that finds similar images in the library. Uses perceptual hashing to create compact fingerprints of images that are robust to minor variations (compression, slight crops, color adjustments).

## Indexing + IDs

- Index is stored as a mapping of `image_id -> {path, hash}` plus index meta.
- `image_id` is SHA-256 of the **image filepath** (stable handle for UI; not the path itself).
- Indexing always hashes full originals (no bbox on library images).
- Hash format is fixed inside `server/phash_engine.py` (no config knob).
- **Index operations:**
  - **Build** (`?rebuild=true`): Clears existing index and rebuilds from scratch
  - **Update** (default): Validates existing entries, removes deleted files, adds new files
  - Update automatically falls back to build if no index exists
- **EXIF transpose**:
  - Indexing uses EXIF transpose when loading originals.
  - `/api/lookup`, `/api/bbox`, `/api/debug` apply EXIF transpose on uploads server-side.

## Index Building (Parallel Processing)

- **Module**: `server/index_builder.py` contains parallel processing logic
- **Configuration**: `build_workers` in config.json controls parallelization:
  - `0` (default): Auto-detect (cpu_count - 1), typically 4-8 workers
  - `1`: Sequential processing (original algorithm, useful for debugging)
  - `N`: Parallel with N worker processes (always capped at cpu_count - 1)
- **Progressive batch loading**: Images discovered via `os.walk` are batched (20 files) and submitted to workers immediately, no need to wait for full directory scan
- **Worker function**: `_process_image_batch()` processes batches, returns (results, errors)
- **Logging**: Progress logged every 100 files without total count (shown at completion)
- **Performance**: Expected 4-6× speedup on 8-core systems vs sequential (5 files/sec → 25-30 files/sec)
- **Fallback**: If parallel processing fails, automatically falls back to sequential with warning
- **Hash consistency**: Same EXIF transpose and PHash algorithm as sequential, hashes are identical
- **Update mode**: Uses same parallel/sequential logic but only processes new files (not in existing index)

## Current Implementation (PHash)

- Using Perception PHash with hash_size=16 in `server/phash_engine.py`.
- Distance is normalized Hamming; "confidence" printed as `1 - distance` is **not** a calibrated probability.
- Increasing hash size can worsen ranking if bbox crops vary; PHash is global and sensitive to crop/rotation/glare.
- With updated bbox, some misses remain; likely root cause is **over-cropped test photos**.
- Next step: gather a new representative lookup set (less crop), then re-evaluate thresholds/hasher choice.

## Future Considerations

- Decide **one canonical preprocessing pipeline** and never vary it:
  - EXIF-transpose upstream, crop to main image bbox, convert to RGB, handle alpha (composite on white).
  - Resize strategy (fixed size + interpolation), then grayscale if the hasher expects it.
- For the Perception module (Thorn), note:
  - Different hashers exist (pHash/dHash/aHash/colorhash); they trade off robustness vs sensitivity.
  - Pick one primary hash and a distance metric (typically Hamming for binary hashes).
  - Set a default **distance threshold** based on a small validation set of true matches/non-matches.
  - Consider multi-hash voting if needed (e.g., pHash + colorhash) but keep it simple first.
- Ensure hashing and detection share the same orientation/crop policy; otherwise matches will drift.
- Normalize input formats (JPEG/PNG/HEIC/WebP) to consistent pixel pipeline before hashing.

---

# Server & API

## FastAPI Application

- FastAPI app in `server/main.py`. Static web UI served from `server/web/`.
- Default port: **14322** (configurable via `PORT` env var).
- API prefix: `/api/*` (e.g., `/api/lookup`, `/api/bbox`, `/api/index`, `/api/index/status`, `/api/image`, `/api/config`, `/api/health`).

## API Endpoints

### Lookup & Detection
- **`/api/lookup`** - Accepts an image blob (`multipart/form-data` with `file`) and optional `bbox` query param: `x0,y0,x1,y1` (inclusive). If bbox is omitted, full image is used for hashing.
- **`/api/bbox`** - Accepts an image blob and returns the detected bbox (for manual adjustment in UI).
- **`/api/image?id=<image_id>`** - Returns image by ID with automatic format conversion for browser compatibility:
  - **Browser-supported formats** (`.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.svg`, `.bmp`): Served as-is with original MIME type
  - **Non-browser formats** (e.g., `.tif`, `.tiff`): Automatically converted to JPEG and served as `image/jpeg`
  - **Conversion pipeline**: EXIF transpose → RGB conversion (alpha composited on white) → JPEG encoding (quality=90)
  - **Performance**: LRU cache with maxsize=100 (keyed by `image_id`) for fast repeated access
  - **Transparency**: Conversion is automatic and transparent to client; no frontend changes required
- **`/api/debug`** - Accepts image + optional `detected_bbox` and `bbox` (form fields), saves JPEG + JSON with matching random id in `debug_dir`.

### Index Management
- **`/api/index`** POST with optional `?rebuild=true` query parameter:
  - **Async operation**: Returns immediately (202 Accepted) with task status, build runs in background thread
  - **Default (no parameter or `?rebuild=false`)**: Incrementally updates index - removes entries for deleted files, adds new files
  - **`?rebuild=true`**: Rebuilds entire index from scratch
  - **Returns**: `{"operation": "build"|"update", "status": "running", "progress": 0, "total": null, "started_at": "..."}`
  - **Error**: 409 Conflict if build already in progress
  - **Concurrency**: Only one build at a time; concurrent requests rejected
- **`/api/index/status`** GET - Returns index metadata and current build status
  - **Response fields**:
    - `exists`: Whether index file exists
    - `index_path`: Path to index file
    - `count`: Number of indexed images (from loaded index, not current build)
    - `meta`: Index metadata (hash info, timestamps, errors, stats)
    - `build_status`: Current or last build progress (null if no build started)
      - `operation`: "build" | "update"
      - `status`: "running" | "completed" | "failed"
      - `progress`: Files processed so far
      - `total`: Total files (only set on completion)
      - `started_at`: ISO timestamp
      - `completed_at`: ISO timestamp (null if running)
      - `error`: Error message (null unless failed)

### Other
- **`/api/config`** - Returns server configuration including version, library paths, defaults, and hash metadata
- **`/api/health`** - Health check endpoint

### Startup Behavior
- Index is loaded on server startup if index file exists; index build/update happens only explicitly via `/api/index`.

## Async Index Building

### Architecture
- **Module**: `server/index_builder_coordinator.py` - Manages async build operations
- **Threading**: Single background thread runs build/update, main thread handles API requests
- **Concurrency**: Only one build at a time (reject concurrent requests with 409 Conflict)
- **Progress tracking**: Progress callbacks from builders report count every 100 files
- **State management**: Thread-safe with `threading.Lock`, in-memory only (lost on server restart)
- **Index safety**: Lookups use existing index during build; new index loaded atomically on completion

### Build Lifecycle
1. **Start**: POST `/api/index` creates background thread, returns 202 immediately
2. **Progress**: GET `/api/index/status` polls for updates (recommended: 2 second interval)
3. **During build**: Lookups continue to use old index (no interruption)
4. **Completion**: New index loaded atomically, status shows "completed"
5. **Failure**: Build marks status as "failed", old index remains intact

### Error Handling
- **Build failure**: Status shows error, old index unchanged, client must retry
- **Server restart**: In-progress build lost, existing index remains valid
- **Shutdown**: Server waits up to 30 seconds for build completion before shutdown

### Thread Safety
- **Lookup safety**: Old index remains loaded during rebuild; new index atomically replaces it on completion
- **Build isolation**: New index built in temporary variables, swapped in single assignment at end
- Build status updates protected by coordinator lock
- No race conditions between lookups and index updates

## Versioning

- **VERSION file**: Single source of truth at project root (e.g., `0.1.1`)
- **Exposure**: Version is read at startup and exposed via `/api/config` endpoint
- **Web UI**: Displays version in footer as "PhotoLookup v{version}"
- **Docker**: VERSION file is copied into image during build

## Configuration System

- **Environment Variable**: `PHOTOLOOKUP_DATA_DIR` (required) - directory containing config and index files
- **Config file**: Always at `${PHOTOLOOKUP_DATA_DIR}/config.json`
- **Index file**: Always at `${PHOTOLOOKUP_DATA_DIR}/index.json` (not configurable)
- **Debug directory**: Defaults to `${PHOTOLOOKUP_DATA_DIR}/debug` (overridable in config.json)
- **Local dev**: Set `PHOTOLOOKUP_DATA_DIR` in `.vscode/launch.json` (e.g., `${workspaceFolder}/config.local`)
- **Docker**: Set via environment variable (default: `/data`)

### config.json Fields

- `image_library_dirs` - Array of photo directory paths
- `top_k_default` - Number of matches to return (default: 3)
- `debug_dir` - Optional override for debug output directory
- `include_extensions` - File extensions to index (default: `.jpg`, `.jpeg`, `.png`, `.tif`, `.tiff`, `.webp`)
- `build_workers` - Parallel index building (0=auto, 1=sequential, N=N workers)

---

# Web UI

## Main Page

- Minimal page in `server/web/` with subtitle and a Browse button (no heading).
- **Subtitle**: "Find the closest image match in your photo library" where "photo library" is a clickable link that opens the library status modal.
- Buttons styled Google Material 3: gray `#f8f9fa` background, `#dadce0` border, `#3c4043` text, sans-serif font (`Google Sans / Roboto`), pill `border-radius: 20px`.
- After selection, the image is displayed on a canvas; `/api/bbox` is called and the bbox is drawn.
- Bbox can be resized by dragging corner handles (L-shaped lines); high-contrast double-stroke rectangle for visibility and larger hit area near edges.
- **Detected-image carousel**: Slider placeholder matches preview canvas dimensions (width + height) via `syncSliderSize()`. A `ResizeObserver` on `previewCanvas` keeps them in sync on resize. Images use `object-fit: contain; object-position: center` to fit without distortion.
- **Slider nav buttons**: Circular prev/next buttons (`40×40`, `border-radius: 50%`) vertically centered inside the slider, inset 8px from edges. Shown/hidden per slide position. Swipe handler guards against button clicks (`event.target.closest('.slider-btn')`).
- **Version footer**: Fixed position at bottom of page, small centered text showing "PhotoLookup v{version}", fetched from `/api/config` on page load.
- Mobile picker: `accept="image/*"` + `capture="environment"` encourages camera option.
- UI renders images using EXIF orientation when supported (`createImageBitmap` with `imageOrientation: from-image`).
- Cache-busting: `?v=devN` query params on CSS/JS links in `index.html`; bump on each change.

## Library Status Modal

- **Trigger**: Click "photo library" link in subtitle
- **Modal content**:
  - Library paths from config (monospace, word-break for long paths)
  - Index status with Material 3 styled badges:
    - ✓ Ready (green): Index exists and ready
    - 🔄 Building... (blue): Build in progress with spinner, shows progress count and start time
    - ⚠ Error (red): Build failed with error message
    - ℹ No Index (yellow): No index found
  - Index details: Total files, last built/updated timestamp, or progress during build
  - Build Index button: Triggers incremental update (POST `/api/index` without rebuild parameter)
- **Auto-refresh**: Polls `/api/config` and `/api/index/status` every 5 seconds while modal is open
- **Close methods**: X button, Close button, click overlay, Escape key
- **Styling**: Material 3 design with rounded corners, subtle shadows, color-coded status badges
- **Progress updates**: Real-time display during build (files processed, started timestamp)
- **Button states**: Build button disabled during build, shows "Building..." text

---

# Deployment

## Docker Deployment

- **Dockerfile**: Python 3.11-slim base, non-root user (UID 1000), port 14322
- **VERSION file**: Copied into image at `/app/VERSION` for runtime version detection
- **docker-compose.yml**: Simplified setup with volume mounts and environment variables
- **Data volume**: Mount host directory to `/data` in container (contains config.json and index.json)
- **Photo mounts**: Read-only mounts for photo libraries (e.g., `/mnt/library:ro`)
- **Build**: `docker build -t photolookup:latest .`
- **Run**: `docker-compose up -d` or `docker run -d -p 14322:14322 -v ./config.docker:/data photolookup:latest`
- **Logs**: `docker logs -f photolookup` or `docker-compose logs -f`
- **Health check**: Built-in, checks `/api/health` every 30s

## Dev Setup (WSL + Mobile Access)

- If phone cannot reach the server via the Windows LAN IP, the likely culprit is **Windows Firewall**. Allow inbound TCP on port 14322.
- Get WSL IP: `ip addr show eth0` (use the `inet` value).
- Add Windows port proxy (PowerShell Admin):
  ```powershell
  netsh interface portproxy add v4tov4 listenport=14322 listenaddress=0.0.0.0 connectport=14322 connectaddress=<WSL_IP>
  ```

  To undo:
  ```powershell
  netsh interface portproxy delete v4tov4 listenport=14322 listenaddress=0.0.0.0
  ```

- Add Windows Firewall rule (PowerShell Admin):
  ```powershell
  netsh advfirewall firewall add rule name="PhotoLookup 14322" dir=in action=allow protocol=TCP localport=14322
  ```

  To undo:
  ```powershell
  netsh advfirewall firewall delete rule name="PhotoLookup 14322"
  ```

- Access from mobile: `http://<Windows-IP>:14322/` (find Windows IP with `ipconfig` in Windows)

---

# Development

## Dev Tools

- `scripts/build_index_cli.py` - Async index builder with progress polling:
  - Default: `python scripts/build_index_cli.py 127.0.0.1:14322` → incremental update
  - Rebuild: `python scripts/build_index_cli.py 127.0.0.1:14322 --rebuild` → full rebuild
  - Polls `/api/index/status` every 2 seconds (configurable via `--poll-interval`)
  - Shows progress updates as files are processed
  - Exits on completion/failure with appropriate return code
- `tools/lookup_image_cli.py` calls `/api/bbox` and `/api/lookup`.

## Code Quality & Linting (CRITICAL)

**ALWAYS run ruff linter after ANY Python code changes before considering the task complete.**

### Mandatory Workflow:
1. **Before changes**: Check Python version (`python3 --version`) and verify `pyproject.toml` target-version matches
2. **After changes**: Run linter on ALL modified files:
   ```bash
   python3 -m ruff check <modified_files>
   python3 -m ruff format --check <modified_files>
   ```
3. **Fix errors**: Address all linting errors before marking task complete
4. **Verify imports**: Quick import test for files with new/changed imports:
   ```bash
   python3 -c "from module.name import Class; print('Import successful')"
   ```

### Linter Configuration:
- **Tool**: ruff (configured in `pyproject.toml`)
- **Target**: Python 3.10 (`target-version = "py310"`)
- **Rules**: pycodestyle (E/W), pyflakes (F), isort (I), flake8-bugbear (B), pyupgrade (UP)
- **Line length**: 100 characters

### Common Issues to Watch For:
- Using Python 3.11+ features (e.g., `datetime.UTC`) when target is 3.10
- Import order violations (isort)
- Unused imports
- Line length violations

**Never skip linting** - it catches compatibility issues, style violations, and potential bugs before runtime.
