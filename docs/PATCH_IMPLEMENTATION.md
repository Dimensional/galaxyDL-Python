# Patch Framework Implementation Summary

## What Was Implemented

The complete **patch downloading framework** has been added to galaxy-dl. This enables downloading xdelta3 patch files for incremental game updates.

### New Files Created

1. **`galaxy_dl/diff.py`** - ManifestDiff class for comparison results
2. **`docs/PATCHES.md`** - Complete patch framework documentation
3. **`examples/test_patch_framework.py`** - Test script demonstrating patch API

### Modified Files

1. **`galaxy_dl/models.py`**
   - Added `FilePatchDiff` dataclass
   - Added `Patch` dataclass with `Patch.get()` method
   - Added `Manifest.compare()` method with patch support
   - Added `Manifest._file_changed()` helper

2. **`galaxy_dl/api.py`**
   - Updated `get_secure_link()` to support `root_path` parameter for `/patches/store`
   - Added `get_patch_info()` method
   - Added `get_patch_manifest()` method
   - Added `get_patch_depot_manifest()` method

3. **`galaxy_dl/constants.py`**
   - Added `PATCHES_QUERY_URL` constant

4. **`galaxy_dl/__init__.py`**
   - Exported `FilePatchDiff`, `Patch`, and `ManifestDiff`

5. **`README.md`**
   - Updated patch support description to clarify download vs. application

## How It Works

### 1. Patch Detection
```python
# Step 1: Query content-system.gog.com
patch_info = api.get_patch_info(product_id, old_build_id, new_build_id)
# Returns: {id, from, to, link} or None

# Step 2: Download root patch manifest
root_manifest = api.get_patch_manifest(patch_info['link'])
# Returns: {algorithm, depots[], clientId, clientSecret}

# Step 3: Download depot manifests and build FilePatchDiff objects
patch = Patch.get(api, new_manifest, old_manifest, "en", dlc_ids)
# Internally:
#  - Downloads depot manifests using depot hashes
#  - Parses DepotDiff items
#  - Creates FilePatchDiff objects
```

**API Calls Made:**
1. `GET https://content-system.gog.com/products/{id}/patches?from_build_id={old}&to_build_id={new}`
   - Returns patch info with repository link
2. `GET {repository_link}` (from step 1)
   - Returns root patch manifest (zlib-compressed)

## API Response Handling

The Content System API returns three distinct response types when querying for patches:

### 1. Valid Patch Response
```python
{
    "id": "67cf3e9356b831e8738b482ed3a8dabf",
    "from": "49999910531550131",
    "to": "56452082907692588",
    "link": "https://cdn.gog.com/content-system/v2/patches/meta/67/cf/67cf3e9356b831e8738b482ed3a8dabf"
}
```
**Interpretation**: Patch exists and is available for download.

### 2. Empty Manifest Response
```python
# Initial query returns valid metadata:
{
    "id": "abc123...",
    "from": "56908074018002614",
    "to": "57325296727241979",
    "link": "https://cdn.gog.com/content-system/v2/patches/meta/..."
}

# But downloading the manifest from the link returns only:
{}
```
**Interpretation**: Build IDs are valid and compatible, but no patch content exists between them. GOG validated the request but has no patch data to provide. This is a valid state, not an error.

**Common Causes**:
- GOG expects full reinstall instead of differential patching
- Patch was created but later removed from CDN
- Builds are too similar to warrant a differential patch

### 3. Error Response
```python
{
    "error": "not_found",
    "error_description": ""
}
```
**Interpretation**: Build IDs are invalid, incompatible, or don't exist.

**Common Causes**:
- Build IDs from different products
- Build IDs from different platforms (Windows/macOS/Linux mismatch)
- Build IDs in wrong chronological order (newer → older)
- Non-existent or deleted build IDs

**Example**:
```python
patch_info = api.get_patch_info(product_id, from_build, to_build)

if not patch_info:
    print("Request failed")
elif 'error' in patch_info:
    print(f"Invalid request: {patch_info['error']}")
else:
    # Download root manifest
    root_manifest = api.get_patch_manifest(patch_info['link'])
    
    if not root_manifest or root_manifest == {}:
        print("No patch available (empty manifest)")
    else:
        print(f"Patch available with {len(root_manifest.get('depots', []))} depots")
```
3. For each depot: `GET https://cdn.gog.com/content-system/v2/meta/{hash[:2]}/{hash[2:4]}/{hash}`
   - Returns depot patch manifest with DepotDiff items

### 2. Manifest Comparison
```python
diff = Manifest.compare(new_manifest, old_manifest, patch)
```

- Compares file lists between manifests
- Matches files by MD5 hash
- Uses patches where available
- Falls back to full download when no patch

Result:
- `diff.new` - New files (full download)
- `diff.changed` - Changed files without patch (full download)
- `diff.patched` - Files with patches (download .delta)
- `diff.deleted` - Files to remove

**Root Patch Manifest Structure:**
```json
{
  "algorithm": "xdelta3",
  "depots": [
    {
      "productId": "1207658924",
      "manifest": "abc123def456...",  // Hash for depot manifest
      "languages": ["en-US", "en-GB"],
      "size": 1234567
    }
  ],
  "clientId": "...",      // Used for secure link authentication
  "clientSecret": "..."   // Used for secure link authentication
}
```

**Depot Patch Manifest Structure:**
```json
{
  "depot": {
    "items": [
      {
        "type": "DepotDiff",
        "path": "game.exe",
        "md5Before": "abc123...",  // Source file MD5
        "md5After": "def456...",   // Target file MD5
        "chunks": [
          {
            "compressedMd5": "xyz789...",
            "compressedSize": 12345
          }
        ]
      }
    ]
  }
}
```

