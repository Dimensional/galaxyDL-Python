# Complete GOG Archival with galaxy_dl

This document explains how to use `galaxy_dl` for complete GOG game archival, combining both Galaxy CDN downloads and traditional HTTP downloads.

## Two Download Systems

GOG provides games through two different systems:

### 1. Galaxy CDN (Depot System)
**What it is:** Modern game distribution via Galaxy client  
**File format:** Depot manifests + chunked files (~10MB each)  
**Use case:** Galaxy client installation, incremental updates, patching  
**Handler:** `GalaxyDownloader`

### 2. Traditional Downloads (HTTP Files)
**What it is:** Direct file downloads (like clicking download links on GOG.com)  
**File format:** Complete files (.exe, .pdf, .zip, etc.)  
**Use case:** Offline installers, bonus content, standalone installation  
**Handler:** `WebDownloader`

## Complete Archival Strategy

For true complete archival, you want **both**:

```python
from galaxy_dl import GalaxyAPI, AuthManager, GalaxyDownloader, WebDownloader

auth = AuthManager()
api = GalaxyAPI(auth)
galaxy_dl = GalaxyDownloader(api)
web_dl = WebDownloader(auth)

game_id = 1207658924  # Example game

# 1. Download Galaxy depot (the actual game files)
builds = api.get_all_product_builds(game_id, 'windows')
manifest = api.get_manifest_from_build(game_id, builds[0], 'windows')
galaxy_dl.download_depot_items(
    manifest.get_all_depot_items(),
    output_dir=f"./archive/{game_id}/galaxy"
)

# 2. Download offline installers (for non-Galaxy installation)
details = api.get_game_details(game_id)
for item in details.get('downloads', []):
    for platform, files in item.items():
        if isinstance(files, list):
            for file_entry in files:
                web_dl.download_from_game_details(
                    file_entry,
                    output_dir=f"./archive/{game_id}/installers"
                )

# 3. Download extras (manuals, wallpapers, soundtracks, etc.)
for extra in details.get('extras', []):
    web_dl.download_from_game_details(
        extra,
        output_dir=f"./archive/{game_id}/extras"
    )
```

## What to Archive

| Category | Type | Size | Purpose |
|----------|------|------|---------|
| **Galaxy Depot** | Chunked files | 5-50 GB | Modern installation, Galaxy client |
| **Offline Installers** | .exe/.sh/.pkg | 5-50 GB | Standalone installation |
| **Extras** | .pdf/.zip/.mp3 | 50 MB - 5 GB | Bonus content, OST, artbooks |
| **Patches** | .exe/.sh | 100 MB - 5 GB | Non-Galaxy updates |
| **Language Packs** | .exe/.sh | 500 MB - 2 GB | Additional languages |

## Directory Structure Example

```
./archive/
└── The_Witcher_2/
    ├── v2/                              # Galaxy v2 depot structure
    │   ├── meta/                        # Repositories and manifests
    │   │   ├── XX/YY/<hash>             # Repository files (zlib compressed JSON)
    │   │   └── XX/YY/<hash>             # Manifest files (zlib compressed JSON)
    │   └── store/                       # Chunked game data
    │       └── <product_id>/            # Product ID subdirectory
    │           └── XX/YY/<hash>         # Chunk files (~10MB each, zlib compressed)
    │
    ├── installers/                      # Offline installers
    │   ├── windows/
    │   │   ├── setup_witcher2_1.0.exe
    │   │   └── setup_witcher2_1.0.bin
    │   ├── osx/
    │   │   └── the_witcher_2.pkg
    │   └── linux/
    │       └── the_witcher_2.sh
    │
    └── extras/                          # Bonus content
        ├── manual_en.pdf
        ├── wallpapers.zip
        ├── soundtrack.zip
        └── making_of.mp4
```

## Why Archive Both?

### Galaxy Depot (v2 Structure)
✅ Incremental updates via patches  
✅ Same format as Galaxy client  
✅ Better for patching/updating  
✅ Deduplication across builds (shared chunks)  
✅ Can create RGOG archives for preservation  
❌ Requires manifest knowledge to reassemble  
❌ Needs tools to extract final game files  

### Offline Installers
✅ Simple double-click installation  
✅ No tools required  
✅ Works offline forever  
❌ No incremental updates  
❌ Larger download (includes redundant data)  
❌ No deduplication between versions  

**Best practice:** Archive both for maximum future-proofing.

## Use Cases

### Scenario 1: Personal Archival
**Goal:** Save everything you own  
**Strategy:** Download Galaxy depot + offline installers + extras  
**Tools:** `galaxy_dl` for Galaxy, `WebDownloader` for the rest

