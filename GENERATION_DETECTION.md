# Generation Detection in Galaxy Downloads

## Overview

GOG Galaxy uses a "generation" field in the builds API to distinguish between two different manifest formats:

- **Generation 1 (V1)**: Legacy format from "GOG 1.0 days"
- **Generation 2 (V2)**: Modern format with chunked downloads

The generation value determines the entire download workflow and file structure.

## How Generation Detection Works

### API Endpoint

The builds endpoint returns generation information:
```
https://content-system.gog.com/products/{product_id}/os/{platform}/builds?generation={1|2}
```

### JSON Structure

Example builds response:
```json
{
  "items": [
    {
      "build_id": "12345",
      "version": "1.0.5",
      "generation": 2,
      "link": "https://cdn.gog.com/content-system/v2/meta/abc123def456...",
      "date_published": "2024-01-15T10:30:00Z"
    }
  ]
}
```

The `generation` field is the key indicator.

## Implementation in galaxy-dl

### Automatic Detection

The `GalaxyAPI` class provides automatic generation detection:

```python
from galaxy_dl.api import GalaxyAPI
from galaxy_dl.auth import AuthManager

auth = AuthManager(...)
api = GalaxyAPI(auth)

# Get manifest with automatic generation detection
manifest = api.get_manifest(product_id="1234567890", build_id=None)

# Generation is stored in the manifest object
print(f"Generation: {manifest.generation}")  # 1 or 2
```

### Manual Build Selection

You can also manually query builds and select specific versions:

```python
# Get latest build info with generation
build_info = api.get_build_by_id(product_id="1234567890")
print(f"Generation: {build_info['generation']}")
print(f"Build ID: {build_info['build']['build_id']}")

# Get specific build by ID
build_info = api.get_build_by_id(
    product_id="1234567890",
    build_id="specific-build-id"
)
```

### Legacy Index-Based Selection

For compatibility with lgogdownloader, build_id can be a numeric string (index):

```python
# Get first build (index 0)
build_info = api.get_build_by_id(product_id="1234567890", build_id="0")

# Get second build (index 1)
build_info = api.get_build_by_id(product_id="1234567890", build_id="1")
```

### Fallback Behavior

If a product doesn't have generation 2 builds, the library automatically falls back to generation 1:

```python
# Tries generation 2 first, then generation 1
manifest = api.get_manifest(product_id="old-game-id")
```

## Differences Between Generations

### Generation 1 (V1)

**Structure:**
- Single `main.bin` blob file containing all game files
- Individual files stored with offset/size metadata
- No compression
- Files extracted from blob using range requests

**Download Process:**
1. Download entire `main.bin` (or use range requests for specific sections)
2. Extract individual files using offset/size from manifest
3. Verify using MD5 hashes

**Manifest Structure:**
```json
{
  "buildId": "12345",
  "depot": {
    "manifest": "v1-manifest-hash",
    "size": 1073741824
  },
  "files": [
    {
      "path": "game.exe",
      "size": 1048576,
      "offset": 0,
      "hash": "abc123..."
    }
  ]
}
```

### Generation 2 (V2)

**Structure:**
- Individual ~10MB chunks with zlib compression
- Each file split into multiple chunks
- Chunks downloaded independently
- MD5 verification for each chunk

**Download Process:**
1. Download each chunk independently
2. Decompress using zlib (window size 15)
3. Assemble chunks into complete files
4. Verify file MD5

**Manifest Structure:**
```json
{
  "baseProductId": "1234567890",
  "buildId": "67890",
  "depots": [
    {
      "manifest": "v2-manifest-hash",
      "languages": ["en", "*"],
      "size": 1073741824
    }
  ]
}
```

## Use Cases

### Frontend Applications

When building a frontend (CLI, TUI, GUI) that uses galaxy-dl:

```python
# 1. List available builds for user selection
builds = api.get_product_builds(product_id, platform)
for i, build in enumerate(builds["items"]):
    print(f"{i}: Version {build.get('version')} (Gen {build.get('generation')})")

# 2. Let user select build by index or ID
selected_build_id = user_input()

# 3. Get manifest with automatic handling
manifest = api.get_manifest(product_id, selected_build_id)

# 4. Download based on generation
if manifest.generation == 1:
    # Handle V1 download workflow
    downloader.download_v1(manifest)
else:
    # Handle V2 download workflow
    downloader.download_v2(manifest)
```

### Delisted Games

For games removed from GOG store but with files still accessible:

```python
# Manually specify product_id even if not in catalog
manifest = api.get_manifest(
    product_id="removed-game-id",
    build_id=None  # Gets latest available
)

# Generation detection still works
if manifest:
    print(f"Found delisted game, generation {manifest.generation}")
```

## Reference Implementations

This implementation is based on:

1. **heroic-gogdl** (Python)
   - `gogdl/dl/managers/manager.py` lines 125-142
   - Uses `target_build["generation"]` to route to v1.Manager or v2.Manager

2. **lgogdownloader** (C++)
   - `src/downloader.cpp` lines ~4908-4920
   - Checks `json["items"][build_index]["generation"].asInt()`

## Migration Notes

### From lgogdownloader

If migrating from lgogdownloader code:

- Generation detection is automatic
- No need to manually check generation field
- Use `api.get_manifest()` instead of separate v1/v2 calls

### From heroic-gogdl

If migrating from heroic-gogdl:

- Similar pattern with `generation` field
- Manifest object includes generation attribute
- Compatible with heroic's v1/v2 manager routing

## Testing

Example test for generation detection:

```python
def test_generation_detection():
    api = GalaxyAPI(auth_manager)
    
    # Test V2 game (modern)
    manifest = api.get_manifest("1207658645")  # The Witcher 3
    assert manifest.generation == 2
    
    # Test V1 game (legacy)
    manifest = api.get_manifest("1097893768")  # The Witcher 2
    # Generation depends on actual game data
    assert manifest.generation in [1, 2]
```

## Troubleshooting

### No builds found
- Check product_id is correct
- Verify authentication is valid
- Try both generation=1 and generation=2 manually

### Wrong generation detected
- Inspect builds JSON directly:
  ```python
  builds = api.get_product_builds(product_id)
  print(builds)
  ```

### Build ID not matching
- Remember build_id can be:
  - Actual build ID string
  - Numeric index (legacy compatibility)
  - None (latest build)