### 3. Patch Download
```python
# Get credentials from root manifest
client_id = root_manifest['clientId']
client_secret = root_manifest['clientSecret']

# Get secure link for each chunk
secure_urls = api.get_patch_secure_link(
    product_id=product_id,
    chunk_hash=chunk_md5,
    client_id=client_id,
    client_secret=client_secret
)

# Build final URL and download
chunk_path = utils.galaxy_path(chunk_md5)
chunk_url = secure_urls[0].replace("{GALAXY_PATH}", chunk_path)
# Download chunk and save as .delta file
```

- Get secure CDN links using clientId/clientSecret from root manifest
- Download patch chunks using `compressedMd5` from DepotDiff chunks
- Save as `.delta` files in proper directory structure

### 4. Patch Application (Separate)

```bash
xdelta3 -d -s old_file file.delta new_file
```

## Design Decisions

### 1. Download-Only Framework
**Rationale:** Library's purpose is to download content from GOG, not apply patches. Separation of concerns.

**Benefits:**
- No C compilation required (no xdelta3 source)
- Users choose patch application method
- Works for download managers that apply patches elsewhere
- Simpler maintenance

### 2. Optional pyxdelta Extra
**Implementation:**
```toml
[project.optional-dependencies]
patch = ["pyxdelta>=1.0.0"]
```

**Benefits:**
- Pure Python (no compilation)
- Optional (not required for downloads)
- Easy to add later

### 3. Patch Metadata Storage
**Recommendation:** Save patch info to JSON:
```json
{
  "from_build": "1234",
  "to_build": "1235",
  "patches": [
    {
      "source": "game.exe",
      "target": "game.exe",
      "delta_file": "game.exe.delta",
      "md5_source": "abc123",
      "md5_target": "def456",
      "applied": false
    }
  ]
}
```

**Benefits:**
- Track which patches downloaded
- Track which patches applied
- Verify patch application
- Resume partial updates

## API Changes

### New Methods

- `GalaxyAPI.get_patch_info(product_id, from_build_id, to_build_id)`
  - Queries content-system.gog.com for patch availability
  - Returns: `{id, from, to, link}` or `None`
  
- `GalaxyAPI.get_patch_manifest(patch_link, return_raw=False)`
  - Downloads root patch manifest (zlib-compressed)
  - Returns: `{algorithm, depots[], clientId, clientSecret}`
  - With `return_raw=True`: Returns `(raw_bytes, dict)` tuple
  
- `GalaxyAPI.get_patch_depot_manifest(depot_manifest_id, return_raw=False)`
  - Downloads depot-specific patch manifest
  - Returns: `{depot: {items: [DepotDiff, ...]}}`
  - With `return_raw=True`: Returns `(raw_bytes, dict)` tuple
  
- `GalaxyAPI.get_patch_secure_link(product_id, chunk_hash, client_id, client_secret)`
  - Gets secure CDN URL for patch chunk download
  - Returns: List of URLs with `{GALAXY_PATH}` placeholder
  
- `Patch.get(api, new_manifest, old_manifest, language, dlc_ids)`
  - High-level: Calls all patch methods internally
  - Downloads and parses all depot manifests
  - Returns: `Patch` object with `FilePatchDiff` items
  
- `Manifest.compare(new_manifest, old_manifest, patch)`
  - Compares manifests with optional patch support
  - Returns: `ManifestDiff` with categorized files

### Modified Methods

- None - All patch functionality is additive via new methods

**Note:** The original design included modifying `get_secure_link()` with a `root_path` parameter, but the actual implementation uses a dedicated `get_patch_secure_link()` method with `clientId`/`clientSecret` parameters instead.

### New Classes

- `FilePatchDiff` - Represents a single file patch
- `Patch` - Collection of patches for a build
- `ManifestDiff` - Comparison result

## Testing

Run the test script:
```bash
python examples/test_patch_framework.py
```

This verifies:
- Patch API methods work
- Model classes create correctly
- Secure link with patch root works
- ManifestDiff generates correctly

## Next Steps (For Users)

### 1. Example Script for Patch Download
Create `examples/download_patches.py` that:
- Gets two builds
- Queries for patches
- Downloads patch chunks
- Saves .delta files
- Stores metadata JSON

### 2. Example Script for Patch Application
Create `examples/apply_patches.py` that:
- Loads patch metadata JSON
- Applies each patch with pyxdelta
- Verifies MD5 hashes
- Updates applied status

### 3. Integration with Downloader
Update `GalaxyDownloader` to:
- Support patch downloads
- Handle .delta file saving
- Track patch application status

## Limitations

1. **V1 builds don't support patches**
   - Only V2 builds have patch support
   - V1->V2 upgrades always full download

2. **Patch availability not guaranteed**
   - GOG may not create patches for all updates
   - Old patches may be removed
   - Falls back to full download automatically

3. **Language-specific patches**
   - Must query with correct language
   - Separate patches for each language

4. **Algorithm fixed to xdelta3**
   - GOG only uses xdelta3
   - Framework rejects other algorithms

## File Size Comparison

Example update (fictional):
- **Full download:** 50 GB
- **Patch download:** 2 GB (.delta files)
- **Savings:** 96%

Actual savings vary by:
- How much changed between builds
- File compression
- Number of files changed

## Backwards Compatibility

✅ All existing code continues to work
- `Manifest.compare()` is new (doesn't break anything)
- `get_secure_link()` parameter is optional
- New classes are additive

## Documentation

- **`docs/PATCHES.md`** - Full patch framework guide
- **`examples/test_patch_framework.py`** - Working examples
- **`README.md`** - Updated feature list

## Credits

Implementation based on:
- **heroic-gogdl** patch system (Python reference)
- **lgogdownloader** (conceptual approach)
- GOG Galaxy API (patch endpoints)
