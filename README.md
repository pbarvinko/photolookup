# PhotoLookup

A lightweight web tool that helps you avoid rescanning photos you already have digitally.

## Why PhotoLookup?

You've digitized your 35mm film collection, but some original films were lost over time. Yet you still have paper prints from those lost films, or friends gave you printed copies of photos you never had on film. Now you're looking at these paper photos wondering: "Do I already have this one digitally?" Manually searching through thousands of images is tedious and error-prone.

PhotoLookup uses perceptual hashing to quickly find if a newly photographed image matches anything in your existing photo collection. Take a picture of a photobook page with your mobile, upload it, and get instant results showing the closest matches from your library.

## Quick Start with Docker

1. Create a config directory with `config.json`:
```json
{
  "image_library_dirs": ["/mnt/photos"],
  "top_k_default": 5
}
```

2. Run with Docker Compose:
```bash
docker-compose up -d
```

3. Open http://YOUR_SERVER_IP:14322 in your browser

4. Build the index (one-time setup) via Web UI or:
```bash
python scripts/build_index_cli.py YOUR_SERVER_IP:14322 --rebuild
```

## Manual Installation

**Requirements**: Python 3.10+

```bash
# Install dependencies
pip install -r requirements.txt

# Set data directory
export PHOTOLOOKUP_DATA_DIR=/path/to/data

# Create config.json in your data directory
# Start server
python -m uvicorn server.main:app --host 0.0.0.0 --port 14322
```

## Configuration

Create `config.json` in your data directory:

```json
{
  "image_library_dirs": [
    "/path/to/photos/folder1",
    "/path/to/photos/folder2"
  ],
  "top_k_default": 3,
  "include_extensions": [".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"],
  "build_workers": 0,
  "debug_dir": "/path/to/debug"
}
```

### Configuration Options

| Field | Description | Default |
|-------|-------------|---------|
| `image_library_dirs` | List of directories containing your photo library | `[]` (required) |
| `top_k_default` | Number of top matches to return | `3` |
| `include_extensions` | Image file extensions to index | `[".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"]` |
| `build_workers` | Parallel workers for index building (0=auto, 1=sequential, N=N workers) | `0` |
| `debug_dir` | Directory for saving debug images | `${data_dir}/debug` |

## Usage

### Web UI

Open http://YOUR_SERVER_IP:14322 in your desktop or mobile browser. Click "photo library" in the subtitle to view index status and trigger index builds directly from the web interface.

**Note**: Replace `YOUR_SERVER_IP` with the actual IP address or hostname where the server is running (e.g., `192.168.1.100`, `localhost` if running locally, or a domain name).

### API Endpoints

**Index Management** (asynchronous operations):
- `POST /api/index?rebuild=true` - Rebuild index from scratch (returns 202, runs in background)
- `POST /api/index` - Update index incrementally (add new/remove deleted, default)
- `GET /api/index/status` - Check index status and build progress

**Lookup & Detection**:
- `POST /api/lookup` - Find similar images (with optional bbox parameter)
- `POST /api/bbox` - Detect image boundaries in uploaded photo
- `GET /api/image?id=<image_id>` - Retrieve image by ID

**Other**:
- `GET /api/config` - Get server configuration
- `GET /api/health` - Health check endpoint

## How It Works

1. **Index Building**: PhotoLookup scans your photo directories and creates perceptual hashes (compact fingerprints) for each image. On an 8-core system, expect ~25-30 images/second. Index building runs asynchronously in the background.

2. **Boundary Detection**: When you upload a photo of a photobook page, the algorithm detects the actual image area, removing borders and backgrounds. This preprocessing improves matching accuracy.

3. **Similarity Search**: Your query image is hashed and compared against the index. Results are ranked by perceptual distance (0.0 = identical, higher values = more different). The web UI displays this as "confidence" (1 - distance) for easier interpretation.

## Docker Deployment

The `docker-compose.yml` provides a production-ready setup:

```yaml
services:
  photolookup:
    build: .
    ports:
      - "14322:14322"
    volumes:
      - ./config.docker:/data
      - /path/to/photos:/mnt/library:ro
    environment:
      - PHOTOLOOKUP_DATA_DIR=/data
    restart: unless-stopped
```

Mount your photo libraries as read-only volumes. The index persists in the `/data` directory.

## Development

See [AGENTS.md](AGENTS.md) for detailed technical documentation.

## Limitations

- **Perceptual hashing** works best for images with consistent content. Heavy crops, rotations, or added overlays may reduce accuracy.
- **Boundary detection** struggles with multiple stacked images on a single page.
- **Memory usage** scales with library size (typically 1-2 KB per image in the index).
- **Corrupted image files**: Large photo libraries may contain corrupted or truncated image files (typically 0.01-0.1% of files). These files are automatically skipped during indexing and logged in the index metadata. Common causes include incomplete file transfers, disk errors, or issues during original file creation (especially for large panoramas or stitched images).
- **Large panorama support**: Very large images (e.g., 8016×3776 panoramas, ~30MP) are supported but are more susceptible to corruption due to file size and complex encoding. Files with "broken data stream" errors indicate incomplete or corrupted JPEG data.
- **Processing failures**: Failed images are collected in the index metadata (`meta.errors` field) and can be inspected via `/api/index/status` or the web UI modal. The index build continues even if individual files fail to process.

## License

Apache License 2.0 - see [LICENSE](LICENSE) for details.

## Contributing

This is a personal tool made public. Feel free to fork and adapt for your needs. Issues and pull requests are welcome but response times may vary.
