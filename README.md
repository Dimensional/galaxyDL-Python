# Galaxy DL - GOG Galaxy CDN Downloader

A specialized Python library for downloading GOG Galaxy files (chunks and binary blobs from Galaxy CDN).

This library focuses exclusively on downloading from the Galaxy content delivery network, handling depot manifests, chunks, and binary files. It is built by referencing and combining best practices from both [heroic-gogdl](https://github.com/Heroic-Games-Launcher/heroic-gogdl) (Python) and [lgogdownloader](https://github.com/Sude-/lgogdownloader) (C++).

## Features

- ✅ **Multi-threaded Downloads** - Both V1 and V2 use parallel chunk downloads
  - **V1**: Multi-threaded range requests for main.bin blob (legacy format)
  - **V2**: Multi-threaded 10MB chunk downloads (current format)
- ✅ **User Library Access** - List owned games and browse available builds
- ✅ **Flexible Build Selection** - Direct access, build browsing, or delisted build support
- ✅ **Generation Auto-Detection** - Automatically detect and handle V1 or V2 manifests
- ✅ **Handle compressed chunks** with zlib decompression  
- ✅ **Support for dependencies and patches**
- ✅ **Small files container support**
- ✅ **Secure link generation and CDN URL management**
- ✅ **MD5/SHA256 verification** for downloaded chunks
- ✅ **Automatic token refresh**
- ✅ **Progress callback support** for frontends
- ✅ **Error recovery** with retry logic

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

### 2. Browse Your Library

```python
from galaxy_dl import GalaxyAPI, AuthManager

auth = AuthManager()
api = GalaxyAPI(auth)

# Get your owned games
game_ids = api.get_owned_games()
print(f"You own {len(game_ids)} games")

# Get details for a specific game
details = api.get_game_details(game_ids[0])
print(f"Title: {details['title']}")
```

### 3. Get Game Builds

```python
# List all available builds for a game
builds = api.get_all_product_builds("1207658924", "windows")

# Show builds to user
for idx, build in enumerate(builds["items"]):
    print(f"{idx}: Build {build['build_id']} - Gen {build.get('generation', 'unknown')}")

# User selects a build
selected_build = builds["items"][0]
```

### 4. Get Manifest

**Option A: From selected build (recommended for frontends):**
```python
manifest = api.get_manifest_from_build("1207658924", selected_build, "windows")
```

**Option B: Auto-detect with build_id:**
```python
manifest = api.get_manifest("1207658924", build_id="3101", platform="windows")
```

**Option C: Direct access (for delisted builds from gogdb.org):**
```python
# V1 with repository_id from gogdb.org
manifest = api.get_manifest_direct(
    product_id="1207658924",
    generation=1,
    repository_id="24085618",  # From gogdb.org "Repository timestamp"
    platform="windows"
)

# V2 with manifest link
manifest = api.get_manifest_direct(
    product_id="1207658924",
    generation=2,
    manifest_link="https://cdn.gog.com/content-system/v2/meta/..."
)
```

### 5. Download Files

```python
from galaxy_dl import GalaxyDownloader

downloader = GalaxyDownloader(api, max_workers=8)

# Get files from manifest
depot = manifest.depots[0]
# ... get items from depot ...

# Download with progress tracking
def progress_callback(downloaded, total):
    percent = (downloaded / total) * 100
    print(f"Progress: {percent:.1f}%")

for item in items:
    path = downloader.download_item(
        item,
        output_dir="./downloads",
        progress_callback=progress_callback
    )
    print(f"Downloaded: {path}")
```

## Architecture

The library is organized into focused modules:

- **`galaxy_dl.api`** - Galaxy API client (user library, builds, manifests)
- **`galaxy_dl.auth`** - Authentication manager for OAuth token management  
- **`galaxy_dl.models`** - Data models for depots, chunks, manifests
- **`galaxy_dl.downloader`** - Unified download manager (V1 and V2, multi-threaded)
- **`galaxy_dl.utils`** - Utility functions for hashing, compression, path handling
- **`galaxy_dl.constants`** - API endpoints and configuration constants
- **`galaxy_dl.cli`** - Command-line interface (basic)

### V1 vs V2 Manifests

**Important**: Galaxy uses two different manifest formats (auto-detected):

- **V1 (Legacy)**: Single `main.bin` blob containing all files at specific offsets
  - Uses multi-threaded HTTP range requests for parallel download
  - Automatically detected when `generation == 1`
  
- **V2 (Current)**: Files split into ~10MB chunks, like Steam CDN
  - Uses multi-threaded chunk downloads
  - Automatically detected when `generation == 2`

The `GalaxyDownloader` handles both transparently. See [GENERATION_DETECTION.md](GENERATION_DETECTION.md) and [DELISTED_BUILDS.md](DELISTED_BUILDS.md) for details.

## API Reference

### Core Classes

**`GalaxyAPI`** - Main API client
- `get_owned_games()` - List user's game library
- `get_game_details(game_id)` - Get game details with download options
- `get_all_product_builds(product_id, platform)` - Get all builds (V1+V2)
- `get_manifest_from_build(product_id, build, platform)` - Get manifest from build dict
- `get_manifest_direct(product_id, generation, ...)` - Direct access for delisted builds
- `get_manifest(product_id, build_id, platform)` - Auto-detect and fetch manifest

**`GalaxyDownloader`** - Unified downloader
- `download_item(item, output_dir, ...)` - Download single file (auto-detects V1/V2)
- `download_items_parallel(items, output_dir, ...)` - Download multiple files in parallel

**`AuthManager`** - OAuth authentication
- `login_with_code(code)` - Login with OAuth code
- `is_authenticated()` - Check authentication status
- `get_token()` - Get current access token

See [API_REFERENCE.md](API_REFERENCE.md) for complete documentation.

## API Endpoints

This library uses the following GOG Galaxy API endpoints:

| Endpoint | Purpose |
|----------|---------|
| `https://embed.gog.com/user/data/games` | Get owned games list |
| `https://embed.gog.com/account/gameDetails/{id}.json` | Get game details |
| `https://content-system.gog.com/products/{id}/os/{platform}/builds` | Get available builds |
| `https://cdn.gog.com/content-system/v2/meta/{path}` | Get v2 manifests |
| `https://cdn.gog.com/content-system/v1/manifests/...` | Get v1 manifests |
| `https://content-system.gog.com/products/{id}/secure_link` | Get secure download links |
| `https://content-system.gog.com/dependencies/repository` | Get dependencies |

## Key Improvements from Reference Implementations

### From lgogdownloader (C++)
- ✅ Updated CDN URLs and API endpoints
- ✅ V1 multi-threaded range requests (original was single-threaded)
- ✅ Better handling of manifest v2 with zlib compression
- ✅ Support for small files containers
- ✅ Enhanced secure link handling with CDN priority
- ✅ Improved path handling from download URLs
- ✅ Builds API quirk handling (generation parameter behavior)

### From heroic-gogdl (Python)
- ✅ Clean Python API design
- ✅ Object-oriented data models
- ✅ Session-based HTTP requests
- ✅ Modular architecture
- ✅ V2 parallel chunk downloads

### Additional Enhancements  
- ✅ **Unified downloader** - Single class handles both V1 and V2
- ✅ **User library access** - Browse owned games and builds
- ✅ **Flexible build selection** - Direct, auto-detect, or delisted build access
- ✅ **Type hints** for better IDE support
- ✅ **Comprehensive logging** with configurable levels
- ✅ **Progress callback support** for frontend integration
- ✅ **Multi-threaded V1 and V2** downloads for maximum speed
- ✅ **Automatic hash verification** with retry logic
- ✅ **Build merging** - Queries both gen=1 and gen=2 to get all available builds

## Example Usage

See the [`examples/`](examples/) directory for practical examples:
- **`list_library.py`** - List your owned games with details
- **`download_game.py`** - Complete download workflow
- **`build_selection.py`** - Interactive build selector
- **`delisted_builds.py`** - Access delisted builds using gogdb.org data

Or see [`example.py`](example.py) for a basic example.

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
