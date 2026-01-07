# RGOG - Reproducible GOG Archive Tool

A command-line tool for creating, managing, and extracting RGOG (Reproducible GOG) archives following the RGOG Format Specification v2.0.

## Features

- **Pack**: Create deterministic RGOG archives from GOG Galaxy v2 directory structures
- **Unpack**: Extract RGOG archives back to the original GOG v2 directory structure
- **List**: View archive contents and build information
- **Extract**: Extract and reassemble chunks into installable game files
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

### Unpack an Archive

Unpack an RGOG archive back to GOG v2 structure:

```bash
python rgog.py unpack tunic.rgog -o TUNIC/v2/
```

Unpack with debug files (human-readable JSON):

```bash
python rgog.py unpack tunic.rgog -o TUNIC/v2/ --debug
```

Unpack only chunks (skip metadata):

```bash
python rgog.py unpack tunic.rgog -o chunks_only/ --chunks-only
```

**Note**: The `unpack` command recreates the original GOG v2 directory structure (meta/, store/). This is different from `extract`, which reassembles chunks into final game files (exes, dlls, etc.).

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
│ Chunk Metadata (Binary)                 │  Catalog of chunks (40 bytes each)
├─────────────────────────────────────────┤
│ Chunk Files (Zlib)                      │  Chunk data
└─────────────────────────────────────────┘
```

### Chunk Metadata Structure

Each chunk entry is exactly 40 bytes:

```
┌────────────────────────────────────┐
│ compressed_md5 (16 bytes)          │  MD5 hash of compressed chunk
├────────────────────────────────────┤
│ offset (8 bytes, uint64_t)         │  Byte offset in chunk data section
├────────────────────────────────────┤
│ size (8 bytes, uint64_t)           │  Compressed chunk size
├────────────────────────────────────┤
│ product_id (8 bytes, uint64_t)     │  GOG product ID
└────────────────────────────────────┘
```

All multi-byte integers are stored in little-endian format.

### Key Features

- **Deterministic**: Same inputs always produce identical outputs
- **Binary Metadata**: Compact, fast-parsing binary structures
- **HDD-Optimized**: Metadata at front for fast seeking on spinning drives
- **Multi-part Support**: Automatic splitting for large archives (default 2 GiB per part)
- **Selective Extraction**: Extract specific builds without reading entire archive

## Input Directory Structure

The pack command expects a GOG Galaxy v2 directory structure:

```
game_directory/
├── v2/
│   ├── meta/
│   │   ├── XX/YY/<hash>     # Repository files (zlib compressed JSON)
│   │   └── XX/YY/<hash>     # Manifest files (zlib compressed JSON)
│   └── store/
│       └── <product_id>/    # Product ID subdirectory (e.g., 1744110647)
│           ├── XX/YY/<hash> # Chunk files (zlib compressed data)
│           ├── XX/YY/<hash> # Organized by first 4 hex chars of MD5
│           └── ...
```

**Note**: The store directory must contain product_id subdirectories (numeric directory names),
as chunks are stored per product ID on the CDN. Less risk of file collision.
This structure is created automatically by the `archive_game.py` download script.

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
- `ChunkMetadata`: 40-byte chunk catalog entries
  - compressed_md5 (16 bytes): MD5 hash of compressed chunk
  - offset (8 bytes): Byte offset in chunk data section
  - size (8 bytes): Compressed chunk size
  - product_id (8 bytes): GOG product ID this chunk belongs to

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
