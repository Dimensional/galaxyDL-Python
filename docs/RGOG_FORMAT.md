# RGOG Format Specification
## Reproducible GOG Archive Format v2.0

### Overview
The RGOG (Reproducible GOG) format is a deterministic archive format for packaging GOG Galaxy v2 build data. Identical inputs guarantee identical outputs with matching checksums, regardless of who creates the archive or when.

### Design Goals
1. **Determinism**: Same inputs → same outputs (identical checksums)
2. **Binary Metadata**: Compact binary structures for all metadata
3. **HDD-Optimized Reads**: Metadata at front for fast seeking on spinning drives
4. **Selective Extraction**: Extract individual builds without full decompression
5. **Built-in Verification**: MD5 checksums from GOG filenames
6. **Multi-part Support**: Split large archives (100+ GB) across multiple files

---

## File Structure

### Single-file Archive Layout
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
│ Chunk Metadata (Binary)                 │  Catalog of chunks in this part
├─────────────────────────────────────────┤
│ Chunk Files (Zlib)                      │  Chunk data
└─────────────────────────────────────────┘
```

**Key Design:**
- All sections aligned to **64-byte boundaries** (fixed)
- **Metadata before data** (HDD-optimized: ~15ms faster seeks vs end-of-file)
- Catalogs (metadata) written with placeholders, updated after data streaming
- Files within data sections written consecutively without padding

---

## 1. RGOG Header (128 bytes)

```
Offset  Size  Field                Description
------  ----  -----                -----------
0       4     Magic                "RGOG" (ASCII, 4 bytes)
4       2     Version              0x0002 (uint16)
6       1     Type                 0x01=Base Build, 0x02=Patch Collection, 0x03-0xFF=Reserved
7       1     Reserved             0x00
8       4     PartNumber           Current part (0 for main, 1-N for additional)
12      4     TotalParts           Total parts in archive (1 for single-file)
16      2     TotalBuildCount      Total builds across all parts (max 65535)
18      4     TotalChunkCount      Total chunks across all parts
22      4     LocalChunkCount      Chunks in this part only
26      8     ProductMetadataOffset   
34      8     ProductMetadataSize     
42      8     BuildFilesOffset     (0 if part > 0)
50      8     BuildFilesSize       (0 if part > 0)
58      8     BuildMetadataOffset  (0 if part > 0)
66      8     BuildMetadataSize    (0 if part > 0)
74      8     ChunkFilesOffset     
82      8     ChunkFilesSize       
90      8     ChunkMetadataOffset  
98      8     ChunkMetadataSize    
106     22    Reserved             0x00
```

**Constants:**
- Section alignment: **64 bytes** (fixed)
- All offsets are 64-byte aligned
- ProductMetadataOffset = 128 (immediately after header)

**Type Field Values:**
- **0x01**: Base Build archive (contains game builds)
- **0x02**: Patch Collection archive (contains differential updates)
- **0x03-0xFF**: Reserved for future use

**Multi-part Design:**
- **Part 0**: Product Metadata + Build Files + Build Metadata + Chunk Files + Chunk Metadata
- **Part 1+**: Chunk Files + Chunk Metadata only
- Offsets/sizes = 0 for sections not present in part
- TotalParts tells you upfront how many files to expect
- Type field must match across all parts of the same archive

**Example (Single-part archive, TUNIC with metadata-first layout):**
```
Offset  Value (hex)              Field
------  -----------              -----
0       52 47 4F 47              Magic "RGOG" (ASCII)
4       02 00                    Version: 0x0002
6       01                       Type: 0x01 (Base Build)
7       00                       Reserved
8       00 00 00 00              PartNumber: 0 (main part)
12      01 00 00 00              TotalParts: 1 (single file)
16      03 00                    TotalBuildCount: 3 (uint16)
18      8A 05 00 00              TotalChunkCount: 1418
22      8A 05 00 00              LocalChunkCount: 1418 (all chunks in part 0)
26      80 00 00 00 00 00 00 00  ProductMetadataOffset: 128
34      40 00 00 00 00 00 00 00  ProductMetadataSize: 64
42      C0 00 00 00 00 00 00 00  BuildMetadataOffset: 192 (after Product)
50      C0 02 00 00 00 00 00 00  BuildMetadataSize: 704 bytes
58      80 03 00 00 00 00 00 00  BuildFilesOffset: 896 (after Build Metadata)
66      00 10 25 00 00 00 00 00  BuildFilesSize: 2429952 bytes
74      80 13 25 00 00 00 00 00  ChunkMetadataOffset: 2430848 (after Build Files)
82      C0 60 00 00 00 00 00 00  ChunkMetadataSize: 49600 bytes (1418 × 32 + padding)
90      40 74 25 00 00 00 00 00  ChunkFilesOffset: 2480448 (after Chunk Metadata)
98      00 40 24 54 00 00 00 00  ChunkFilesSize: 1410203648 bytes
106     00 00 00 00 00 00 00 00  Reserved
114     00 00 00 00 00 00 00 00  Reserved
122     00 00 00 00 00 00        Reserved (6 bytes)
```

---

## 2. Product Metadata (Binary)

Product-level information, always in Part 0.

```
Offset  Size       Field              Description
------  ----       -----              -----------
0       8          ProductId          uint64 (GOG product ID)
8       4          ProductNameSize    uint32 (length in bytes, excluding padding)
12      variable   ProductName        UTF-8 string (no null terminator)
?       variable   Padding            Pad ProductName to 8-byte boundary (0x00)
```

**Example (TUNIC):**
```
ProductId:        0x0000000066504239 (1716751737 decimal)
ProductNameSize:  0x00000005 (5)
ProductName:      "TUNIC" (5 bytes: 54 55 4E 49 43)
Padding:          0x00 0x00 0x00 (3 bytes, to reach 8-byte alignment)
Total size:       8 + 4 + 8 = 20 bytes → padded to 64 bytes
```

**Binary Layout:**
```
Offset  Value (hex)              Field
------  -----------              -----
0       39 42 50 66 00 00 00 00  ProductId: 1716751737 (little-endian)
8       05 00 00 00              ProductNameSize: 5
12      54 55 4E 49 43           ProductName: "TUNIC"
17      00 00 00                 Padding to 8-byte boundary
20      00 00 00 00 00 00 00 00  Padding to 64-byte section
...     (44 more 0x00 bytes)
63      00
```

**Note:** TotalBuildCount and TotalChunkCount are already in the RGOG Header, no duplication needed.

---

## 3. Build Metadata (Binary)

Catalog of all builds in the archive. Written immediately after Product Metadata with placeholder offsets, then updated after Build Files are written.

**Location:** Always in Part 0 only (not duplicated in other parts).

**Structure (per build):**
```
Offset  Size  Field              Description
------  ----  -----              -----------
0       8     BuildId            uint64 (GOG build ID)
8       1     OS                 uint8 (0=null, 1=Windows, 2=Mac, 3=Linux)
9       3     Reserved           0x00
12      16    RepositoryId       16-byte binary MD5
28      8     RepositoryOffset   uint64 (relative to Build Files start)
36      8     RepositorySize     uint64 (compressed size)
44      2     ManifestCount      uint16 (max 65535 manifests)
46      2     Reserved           0x00
48      ?     Manifests[]        Array of manifest entries
```

**Manifest Entry (per manifest):**
```
Offset  Size  Field           Description
------  ----  -----           -----------
0       16    DepotId         16-byte binary MD5
16      8     Offset          uint64 (relative to Build Files start)
24      8     Size            uint64 (compressed size)
32      8     Languages1      uint64 bit flags (bits 0-63)
40      8     Languages2      uint64 bit flags (bits 64-127)
```

**Total entry sizes:**
- Build entry base: 48 bytes
- Per manifest: 48 bytes
- Example (1 manifest): 48 + 48 = 96 bytes per build

**OS Codes:**
- 0: Null/unspecified (allows future expansion)
- 1: Windows
- 2: Mac
- 3: Linux

**Sorting:** Builds sorted by BuildId (numeric ascending)

**Writing Process:**
1. Pre-calculate Build Metadata size from scanned builds
2. Write Build Metadata with placeholder offsets (0x00 for RepositoryOffset/Size and Manifest Offset/Size)
3. Write Build Files section (Section 4)
4. Seek back to Build Metadata
5. Update RepositoryOffset, RepositorySize, and Manifest Offset/Size fields with actual values
6. Continue to Chunk Metadata section (Section 5)

**Language Bit Flags (2x uint64 - 128 bits total):**

**Languages1 (bits 0-63):**
- Bit 0: English (en-US)
- Bit 1: British English (en-GB)
- Bit 2: French (fr-FR)
- Bit 3: German (de-DE)
- Bit 4: Spanish (es-ES)
- Bit 5: Latin American Spanish (es-MX)
- Bit 6: Polish (pl-PL)
- Bit 7: Russian (ru-RU)
- Bit 8: Italian (it-IT)
- Bit 9: Portuguese Brazilian (pt-BR)
- Bit 10: Portuguese (pt-PT)
- Bit 11: Chinese Simplified (zh-Hans)
- Bit 12: Chinese Traditional (zh-Hant)
- Bit 13: Japanese (ja-JP)
- Bit 14: Korean (ko-KR)
- Bit 15: Turkish (tr-TR)
- Bit 16: Czech (cs-CZ)
- Bit 17: Hungarian (hu-HU)
- Bit 18: Dutch (nl-NL)
- Bit 19: Swedish (sv-SE)
- Bit 20: Norwegian (nb-NO)
- Bit 21: Danish (da-DK)
- Bit 22: Finnish (fi-FI)
- Bit 23: Arabic (ar)
- Bit 24: Thai (th-TH)
- Bit 25: Greek (el-GR)
- Bit 26: Romanian (ro-RO)
- Bit 27: Ukrainian (uk-UA)
- Bit 28: Bulgarian (bg-BG)
- Bit 29: Croatian (hr-HR)
- Bit 30: Vietnamese (vi-VN)
- Bit 31: Indonesian (id-ID)
- Bit 32: Hindi (hi-IN)
- Bit 33: Hebrew (he-IL)
- Bit 34: Serbian (sr-SP)
- Bit 35: Slovak (sk-SK)
- Bit 36: Slovenian (sl-SI)
- Bit 37: Albanian (sq-AL)
- Bit 38: Lithuanian (lt-LT)
- Bit 39: Latvian (lv-LV)
- Bit 40: Estonian (et-EE)
- Bit 41: Icelandic (is-IS)
- Bit 42: Persian (fa-IR)
- Bit 43: Afrikaans (af-ZA)
- Bit 44: Azeri (az-AZ)
- Bit 45: Belarusian (be-BY)
- Bit 46: Bengali (bn-BD)
- Bit 47: Bosnian (bs-BA)
- Bit 48: Catalan (ca-ES)
- Bit 49: Welsh (cy-GB)
- Bit 50: Divehi (dv-MV)
- Bit 51: Basque (eu-ES)
- Bit 52: Faroese (fo-FO)
- Bit 53: Galician (gl-ES)
- Bit 54: Gujarati (gu-IN)
- Bit 55: Armenian (hy-AM)
- Bit 56: Javanese (jv-ID)
- Bit 57: Georgian (ka-GE)
- Bit 58: Kazakh (kk-KZ)
- Bit 59: Kannada (kn-IN)
- Bit 60: Konkani (kok-IN)
- Bit 61: Kyrgyz (ky-KG)
- Bit 62: Latin (la)
- Bit 63: Malayalam (ml-IN)

**Languages2 (bits 64-127):**
- Bit 64: Maori (mi-NZ)
- Bit 65: Macedonian (mk-MK)
- Bit 66: Mongolian (mn-MN)
- Bit 67: Marathi (mr-IN)
- Bit 68: Malay (ms-MY)
- Bit 69: Maltese (mt-MT)
- Bit 70: Northern Sotho (ns-ZA)
- Bit 71: Punjabi (pa-IN)
- Bit 72: Pashto (ps-AR)
- Bit 73: Sanskrit (sa-IN)
- Bit 74: Kiswahili (sw-KE)
- Bit 75: Tamil (ta-IN)
- Bit 76: Telugu (te-IN)
- Bit 77: Tagalog (tl-PH)
- Bit 78: Setswana (tn-ZA)
- Bit 79: Tatar (tt-RU)
- Bit 80: Urdu (ur-PK)
- Bit 81: Uzbek (uz-UZ)
- Bit 82: isiXhosa (xh-ZA)
- Bit 83: isiZulu (zu-ZA)
- Bits 84-127: Reserved for future languages

**Special values:**
- Languages1=0, Languages2=0: No language specified (depot applies to all or is language-neutral)

**Example - 3 Builds with Multiple Manifests:**
```
Build 1 (Windows, English only):
  BuildId:         1716751700
  OS:              1 (Windows)
  RepositoryId:    "a1b2c3d4e5f6789012345678901abcde"
  RepositoryOffset: 0
  RepositorySize:  4096
  ManifestCount:   1
  Manifest[0]:
    DepotId:       "591439b971de4cef68b45a95a6827fcd"
    Offset:        16384 (after all repos)
    Size:          8192
    Languages1:    0x0000000000000001 (bit 0: en-US)
    Languages2:    0x0000000000000000

