# Small Files Container (SFC) Support

## Overview

Galaxy V2 manifests use **Small Files Containers (SFC)** to efficiently store small metadata and license files. Instead of downloading many tiny files individually, they are packed into a single compressed container.

## Structure

### Manifest Format

```json
{
  "depot": {
    "items": [
      {
        "path": "goggame-1901931967.hashdb",
        "type": "DepotFile",
        "sfcRef": {
          "offset": 0,
          "size": 178
        },
        "chunks": [...]  // NOTE: These chunks describe the extracted file, not downloadable chunks!
      },
      {
        "path": "goggame-1901931967.info",
        "type": "DepotFile",
        "sfcRef": {
          "offset": 178,
          "size": 241
        },
        "chunks": [...]  // These are phantom chunks - don't download them!
      }
    ],
    "smallFilesContainer": {
      "chunks": [
        {
          "compressedMd5": "856aac6b952abcd3b62c6f0340ba3798",
          "compressedSize": 271,
          "md5": "b4b24685d6c5c6e4809220226c4a3ad7",
          "size": 419
        }
      ]
    }
  }
}
```

### Key Points

1. **Items with `sfcRef`**: These files are stored in the SFC
   - `offset`: Byte offset within the decompressed SFC data
   - `size`: Size of the file within the SFC
   - `chunks`: Describes what the extracted file looks like (MD5, size)

2. **smallFilesContainer**: The actual container to download
   - Has its own `chunks` array - these ARE always downloadable
   - Must be downloaded and decompressed first
   - Contains multiple small files packed together

3. **Individual Chunks May or May Not Exist**: 
   - Items with `sfcRef` have a `chunks` array describing the extracted file
   - These chunks **MAY** exist on the CDN (older builds) or **MAY NOT** (newer builds)
   - The SFC is the guaranteed source - individual chunks are opportunistic
   - **Archival strategy**: Download SFC first, then try individual chunks (they might exist for redundancy)
   - **Installation strategy**: Extract from SFC (always works) or download individual chunks if they exist

## Implementation

### DepotItem Fields

```python
@dataclass
class DepotItem:
    is_small_files_container: bool = False  # True if this IS the SFC
    is_in_sfc: bool = False                 # True if this file is IN an SFC
    sfc_offset: int = 0                     # Offset within SFC
    sfc_size: int = 0                       # Size within SFC
```

### API Parsing (galaxy_dl/api.py)

```python
def get_depot_items(self, manifest_hash: str) -> List[DepotItem]:
    depot = manifest_json["depot"]
    items = []
    
    # Create SFC item
    if "smallFilesContainer" in depot:
        sfc_item = DepotItem.from_json_sfc(depot["smallFilesContainer"])
        items.append(sfc_item)
    
    # Create regular items (including those with sfcRef)
    for item_json in depot["items"]:
        item = DepotItem.from_json_v2(item_json)
        items.append(item)
    
    return items
```

### Download Process (galaxy_dl/downloader.py)

```python
def download_depot_items(self, items: List[DepotItem], output_dir: str,
                        delete_sfc_after_extraction: bool = True):
    # 1. Download SFC containers
    for item in items:
        if item.is_small_files_container:
            sfc_path = download_item(item)
            sfc_data = decompress(sfc_path)
    
    # 2. Extract files from SFC
    for item in items:
        if item.is_in_sfc:
            file_data = sfc_data[item.sfc_offset:item.sfc_offset + item.sfc_size]
            save_file(item.path, file_data)
    
    # 3. Download regular files
    for item in items:
        if not item.is_small_files_container and not item.is_in_sfc:
            download_item(item)
    
    # 4. Delete SFC containers (optional)
    if delete_sfc_after_extraction:
        delete(sfc_path)
```

## Archival Mode

For archiving, you want to preserve the raw SFC chunks without extraction:

```python
# In archive_game.py
for depot in depot_json['depots']:
    manifest_json = get_manifest(depot['manifest'])
    
    # Skip chunks from items with sfcRef (they're phantom chunks)
    for item in manifest_json['depot']['items']:
        if 'sfcRef' not in item:  # Only collect real chunks
            for chunk in item['chunks']:
                all_chunks[chunk['compressedMd5']] = chunk
    
    # Collect SFC chunks (these are real)
    if 'smallFilesContainer' in manifest_json['depot']:
        for chunk in manifest_json['depot']['smallFilesContainer']['chunks']:
            all_chunks[chunk['compressedMd5']] = chunk
```

## Comparison with Other Tools

### lgogdownloader
- ✅ Full SFC support
- Downloads SFC, extracts files, deletes SFC
- Skips SFC if files already exist

### heroic-gogdl
- ❌ No SFC support
- Tries to download phantom chunks (fails)
- Missing license/metadata files

### galaxyDL-Python
- ✅ Full SFC support (as of this implementation)
- Supports both archival and installation modes
- Handles DLC SFCs with different product IDs

## Common Files in SFC

Typically contains:
- `goggame-*.hashdb` - Hash database for integrity checks
- `goggame-*.info` - Game/DLC metadata JSON
- License files
- Small configuration files

## Example Usage

### Installation Mode
```python
from galaxy_dl import GalaxyDownloader

downloader = GalaxyDownloader(auth_token)
items = api.get_depot_items(manifest_hash)

# Downloads SFC, extracts files, deletes SFC
results = downloader.download_depot_items(
    items, 
    "output_dir",
    delete_sfc_after_extraction=True
)
```

### Archival Mode
```python
# Download raw SFC chunks without extraction
for chunk_md5 in sfc_chunk_md5s:
    downloader.download_raw_chunk(
        chunk_md5, 
        f"store/{chunk_md5[:2]}/{chunk_md5[2:4]}/{chunk_md5}",
        product_id=depot_product_id
    )
```
