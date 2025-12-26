# RGOG - Reproducible GOG Archive Tool

A command-line tool for creating, managing, and extracting RGOG (Reproducible GOG) archives following the RGOG Format Specification v2.0.

## Features

- **Pack**: Create deterministic RGOG archives from GOG Galaxy v2 directory structures
- **List**: View archive contents and build information
- **Extract**: Extract builds and chunks from archives
- **Verify**: Validate archive integrity and checksums
- **Info**: Display detailed statistics about archives

## Requirements

- Python 3.7+
- No external dependencies (uses only Python standard library)

## Usage

### Pack an Archive

Create an RGOG archive from a GOG v2 directory:

```bash
python rgog.py pack TUNIC/v2/ -o tunic.rgog
```

With custom part size:

```bash
python rgog.py pack TUNIC/v2/ -o tunic.rgog --max-part-size 4GB
```

### List Archive Contents

Quick list (shows builds from metadata):

```bash
python rgog.py list tunic.rgog
```

Detailed list (decompresses repositories for full info):

```bash
python rgog.py list tunic.rgog --detailed
```

Show specific build:

```bash
python rgog.py list tunic.rgog --build 1716751705
```

### Extract from Archive

Extract everything:

```bash
python rgog.py extract tunic.rgog -o output/
```

Extract specific build:

```bash
python rgog.py extract tunic.rgog --build 1716751705 -o output/
```

Extract only chunks:

```bash
python rgog.py extract tunic.rgog --chunks-only -o chunks/
```

Extract and reassemble final game files:

```bash
python rgog.py extract tunic.rgog --reassemble -o game/
```

### Verify Archive

Full verification (checks all MD5 checksums):

```bash
python rgog.py verify tunic.rgog
```

Quick verification (structure only):

```bash
python rgog.py verify tunic.rgog --quick
```

Verify specific build:

```bash
python rgog.py verify tunic.rgog --build 1716751705
```

### Show Archive Information

Basic info:

```bash
python rgog.py info tunic.rgog
```

With detailed statistics:

```bash
python rgog.py info tunic.rgog --stats
```

## Archive Format

RGOG archives follow a metadata-first layout optimized for both creation and extraction:

```
┌─────────────────────────────────────────┐
│ RGOG Header (128 bytes)                 │
├─────────────────────────────────────────┤
│ Product Metadata (Binary)               │  Product info
├─────────────────────────────────────────┤
│ Build Metadata (Binary)                 │  Catalog of all builds
├─────────────────────────────────────────┤
│ Build Files (Zlib)                      │  Repositories + Manifests
├─────────────────────────────────────────┤
│ Chunk Metadata (Binary)                 │  Catalog of chunks
├─────────────────────────────────────────┤
│ Chunk Files (Zlib)                      │  Chunk data
└─────────────────────────────────────────┘
```

### Key Features

- **Deterministic**: Same inputs always produce identical outputs
- **Binary Metadata**: Compact, fast-parsing binary structures
- **HDD-Optimized**: Metadata at front for fast seeking on spinning drives
- **Multi-part Support**: Automatic splitting for large archives (default 2 GiB per part)
- **Selective Extraction**: Extract specific builds without reading entire archive

## Input Directory Structure

The tool expects a GOG Galaxy v2 directory structure:

```
TUNIC/v2/
├── meta/
│   ├── <hash1>              # Repository files (zlib compressed JSON)
│   ├── <hash2>              # Manifest files (zlib compressed JSON)
│   └── ...
└── chunks/
    ├── <md5>.chunk          # Chunk files (zlib compressed data)
    └── ...
```

## Code Structure

```
examples/
├── rgog.py                  # Main CLI entry point
└── rgog/                    # Package directory
    ├── __init__.py          # Package initialization
    ├── common.py            # Shared data classes and utilities
    ├── pack.py              # Pack command implementation
    ├── list.py              # List command implementation
    ├── extract.py           # Extract command implementation
    ├── verify.py            # Verify command implementation
    └── info.py              # Info command implementation
```

### Extending the Tool

All code is self-contained and well-documented. To extend:

1. **Add new commands**: Create a new module in `rgog/` with an `execute(args)` function
2. **Modify data structures**: Edit `common.py` to add new fields or structures
3. **Customize packing**: Modify `pack.py` to change archive creation logic

### Data Classes

The `common.py` module provides all binary structure definitions:

- `RGOGHeader`: 128-byte archive header
- `ProductMetadata`: Product information
- `BuildMetadata`: Build and manifest metadata
- `ChunkMetadata`: Chunk catalog entries

All classes include:
- Comprehensive docstrings
- `to_bytes()` serialization
- `from_bytes()` deserialization
- Type hints

## Performance

Typical performance on modern hardware:

- **Packing**: ~500 MB/s (limited by disk I/O)
- **Listing**: Instant (reads only small metadata sections)
- **Extraction**: ~500 MB/s (limited by disk I/O)
- **Verification**: ~300 MB/s (limited by MD5 computation)

## License

This implementation is provided as a reference for the RGOG Format Specification v2.0.