Build 2 (Windows, Multi-language):
  BuildId:         1716751705
  OS:              1 (Windows)
  RepositoryId:    "c0b8eafca369caf82ec6f392b27653a2"
  RepositoryOffset: 4096
  RepositorySize:  4096
  ManifestCount:   3
  Manifest[0]:
    DepotId:       "d4c35309d1c7b919f54c4a410ce31c72"
    Offset:        24576
    Size:          8192
    Languages1:    0x0000000000000001 (bit 0: en-US)
    Languages2:    0x0000000000000000
  Manifest[1]:
    DepotId:       "dbfe3d05c7ce02a2c49d06504d39a735"
    Offset:        32768
    Size:          8192
    Languages1:    0x000000000000001F (bits 0-4: en-US, en-GB, fr-FR, de-DE, es-ES)
    Languages2:    0x0000000000000000
  Manifest[2]:
    DepotId:       "e6a45c8f3d9e7b2a1f8c4e5d6b3a2f1e"
    Offset:        40960
    Size:          4096
    Languages1:    0x00000000000000C0 (bits 6-7: pl-PL, ru-RU)
    Languages2:    0x0000000000000000

Build 3 (Mac, English + French):
  BuildId:         1716751710
  OS:              2 (Mac)
  RepositoryId:    "f2d8ebfca379bcb94ed8f594d49865c4"
  RepositoryOffset: 8192
  RepositorySize:  4096
  ManifestCount:   2
  Manifest[0]:
    DepotId:       "a5b87af416cd9e0b13fa8fe0f1372dac"
    Offset:        45056
    Size:          8192
    Languages1:    0x0000000000000005 (bits 0, 2: en-US, fr-FR)
    Languages2:    0x0000000000000000
  Manifest[1]:
    DepotId:       "b7c98bf527de0f1c24fb9af1e2483ebd"
    Offset:        53248
    Size:          8192
    Languages1:    0x0000000000000000 (no language or all)
    Languages2:    0x0000000000000000

