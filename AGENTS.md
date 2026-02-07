# Notes (Image Detection)

## Application purpose
- Photo lookup: detect whether a newly taken photo of a paper photobook image matches an existing image in the photo library to decide if a photobook photo has to be scanned and added to the digital library
- Digital library size is about 6000 photos (mainly jpg, tiff, png, but may be others as well), which are located in different folders and may contain copies (e.g. original tiff and its post-processed jpg)

## Detection pipeline (current)
- Input must be **upright** already (EXIF transpose applied on the server for all uploads).
- Downscale to max 1000px on the longer side for speed.
- Convert to grayscale and blur lightly to suppress noise.
- Compute per-row/col edge contrast (mean abs diff between adjacent rows/cols), then smooth 1D signals.
- Use border vs interior medians to build a threshold; scan within outer bands to find edges.
- Top edge uses a gradient guard to avoid tiny early crossings when the border is quiet.
- Left edge prefers a later segment when the first segment is weak vs a stronger later one.
- Bottom edge falls back to variance when the border is noisy but variance drops sharply.
- If the detected box is too large, pick a later top segment to shrink it toward ~72% area.
- Guardrail: if bbox is invalid or area < 60% of image, fallback to full image bounds.

## Test images
- Debug samples live in `tests/debug` with per-image JSON sidecars containing `bbox`.
- Test runner uses a 5% per-side tolerance against those sidecars.

## Known hard cases / potential future improvements
- Very low-contrast borders or highly textured frames can weaken edge-contrast signals.
- Strong leftover images near the edges can introduce competing edges.
- Potential fixes: multi-scale edge contrast, or local texture masks to suppress leftover strips.

## Tests & configs
- Test runner: `scripts/detect_main_image_test.py`
- Default data: `tests/debug` (image + JSON sidecar with `bbox`)
- Default tolerance: 5% per side
- CLI preview: `scripts/detect_main_image_cli.py` (draws rectangle on EXIF-transposed image)

## Server + API (current)
- FastAPI app in `server/main.py`. Static web UI served from `server/web/`.
- API prefix: `/api/*` (e.g., `/api/lookup`, `/api/bbox`, `/api/index`, `/api/index/status`, `/api/image`, `/api/config`, `/api/health`).
- `/api/lookup` accepts an image blob (`multipart/form-data` with `file`) and optional `bbox` query param: `x0,y0,x1,y1` (inclusive). If bbox is omitted, full image is used for hashing.
- `/api/bbox` accepts an image blob and returns the detected bbox (for manual adjustment in UI).
- `/api/image?id=<image_id>` returns the raw image blob by ID (no filesystem paths exposed to clients).
- `/api/debug` accepts image + optional `detected_bbox` and `bbox` (form fields), saves JPEG + JSON with matching random id in `debug_dir`.
- Index is loaded on server startup if index file exists; otherwise requires `/api/index` to build.

## Indexing + IDs
- Index is stored as a mapping of `image_id -> {path, hash}` plus index meta.
- `image_id` is SHA-256 of the **image filepath** (stable handle for UI; not the path itself).
- Indexing always hashes full originals (no bbox on library images).
- Hash format is fixed inside `server/phash_engine.py` (no config knob).
- EXIF transpose:
  - Indexing uses EXIF transpose when loading originals.
  - `/api/lookup`, `/api/bbox`, `/api/debug` apply EXIF transpose on uploads server-side.

## Web UI (current)
- Minimal “Google-style” page in `server/web/` with “Photo lookup” title and a Browse button.
- After selection, the image is displayed on a canvas; `/api/bbox` is called and the bbox is drawn.
- Bbox can be resized by dragging corner handles (L-shaped lines); high-contrast double-stroke rectangle for visibility and larger hit area near edges.
- Mobile picker: `accept="image/*"` + `capture="environment"` encourages camera option.
- UI renders images using EXIF orientation when supported (`createImageBitmap` with `imageOrientation: from-image`).

## Dev tools
- `tools/build_index_cli.py` calls `/api/index`.
- `tools/lookup_image_cli.py` calls `/api/bbox` and `/api/lookup`.

## Contract to remember
- `detect_main_image()` expects **upright pixels** (EXIF-transposed upstream).
- Returns `(x0, y0, x1, y1)` in the same orientation as input pixels.

## Perceptual hashing (future)
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

## Perceptual hashing (current learnings)
- Using Perception PHash with hash_size=16 in `server/phash_engine.py`.
- Distance is normalized Hamming; "confidence" printed as `1 - distance` is **not** a calibrated probability.
- Increasing hash size can worsen ranking if bbox crops vary; PHash is global and sensitive to crop/rotation/glare.
- With updated bbox, some misses remain; likely root cause is **over-cropped test photos**.
- Next step: gather a new representative lookup set (less crop), then re-evaluate thresholds/hasher choice.

## Dev setup (WSL + mobile access)
- If phone cannot reach the server via the Windows LAN IP, the likely culprit is **Windows Firewall**. Allow inbound TCP on the server port (e.g., 8000).
- Get WSL IP: `ip addr show eth0` (use the `inet` value).
- Add Windows port proxy (PowerShell Admin):
  - `netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=<WSL_IP>`
- Add Windows Firewall rule (PowerShell Admin):
  - `netsh advfirewall firewall add rule name="PhotoLookup 8000" dir=in action=allow protocol=TCP localport=8000`
