# Patch Framework Documentation

## Overview

The patch framework enables **incremental updates** for GOG games by downloading xdelta3 patch files instead of full game files. This significantly reduces download size for updates.

## Architecture

### Core Components

1. **`FilePatchDiff`** - Represents a single file patch
   - Source/target MD5 hashes
   - Source/target paths
   - Patch chunks to download
   - References to old/new DepotItems

2. **`Patch`** - Collection of file patches for a build update
   - Query GOG API for patch availability
   - Download patch manifests
   - Parse depot-specific patch information

3. **`ManifestDiff`** - Comparison result with patch support
   - `new` - Files that don't exist (full download)
   - `changed` - Files that changed but no patch (full download)
   - `patched` - Files with available patches (patch download)
   - `deleted` - Files to remove

### Workflow

```
1. Get old and new manifests
2. Query content-system.gog.com: Patch available?
   ├─ Returns: {id, from, to, link} or error
   └─ No → Fall back to full downloads

3. Download root patch manifest (from link)
   ├─ Contains: algorithm, depots[], clientId, clientSecret
   └─ Compressed with zlib

4. Download depot patch manifests
   ├─ For each depot in depots[]
   ├─ Get depot manifest using depot hash
   └─ Parse DepotDiff items → FilePatchDiff objects

5. Compare manifests with patch data
   ├─ Match files by MD5
   ├─ Use patches where available
   └─ Full download for rest

6. Download phase
   ├─ Download full files (new/changed)
   └─ Download patch chunks using clientId/clientSecret

7. (Optional) Apply patches
   └─ Use pyxdelta or external tool
```

## API Response States

When querying for patches, the Content System API can return three distinct states:

### 1. Valid Patch Available
```json
{
  "id": "67cf3e9356b831e8738b482ed3a8dabf",
  "from": "49999910531550131",
  "to": "56452082907692588",
  "link": "https://cdn.gog.com/content-system/v2/patches/meta/67/cf/67cf3e9356b831e8738b482ed3a8dabf"
}
```
- Build IDs are valid and compatible
- Patch exists between the specified builds
- The `link` points to a root manifest containing patch data

### 2. No Patch Available (Empty Manifest)
```json
{
  "id": "abc123...",
  "from": "56908074018002614",
  "to": "57325296727241979",
  "link": "https://cdn.gog.com/content-system/v2/patches/meta/ab/c1/abc123..."
}
```
- API returns valid metadata with a manifest link
- But the root manifest contains only `{}` (empty JSON object)
- **Meaning**: Build IDs are valid and compatible, but GOG never created a patch between them
- This can occur when:
  - GOG expects full reinstall instead of patching
  - Patch was created but later removed
  - Builds are too close to warrant a differential patch

### 3. Invalid Request (Not Found)
```json
{
  "error": "not_found",
  "error_description": ""
}
```
- Build IDs are invalid, don't exist, or are incompatible
- Examples of incompatible builds:
  - Build IDs from different products
  - Build IDs from different platforms (Windows vs macOS vs Linux)
  - Build IDs in wrong order (newer → older)
  - Non-existent build IDs

**Note**: When archiving patches, all three states should be preserved:
- **State 1**: Download and store complete patch data
- **State 2**: Store the empty manifest to document "no patch exists"
- **State 3**: Log the error response for troubleshooting

## Usage

### Basic Patch Detection

```python
from galaxy_dl import GalaxyAPI, Manifest, Patch

# Get manifests for old and new builds
old_manifest = api.get_manifest_direct(product_id, old_build_id)
new_manifest = api.get_manifest_direct(product_id, new_build_id)

# Step 1: Query for patch availability
patch_info = api.get_patch_info(product_id, old_build_id, new_build_id)

if not patch_info or 'error' in patch_info:
    print("No patch available")
else:
    # Step 2: Download root patch manifest
    patch_link = patch_info['link']
    root_manifest = api.get_patch_manifest(patch_link)
    
    print(f"Patch ID: {patch_info['id']}")
    print(f"Algorithm: {root_manifest['algorithm']}")
    print(f"Depots: {len(root_manifest['depots'])}")
    
    # Step 3: Use Patch.get() to download depot manifests and build FilePatchDiff objects
    patch = Patch.get(
        api_client=api,
        manifest=new_manifest,
        old_manifest=old_manifest,
        language="en",
        dlc_product_ids=["123", "456"]  # DLC IDs to include
    )
    
    if patch:
        print(f"Patch available! {len(patch.files)} files can be patched")
```

### Generate Diff with Patches

```python
from galaxy_dl import Manifest

# Compare with patch support
diff = Manifest.compare(new_manifest, old_manifest, patch)

print(f"New files: {len(diff.new)}")
print(f"Changed files (full): {len(diff.changed)}")
print(f"Patched files: {len(diff.patched)}")
print(f"Deleted files: {len(diff.deleted)}")

# Process diff
for file_patch in diff.patched:
    print(f"Patch: {file_patch.source_path}")
    print(f"  Old MD5: {file_patch.md5_source}")
    print(f"  New MD5: {file_patch.md5_target}")
    print(f"  Chunks: {len(file_patch.chunks)}")
```

