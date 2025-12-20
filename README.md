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
- ✅ **MD5 verification** for downloaded chunks
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

## Command-Line Interface

The library includes a minimal CLI (`galaxy-dl`) for authentication and basic operations. For full functionality, use the example scripts in the `examples/` folder.

### Authentication

Get started by authenticating with your GOG account:

```bash
# Show authentication instructions
galaxy-dl login

# Authenticate with OAuth code
galaxy-dl login YOUR_CODE_HERE
```

The CLI will guide you through:
1. Visiting the GOG OAuth URL
2. Logging into your GOG account
3. Copying the authorization code from the redirect URL
4. Completing authentication

Credentials are saved to `~/.config/galaxy_dl/auth.json` and automatically used by all CLI commands and example scripts.

### Browse Your Library

```bash
# List your owned games (IDs only)
galaxy-dl library

# List with game titles (slower, fetches details)
galaxy-dl library --details

# Limit number of games shown
galaxy-dl library --details --limit 20
```

### View Build Information

```bash
# Show available builds for a game
galaxy-dl info 1207658930

# Show builds for a specific platform
galaxy-dl info 1207658930 --platform osx
```

### Full-Featured Examples

For actual downloading and validation, use the example scripts:
- `examples/download_game.py` - Interactive game downloader
- `examples/validate_game.py` - Validate downloaded archives
- `examples/archive_game.py` - Mirror entire game to local archive
- `examples/list_library.py` - Full library browser with details
- See `examples/` folder for more

## Quick Start (Python API)

### 1. Authentication

First, authenticate with GOG (or use `galaxy-dl login`):

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

## CDN Structure and Archive Mirroring

### Understanding GOG Galaxy CDN Paths

The archive system (`archive_game.py`) mirrors GOG's exact CDN structure to preserve the 1:1 relationship between local files and remote resources. This documentation explains why paths are structured the way they are.

### V1 Build Structure (Legacy Format)

**Directory Layout:**
```
<game_name>/v1/
├── manifests/{game_id}/{platform}/{timestamp}/
│   ├── repository.json                    # Build metadata
│   └── {manifest_uuid}.json               # File manifests (plain JSON)
└── depots/{game_id}/{platform}/{timestamp}/
    └── main.bin                           # All files in one blob
```

**CDN URLs (Static - No Authentication Required):**
```
Repository:  https://cdn.gog.com/content-system/v1/manifests/{game_id}/{platform}/{timestamp}/repository.json
Manifests:   https://cdn.gog.com/content-system/v1/manifests/{game_id}/{platform}/{timestamp}/{manifest_uuid}.json
```

**CDN URLs (Authenticated - Secure Links Required):**
```
main.bin:    Requires secure link authentication
             Path format: /{platform}/{timestamp}/main.bin
             
API Call:    GET https://content-system.gog.com/products/{game_id}/secure_link
             ?_version=2&type=depot&path=/{platform}/{timestamp}/main.bin

Response:    { "url_format": "{base_url}/token=...{path}",
               "parameters": { "path": "/content-system/v1/depots/{game_id}/{platform}/{timestamp}/main.bin", ... } }
```

**How V1 Works:**
1. Repository contains list of manifest UUIDs
2. Each manifest contains file entries with offset/size in main.bin
3. main.bin is a single binary blob containing all files
4. Files extracted using byte-range requests at specified offsets

**Why This Structure:**
- `{timestamp}` is the repository ID (e.g., 37794096)
- Each platform (windows/osx/linux) has separate main.bin
- Same files appear at different offsets per platform
- Manifests are plain JSON (no compression)

---

### V2 Build Structure (Current Format)

**Directory Layout:**
```
<game_name>/v2/
├── meta/{hash[:2]}/{hash[2:4]}/{hash}     # Depot & manifest metadata (zlib compressed)
├── store/{hash[:2]}/{hash[2:4]}/{hash}    # File chunks (zlib compressed)
└── debug/
    ├── {hash}_depot.json                  # Human-readable depot
    └── {hash}_manifest.json               # Human-readable manifests
```