Total Build Files size: 12288 (repos) + 45056 (manifests) = 57344 bytes
```

**Binary Layout Example (Build 2, Manifest[0]):**
```
Offset  Value (hex)              Field
------  -----------              -----
[Build 2 Header - 48 bytes]
0       D9 64 50 66 00 00 00 00  BuildId: 1716751705 (little-endian)
8       01                       OS: 1 (Windows)
9       00 00 00                 Reserved
12      C0 B8 EA FC A3 69 CA F8  RepositoryId: binary MD5 (first 8 bytes)
20      2E C6 F3 92 B2 76 53 A2  (last 8 bytes)
28      00 10 00 00 00 00 00 00  RepositoryOffset: 4096 (little-endian)
36      00 10 00 00 00 00 00 00  RepositorySize: 4096 (little-endian)
44      03 00                    ManifestCount: 3 (uint16)
46      00 00                    Reserved

[Manifest[0] - 48 bytes]
48      D4 C3 53 09 D1 C7 B9 19  DepotId: binary MD5 (first 8 bytes)
56      F5 4C 4A 41 0C E3 1C 72  (last 8 bytes)
64      00 60 00 00 00 00 00 00  Offset: 24576 (little-endian)
72      00 20 00 00 00 00 00 00  Size: 8192 (little-endian)
80      01 00 00 00 00 00 00 00  Languages1: 0x0000000000000001 (en-US)
88      00 00 00 00 00 00 00 00  Languages2: 0x0000000000000000

