# RGOG Workflow Summary

## Complete Workflow Overview

This document explains the relationship between the different RGOG commands and how they work together.

## The Three Main Operations

### 1. Pack → Unpack (Archive Management)

```
GOG v2 Directory          RGOG Archive         GOG v2 Directory
     (meta/)     ─────→   (compressed)   ─────→    (meta/)
     (store/)     pack                   unpack    (store/)
```

**Pack** creates a deterministic archive from GOG Galaxy v2 files:
- Input: `meta/` (repositories, manifests) + `store/` (chunks)
- Output: `.rgog` archive file(s)
- Purpose: Storage, transfer, archival

**Unpack** reverses the pack operation:
- Input: `.rgog` archive file(s)
- Output: `meta/` (repositories, manifests) + `store/` (chunks)
- Purpose: Restore original v2 structure, prepare for re-packing, debug

**Key Point**: Pack and unpack are **inverse operations**. If you pack a directory and then unpack it, you get back the exact same files (byte-for-byte identical).

### 2. Extract (Game Installation)

```
RGOG Archive       →      Game Files
(compressed)       extract    (exes, dlls, ini, etc.)
```

**Extract** reassembles chunks into installable game files:
- Input: `.rgog` archive file(s)
- Output: Final game files ready to run
- Purpose: Install and play the game

**Note**: Extract uses the manifest metadata to know how to reassemble chunks into the final files. It decompresses chunks and combines them according to the build instructions.

## Typical Use Cases

### Archival Workflow
```
1. Download game with galaxy_dl
   └─→ v2/meta/ and v2/store/

2. Pack into RGOG archive
   └─→ TUNIC.rgog (deterministic, compressed)

3. Store or transfer archive
   └─→ Backup to NAS, share with others, etc.

4. Unpack when needed
   └─→ Restore v2/ directory structure

5. Extract to install
   └─→ Get playable game files
```

### Debug/Inspection Workflow
```
1. Receive RGOG archive
   └─→ TUNIC.rgog

2. Unpack with debug flag
   └─→ v2/ structure + debug/ (human-readable JSON)

3. Inspect debug files
   └─→ Understand build structure, depot contents, etc.

4. Re-pack if needed
   └─→ Create modified archive
```

### Distribution Workflow
```
1. Game developer/archivist creates RGOG
   └─→ Pack from v2/ directory

2. Users receive archive
   └─→ Download TUNIC.rgog

3. Users extract to play
   └─→ Skip unpack, go straight to extract for game files
```

## Command Comparison

| Command | Input | Output | Use Case |
|---------|-------|--------|----------|
| `pack` | v2/ directory | .rgog archive | Create archive for storage/transfer |
| `unpack` | .rgog archive | v2/ directory | Restore v2 structure, debug, re-pack |
| `extract` | .rgog archive | Game files | Install and play the game |
| `list` | .rgog archive | Text output | View archive contents |
| `verify` | .rgog archive | Pass/fail | Validate integrity |
| `info` | .rgog archive | Statistics | Get archive information |

## File Flow Diagram

```
Download Game (galaxy_dl)
         ↓
    v2/meta/    ← Repository files (compressed JSON)
    v2/store/   ← Chunk files (compressed game data)
         ↓
      [pack]
         ↓
    .rgog archive (deterministic, multi-part support)
         ↓
    ┌────┴────┐
    ↓         ↓
[unpack]  [extract]
    ↓         ↓
v2/ directory  Final game files
(with debug/)  (exes, dlls, etc.)
    ↓
 [pack]
    ↓
.rgog archive
```

## Key Differences: Unpack vs Extract

### Unpack
- **Output**: GOG v2 directory structure (meta/, store/)
- **Files remain**: Compressed (repositories, manifests, chunks)
- **Structure**: Nested directories (store/XX/YY/hash)
- **Debug option**: Creates human-readable JSON files
- **Use when**: You want to inspect, modify, or re-pack the archive

### Extract
- **Output**: Final game files (exe, dll, ini, png, etc.)
- **Files become**: Decompressed and reassembled
- **Structure**: Game's install directory structure
- **Result**: Ready to play
- **Use when**: You want to install and run the game

## Example Commands

### Create an archive
```bash
# Pack GOG v2 directory into RGOG archive
python rgog.py pack TUNIC/v2/ -o TUNIC.rgog
```

### Restore v2 structure
```bash
# Unpack RGOG back to v2 directory
python rgog.py unpack TUNIC.rgog -o TUNIC/v2/

# Unpack with debug files for inspection
python rgog.py unpack TUNIC.rgog -o TUNIC/v2/ --debug
```

### Install the game
```bash
# Extract to get playable game files
python rgog.py extract TUNIC.rgog -o TUNIC/game/ --reassemble
```

### Inspect archive
```bash
# List builds in archive
python rgog.py list TUNIC.rgog

# Get detailed statistics
python rgog.py info TUNIC.rgog --stats

# Verify integrity
python rgog.py verify TUNIC.rgog
```

## Storage Optimization

### Space Comparison

For a typical game (e.g., TUNIC ~6 GB):

```
Original v2/:        ~6.2 GB (meta/ + store/)
RGOG archive:        ~6.0 GB (compressed, deterministic)
Unpacked v2/:        ~6.2 GB (identical to original)
Extracted game:      ~8.5 GB (decompressed, ready to run)
```

**Notes:**
- RGOG archives are slightly smaller due to efficient packing
- Multi-part archives split large games (default 2 GB per part)
- Pack/unpack preserves exact bytes (deterministic)

## Advanced Workflows

### Incremental Updates (Future)
```
Base game RGOG:      TUNIC_base.rgog
Patch RGOG:          TUNIC_patch_v1.1.rgog
Combined:            Unpack both → merge → re-pack
```

### Selective Extraction
```
# Extract only specific build
python rgog.py extract TUNIC.rgog --build 1716751705 -o output/

# Unpack only chunks (skip metadata)
python rgog.py unpack TUNIC.rgog -o chunks/ --chunks-only
```

### Verification Pipeline
```
1. Download RGOG from untrusted source
2. Verify integrity: python rgog.py verify TUNIC.rgog
3. If valid, unpack or extract
4. If invalid, report corruption
```

## Summary

- **Pack/Unpack**: For archive management and v2 structure preservation
- **Extract**: For game installation and playback
- **Verify/List/Info**: For inspection and validation
- **Unpack is the inverse of pack**: Restores exact original files
- **Extract is different**: Produces playable game files

Choose the right command for your use case:
- Archive creation → `pack`
- Archive inspection → `unpack` (with --debug)
- Game installation → `extract`
- Archive validation → `verify`
- Archive browsing → `list` or `info`
