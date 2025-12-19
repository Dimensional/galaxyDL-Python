# Galaxy DL - GOG Galaxy CDN Downloader

A specialized Python library for downloading GOG Galaxy files (chunks and binary blobs from Galaxy CDN).

This library focuses exclusively on downloading from the Galaxy content delivery network, handling depot manifests, chunks, and binary files. It is built by referencing and combining best practices from both [heroic-gogdl](https://github.com/Heroic-Games-Launcher/heroic-gogdl) (Python) and [lgogdownloader](https://github.com/Sude-/lgogdownloader) (C++).

## Features

- ✅ Download Galaxy v1 and v2 depot files
  - **V1**: Single-threaded main.bin blob downloads (legacy format)
  - **V2**: Multi-threaded 10MB chunk downloads (current format)
- ✅ Handle compressed chunks with zlib decompression  
- ✅ Support for dependencies and patches
- ✅ Small files container support
- ✅ Secure link generation and CDN URL management
- ✅ MD5/SHA256 verification for downloaded chunks
- ✅ Multi-threaded parallel downloads (V2)
- ✅ Automatic token refresh
- ✅ Resume capability for interrupted downloads

## Installation

```bash
pip install -e .
```

Or install dependencies manually:

```bash
pip install requests
```

## Quick Start

### 1. Authentication

First, authenticate with GOG:

```python
from galaxy_dl import AuthManager

auth = AuthManager()

# Get OAuth code from:
# https://auth.gog.com/auth?client_id=46899977096215655&redirect_uri=https%3A%2F%2Fembed.gog.com%2Fon_login_success%3Forigin%3Dclient&response_type=code&layout=client2

auth.login_with_code(code="YOUR_OAUTH_CODE_HERE")
```

### 2. Download Galaxy Files

**For V2 Manifests (10MB chunks - current format):**

```python
from galaxy_dl import GalaxyAPI, GalaxyDownloader, AuthManager

# Initialize
auth = AuthManager()
api = GalaxyAPI(auth)
downloader = GalaxyDownloader(api, max_workers=8)  # Multi-threaded

# Get depot items
depot_items = api.get_depot_items(manifest_hash="abc123...")

# Download chunks in parallel
for item in depot_items:
    output_path = downloader.download_item(item, output_dir="./downloads")
    print(f"Downloaded: {output_path}")
```

**For V1 Manifests (main.bin blob - legacy format):**

```python
from galaxy_dl import GalaxyAPI, GalaxyV1Downloader, AuthManager

# Initialize
auth = AuthManager()
api = GalaxyAPI(auth)
v1_downloader = GalaxyV1Downloader(api)  # Single-threaded

# Download main.bin blob
blob_path = v1_downloader.download_v1_blob(
    manifest_hash="abc123...",
    product_id="1234567890",
    output_dir="./downloads"
)

# Optional: Extract individual files
manifest_data = api.get_manifest_v1(product_id, "", manifest_hash)
if "files" in manifest_data:
    v1_downloader.extract_all_files_from_blob(
        blob_path,
        manifest_data["files"],
        "./game_files"
    )V2 chunk-based downloads (multi-threaded)
- **`galaxy_dl.downloader_v1`** - Download manager for V1 main.bin blobs (single-threaded)
- **`galaxy_dl.utils`** - Utility functions for hashing, compression, path handling
- **`galaxy_dl.constants`** - API endpoints and configuration constants

### V1 vs V2 Manifests

**Important**: Galaxy uses two different manifest formats:

- **V1 (Legacy)**: Single `main.bin` blob containing all files at specific offsets
  - Use `GalaxyV1Downloader` for single-threaded blob downloads
  - Extract files after downloading the blob
  
- **V2 (Current)**: Files split into ~10MB chunks, like Steam CDN
  - Use `GalaxyDownloader` for multi-threaded chunk downloads
  - Chunks automatically assembled into files

See [V1_VS_V2.md](V1_VS_V2.md) for detailed comparison and usage guide.
### 3. Download with Progress Tracking

```python
def progress_callback(downloaded, total):
    percent = (downloaded / total) * 100
    print(f"Progress: {percent:.1f}%")

downloader.download_item(
    item, 
    output_dir="./downloads",
    progress_callback=progress_callback
)
```

## Architecture

The library is organized into focused modules:

- **`galaxy_dl.api`** - Galaxy API client for accessing content-system endpoints
- **`galaxy_dl.auth`** - Authentication manager for OAuth token management  
- **`galaxy_dl.models`** - Data models for depots, chunks, manifests
- **`galaxy_dl.downloader`** - Download manager for chunk-based downloads
- **`galaxy_dl.utils`** - Utility functions for hashing, compression, path handling
- **`galaxy_dl.constants`** - API endpoints and configuration constants

## API Endpoints

This library uses the following GOG Galaxy API endpoints (updated from lgogdownloader):

| Endpoint | Purpose |
|----------|---------|
| `https://content-system.gog.com/products/{id}/os/{platform}/builds` | Get available builds |
| `https://cdn.gog.com/content-system/v2/meta/{path}` | Get v2 manifests |
| `https://cdn.gog.com/content-system/v1/manifests/{product_id}/{platform}/{build_id}/{manifest_id}.json` | Get v1 manifests |
| `https://content-system.gog.com/products/{id}/secure_link` | Get secure download links |
| `https://content-system.gog.com/dependencies/repository?generation=2` | Get dependencies |
| `https://content-system.gog.com/open_link` | Get dependency download links |

## Key Improvements from Reference Implementations

### From lgogdownloader (C++)
- ✅ Updated CDN URLs and API endpoints
- ✅ Better handling of manifest v2 with zlib compression
- ✅ Support for small files containers
- ✅ Enhanced secure link handling with CDN priority
- ✅ Improved path handling from download URLs

### From heroic-gogdl (Python)
- ✅ Clean Python API design
- ✅ Object-oriented data models
- ✅ Session-based HTTP requests
- ✅ Modular architecture

### Additional Enhancements  
- ✅ Type hints for better IDE support
- ✅ Comprehensive logging
- ✅ Progress callback support
- ✅ Parallel downloads with ThreadPoolExecutor
- ✅ Automatic hash verification

## Example Usage

See [`example.py`](example.py) for a complete working example.

## Development

### Project Structure

```
galaxy_dl/
├── __init__.py          # Package initialization
├── api.py               # Galaxy API client
├── auth.py              # Authentication manager
├── constants.py         # API endpoints and constants
├── downloader.py        # Download manager
├── models.py            # Data models
└── utils.py             # Utility functions
```

### Running Tests

```bash
pytest tests/
```

### Code Style

```bash
black galaxy_dl/
ruff check galaxy_dl/
```

## License

MIT License - See [LICENSE.new](LICENSE.new)

## Credits

This library is built upon research and reference implementations from:

- **[heroic-gogdl](https://github.com/Heroic-Games-Launcher/heroic-gogdl)** - Python GOG downloader by Heroic Games Launcher team
- **[lgogdownloader](https://github.com/Sude-/lgogdownloader)** - C++ GOG downloader by Sude-

Special thanks to the developers of these projects for their pioneering work in understanding the GOG Galaxy API.

## Disclaimer

This is an unofficial library and is not affiliated with or endorsed by GOG or CD Projekt. Use responsibly and in accordance with GOG's Terms of Service.