### Download Patch Chunks

```python
from galaxy_dl import utils

# Get clientId and clientSecret from root patch manifest
client_id = root_manifest['clientId']
client_secret = root_manifest['clientSecret']

# Download patch chunks
for file_patch in diff.patched:
    # Create .delta file path
    delta_path = f"{file_patch.target_path}.delta"
    
    # Download chunks using patch-specific secure link
    for chunk in file_patch.chunks:
        chunk_md5 = chunk["compressedMd5"]
        
        # Get secure link for this chunk (uses clientId/clientSecret)
        # Note: Patches use /patches/store root instead of regular /store
        secure_urls = api.get_patch_secure_link(
            product_id=product_id,
            chunk_hash=chunk_md5,
            client_id=client_id,
            client_secret=client_secret
        )
        
        # Build final URL with galaxy_path
        chunk_path = utils.galaxy_path(chunk_md5)
        chunk_url = secure_urls[0].replace("{GALAXY_PATH}", chunk_path)
        
        # Download and save chunk
        # (see examples/download_patches.py for complete implementation)
```

**Storage Location:**
- Regular game files: `/store/{hash[:2]}/{hash[2:4]}/{hash}`
- Patch delta files: `/patches/store/{hash[:2]}/{hash[2:4]}/{hash}`

### Patch Metadata Storage

Store patch information for tracking:

```python
import json

# Create patch record
patch_record = {
    "from_build": old_manifest.build_id,
    "to_build": new_manifest.build_id,
    "algorithm": "xdelta3",
    "patches": [
        {
            "source": fp.source_path,
            "target": fp.target_path,
            "delta_file": f"{fp.target_path}.delta",
            "md5_source": fp.md5_source,
            "md5_target": fp.md5_target,
            "applied": False  # Track application status
        }
        for fp in diff.patched
    ]
}

# Save to JSON
with open("patch_manifest.json", "w") as f:
    json.dump(patch_record, f, indent=2)
```

## Patch Application

The framework **downloads** patches but doesn't apply them. Application is separate:

### Option 1: pyxdelta (Python)

```bash
pip install galaxy-dl[patch]  # Includes pyxdelta
```

```python
import pyxdelta

# Apply patch
pyxdelta.patch(
    source="old_game.exe",     # Original file
    delta="game.exe.delta",     # Downloaded patch
    output="new_game.exe"       # Patched result
)

# Verify
import hashlib
with open("new_game.exe", "rb") as f:
    actual_md5 = hashlib.md5(f.read()).hexdigest()
    
assert actual_md5 == file_patch.md5_target, "Patch verification failed!"
```

### Option 2: External xdelta3

```bash
# Linux/Mac
xdelta3 -d -s old_game.exe game.exe.delta new_game.exe

# Windows (download xdelta3.exe)
xdelta3.exe -d -s old_game.exe game.exe.delta new_game.exe
```

## API Reference

### `GalaxyAPI.get_patch_info()`

Query content-system.gog.com for patch availability between two builds.

**Parameters:**
- `product_id` - GOG product ID
- `from_build_id` - Source build ID
- `to_build_id` - Target build ID

**Returns:** Dict with `{id, from, to, link}` or `None` if no patch

**Example:**
```python
patch_info = api.get_patch_info("1207658924", "12345", "12346")
if patch_info:
    patch_link = patch_info['link']  # Link to root patch manifest
```

### `GalaxyAPI.get_patch_manifest()`

Download root patch manifest (zlib-compressed JSON).

**Parameters:**
- `patch_link` - Link from `get_patch_info()['link']`
- `return_raw` - If True, returns `(raw_bytes, dict)` tuple

**Returns:** Dict with `{algorithm, depots[], clientId, clientSecret}`

**Root manifest structure:**
```json
{
  "algorithm": "xdelta3",
  "depots": [
    {
      "productId": "1207658924",
      "manifest": "abc123...",
      "languages": ["en-US"],
      "size": 1234567
    }
  ],
  "clientId": "...",
  "clientSecret": "..."
}
```

### `GalaxyAPI.get_patch_depot_manifest()`

Download depot-specific patch manifest (contains DepotDiff items).

**Parameters:**
- `depot_manifest_id` - Depot hash from `root_manifest['depots'][]['manifest']`
- `return_raw` - If True, returns `(raw_bytes, dict)` tuple

**Returns:** Dict with DepotDiff items containing file patches

**Depot manifest structure:**
```json
{
  "depot": {
    "items": [
      {
        "type": "DepotDiff",
        "path": "game.exe",
        "md5Before": "abc123",
        "md5After": "def456",
        "chunks": [
          {
            "compressedMd5": "...",
            "compressedSize": 12345
          }
        ]
      }
    ]
  }
}
```