[Manifest[1] - 48 bytes]
96      DB FE 3D 05 C7 CE 02 A2  DepotId: binary MD5 ...
...     (continues for remaining 40 bytes)

[Manifest[2] - 48 bytes]
144     E6 A4 5C 8F 3D 9E 7B 2A  DepotId: binary MD5 ...
...     (continues for remaining 40 bytes)
```

**Sorting:** Builds sorted by BuildId (numeric ascending)

**Writing Process:**
1. Pre-calculate Build Metadata size from scanned builds
2. Write Build Metadata with placeholder offsets (0x00)
3. Write Build Files section
4. Seek back to Build Metadata
5. Update RepositoryOffset, RepositorySize, and Manifest Offset/Size fields
6. Continue to Chunk Metadata section

---

## 4. Build Files (Zlib)

Repository and manifest files, zlib-compressed as downloaded from GOG.

**Storage Order:**
1. All repositories (sorted by repositoryId/filename alphanumeric)
2. All manifests (sorted by depotId/filename alphanumeric)

**No padding between files** - written consecutively.

**Rationale:**
- Grouped by type for cleaner organization
- Each type sorted deterministically
- Repositories provide metadata to find manifests

---

## 5. Chunk Metadata (Binary)

Catalog of chunks stored in THIS PART only. Written immediately after Build Files (Part 0) or after Header (Part 1+) with placeholder offsets, then updated after Chunk Files are written.

**Location:** Present in ALL parts (each part catalogs its own chunks only).

**Structure (per chunk):**
```
Offset  Size  Field           Description
------  ----  -----           -----------
0       16    CompressedMd5   16-byte binary MD5 (from filename)
16      8     Offset          uint64 (relative to Chunk Files start in this part)
24      8     Size            uint64 (compressed size)
```

**Total entry size:** 32 bytes per chunk

**Sorting:** By CompressedMd5 (alphanumeric)

**Multi-part Notes:**
- Each part contains metadata ONLY for chunks stored in that part
- Part 0 does NOT contain metadata for chunks in other parts
- Extractors build cross-file chunk index in memory by reading all parts

**Writing Process:**
1. Pre-calculate which chunks go in this part (based on 2 GiB limit)
2. Write Chunk Metadata with placeholder offsets (0x00)
3. Write Chunk Files section
4. Seek back to Chunk Metadata
5. Update Offset and Size fields for each chunk
6. Seek back to Header
7. Update LocalChunkCount and all section offsets/sizes

**Example (first chunk in TUNIC):**
```
CompressedMd5:  0x000DD588E642C89B6E7DC5BDC5E7A02A (16 bytes binary)
Offset:         0x0000000000000000 (0, first chunk in section)
Size:           0x000000000000D4E4 (54500 bytes compressed)
```

**Binary Layout:**
```
Offset  Value (hex)              Field
------  -----------              -----
0       00 0D D5 88 E6 42 C8 9B  CompressedMd5: binary MD5 (first 8 bytes)
8       6E 7D C5 BD C5 E7 A0 2A  (last 8 bytes)
16      00 00 00 00 00 00 00 00  Offset: 0 (little-endian uint64)
24      E4 D4 00 00 00 00 00 00  Size: 54500 (little-endian uint64)
```

---

## 6. Chunk Files (Zlib)

Chunk files, zlib-compressed as downloaded from GOG.

**Storage Order:** Sorted by chunk filename (compressedMd5) alphanumeric

**No padding between files** - written consecutively.

---

## Deterministic Rules

1. **Sorting:**
   - Builds: By BuildId (uint64, ascending)
   - Repositories: By RepositoryId (alphanumeric)
   - Manifests: By DepotId (alphanumeric)
   - Chunks: By chunk filename (compressedMd5, alphanumeric)

2. **Alignment:**
   - All sections: 64-byte boundaries (fixed)
   - Padding: 0x00 bytes
   - Files within data sections: No padding (consecutive)

3. **Binary Format:**
   - All integers: Little-endian
   - All strings: UTF-8 encoding (no null terminators unless specified)
   - MD5 hashes: Stored as 16-byte binary (not ASCII hex strings)
     - Example: "c0b8eafca369caf82ec6f392b27653a2" → 0xC0 0xB8 0xEA 0xFC 0xA3 0x69 0xCA 0xF8 0x2E 0xC6 0xF3 0x92 0xB2 0x76 0x53 0xA2

4. **Compression:**
   - Use files as downloaded from GOG (already zlib-compressed)
   - No recompression - preserves original compressedMd5

---

## Multi-part Archives

When splitting archives across multiple files:

**Part Size:** Configurable by the packer (not enforced by format)
- **Recommended default: 2 GiB (2,147,483,648 bytes)** for data sections
  - Maximum compatibility across filesystems (FAT32 limit is 4 GiB)
  - Easier to transfer and store on various media
  - Reasonable balance between file count and individual file size
  - Approximately 200 chunks per part (assuming ~10 MB average chunk size)
- Other common limits: 4 GiB - 1 byte (FAT32 max), 10+ GiB (modern filesystems)

**Splitting Algorithm:**
1. Sort all chunks by CompressedMd5 (deterministic order)
2. Fill Part 0 with Build Files and chunks until **data size limit** reached
   - Size limit applies to Build Files + Chunk Files only (metadata excluded)
   - Metadata overhead does not count against the limit
3. Create Part 1, Part 2, etc. with remaining chunks (each part up to data size limit)
4. Each part tracks only its own chunks in local metadata
5. Final file sizes may exceed limit slightly due to metadata + alignment padding

### Part 0 Structure (`game.rgog`)
Contains **ALL** metadata and build files, plus initial chunks:
```
[Header: PartNumber=0, TotalParts=4, TotalBuildCount=2, TotalChunkCount=1523, LocalChunkCount=500]
[Product Metadata - binary]
[Build Files - ALL repositories + manifests, zlib-compressed]
[Build Metadata - binary, describes all builds]
[Chunk Files - first 500 chunks, zlib-compressed]
[Chunk Metadata - binary, ALL 1523 chunks with part# assignments]
```

### Part 1+ Structure (`game.rgog.1`, `game.rgog.2`, etc.)
Contains **ONLY** chunk storage (no metadata duplication):
```
[Header: PartNumber=N, TotalParts=4, TotalBuildCount=2, TotalChunkCount=1523, LocalChunkCount=512]
[Chunk Metadata - binary, ONLY 512 chunks in this part]
[Chunk Files - 512 chunks in this part]
```

**Example Header (Part 1 of 3):**
```
Offset  Value (hex)              Field
------  -----------              -----
0       52 47 4F 47              Magic "RGOG" (ASCII)
4       02 00                    Version: 0x0002
6       01                       Type: 0x01 (Base Build)
7       00                       Reserved
8       01 00 00 00              PartNumber: 1 (second file)
12      03 00 00 00              TotalParts: 3 (total files)
16      02 00                    TotalBuildCount: 2 (uint16)
18      F3 05 00 00              TotalChunkCount: 1523 (across all parts)
22      00 02 00 00              LocalChunkCount: 512 (in this part only)
26      00 00 00 00 00 00 00 00  ProductMetadataOffset: 0 (not in this part)
34      00 00 00 00 00 00 00 00  ProductMetadataSize: 0
42      00 00 00 00 00 00 00 00  BuildMetadataOffset: 0 (not in this part)
50      00 00 00 00 00 00 00 00  BuildMetadataSize: 0
58      00 00 00 00 00 00 00 00  BuildFilesOffset: 0 (not in this part)
66      00 00 00 00 00 00 00 00  BuildFilesSize: 0
74      80 00 00 00 00 00 00 00  ChunkMetadataOffset: 128 (right after header)
82      00 40 00 00 00 00 00 00  ChunkMetadataSize: 16384 bytes (512 × 32)
90      80 40 00 00 00 00 00 00  ChunkFilesOffset: 16512 (after Chunk Metadata)
98      00 00 00 40 02 00 00 00  ChunkFilesSize: ~536MB
106     00 00 00 00 00 00 00 00  Reserved
114     00 00 00 00 00 00 00 00  Reserved
122     00 00 00 00 00 00        Reserved (6 bytes)
```

**Key Differences from Part 0:**
- PartNumber = 1 (not 0)
- LocalChunkCount (512) < TotalChunkCount (1523)
- Product/Build metadata offsets/sizes are all 0
- ChunkMetadataOffset starts at 128 (right after header)
- ChunkFilesOffset comes after Chunk Metadata
- Chunk Metadata only catalogs the 512 chunks in this part
- ChunkFilesOffset starts at 128 (right after header)
- Chunk Metadata only contains the 512 chunks in this part

**Design Rationale:**
- **No duplication:** Metadata and build files appear ONLY in Part 0
- **Part 0 required:** Must have Part 0 to know archive contents
- **Self-contained verification:** Each part can verify its own chunks via metadata
- **Deterministic splitting:** Chunks assigned to parts in sorted order
- **TotalParts known upfront:** Header tells you how many files to expect

**Extraction Process:**
1. Open Part 0, read header to get TotalParts
2. Load Product Metadata and Build Metadata from Part 0
3. For each chunk needed:
   - Read Chunk Metadata from appropriate part to find offset
   - If PartNumber in chunk entry = 0: read from Part 0 Chunk Files
   - If PartNumber > 0: open `game.rgog.{PartNumber}`, read from that part's Chunk Files

---

## Reading Workflow

### Quick Build List
1. Read Part 0 header → get TotalBuildCount, TotalChunkCount from header
2. Seek to ProductMetadataOffset, read Product Metadata → get product info
3. Seek to BuildMetadataOffset, read Build Metadata → list all builds with BuildId

### Detailed Build Info
1. Parse Build Metadata to find build entry
2. Get repository offset from build entry
3. Seek to BuildFilesOffset + repository offset
4. Read repository (zlib-compressed) → decompress → parse JSON → get version, date, depot list

### Extract Specific Build
1. Parse Build Metadata for target build
2. Extract repository from BuildFilesOffset + offset
3. Extract all manifests for build's depots from BuildFilesOffset + offsets
4. Parse manifests to get chunk list
5. For each chunk:
   - Lookup in Part 0 Chunk Metadata to find PartNumber and offset
   - Seek to appropriate part's ChunkFilesOffset + offset
   - Read chunk (zlib-compressed)

---

## Writing Workflow

### Pre-calculation Phase (Before Any Writing)

**Step 1: Scan and Sort All Files**
1. Scan `meta/` folder, collect all files
2. Sort filenames alphanumerically
3. For each file:
   - Decompress and parse JSON (minimal read)
   - If has `productId` and `buildId` → Repository
     - Extract: `{filename, buildId, productId, os}`
   - Else → Manifest
     - Extract: `{filename, depotId, languages[]}`
4. Sort repositories by filename
5. Sort manifests by filename
6. Group manifests by build (match depotIds from repository metadata)

**Step 2: Calculate Part Assignments**
1. Scan `chunks/` folder, collect all chunk files
2. Sort chunk filenames alphanumerically
3. Get file size for each chunk
4. Calculate metadata sizes:
   - Header: 128 bytes
   - Product Metadata: ~64 bytes (aligned)
   - Build Metadata: (48 + 48×manifestCount) × buildCount
   - Chunk Metadata per chunk: 32 bytes
5. Walk chunks in sorted order:
   - `partSize = headerSize + productMetadataSize + buildMetadataSize`
   - For each chunk:
     - `partSize += 32 (metadata) + chunkFileSize`
     - If `partSize > 2GB`: assign chunk to next part, reset counter
   - Result: List of chunks per part

### Writing Phase

**Part 0 (Main Archive):**

**Step 1: Write Header (Placeholder)**
1. Write 128-byte header with known counts:
   - Magic, Version, Type
   - PartNumber = 0
   - TotalParts (from pre-calculation)
   - TotalBuildCount (from scan)
   - TotalChunkCount (from scan)
   - LocalChunkCount (chunks assigned to Part 0)
   - All offsets/sizes = 0 (placeholders)

**Step 2: Write Product Metadata**
1. Extract productId from first repository
2. Extract product name if available
3. Write Product Metadata (binary)
4. Align to 64 bytes
5. Record: ProductMetadataOffset = 128, ProductMetadataSize

**Step 3: Write Build Metadata (Placeholder)**
1. Calculate exact Build Metadata size from pre-scanned builds
2. Write Build Metadata entries with:
   - Known: BuildId, OS, RepositoryId, ManifestCount
   - Placeholder (0x00): RepositoryOffset, RepositorySize, Manifest Offset/Size
3. Align to 64 bytes
4. Record: BuildMetadataOffset, BuildMetadataSize

**Step 4: Write Build Files**
1. For each repository (in sorted order):
   - Write repository file (zlib as-is)
   - Track: `{repositoryId, offset, size}` (offset relative to BuildFilesOffset)
2. For each manifest (in sorted order):
   - Write manifest file (zlib as-is)
   - Track: `{depotId, offset, size}` (offset relative to BuildFilesOffset)
3. Align to 64 bytes
4. Record: BuildFilesOffset, BuildFilesSize

**Step 5: Update Build Metadata**
1. Seek back to BuildMetadataOffset
2. For each build entry:
   - Write RepositoryOffset, RepositorySize (from tracked data)
   - For each manifest: write Offset, Size (from tracked data)
3. Seek to end of Build Files (resume writing)

**Step 6: Write Chunk Metadata (Placeholder)**
1. Write Chunk Metadata entries for chunks in Part 0:
   - Known: CompressedMd5 (from filename)
   - Placeholder (0x00): Offset, Size
2. Align to 64 bytes
3. Record: ChunkMetadataOffset, ChunkMetadataSize

**Step 7: Write Chunk Files**
1. For each chunk assigned to Part 0 (in sorted order):
   - Write chunk file (zlib as-is)
   - Track: `{compressedMd5, offset, size}` (offset relative to ChunkFilesOffset)
2. Align to 64 bytes
3. Record: ChunkFilesOffset, ChunkFilesSize

**Step 8: Update Chunk Metadata**
1. Seek back to ChunkMetadataOffset
2. For each chunk entry:
   - Write Offset, Size (from tracked data)
3. Seek to end of file

**Step 9: Update Header**
1. Seek back to offset 0
2. Write complete header with all section offsets/sizes
3. Part 0 complete

---

**Part 1+ (Additional Parts):**

**Step 1: Write Header (Placeholder)**
1. Write 128-byte header:
   - Magic, Version, Type (same as Part 0)
   - PartNumber = N
   - TotalParts (same as Part 0)
   - TotalBuildCount (same as Part 0)
   - TotalChunkCount (same as Part 0)
   - LocalChunkCount (chunks assigned to this part)
   - Product/Build metadata offsets/sizes = 0
   - Chunk offsets/sizes = 0 (placeholders)

**Step 2: Write Chunk Metadata (Placeholder)**
1. Write Chunk Metadata entries for chunks in this part:
   - Known: CompressedMd5
   - Placeholder (0x00): Offset, Size
2. Align to 64 bytes
3. Record: ChunkMetadataOffset, ChunkMetadataSize

**Step 3: Write Chunk Files**
1. For each chunk assigned to this part (in sorted order):
   - Write chunk file (zlib as-is)
   - Track: `{compressedMd5, offset, size}` (offset relative to ChunkFilesOffset)
2. Align to 64 bytes
3. Record: ChunkFilesOffset, ChunkFilesSize

**Step 4: Update Chunk Metadata**
1. Seek back to ChunkMetadataOffset
2. For each chunk entry:
   - Write Offset, Size (from tracked data)
3. Seek to end of file

**Step 5: Update Header**
1. Seek back to offset 0
2. Write complete header with chunk section offsets/sizes
3. Part N complete

---

### Summary of Update Operations

**Part 0:**
- Write Build Metadata → Write Build Files → **Update Build Metadata**
- Write Chunk Metadata → Write Chunk Files → **Update Chunk Metadata + Header**

**Part 1+:**
- Write Chunk Metadata → Write Chunk Files → **Update Chunk Metadata + Header**

---

## Tools (Proposed)

```bash
# Pack archive
rgog pack TUNIC/v2/ -o tunic.rgog
rgog pack TUNIC/v2/ -o tunic.rgog --max-part-size 10GB

# List contents
rgog list tunic.rgog                    # Quick: show product + builds
rgog list tunic.rgog --detailed         # Decompress repos for versions/dates
rgog list tunic.rgog --build 1716751705 # Show specific build info

# Extract
rgog extract tunic.rgog -o output/                  # Everything
rgog extract tunic.rgog --build 1716751705 -o out/ # Single build
rgog extract tunic.rgog --chunks -o chunks/         # Only chunks

# Verify
rgog verify tunic.rgog                    # Check all MD5s
rgog verify tunic.rgog --build 1716751705 # Check single build

# Info
rgog info tunic.rgog  # Stats, deduplication, part count
```

---

## Advantages

1. **Three-tier metadata**: Clear separation (product/build/chunk)
---

## Advantages

1. **Binary metadata**: Compact, fast to parse, no JSON overhead
2. **Streaming writes**: Data first, metadata after (no size pre-calculation)
3. **No duplication**: Metadata only in Part 0
4. **Selective extraction**: Extract builds without full scan
5. **No redundant checksums**: Use compressedMd5 (already in filenames)
6. **64-byte alignment**: Optimal for cache lines, fixed (deterministic)
7. **Per-part chunk tracking**: TotalCount + LocalCount in each part
8. **Deterministic**: Same inputs always produce identical outputs

---

## Example: Multi-part Archive

```
tunic.rgog          (10.5 GB)  Part 0: Product + builds + 500 chunks
tunic.rgog.1        (10.0 GB)  Part 1: 512 chunks only
tunic.rgog.2        (10.0 GB)  Part 2: 511 chunks only
```

**Part 0 breakdown:**
```
Header:              128 bytes
Product Metadata:    64 bytes (aligned)
Build Files:         50 MB (repos + manifests)
Build Metadata:      5 KB (describes builds)
Chunk Files:         10.4 GB (500 chunks)
Chunk Metadata:      80 KB (ALL 1523 chunks catalog)
```

**Benefits:**
- Easier transfer (smaller files)
- Parallel verification (each part self-contained)
- Resume failed transfers (re-download failed part only)
- Extract builds without all parts (if chunks are in Part 0)

---

## Future Extensions

### Version 2.1: Patch Archive Support

**Overview**

RGOG v2.1 will introduce specialized patch archive functionality. While the Type field (offset 6) is already defined in v2.0 headers to distinguish Base Build (0x01) from Patch Collection (0x02) archives, the full patch metadata structures and workflows will be formalized in v2.1.

**File Naming Convention**
- Base builds: `game.rgog`, `game.rgog.1`, etc.
- Patch archives: `game_patches.rgog`, `game_patches.rgog.1`, etc.

**Type Field (Already Implemented in v2.0)**

The RGOG header includes a Type field at offset 6 (uint8):

```
Offset  Size  Field           Value
------  ----  -----           -----
6       1     Type            0x01 = Base Build
                              0x02 = Patch Collection
                              0x03-0xFF = Reserved
```

**Note:** RGOG v2.0 implementations should write Type=0x01 for all base build archives and validate that Type field is recognized when reading.

**Patch Archive Structure**

Patch archives follow the same overall RGOG structure but with specialized metadata:

```
┌─────────────────────────────┐
│ RGOG Header (Type=0x02)     │  128 bytes
├─────────────────────────────┤
│ Product Metadata            │  Variable (binary, same as v2.0)
├─────────────────────────────┤
│ Patch Metadata Section      │  Variable (binary, describes all patches)
├─────────────────────────────┤
│ Patch Repository Files      │  Variable (zlib compressed JSON, contains xdelta3 manifests)
├─────────────────────────────┤
│ Differential Chunk Files    │  Variable (xdelta3 differential data, zlib compressed)
├─────────────────────────────┤
│ Chunk Metadata Section      │  Variable (binary, catalogs differential chunks)
└─────────────────────────────┘
```

**Patch Metadata Format**

Each patch entry describes a single patch repository:

```c
struct PatchEntry {
    uint64_t  PatchId;              // GOG patch ID
    uint64_t  SourceBuildId;        // Build to apply patch FROM
    uint64_t  TargetBuildId;        // Build to apply patch TO
    uint8_t   OS;                   // 0=null, 1=Windows, 2=Mac, 3=Linux
    uint8_t   RepositoryId[16];     // MD5 of repository filename (binary)
    uint64_t  RepositoryOffset;     // Offset in Patch Repository Files section
    uint32_t  RepositorySize;       // Size of repository file
    uint16_t  DepotCount;           // Number of depot diffs in this patch
    // Followed by DepotCount DepotDiffEntry structures
};

struct DepotDiffEntry {
    uint8_t   DepotId[16];          // MD5 of depot manifest filename (binary)
    uint64_t  Languages1;           // Language bit flags (bits 0-63)
    uint64_t  Languages2;           // Language bit flags (bits 64-127)
    uint16_t  ChunkCount;           // Number of differential chunks for this depot
    // Followed by ChunkCount ChunkReference structures
};

struct ChunkReference {
    uint8_t   CompressedMd5[16];    // MD5 of differential chunk filename (binary)
};
```

**Patch Repository Files**

- Contains GOG patch repository JSON files (zlib compressed, as-is from GOG)
- Repository contains `depotDiff` entries with lists of xdelta3 differential chunks
- Sorted alphanumerically by repository filename (MD5)
- Type-grouped: all repositories before chunk files

**Differential Chunk Files**

- Contains xdelta3 differential data files (`.xdelta` or `.xdelta3`)
- Files are zlib compressed (as-is from GOG)
- Sorted alphanumerically by CompressedMd5
- Used to generate updated chunks from previous build chunks

**Usage Pattern**

1. User downloads base build: `game.rgog`
2. User downloads patches: `game_patches.rgog`
3. Unpacker extracts base build to directory structure
4. Unpacker applies patches:
   - Reads patch metadata to find SourceBuildId → TargetBuildId
   - Extracts differential chunks for matching OS/language
   - Applies xdelta3 patches to existing chunks
   - Generates updated repository/manifest files

**Benefits of Separation**

1. **Modularity**: Base builds remain standalone, patches are optional
2. **Bandwidth**: Users download only needed patches (not re-downloading full builds)
3. **Simplicity**: Each archive type has focused structure
4. **Compatibility**: RGOG v2.0 readers ignore Type field, still work with base builds
5. **Flexibility**: Patches can reference multiple source/target build pairs

**Deferred to v2.1**

The current RGOG v2.0 specification focuses exclusively on base builds. Patch archive support requires additional testing with real-world GOG patch data and will be formalized in the v2.1 specification update.
