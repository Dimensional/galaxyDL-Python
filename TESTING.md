# Testing Galaxy-DL Archival Features

## Overview

The library now supports complete 1:1 CDN archival with these methods:

### Added to `GalaxyAPI`:
- `get_depot_url(build_id)` - Get depot JSON URL
- `get_repository_url(repository_id)` - Get repository JSON URL  
- `get_manifest_url(manifest_id, generation)` - Get manifest JSON URL
- `get_chunk_url(compressed_md5)` - Get V2 chunk URL
- `download_raw(url, output_path)` - Download without processing

### Added to `GalaxyDownloader`:
- `download_raw_depot(build_id, output_path)` - Download depot JSON
- `download_raw_repository(repository_id, output_path)` - Download repository JSON
- `download_raw_manifest(manifest_id, output_path, generation)` - Download manifest JSON
- `download_raw_chunk(compressed_md5, output_path)` - Download compressed chunk

## Test 1: V2 Build Archival

```bash
# Archive a V2 build (The Witcher 2 example)
python examples/archive_game.py v2 1207658930 92ab42631ff4742b309bb62c175e6306
```

**Expected output structure:**
```
archives/v2_1207658930_92ab42631ff4742b309bb62c175e6306/
├── depot_92ab42631ff4742b309bb62c175e6306.dat   # Compressed
├── depot_92ab42631ff4742b309bb62c175e6306.json  # Reference
├── manifests/
│   ├── {manifest_id}.dat                         # Original format
│   ├── {manifest_id}.json                        # Reference
├── chunks/
│   ├── {compressedMd5}.dat                       # Compressed chunks
│   └── ...
└── metadata.json                                 # Archive info
```

**Verify:**
1. Depot .dat file is zlib compressed
2. All manifests downloaded
3. All unique chunks downloaded (deduplicated)
4. Chunk count matches metadata.json

## Test 2: V1 Build Archival

```bash
# Archive a V1 build (requires repository_id from builds API or gogdb.org)
python examples/archive_game.py v1 1207658930 4906035348831941901
```

**Expected output structure:**
```
archives/v1_1207658930_4906035348831941901/
├── repository_4906035348831941901.dat   # Compressed
├── repository_4906035348831941901.json  # Reference
├── manifests/
│   └── manifest.json                    # File list with offsets
├── blobs/
│   └── main.bin                         # Binary blob
└── metadata.json                        # Archive info
```

**Verify:**
1. Repository .dat is zlib compressed
2. main.bin downloaded
3. Manifest shows file offsets into main.bin

## Test 3: Manual URL Construction

```python
from galaxy_dl import GalaxyAPI, AuthManager

api = GalaxyAPI(AuthManager())

# V2 URLs
depot_url = api.get_depot_url("92ab42631ff4742b309bb62c175e6306")
# https://cdn.gog.com/content-system/v2/meta/92/ab/92ab42631ff4742b309bb62c175e6306

manifest_url = api.get_manifest_url("79a1f5fd67f6d0cda22c51f1bd706b31", generation=2)
# https://cdn.gog.com/content-system/v2/meta/79/a1/79a1f5fd67f6d0cda22c51f1bd706b31

chunk_url = api.get_chunk_url("2e0dc2f5707ec0d88d570240ba918bb2")
# https://cdn.gog.com/content-system/v2/store/2e/0d/2e0dc2f5707ec0d88d570240ba918bb2

# V1 URLs
repo_url = api.get_repository_url("4906035348831941901")
# https://cdn.gog.com/content-system/v1/meta/49/06/4906035348831941901
```

## Test 4: Existing Raw Downloads

The library already supports raw chunk downloads for V2:

```python
from galaxy_dl import GalaxyDownloader, GalaxyAPI, AuthManager

api = GalaxyAPI(AuthManager())
downloader = GalaxyDownloader(api)

# Get manifest
manifest = api.get_manifest_direct("build_id", generation=2)

# Download item in raw mode (saves compressed chunks)
for item in manifest.depots[0].items:
    if not item.is_v1_blob:
        downloader.download_item(item, "output_dir", raw_mode=True)
```

This creates:
```
output_dir/{item.path}_chunks/
├── chunk_000000.dat  # Compressed
├── chunk_000001.dat
└── chunks.json       # Metadata for reassembly
```

## Validation Checklist

- [ ] V2 depot JSON is zlib compressed
- [ ] V2 manifests download (may be compressed or plain)
- [ ] V2 chunks download in original compressed format
- [ ] V1 repository JSON is zlib compressed
- [ ] V1 main.bin blob downloads correctly
- [ ] All JSON .dat files can be decompressed with zlib
- [ ] Reference .json files parse correctly
- [ ] Chunk MD5 hashes can be verified against manifest
- [ ] File sizes match expected values
- [ ] URLs construct correctly with 2-char directory split

## Finding Build IDs

### From builds API:
```python
builds = api.get_all_product_builds(game_id, "windows")
for build in builds['items']:
    print(f"Generation {build['generation']}")
    if build['generation'] == 2:
        build_id = build['link'].split('/')[-1]  # Last part of URL
        print(f"  Build ID: {build_id}")
    else:
        repository_id = build['legacy_build_id']
        print(f"  Repository ID: {repository_id}")
```

### From gogdb.org:
Visit: `https://www.gogdb.org/product/{game_id}`
- Look for "Build ID" or "Repository" in builds table
- V2 builds show 32-char hex hash
- V1 builds show numeric repository timestamp
