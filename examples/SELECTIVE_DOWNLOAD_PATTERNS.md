# Selective File Download - Common Patterns

This document provides useful patterns for filtering and downloading specific files using `download_selective_files.py`.

## Quick Start

```bash
python examples/download_selective_files.py
```

Follow the interactive prompts to:
1. Select a game
2. Choose a build
3. Filter files by various criteria
4. Download only what you need

## Common Wildcard Patterns

### Executables and Libraries

| Pattern | Description | Example Matches |
|---------|-------------|-----------------|
| `*.exe` | All Windows executables | `game.exe`, `launcher.exe`, `setup.exe` |
| `*.dll` | All DLL libraries | `game.dll`, `steam_api.dll`, `d3d11.dll` |
| `*.so` | All Linux shared libraries | `libgame.so`, `libSDL2.so` |
| `*.dylib` | All macOS dynamic libraries | `libgame.dylib` |
| `bin/*` | All files in bin directory | `bin/game.exe`, `bin/launcher.exe` |

### Game Assets

| Pattern | Description | Example Matches |
|---------|-------------|-----------------|
| `*.pak` | All PAK archives | `data.pak`, `textures.pak`, `audio.pak` |
| `*.vpk` | All VPK archives | `pak01.vpk`, `models.vpk` |
| `*.wad` | All WAD archives | `game.wad`, `textures.wad` |
| `data/*` | All files in data directory | `data/config.ini`, `data/levels/` |
| `*.dat` | All DAT files | `game.dat`, `save.dat` |

### Configuration and Documentation

| Pattern | Description | Example Matches |
|---------|-------------|-----------------|
| `*.ini` | All INI config files | `game.ini`, `settings.ini` |
| `*.cfg` | All CFG config files | `game.cfg`, `video.cfg` |
| `*.txt` | All text files | `readme.txt`, `changelog.txt` |
| `*.pdf` | All PDF documents | `manual.pdf`, `guide.pdf` |
| `docs/*` | All documentation | `docs/readme.txt`, `docs/manual.pdf` |

### Multimedia

| Pattern | Description | Example Matches |
|---------|-------------|-----------------|
| `*.mp4` | All MP4 videos | `intro.mp4`, `cutscene01.mp4` |
| `*.ogg` | All OGG audio | `music.ogg`, `sfx.ogg` |
| `*.wav` | All WAV audio | `sound.wav`, `voice.wav` |
| `*.png` | All PNG images | `icon.png`, `banner.png` |
| `videos/*` | All video files | `videos/intro.mp4`, `videos/credits.mp4` |

### Language-Specific Files

| Pattern | Description | Example Matches |
|---------|-------------|-----------------|
| `*_en.pak` | English language packs | `text_en.pak`, `audio_en.pak` |
| `*_de.pak` | German language packs | `text_de.pak`, `audio_de.pak` |
| `localization/*` | All localization files | `localization/en.txt` |
| `languages/en/*` | English language directory | `languages/en/strings.txt` |

## Advanced Patterns

### Complex Directories

```
assets/textures/*         # All files in assets/textures/
*/config.ini              # config.ini in any directory
data/*/levels/*           # levels subdirectory in any data subdirectory
**/videos/*.mp4           # Won't work - use regex instead
```

### Multiple Extensions

Use the extension filter instead:
```
Extensions: exe,dll,txt
```

Or in code:
```python
filter_by_extension(items, ['.exe', '.dll', '.txt'])
```

## Regular Expression Patterns

For more complex filtering, use regex mode:

### By File Type

| Pattern | Description |
|---------|-------------|
| `\.(exe\|dll)$` | Executables and DLLs |
| `\.(pak\|vpk\|wad)$` | Archive formats |
| `\.(mp4\|ogg\|wav)$` | Multimedia files |
| `\.((txt\|pdf\|md)$` | Documentation files |

### By Directory Structure

| Pattern | Description |
|---------|-------------|
| `^bin/` | Files starting with bin/ |
| `/config/` | Files with config in path |
| `^data/.*\.pak$` | PAK files in data directory |
| `^(bin\|lib)/` | Files in bin OR lib |

### By Content

| Pattern | Description |
|---------|-------------|
| `readme` | Any file with readme in name |
| `^[^/]+\.exe$` | EXE files in root only |
| `_v\d+\.\d+` | Files with version numbers |
| `(alpha\|beta\|test)` | Files with test keywords |

## Size Filtering

Filter by file size (in MB):

### Common Size Ranges

