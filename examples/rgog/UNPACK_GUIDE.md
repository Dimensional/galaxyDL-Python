# RGOG Unpack Command

## Overview
The `unpack` subcommand extracts files from an RGOG archive back to the original GOG Galaxy v2 directory structure. This is the inverse operation of the `pack` command.

## Purpose
While the `extract` command is designed to reassemble chunks into final installable files (exes, dlls, etc.), the `unpack` command recreates the original GOG v2 metadata and chunk structure:
- Extracts repository files to `meta/`
- Extracts depot manifest files to `meta/`
- Extracts chunk files to `store/` (nested structure)
- Optionally creates human-readable JSON debug copies in `debug/`

## Usage

### Basic Unpack
```bash
python rgog.py unpack archive.rgog -o output_dir
```

This will extract:
- `output_dir/meta/` - Repository and depot manifest files (compressed)
- `output_dir/store/` - Chunk files in nested directory structure

### Unpack With Debug Files
```bash
python rgog.py unpack archive.rgog -o output_dir --debug
```

Adds a `debug/` directory with human-readable JSON copies of build records.

### Unpack Chunks Only
```bash
python rgog.py unpack archive.rgog -o output_dir --chunks-only
```

Extract only chunk files to `store/`, skipping build metadata and repository files.

## Output Structure

### Full Unpack (default)
```
output_dir/
├── meta/
│   ├── {repository_md5}          # Compressed repository file
│   ├── {depot_md5}               # Compressed depot manifest
│   └── ...
├── store/
│   ├── 00/
│   │   ├── 30/
│   │   │   └── 0030af763e1a09ab307d84a24d0066a2
│   │   └── ...
│   └── ...
└── debug/                         # Optional human-readable copies
    ├── {repository_md5}_repository.json
    ├── {depot_md5}_manifest.json
    └── ...
```

### Chunks Only (--chunks-only)
```
output_dir/
└── store/
    ├── 00/
    │   ├── 30/
    │   │   └── 0030af763e1a09ab307d84a24d0066a2
    │   └── ...
    └── ...
```

## Multi-Part Archives
The unpack command automatically handles multi-part archives:
1. Reads Part 0 for build metadata and some chunks
2. Reads Part 1, 2, ... N for additional chunks
3. All chunks are extracted to the same `store/` directory

## Debug Files
When `--debug` is enabled, the unpack command creates human-readable JSON files in the `debug/` directory:
- `{md5}_repository.json` - Decompressed repository metadata
- `{md5}_manifest.json` - Decompressed depot manifest metadata

These files are useful for:
- Understanding build structure
- Debugging archive contents
- Manual inspection of metadata

**Note:** Debug files are NOT needed for normal operation - they're purely for human inspection.

## Comparison with Extract Command

| Feature | Unpack | Extract |
|---------|--------|---------|
| Purpose | Recreate GOG v2 structure | Reassemble installable files |
| Outputs | meta/, store/, debug/ | Final game files (exe, dll, etc.) |
| Use Case | Archive inspection, debugging | Installing/running the game |
| Metadata | Extracts as-is (compressed) | Uses metadata to reassemble |
| Chunks | Extracts as-is (compressed) | Decompresses and reassembles |

## Examples

### Unpack for inspection
```bash
# Extract everything including debug files
python rgog.py unpack TUNIC.rgog -o TUNIC_unpacked --debug
```

### Unpack for re-packing
```bash
# Extract to recreate exact v2 structure (no debug files)
python rgog.py unpack TUNIC.rgog -o TUNIC_v2
```

### Unpack chunks for analysis
```bash
# Extract only chunk files
python rgog.py unpack TUNIC.rgog -o chunks_only --chunks-only
```

### Unpack multi-part archive
```bash
# Automatically handles all parts
python rgog.py unpack TUNIC.rgog -o TUNIC_unpacked
# Will read TUNIC.rgog, TUNIC.part1.rgog, TUNIC.part2.rgog, etc.
```

## Error Handling
- Validates RGOG header before unpacking
- Reports missing parts in multi-part archives
- Warns if depot manifests are missing
- Creates output directories automatically

## Performance
Unpacking is I/O bound and depends on:
- Archive size
- Number of chunks (thousands for large games)
- Disk speed

Typical speeds:
- SSD: 200-500 MB/s
- HDD: 50-150 MB/s

## Exit Codes
- `0` - Success
- `1` - Error (missing archive, invalid format, write errors)
