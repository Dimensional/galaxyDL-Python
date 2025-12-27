# Patch Download V2 Structure

## Overview

This document describes the V2-compatible directory structure for patch downloads, which matches the structure used for V2 build downloads.

## Implementation

The patch download functionality has been enhanced to save manifests in a V2-compatible structure:

### API Changes

Modified `galaxy_dl/api.py`:
- Added `return_raw` parameter to `get_patch_manifest()`
- Added `return_raw` parameter to `get_patch_depot_manifest()`
- Both methods now return `(raw_bytes, decompressed_json)` tuple when `return_raw=True`
- Raw bytes are preserved from the API response (zlib-compressed)

### Directory Structure

```
<output_dir>/
├── v2/
│   └── patches/
│       ├── meta/                      # Raw zlib-compressed manifests
│       │   ├── {hash[:2]}/
│       │   │   └── {hash[2:4]}/
│       │   │       └── {hash}         # Manifest file (zlib-compressed)
│       │   ├── 67/cf/67cf3e9356b831e8738b482ed3a8dabf  # Root manifest
│       │   └── 8a/5a/8a5a6f3f57ef5b21a855b4a0f0e3523f  # Depot manifest
│       │
│       └── store/                     # Patch delta chunks
│           └── {chunk_hash[:2]}/
│               └── {chunk_hash[2:4]}/
│                   └── {chunk_hash}   # .delta file (xdelta3 format)
│
├── debug/                             # Human-readable JSON manifests
│   ├── {hash}_root.json               # Pretty-printed root manifest
│   ├── {hash}_depot.json              # Pretty-printed depot manifest
│   ├── 67cf3e9356b831e8738b482ed3a8dabf_root.json
│   └── 8a5a6f3f57ef5b21a855b4a0f0e3523f_depot.json
│
└── patch_summary.json                 # Download summary and metadata
```

## Manifest Storage

### Raw Manifests (v2/patches/meta/)

- Stored exactly as received from GOG API (zlib-compressed)
- Uses galaxy_path structure: `{hash[:2]}/{hash[2:4]}/{hash}`
- Can be decompressed with `zlib.decompress(data, 15)`
- Mirrors CDN URL structure: `cdn.gog.com/content-system/v2/patches/meta/{path}`

### Debug Manifests (debug/)

- Decompressed, pretty-printed JSON
- Named with `_root.json` or `_depot.json` suffix
- For human inspection and debugging
- Not compressed

## Chunk Storage

### Store Storage (v2/patches/store/)

- Stores patch delta chunks (xdelta3 format)
- Uses galaxy_path structure: `{chunk_hash[:2]}/{chunk_hash[2:4]}/{chunk_hash}`
- Mirrors CDN URL structure: `cdn.gog.com/content-system/v2/patches/store/{path}`
- All patch chunks stored in this location

## Example Usage

```python
from galaxy_dl import GalaxyAPI, AuthManager
import hashlib
import json
from pathlib import Path

auth = AuthManager()
api = GalaxyAPI(auth)

# Download with raw bytes preserved
result = api.get_patch_manifest(patch_link, return_raw=True)
raw_bytes, manifest_dict = result

# Save raw manifest to v2/patches/meta/
manifest_hash = hashlib.md5(raw_bytes).hexdigest()
meta_dir = base_dir / "v2" / "patches" / "meta" / manifest_hash[:2] / manifest_hash[2:4]
meta_dir.mkdir(parents=True, exist_ok=True)
(meta_dir / manifest_hash).write_bytes(raw_bytes)

# Save debug JSON
debug_dir = base_dir / "debug"
debug_dir.mkdir(parents=True, exist_ok=True)
with open(debug_dir / f"{manifest_hash}_root.json", 'w') as f:
    json.dump(manifest_dict, f, indent=2)
```

## Compatibility

This structure mirrors the GOG CDN URL structure:

- CDN: `cdn.gog.com/content-system/v2/patches/meta/{path}` → Local: `v2/patches/meta/{path}`
- CDN: `cdn.gog.com/content-system/v2/patches/store/{path}` → Local: `v2/patches/store/{path}`
- Both use galaxy_path structure: `{hash[:2]}/{hash[2:4]}/{hash}`
- Same pattern can be applied to regular game downloads with `v2/meta/` and `v2/store/`
- Debug folder provides human-readable inspection without extracting from v2/

## Verification

To verify manifests are properly saved:

```python
import zlib
import json
from pathlib import Path

# Load raw manifest from v2/patches/meta/
manifest_file = Path("v2/patches/meta/67/cf/67cf3e9356b831e8738b482ed3a8dabf")
raw_data = manifest_file.read_bytes()

# Decompress
decompressed = zlib.decompress(raw_data, 15)

# Parse JSON
manifest = json.loads(decompressed)
print(f"Algorithm: {manifest.get('algorithm')}")
```

## Complete Example

See `examples/download_patches.py` for a complete working example that:
1. Downloads patch manifests with raw bytes
2. Saves to v2/patches/ structure mirroring CDN URLs
3. Downloads all patch chunks to v2/patches/store/
4. Saves debug JSON for inspection
5. Generates summary JSON with download metadata

## Benefits

1. **CDN Mirror**: Directory structure mirrors GOG CDN URL paths
2. **Archival**: Raw zlib files preserved exactly as from API
3. **Debugging**: Human-readable JSON in debug/ folder
4. **Consistency**: Same pattern for game downloads (v2/meta/, v2/store/)
5. **Verification**: Can re-read and validate saved manifests
6. **Clarity**: Clear separation between patches (v2/patches/) and regular builds (v2/)