**CDN URLs (Static URLs - No Authentication Required):**
```
Depot:       https://cdn.gog.com/content-system/v2/meta/{hash[:2]}/{hash[2:4]}/{hash}
Manifests:   https://cdn.gog.com/content-system/v2/meta/{hash[:2]}/{hash[2:4]}/{hash}
```

**CDN URLs (Authenticated - Secure Links Required):**
```
Chunks:      https://cdn.gog.com/content-system/v2/store/{product_id}/{hash[:2]}/{hash[2:4]}/{hash}
             
API Call:    GET https://content-system.gog.com/products/{product_id}/secure_link
             ?_version=2&generation=2&path=/

Response:    { "url_format": "{base_url}/token=...{path}",
               "parameters": { "path": "/content-system/v2/store/{product_id}", ... } }
             
Final URL:   Append "/{hash[:2]}/{hash[2:4]}/{hash}" to path parameter
             Result: /content-system/v2/store/{product_id}/{hash[:2]}/{hash[2:4]}/{hash}
```

**How V2 Works:**
1. Depot metadata lists 1+ manifest hashes
2. Each manifest contains file entries with chunk lists
3. Each chunk is a compressed piece of file data
4. Chunks are deduplicated per-product (same hash = same chunk)
5. Files assembled by concatenating decompressed chunks

**Why This Structure:**
- Content-addressed storage: `{hash}` = MD5 of compressed chunk
- Per-product deduplication: All builds of same game share chunk pool
- Hash-based paths enable global CDN caching
- Compressed JSONs saved efficiency (zlib format)

---

### Secure Link Authentication

**Why Some URLs Need Secure Links:**

GOG uses secure links for paid content to:
- Verify user owns the product
- Prevent unauthorized downloads
- Enable CDN token-based authentication
- Set time-limited download windows

**Static URLs (No Auth):**
- V1 repository.json and manifests
- V2 depot and manifest metadata

**Secure Links Required:**
- V1 main.bin (entire game blob)
- V2 chunks (individual file pieces)

**How We Optimize:**
- V1: One secure link call per main.bin download
- V2: One secure link call per product (reused for all chunks)
  - Get base path: `/content-system/v2/store/{product_id}`
  - Append chunk paths: `/{hash[:2]}/{hash[2:4]}/{hash}`
  - Avoids 3,000+ API calls for large games

**Token Expiration:**
```
"expires_at": 1766336033  (Unix timestamp)
```
Tokens typically valid for ~1 hour. Archive script completes before expiration for most games.

---

### Archive Benefits

**1:1 CDN Mirror:**
- Exact replica of GOG's storage structure
- Can verify against live CDN
- Easy to understand and audit
- Preserves original compression

**Delisted Build Support:**
- Works with repository IDs from gogdb.org
- No need for game to be in your library
- Historical build preservation

**Efficient Storage:**
- V2 deduplication saves space
- Compressed format preserved
- Debug JSONs optional for inspection

---

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
- **`archive_game.py`** - Downloads v1/v2 manifests and files.

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

### Code Style

```bash
black galaxy_dl/
ruff check galaxy_dl/
```

## License

MIT License - See [LICENSE](LICENSE)

## Credits

This library is built upon research and reference implementations from:

- **[heroic-gogdl](https://github.com/Heroic-Games-Launcher/heroic-gogdl)** - Python GOG downloader by Heroic Games Launcher team
- **[lgogdownloader](https://github.com/Sude-/lgogdownloader)** - C++ GOG downloader by Sude-

Special thanks to the developers of these projects for their pioneering work in understanding the GOG Galaxy API.

## Disclaimer

This is an unofficial library and is not affiliated with or endorsed by GOG or CD Projekt. Use responsibly and in accordance with GOG's Terms of Service.
