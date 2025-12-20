# Archival Features Summary

## What Was Added

### GalaxyAPI (galaxy_dl/api.py)
```python
# URL Construction Methods
get_depot_url(build_id) -> str
get_repository_url(repository_id) -> str  
get_manifest_url(manifest_id, generation=2) -> str
get_chunk_url(compressed_md5) -> str

# Raw Download Method
download_raw(url, output_path) -> None
```

### GalaxyDownloader (galaxy_dl/downloader.py)
```python
# Convenience Methods (use GalaxyAPI methods internally)
download_raw_depot(build_id, output_path) -> None
download_raw_repository(repository_id, output_path) -> None
download_raw_manifest(manifest_id, output_path, generation=2) -> None
download_raw_chunk(compressed_md5, output_path) -> None
```

## What Already Existed

### V2 Raw Chunk Downloads
```python
# Already supported via raw_mode parameter
downloader.download_item(item, output_dir, raw_mode=True)
```
This saves compressed chunks as separate files with metadata for reassembly.

### V1 Blob Downloads
```python
# Already works - downloads main.bin blob
downloader.download_item(blob_item, output_dir)
```

## New Example: archive_game.py

Complete 1:1 CDN archival script that:
1. Downloads depot/repository JSON (compressed)
2. Downloads all manifest JSONs (as received)
3. Downloads all chunks/blobs (compressed)
4. Saves metadata for verification

```bash
# V2 build
python examples/archive_game.py v2 1207658930 92ab42631ff4742b309bb62c175e6306

# V1 build
python examples/archive_game.py v1 1207658930 4906035348831941901
```

## Testing

See [TESTING.md](TESTING.md) for:
- Validation checklist
- Expected directory structures
- How to find build IDs
- Manual URL construction examples

## URLs Constructed

### V2 Build:
```
Depot:    https://cdn.gog.com/content-system/v2/meta/92/ab/{build_id}
Manifest: https://cdn.gog.com/content-system/v2/meta/79/a1/{manifest_id}
Chunk:    https://cdn.gog.com/content-system/v2/store/2e/0d/{compressedMd5}
```

### V1 Build:
```
Repository: https://cdn.gog.com/content-system/v1/meta/49/06/{repository_id}
Manifest:   https://cdn.gog.com/content-system/v1/meta/79/a1/{manifest_id}
Blob:       Uses secure link from API (existing functionality)
```

All URLs use the 2-character directory split pattern: `{first_2_chars}/{next_2_chars}/{full_hash}`