| Range | Use Case |
|-------|----------|
| 0 - 1 MB | Config files, small text/docs |
| 1 - 10 MB | Small executables, libraries |
| 10 - 100 MB | Medium assets, small archives |
| 100 - 1000 MB | Large archives, video files |
| 1000+ MB | Very large data files |

### Practical Examples

```
Minimum: 0 MB, Maximum: 10 MB      # Only small files
Minimum: 100 MB, Maximum: (blank)  # Only large files
Minimum: (blank), Maximum: 50 MB   # Exclude large files
```

## Combined Filtering Examples

### Example 1: Download Only Game Executable and Core DLLs

1. Start with all files
2. Filter by pattern: `*.exe`
3. Note the files you want
4. Reset filters
5. Filter by pattern: `*.dll`
6. Filter by directory: `bin` (if DLLs are in bin/)
7. Download

### Example 2: Download Documentation Only

1. Filter by extension: `txt,pdf,md`
2. May also want: `docs/*` pattern
3. Download

### Example 3: Download English Language Files Only

1. Filter by pattern: `*_en.*`
2. Or filter by directory: `languages/en`
3. Download

### Example 4: Download Game Without Large Video Files

1. Start with all files
2. Filter by size: Max 100 MB
3. This excludes most video cutscenes
4. Download

### Example 5: Get Only Configuration Files for Modding

1. Filter by extension: `ini,cfg,xml,json`
2. Or filter by pattern: `*/config/*`
3. Download

## Tips and Best Practices

### 1. **Start Broad, Then Narrow**
   - Begin with simple patterns
   - Use "Undo" to revert filters
   - Gradually refine your selection

### 2. **Use "Show Detailed List" to Preview**
   - Before downloading, always review the file list
   - Check sizes to avoid surprises
   - Ensure you're getting what you expect

### 3. **Understand SFC (Small Files Container)**
   - Some small files are packed in SFC containers
   - SFC will be downloaded automatically if needed
   - Files marked `[in SFC]` will be extracted
   - SFC is deleted after extraction by default

### 4. **Save Bandwidth with Selective Downloads**
   - For testing: download only `.exe` and config files
   - For modding: download only data/config files
   - For analysis: download only specific asset types

### 5. **Wildcard vs Regex**
   - Use wildcards for simple patterns: `*.exe`, `data/*`
   - Use regex for complex matching: `\.(exe|dll)$`
   - Wildcards are easier, regex is more powerful

### 6. **Check Download Size Before Confirming**
   - The summary shows total compressed/uncompressed size
   - Ensure you have enough disk space
   - Bandwidth estimation: compressed size ≈ download size

## Directory Structure After Download

Files maintain their relative paths:

```
downloads/
└── <product_id>/
    └── <build_id>/
        ├── game.exe
        ├── bin/
        │   └── game.dll
        ├── data/
        │   ├── game.pak
        │   └── textures.pak
        └── docs/
            └── readme.txt
```

## Scripting / Command-Line Usage

For automation, you can modify the script or use it as a library:

```python
from galaxy_dl import GalaxyAPI, GalaxyDownloader, AuthManager
from galaxy_dl.models import DepotItem
import fnmatch

# Authenticate
auth = AuthManager()
api = GalaxyAPI(auth)

# Get manifest
manifest = api.get_manifest_from_build(product_id, build, platform)
items = get_all_depot_items(api, manifest)

# Filter programmatically
exe_files = [item for item in items 
             if fnmatch.fnmatch(item.path.lower(), '*.exe')]

# Download
downloader = GalaxyDownloader(api, max_workers=8)
results = downloader.download_depot_items(
    exe_files, 
    output_dir,
    verify_hash=True
)
```

## Troubleshooting

### "No files match pattern"
- Check pattern syntax (wildcards: `*`, `?`)
- Patterns are case-insensitive
- Use "Show detailed list" to see actual file paths

### "Some files failed to download"
- Check internet connection
- Verify authentication is still valid
- Try reducing `max_workers` in script (line 589)
- Re-run download for failed files only

### "SFC extraction failed"
- Ensure enough disk space
- Check file permissions in output directory
- SFC must be downloaded before files can be extracted

### Files downloaded but not in expected location
- Files maintain their relative paths from manifest
- Check the full path in the manifest
- Some games use deep directory structures

## See Also

- [download_selective_files.py](download_selective_files.py) - The main script
- [README.md](README.md) - All examples overview
- [../API_REFERENCE.md](../API_REFERENCE.md) - Complete API documentation
- [../STRUCTURE.md](../STRUCTURE.md) - Understanding file structures
