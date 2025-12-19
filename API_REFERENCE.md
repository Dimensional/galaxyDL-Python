# API Reference

Complete reference for all classes and methods in galaxy-dl.

## Table of Contents
- [GalaxyAPI](#galaxyapi) - Main API client
- [GalaxyDownloader](#galaxydownloader) - File downloader
- [AuthManager](#authmanager) - Authentication
- [Data Models](#data-models) - Manifest, Depot, DepotItem

---

## GalaxyAPI

Main API client for accessing GOG Galaxy content system and user library.

### Constructor

```python
GalaxyAPI(auth_manager: AuthManager, logger: Optional[logging.Logger] = None)
```

**Parameters:**
- `auth_manager`: AuthManager instance for authentication
- `logger`: Optional logger instance

**Example:**
```python
from galaxy_dl import GalaxyAPI, AuthManager

auth = AuthManager()
api = GalaxyAPI(auth)
```

---

### User Library Methods

#### `get_owned_games() -> List[int]`

Get list of owned game IDs from user's GOG library.

**Returns:** List of product IDs (integers)

**Example:**
```python
game_ids = api.get_owned_games()
print(f"You own {len(game_ids)} games")
# [1207658691, 1207658713, 1207658805, ...]
```

---

#### `get_game_details(game_id: int) -> Dict[str, Any]`

Get detailed information about a specific game.

**Parameters:**
- `game_id`: GOG product ID

**Returns:** Dictionary containing:
- `title`: Game title
- `backgroundImage`: Background image URL  
- `downloads`: Available downloads per language/platform
- `extras`: Bonus content (manuals, wallpapers, etc.)
- `dlcs`: DLC information
- `tags`: Game tags
- `releaseTimestamp`: Release date (Unix timestamp)
- `forumLink`: Forum URL
- `changelog`: Changelog (if available)

**Example:**
```python
details = api.get_game_details(1207658924)
print(details["title"])
# "Unreal Tournament 2004 Editor's Choice Edition"

for lang, platforms in details["downloads"]:
    print(f"Language: {lang}")
    for platform, files in platforms.items():
        print(f"  {platform}: {len(files)} files")
```

---

#### `get_owned_games_with_details(limit: Optional[int] = None) -> List[Dict[str, Any]]`

Get owned games with full details for each.

**Parameters:**
- `limit`: Optional limit on number of games (useful for testing/pagination)

**Returns:** List of game detail dictionaries (each includes `id` field)

**Example:**
```python
# Get first 10 games with details
games = api.get_owned_games_with_details(limit=10)
for game in games:
    print(f"{game['title']} (ID: {game['id']})")
```

---

### Build Methods

#### `get_product_builds(product_id: str, platform: str = "windows", generation: str = "2", filter_generation: Optional[int] = None) -> Dict[str, Any]`

Get available builds for a product from a specific generation endpoint.

**Important:** GOG API has quirky behavior:
- `generation="1"` returns ONLY V1 builds (may miss some in gen=2)
- `generation="2"` returns BOTH V1 and V2 builds (may miss some in gen=1)
- Some builds only appear in one endpoint

**Parameters:**
- `product_id`: GOG product ID
- `platform`: Platform (`"windows"`, `"osx"`, `"linux"`)
- `generation`: Generation to query (`"1"` or `"2"`)
- `filter_generation`: Optional filter to specific generation after query

**Returns:** Build list JSON with `items` array

**Example:**
```python
# Query generation 2 endpoint
builds = api.get_product_builds("1207658924", "windows", generation="2")
```

---

#### `get_all_product_builds(product_id: str, platform: str = "windows") -> Dict[str, Any]`

Get ALL available builds (both V1 and V2) by querying both endpoints and merging results.

**Recommended** for complete build discovery. This method:
1. Queries `generation="1"` endpoint
2. Queries `generation="2"` endpoint  
3. Merges and deduplicates results
4. Sorts by date (newest first)

**Parameters:**
- `product_id`: GOG product ID
- `platform`: Platform

**Returns:** Merged build list with all builds

**Example:**
```python
builds = api.get_all_product_builds("1207658924", "windows")
for build in builds["items"]:
    print(f"Build {build['build_id']} - Gen {build.get('generation')}")
```

---

#### `get_build_by_id(product_id: str, build_id: Optional[str] = None, platform: str = "windows") -> Optional[Dict[str, Any]]`

Get specific build by ID or latest build.

**Parameters:**
- `product_id`: GOG product ID
- `build_id`: Build ID (if None, returns latest)
- `platform`: Platform

**Returns:** Dict with `"build"` and `"generation"` keys, or None

**Example:**
```python
build_info = api.get_build_by_id("1207658924", "3101")
if build_info:
    print(f"Generation: {build_info['generation']}")
    print(f"Build ID: {build_info['build']['build_id']}")
```

---

### Manifest Methods

#### `get_manifest(product_id: str, build_id: Optional[str] = None, platform: str = "windows") -> Optional[Manifest]`

Get manifest with automatic generation detection.

Queries builds API to find build, then fetches appropriate manifest.

**Parameters:**
- `product_id`: GOG product ID
- `build_id`: Build ID (if None, uses latest)
- `platform`: Platform

**Returns:** Manifest object or None

**Example:**
```python
manifest = api.get_manifest("1207658924", "3101", "windows")
print(f"Generation: {manifest.generation}")
print(f"Depots: {len(manifest.depots)}")
```

---

#### `get_manifest_from_build(product_id: str, build: Dict[str, Any], platform: str = "windows") -> Optional[Manifest]`

**Recommended for frontends** - Get manifest from a build dict.

Use this after user selects from builds list to avoid redundant API queries.

**Parameters:**
- `product_id`: GOG product ID
- `build`: Build dict from `get_all_product_builds()` 
- `platform`: Platform

**Returns:** Manifest object or None

**Example:**
```python
# Frontend workflow
builds = api.get_all_product_builds("1207658924")
selected_build = builds["items"][0]  # User selects
manifest = api.get_manifest_from_build("1207658924", selected_build)
```

---

#### `get_manifest_direct(product_id: str, generation: int, repository_id: Optional[str] = None, manifest_link: Optional[str] = None, build_id: Optional[str] = None, platform: str = "windows") -> Optional[Manifest]`

Get manifest directly without querying builds API.

Use for delisted builds (from gogdb.org) or cached data.

**Parameters:**
- `product_id`: GOG product ID
- `generation`: 1 or 2
- `repository_id`: Required for V1 (legacy_build_id / repository timestamp)
- `manifest_link`: Required for V2 (full manifest URL)
- `build_id`: Optional (for tracking)
- `platform`: Platform (V1 only)

**Returns:** Manifest object or None

**Example (V1 from gogdb.org):**
```python
# gogdb.org shows: Repository timestamp: 24085618
manifest = api.get_manifest_direct(
    product_id="1207658924",
    generation=1,
    repository_id="24085618",
    platform="osx"
)
```

**Example (V2 with cached link):**
```python
manifest = api.get_manifest_direct(
    product_id="1207658924",
    generation=2,
    manifest_link="https://cdn.gog.com/content-system/v2/meta/..."
)
```

---

#### `get_manifest_v1(product_id: str, repository_id: str, manifest_id: str = "repository", platform: str = "windows") -> Dict[str, Any]`

Get V1 manifest JSON using repository ID.

**Parameters:**
- `product_id`: GOG product ID
- `repository_id`: Repository ID (legacy_build_id)
- `manifest_id`: Manifest ID (default: "repository")
- `platform`: Platform

**Returns:** V1 manifest JSON

---

#### `get_manifest_v1_direct(product_id: str, repository_id: str, platform: str = "windows") -> Dict[str, Any]`

Get V1 manifest directly by repository ID (for delisted builds).

**Parameters:**
- `product_id`: GOG product ID
- `repository_id`: Repository ID from gogdb.org
- `platform`: Platform

**Returns:** V1 manifest JSON

**Example:**
```python
# From gogdb.org Repository timestamp
manifest_json = api.get_manifest_v1_direct("1207658924", "24085618", "osx")
```

---

#### `get_manifest_by_url(url: str) -> Dict[str, Any]`

Get manifest directly by URL (maximum flexibility).

**Parameters:**
- `url`: Full manifest URL

**Returns:** Manifest JSON

**Example:**
```python
url = "https://cdn.gog.com/content-system/v1/manifests/1207658924/osx/24085618/repository.json"
manifest = api.get_manifest_by_url(url)
```

---

#### `get_manifest_v2(manifest_hash: str, is_dependency: bool = False) -> Dict[str, Any]`

Get V2 manifest data.

**Parameters:**
- `manifest_hash`: Manifest hash  
- `is_dependency`: Whether this is a dependency

**Returns:** V2 manifest JSON

---

### Other Methods

#### `get_secure_link(product_id: str, path: str = "/", generation: str = "2") -> List[str]`

Get secure download links (CDN URLs) for a product.

**Parameters:**
- `product_id`: GOG product ID
- `path`: Path parameter
- `generation`: Generation version

**Returns:** List of CDN URLs with `{GALAXY_PATH}` placeholder

---

#### `get_product_info(product_id: str) -> Dict[str, Any]`

Get detailed product information from GOG API.

**Parameters:**
- `product_id`: GOG product ID

**Returns:** Product info JSON

---

## GalaxyDownloader

Unified downloader for both V1 and V2 manifests.

### Constructor

```python
GalaxyDownloader(api: GalaxyAPI, max_workers: int = 4)
```

**Parameters:**
- `api`: GalaxyAPI instance
- `max_workers`: Maximum concurrent download threads

**Example:**
```python
downloader = GalaxyDownloader(api, max_workers=8)
```

---

### Methods

#### `download_item(item: DepotItem, output_dir: str, cdn_urls: Optional[List[str]] = None, verify_hash: bool = True, progress_callback: Optional[Callable[[int, int], None]] = None) -> str`

Download a depot item (auto-detects V1 vs V2).

**Parameters:**
- `item`: DepotItem to download
- `output_dir`: Directory to save file
- `cdn_urls`: List of CDN URLs (fetched if not provided)
- `verify_hash`: Whether to verify hashes
- `progress_callback`: Optional callback(bytes_downloaded, total_bytes)

**Returns:** Path to downloaded file

**Example:**
```python
def progress(downloaded, total):
    percent = (downloaded / total) * 100
    print(f"\rProgress: {percent:.1f}%", end="")

path = downloader.download_item(
    item,
    output_dir="./downloads",
    progress_callback=progress
)
```

---

#### `download_items_parallel(items: List[DepotItem], output_dir: str, cdn_urls: Optional[List[str]] = None, verify_hash: bool = True, progress_callback: Optional[Callable[[str, int, int], None]] = None) -> Dict[str, str]`

Download multiple items in parallel.

**Parameters:**
- `items`: List of DepotItems
- `output_dir`: Directory to save files
- `cdn_urls`: List of CDN URLs
- `verify_hash`: Whether to verify hashes
- `progress_callback`: Optional callback(item_path, bytes_downloaded, total_bytes)

**Returns:** Dict mapping item paths to downloaded file paths

**Example:**
```python
def item_progress(path, downloaded, total):
    print(f"{path}: {downloaded}/{total} bytes")

results = downloader.download_items_parallel(
    items,
    output_dir="./downloads",
    progress_callback=item_progress
)
```

---

## AuthManager

OAuth authentication manager.

### Constructor

```python
AuthManager(config_path: str = "~/.config/galaxy-dl/auth.json")
```

**Parameters:**
- `config_path`: Path to store authentication tokens

---

### Methods

#### `login_with_code(code: str) -> bool`

Login with OAuth code from GOG.

Get code from: https://auth.gog.com/auth?client_id=46899977096215655&redirect_uri=https%3A%2F%2Fembed.gog.com%2Fon_login_success%3Forigin%3Dclient&response_type=code&layout=client2

**Parameters:**
- `code`: OAuth code

**Returns:** True if successful

**Example:**
```python
auth = AuthManager()
if auth.login_with_code("YOUR_CODE_HERE"):
    print("Authenticated!")
```

---

#### `is_authenticated() -> bool`

Check if user is authenticated with valid token.

**Returns:** True if authenticated

---

#### `get_token() -> Optional[str]`

Get current access token.

**Returns:** Access token string or None

---

#### `refresh_token() -> bool`

Refresh the access token using refresh token.

**Returns:** True if successful

---

## Data Models

### Manifest

Represents a Galaxy manifest.

**Attributes:**
- `base_product_id: str` - Base product ID
- `build_id: Optional[str]` - Build ID (user-facing)
- `repository_id: Optional[str]` - Repository ID (V1 only, legacy_build_id)
- `generation: int` - Build generation (1 or 2)
- `version: int` - Manifest version (same as generation)
- `install_directory: str` - Installation directory name
- `depots: List[Depot]` - List of depots
- `dependencies: List[str]` - List of dependency IDs
- `raw_data: Dict[str, Any]` - Raw JSON data

**Methods:**
- `from_json_v1(manifest_json, product_id)` - Create from V1 JSON
- `from_json_v2(manifest_json)` - Create from V2 JSON
- `get_filtered_depots(language, bitness, product_ids)` - Get filtered depots

---

### Depot

Represents a depot in a manifest.

**Attributes:**
- `product_id: str` - Product ID
- `manifest: str` - Manifest hash
- `languages: List[str]` - Supported languages
- `size: int` - Total size
- `compressed_size: int` - Compressed size
- `bitness: Optional[List[str]]` - OS bitness (32/64)

**Methods:**
- `from_json(depot_json)` - Create from JSON
- `matches_filters(language, bitness)` - Check if depot matches filters

---

### DepotItem

Represents a file in a depot.

**Attributes:**
- `path: str` - Relative file path
- `chunks: List[DepotItemChunk]` - Chunks (V2)
- `total_size_compressed: int` - Total compressed size
- `total_size_uncompressed: int` - Total uncompressed size
- `md5: Optional[str]` - MD5 hash
- `sha256: Optional[str]` - SHA256 hash
- `product_id: str` - Product ID
- `is_dependency: bool` - Is dependency
- `is_v1_blob: bool` - Is V1 main.bin blob
- `v1_offset: int` - Offset in V1 main.bin
- `v1_size: int` - Size in V1 main.bin
- `v1_blob_md5: str` - MD5 of V1 blob
- `v1_blob_path: str` - Path to main.bin

**Methods:**
- `from_json_v2(item_json, product_id, is_dependency)` - Create from V2 JSON
- `from_json_sfc(sfc_json, product_id, is_dependency)` - Create from small files container JSON

---

### DepotItemChunk

Represents a single chunk in V2.

**Attributes:**
- `md5_compressed: str` - MD5 of compressed chunk
- `md5_uncompressed: str` - MD5 of uncompressed chunk
- `size_compressed: int` - Compressed size
- `size_uncompressed: int` - Uncompressed size
- `offset_compressed: int` - Offset in compressed file
- `offset_uncompressed: int` - Offset in uncompressed file

**Methods:**
- `from_json(chunk_json, offset_compressed, offset_uncompressed)` - Create from JSON

---

## Error Handling

### DownloadError

Raised when download fails.

```python
from galaxy_dl.downloader import DownloadError

try:
    path = downloader.download_item(item, "./downloads")
except DownloadError as e:
    print(f"Download failed: {e}")
```

---

## Examples

See the [`examples/`](examples/) directory for complete working examples.
