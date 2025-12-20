# Examples

Practical examples for using galaxy-dl.

## Getting Started

1. **Authentication Required**: Run `list_library.py` first to authenticate
2. **Each example** demonstrates specific functionality
3. **All examples** include helpful prompts and error handling

## Examples

### [list_library.py](list_library.py)
**Browse your GOG library**

Shows how to:
- Authenticate with GOG
- List all owned games
- Get detailed information for each game
- Display available platforms and extras

```bash
python examples/list_library.py
```

---

### [build_selection.py](build_selection.py)
**Interactive build selector**

Shows how to:
- List all available builds for a game
- Display V1 vs V2 generation info
- Let user select from builds list
- Get manifest efficiently using `get_manifest_from_build()`

```bash
python examples/build_selection.py
```

---

### [delisted_builds.py](delisted_builds.py)
**Access delisted builds using gogdb.org**

Shows how to:
- Use repository_id from gogdb.org for V1 builds
- Use manifest links for V2 builds
- Access builds without querying builds API
- Handle delisted/removed builds

```bash
python examples/delisted_builds.py
```

**Note:** Get build information from [gogdb.org](https://www.gogdb.org/) for delisted builds.

---

### [download_game.py](download_game.py)
**Complete download workflow**

Shows the full process:
1. Browse your game library
2. Select a game
3. Choose platform
4. Select build
5. Get manifest
6. Download files

```bash
python examples/download_game.py
```

---

### [v1_download.py](v1_download.py)
**V1 Download - Two Approaches**

Shows both V1 download methods:
1. **Download whole main.bin blob** - Fastest for complete game, large file
2. **Extract individual files** - Range requests from main.bin, selective download

```bash
python examples/v1_download.py
```

**Use Cases:**
- **Blob mode**: Download entire game quickly, extract files later
- **File mode**: Download only specific files (e.g., .exe, .dll)

---

### [v2_download.py](v2_download.py)
**V2 Download - Two Approaches**

Shows both V2 download methods:
1. **Raw chunks** - Save compressed ~10MB chunks without decompression
2. **Processed files** - Download, decompress, and assemble into game files

```bash
python examples/v2_download.py
```

**Use Cases:**
- **Raw mode**: Cache chunks for faster reinstalls, custom processing
- **Processed mode**: Direct installation, files ready immediately

---

### [archive_game.py](archive_game.py)
**Complete 1:1 CDN Archival**

Downloads everything in original format for archival/mirroring:
- **Depot/Repository JSONs** (as served from CDN)
- **Manifest JSONs** (as served from CDN)
- **All chunks/blobs** (original CDN format)
- **Directory structure mirrors CDN URL paths exactly**

```bash
# V2 build
python examples/archive_game.py v2 <game_id> <build_id> [game_name]

# V1 build
python examples/archive_game.py v1 <game_id> <repository_id> [game_name]
```

**Examples:**
```bash
python examples/archive_game.py v2 1207658930 92ab42631ff4742b309bb62c175e6306 "The Witcher 2"
python examples/archive_game.py v1 1207658930 37794096 "The Witcher 2"
```

**V2 Directory Structure** (mirrors CDN `/content-system/v2/...`):
```
The Witcher 2/
└── v2/
    ├── meta/
    │   ├── 92/ab/92ab42631ff4742b309bb62c175e6306       # Depot (zlib compressed)
    │   ├── 79/a1/79a1f5fd67f6d0cda22c51f1bd706b31       # Manifest (zlib compressed)
    │   └── ...                                          # All manifests
    ├── store/
    │   ├── 2e/0d/2e0dc2f5707ec0d88d570240ba918bb2       # Chunk (zlib compressed)
    │   └── ...                                          # All chunks
    └── debug/
        ├── 92ab42631ff4742b309bb62c175e6306_depot.json     # Human-readable depot
        ├── 79a1f5fd67f6d0cda22c51f1bd706b31_manifest.json  # Human-readable manifest
        └── ...                                              # All decompressed JSONs
```

**V1 Directory Structure** (mirrors CDN `/content-system/v1/...`):
```
The Witcher 2/
└── v1/
    └── manifests/
        └── 1207658930/                                  # Game ID
            └── windows/                                 # Platform
                └── 37794096/                            # Repository ID
                    ├── repository.json                  # Plain JSON
                    └── 463cd4b2-783e-447a-b17e-a68d601911e3.json  # Manifest UUID
```

**CDN File Formats:**
- **V2**: NO file extensions, all content is zlib compressed
  - **Debug folder**: Human-readable decompressed JSONs with type suffixes (`_depot.json`, `_manifest.json`)
- **V1**: `.json` extensions, plain JSON (no compression, already human-readable)
- **Paths match exactly** what appears after `content-system` in CDN URLs

**Use Cases:**
- **Legal archival/preservation** - Save games exactly as distributed
- **Offline CDN mirror** - Create local replica for reinstalls
- **Integrity verification** - Validate using manifest hashes
- **Custom extraction tools** - Process raw data with your own code

---

## Common Patterns```bash
python examples/v2_download.py
```

**Use Cases:**
- **Raw mode**: Cache chunks for faster reinstalls, custom processing
- **Processed mode**: Direct installation, files ready immediately

---

## Common Patterns

### Authenticating

```python
from galaxy_dl import AuthManager

auth = AuthManager()

if not auth.is_authenticated():
    # Get code from GOG OAuth URL
    code = input("Enter OAuth code: ")
    auth.login_with_code(code)
```

### Listing Games

```python
from galaxy_dl import GalaxyAPI

api = GalaxyAPI(auth)
game_ids = api.get_owned_games()
games = api.get_owned_games_with_details(limit=10)
```

### Getting Builds

```python
# Get ALL builds (recommended)
builds = api.get_all_product_builds(product_id, "windows")

# User selects from list
selected_build = builds["items"][0]

# Get manifest efficiently
manifest = api.get_manifest_from_build(product_id, selected_build)
```

### Downloading

```python
from galaxy_dl import GalaxyDownloader

downloader = GalaxyDownloader(api, max_workers=8)

# Download with progress
def progress(downloaded, total):
    print(f"Progress: {downloaded}/{total}")

path = downloader.download_item(
    item,
    output_dir="./downloads",
    progress_callback=progress
)
```

---

## Tips

1. **Use `get_all_product_builds()`** - Queries both generation endpoints to get all builds
2. **Use `get_manifest_from_build()`** - More efficient when user selects from list
3. **Use `get_manifest_direct()`** - For delisted builds with gogdb.org data
4. **Check gogdb.org** - For repository IDs and historical build data
5. **Multi-threading** - Both V1 and V2 downloads use parallel workers

---

## See Also

- [API Reference](../API_REFERENCE.md) - Complete API documentation
- [README](../README.md) - Library overview
- [GENERATION_DETECTION.md](../GENERATION_DETECTION.md) - Understanding V1 vs V2
- [DELISTED_BUILDS.md](../DELISTED_BUILDS.md) - Accessing delisted builds
