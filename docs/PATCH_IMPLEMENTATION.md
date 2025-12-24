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
patch = Patch.get(api, new_manifest, old_manifest, "en", dlc_ids)
```

- Queries GOG: `/products/{id}/patches?from_build={old}&to_build={new}`
- Downloads patch metadata manifest
- Parses depot-specific patch manifests
- Returns `Patch` object with list of `FilePatchDiff` items

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

### 3. Patch Download
```python
links = api.get_secure_link(product_id, "/", root_path="/patches/store")
```

- Get secure CDN links with `/patches/store` root
- Download patch chunks using `compressedMd5` from chunks
- Save as `.delta` files

### 4. Patch Application (Separate)

**Option A: pyxdelta**
```bash
pip install galaxy-dl[patch]
```
```python
import pyxdelta
pyxdelta.patch(source, delta, output)
```

**Option B: External xdelta3**
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

- `GalaxyAPI.get_patch_info(product_id, from_build, to_build)`
- `GalaxyAPI.get_patch_manifest(patch_link)`
- `GalaxyAPI.get_patch_depot_manifest(depot_manifest_id)`
- `Patch.get(api, new_manifest, old_manifest, language, dlc_ids)`
- `Manifest.compare(new_manifest, old_manifest, patch)`

### Modified Methods

- `GalaxyAPI.get_secure_link()` - Added `root_path` parameter

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
