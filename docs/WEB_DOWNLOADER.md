# Web Downloader

The `WebDownloader` class provides simple downloading of non-Galaxy files from GOG. These are regular HTTP downloads (not depot-based) and include:

- **Offline Installers** - Standalone game installers (.exe, .sh, .pkg, .dmg)
- **Extras/Bonus Content** - Manuals, wallpapers, soundtracks, artbooks, etc.
- **Patches** - Non-Galaxy patches (traditional installers)
- **Language Packs** - Additional language installers

## Key Differences from Galaxy Downloads

| Feature | Galaxy Downloads | Web Downloads |
|---------|-----------------|------------------|
| **Source** | Galaxy CDN depots | Regular GOG CDN |
| **Format** | Manifest + chunks | Single files |
| **Processing** | Chunk assembly, decompression | Direct download |
| **Verification** | Per-chunk MD5 | Optional file MD5 via XML |
| **Use Case** | Game installation via Galaxy | Direct downloads, archival |

## Quick Start

```python
from galaxy_dl import GalaxyAPI, AuthManager, WebDownloader

# Initialize
auth = AuthManager()
api = GalaxyAPI(auth)
web_dl = WebDownloader(auth)

# Get game details
details = api.get_game_details(1207658924)

# Download an extra (manual, wallpaper, etc.)
for extra in details.get('extras', []):
    web_dl.download_from_game_details(
        extra,
        output_dir="./downloads/extras"
    )

# Download installers
for item in details.get('downloads', []):
    for platform, files in item.items():
        if isinstance(files, list):
            for file_entry in files:
                web_dl.download_from_game_details(
                    file_entry,
                    output_dir="./downloads/installers"
                )
```

## File Entry Structure

Files from `get_game_details()` have this structure:

```python
{
    "manualUrl": "https://api.gog.com/products/.../downlink/...",  # URL to get download link
    "name": "File Name",
    "size": "1234567",  # Size in bytes (as string)
    "version": "1.0.0",  # Optional version
    "type": "installer",  # Type identifier
    # ... other metadata
}
```

## Download Flow

The download process involves two API calls:

1. **Get Downlink JSON** (`manualUrl` → downlink info)
   ```python
   downlink_info = web_dl.get_downlink_info(file_entry['manualUrl'])
   # Returns: {"downlink": "https://...", "checksum": "https://..."}
   ```

2. **Download File** (using `downlink` URL)
   ```python
   web_dl.download_file(
       downlink_info['downlink'],
       output_path="./file.exe"
   )
   ```

3. **Optional: Verify Checksum** (using `checksum` XML URL)
   ```python
   if downlink_info['checksum']:
       checksum_info = web_dl.get_checksum_info(downlink_info['checksum'])
       # Returns: {"name": "file.exe", "md5": "abc123...", "chunks": [...]}
   ```

## Checksum Verification

GOG provides MD5 checksums via XML files for verification:

```python
# Automatic verification (recommended)
web_dl.download_from_game_details(
    file_entry,
    output_dir="./downloads",
    verify_checksum=True  # Default
)

# Manual verification
downlink_info = web_dl.get_downlink_info(file_entry['manualUrl'])
if downlink_info['checksum']:
    checksum_info = web_dl.get_checksum_info(downlink_info['checksum'])
    expected_md5 = checksum_info['md5']
    
    web_dl.download_file(
        downlink_info['downlink'],
        output_path="./file.exe",
        expected_md5=expected_md5
    )
```

### Checksum XML Format

```xml
<file name="setup_game_1.0.exe" available="1" md5="abc123..." ...>
  <chunks>
    <chunk id="0" from="0" to="1048575" method="md5">chunk_hash_1</chunk>
    <chunk id="1" from="1048576" to="2097151" method="md5">chunk_hash_2</chunk>
  </chunks>
</file>
```

The `chunks` are used for verifying split/partial downloads (lgogdownloader feature).

## Complete Example

```python
from galaxy_dl import GalaxyAPI, AuthManager, WebDownloader

def download_complete_game(game_id: int):
    """Download all extras and installers for a game."""
    auth = AuthManager()
    api = GalaxyAPI(auth)
    web_dl = WebDownloader(auth)
    
    # Get game info
    details = api.get_game_details(game_id)
    title = details['title']
    
    print(f"Downloading all files for: {title}")
    
    # Download installers
    downloads = details.get('downloads', [])
    for item in downloads:
        lang = item.get('language_full', 'unknown')
        
        for platform, files in item.items():
            if platform in ['language', 'language_full']:
                continue
            
            if isinstance(files, list):
                for file_entry in files:
                    print(f"Downloading installer: {file_entry['name']} ({lang}, {platform})")
                    
                    web_dl.download_from_game_details(
                        file_entry,
                        output_dir=f"./archive/{title}/installers/{platform}",
                        verify_checksum=True
                    )
    
    # Download extras
    for extra in details.get('extras', []):
        print(f"Downloading extra: {extra['name']}")
        
        web_dl.download_from_game_details(
            extra,
            output_dir=f"./archive/{title}/extras",
            verify_checksum=True
        )
    
    print("Download complete!")

# Usage
download_complete_game(1207658924)  # Unreal Tournament 2004
```