### `GalaxyAPI.get_patch_secure_link()`

Get secure CDN URL for downloading patch chunks.

**Parameters:**
- `product_id` - GOG product ID
- `chunk_hash` - Chunk MD5 from depot manifest
- `client_id` - From root manifest
- `client_secret` - From root manifest

**Returns:** List of secure URLs with `{GALAXY_PATH}` placeholder

### `Patch.get()`

High-level method: Query GOG, download manifests, and build Patch object.

**Parameters:**
- `api_client` - GalaxyAPI instance
- `manifest` - New/target manifest
- `old_manifest` - Old/source manifest
- `language` - Language code (e.g., "en")
- `dlc_product_ids` - List of DLC IDs to include

**Returns:** `Patch` object with `FilePatchDiff` items, or `None`

**Note:** This calls `get_patch_info()`, `get_patch_manifest()`, and `get_patch_depot_manifest()` internally.

### `Manifest.compare()`

Compare manifests and generate diff with patch support.

**Parameters:**
- `new_manifest` - Target manifest
- `old_manifest` - Source manifest (optional)
- `patch` - Patch object from `Patch.get()` (optional)

**Returns:** `ManifestDiff` object with categorized files

## Notes

- **V1 builds don't support patches** (returns None)
- **Both manifests must have build IDs** for patch query
- **Patch algorithm must be xdelta3** (GOG standard)
- **Patches are language-specific** (query with correct language)
- **Patch application is optional** (download-only is valid)
- **Delta files can be large** (plan storage accordingly)
- **Complete acquisition flow:**
  1. Query content-system.gog.com → get patch info with repository link
  2. Download root manifest from repository link → get algorithm, depots, credentials
  3. Download depot manifests for matching language/products → get DepotDiff items
  4. Use clientId/clientSecret for secure links to download chunks from /patches/store
- **See examples/download_patches.py for working implementation**

## Example: Full Workflow

```python
from galaxy_dl import GalaxyAPI, AuthManager, Manifest, Patch, utils

# Initialize
auth = AuthManager()
api = GalaxyAPI(auth)

# Get builds
builds = api.get_all_product_builds("1207658924", "windows")
old_build = builds[1]  # Previous build
new_build = builds[0]  # Latest build

# Get manifests
old_manifest = api.get_manifest_direct("1207658924", old_build["link"])
new_manifest = api.get_manifest_direct("1207658924", new_build["link"])

# Step 1: Query for patch
patch_info = api.get_patch_info(
    "1207658924",
    old_build["build_id"],
    new_build["build_id"]
)

if not patch_info:
    print("No patch available")
    # Fall back to full download
else:
    # Step 2: Download root patch manifest
    root_manifest = api.get_patch_manifest(patch_info['link'])
    client_id = root_manifest['clientId']
    client_secret = root_manifest['clientSecret']
    
    # Step 3: Use high-level Patch.get() to handle depot manifests
    patch = Patch.get(api, new_manifest, old_manifest, "en", [])
    
    # Step 4: Compare manifests
    diff = Manifest.compare(new_manifest, old_manifest, patch)
    
    print(f"Update requires:")
    print(f"  {len(diff.new)} new files")
    print(f"  {len(diff.changed)} full downloads")
    print(f"  {len(diff.patched)} patches")
    
    # Step 5: Download patch chunks
    if diff.patched:
        for file_patch in diff.patched:
            for chunk in file_patch.chunks:
                chunk_md5 = chunk["compressedMd5"]
                
                # Get secure link
                secure_urls = api.get_patch_secure_link(
                    "1207658924",
                    chunk_md5,
                    client_id,
                    client_secret
                )
                
                # Build URL and download
                chunk_path = utils.galaxy_path(chunk_md5)
                chunk_url = secure_urls[0].replace("{GALAXY_PATH}", chunk_path)
                # ... download and save chunk

# See examples/download_patches.py for complete implementation
```

## Troubleshooting

**No patch available:**
- `get_patch_info()` returns `None` or `{'error': ...}`
- Builds too different (GOG doesn't create patch)
- Build IDs incorrect
- Patch expired (GOG removes old patches)

**Patch download fails:**
- Verify `clientId` and `clientSecret` from root manifest
- Check chunk MD5 matches between depot manifest and downloaded data
- Ensure `get_patch_secure_link()` uses correct credentials

**Depot manifest download fails:**
- Verify depot hash from `root_manifest['depots'][]['manifest']`
- Check network connection to CDN
- Ensure authentication is valid

**Patch application fails:**
- Verify source file MD5 matches `md5Before` from DepotDiff
- Check delta file downloaded completely
- Ensure xdelta3/pyxdelta is installed correctly
- Verify target MD5 after patching matches `md5After`