### Scenario 2: NAS/Server Archival
**Goal:** Centralized game library accessible from multiple devices  
**Strategy:** Use Flask web UI for download management  
**Implementation:**
```python
# Flask app that:
# - Lets user auth via browser (bypasses reCAPTCHA)
# - Shows owned games
# - Queues downloads
# - Serves files via web interface
```

### Scenario 3: Preservation Project
**Goal:** Archive games for historical preservation  
**Strategy:** Download everything, including delisted games  
**Tools:** Use `get_owned_games()` to get ALL games (including delisted)

### Scenario 4: Game Installation
**Goal:** Install a game on a new machine  
**Options:**
- Use offline installer (simple, double-click installation)
- Use Galaxy v2 depot (requires extraction/reassembly from chunks using manifests)
- Create RGOG archive from v2 depot for portable preservation

## File Comparison

### Same Game, Different Formats

**Galaxy Depot (v2 structure):**
```
The_Witcher_2/v2/
├── meta/
│   ├── 31/e6/31e6481dca5ba189f508224ac43db509  # Repository (730 bytes)
│   ├── c6/ab/c6ab23f6210c2ed7ca55a746b8440ceb  # Manifest (~42 KB)
│   └── ... (more manifests)
└── store/
    └── 1207658924/                              # Product ID
        ├── 00/1a/001a2b3c...                    # Chunk (~10 MB)
        ├── 00/2f/002f3e4d...                    # Chunk (~10 MB)
        └── ... (~1800 chunks)
Total: ~18 GB in chunks + ~500 KB in manifests
```

**Offline Installer:**
```
setup_witcher2_1.0.exe (4.5 GB)
setup_witcher2_1.0-1.bin (4.5 GB)
setup_witcher2_1.0-2.bin (4.5 GB)
setup_witcher2_1.0-3.bin (4.5 GB)
Total: ~18 GB
```

The Galaxy v2 format stores raw chunks and metadata, while the installer packages everything for direct installation. Both install the same game, but v2 allows incremental updates and deduplication.

## Bandwidth Considerations

For a 100-game library:
- **Galaxy depot only:** ~1.5 TB
- **Offline installers only:** ~1.5 TB
- **Both:** ~3 TB
- **+ Extras:** ~3.2 TB

**Recommendation:** Start with Galaxy depot for games you play, add offline installers for permanent archival.

## Web GUI Architecture (Your NAS Use Case)

```python
# Flask app structure
from flask import Flask, render_template, request, session
from galaxy_dl import GalaxyAPI, AuthManager, GalaxyDownloader, WebDownloader

app = Flask(__name__)

@app.route('/login')
def login():
    # User authenticates via browser (bypasses reCAPTCHA)
    # Store token in session
    pass

@app.route('/library')
def library():
    # Show owned games
    auth = AuthManager(token=session['token'])
    api = GalaxyAPI(auth)
    games = api.get_owned_games_with_details(limit=100)
    return render_template('library.html', games=games)

@app.route('/download/<game_id>')
def download_game(game_id):
    # Queue download task (use Celery or similar)
    # Download in background
    # Update progress via websocket
    pass

@app.route('/files')
def browse_files():
    # Browse downloaded files
    # Serve via send_file() or nginx
    pass
```

**Benefits:**
- Headless operation on NAS
- Browser handles reCAPTCHA
- Download management from any device
- Centralized storage

## Verification

Both download types support verification:

```python
# Galaxy depot - per-chunk MD5
downloader.download_item(item, verify_hash=True)

# Extras - per-file MD5 via XML
web_dl.download_from_game_details(
    file_entry,
    verify_checksum=True
)
```

## Future Enhancements

Potential additions to `WebDownloader`:
- Resumable downloads (HTTP range requests)
- Parallel downloads (download multiple files at once)
- Bandwidth limiting
- Download queue with priorities
- Duplicate detection (skip already downloaded)

These would make it more suitable for large-scale archival operations.

## Summary

`galaxy_dl` now provides **complete GOG archival**:

1. **Galaxy CDN** (`GalaxyDownloader`) - Modern depot system
2. **Extras/Installers** (`WebDownloader`) - Traditional HTTP downloads

Both work together to provide full game + extras + installers archival, suitable for personal backup, NAS storage, or preservation projects.

The separation keeps the codebase clean:
- Galaxy downloader stays focused on complex depot logic
- Extras downloader provides simple HTTP download wrapper
- Both use the same `GalaxyAPI` for metadata

Perfect for your Flask-based NAS downloader idea! 🎮