## Progress Tracking

```python
def progress_callback(downloaded: int, total: int):
    """Track download progress."""
    if total > 0:
        percent = (downloaded / total) * 100
        print(f"\rProgress: {downloaded:,} / {total:,} bytes ({percent:.1f}%)", end='')

web_dl.download_file(
    download_url,
    output_path="./file.exe",
    progress_callback=progress_callback
)
```

## Error Handling

```python
try:
    web_dl.download_from_game_details(
        file_entry,
        output_dir="./downloads"
    )
except ValueError as e:
    print(f"Invalid file entry: {e}")
except RuntimeError as e:
    print(f"Download or verification failed: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Integration with Galaxy Downloads

For complete archival, combine with Galaxy depot downloads:

```python
from galaxy_dl import GalaxyAPI, AuthManager, GalaxyDownloader, WebDownloader

auth = AuthManager()
api = GalaxyAPI(auth)
galaxy_dl = GalaxyDownloader(api)
web_dl = WebDownloader(auth)

game_id = 1207658924

# 1. Download Galaxy depot files (the actual game)
builds = api.get_all_product_builds(game_id, 'windows')
manifest = api.get_manifest_from_build(game_id, builds[0], 'windows')
galaxy_dl.download_depot_items(
    manifest.get_all_depot_items(),
    output_dir=f"./archive/{game_id}/game"
)

# 2. Download extras (manuals, wallpapers, etc.)
details = api.get_game_details(game_id)
for extra in details.get('extras', []):
    web_dl.download_from_game_details(
        extra,
        output_dir=f"./archive/{game_id}/extras"
    )

# 3. Download offline installers (for non-Galaxy installation)
for item in details.get('downloads', []):
    for platform, files in item.items():
        if isinstance(files, list):
            for file_entry in files:
                web_dl.download_from_game_details(
                    file_entry,
                    output_dir=f"./archive/{game_id}/installers"
                )
```

## API Reference

### `WebDownloader(auth_manager: AuthManager)`

Initialize web downloader with authentication.

### `get_downlink_info(manual_url: str) -> Dict[str, Any]`

Get download link from manualUrl.

**Returns:**
```python
{
    "downlink": "https://...",  # Direct download URL
    "checksum": "https://..."   # Checksum XML URL (may be empty)
}
```

### `get_checksum_info(checksum_url: str) -> Dict[str, str]`

Parse checksum XML file.

**Returns:**
```python
{
    "name": "file.exe",
    "md5": "abc123...",
    "chunks": [...]  # Chunk info for split files
}
```

### `download_file(downlink_url, output_path, expected_md5=None, ...)`

Download file from direct URL with optional verification.

### `download_from_game_details(file_entry, output_dir, verify_checksum=True, ...)`

Complete download flow from game details entry (recommended).

## Use Cases

### 1. Complete Game Archival
Download everything: Galaxy builds + installers + extras

### 2. Offline Installer Collection
Download standalone installers without Galaxy

### 3. Extras Collection
Download all bonus content (soundtracks, manuals, artbooks)

### 4. Version Preservation
Download specific installer versions for archival

### 5. Web-Based Downloader
Use in Flask/web app for headless NAS downloading:
- User authenticates via browser (bypasses reCAPTCHA)
- Pass token to library
- Download in background
- Serve files via web interface

## Limitations

- **No resumable downloads** - If interrupted, download restarts (could be added)
- **No parallel downloads** - Downloads one file at a time (could be added)
- **MD5 only** - GOG only provides MD5 checksums, no SHA256

## Future Enhancements

Potential additions:
- Resumable downloads (HTTP range requests)
- Parallel multi-file downloads
- Bandwidth limiting
- Download queue management
- Better progress tracking (ETA, speed)

## Comparison with lgogdownloader

| Feature | lgogdownloader | galaxy_dl extras |
|---------|---------------|------------------|
| Installers | ✅ | ✅ |
| Extras | ✅ | ✅ |
| MD5 Verification | ✅ | ✅ |
| Chunk Verification | ✅ | ⚠️ (data available, not implemented) |
| Resumable Downloads | ✅ | ❌ (could be added) |
| Galaxy Depot Downloads | ✅ | ✅ |
| Implementation | C++ | Python |

The `WebDownloader` provides the essential functionality in a simple, Pythonic API suitable for integration into web applications and automation scripts.
