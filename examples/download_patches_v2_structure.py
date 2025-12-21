"""
Download patches with V2-compatible manifest structure

This example demonstrates:
1. Downloading patch manifests (root + depot)
2. Saving raw zlib manifests to meta/ folder (galaxy_path structure)
3. Saving decompressed JSON to debug/ folder
4. Downloading patch chunks to store/ folder
5. Creating a complete V2-compatible directory structure

Directory structure created (matches V2 builds):
patches/
├── meta/
│   ├── {hash[:2]}/
│   │   └── {hash[2:4]}/
│   │       └── {hash}              # Raw zlib-compressed manifest
├── debug/
│   ├── {root_hash}_manifest.json   # Pretty-printed root manifest
│   └── {depot_hash}_manifest.json  # Pretty-printed depot manifest
├── depot/
│   └── patches/
│       └── {depot_manifest_hash}/
│           └── {chunk_hash[:2]}/
│               └── {chunk_hash[2:4]}/
│                   └── {chunk_hash} # Patch delta chunk
└── store/
    └── {chunk_hash[:2]}/
        └── {chunk_hash[2:4]}/
            └── {chunk_hash}         # Patch delta chunk (symlink or copy)
"""

import os
import json
import hashlib
from pathlib import Path

from galaxy_dl import GalaxyAPI, AuthManager, Manifest, Patch, utils


# Build information for The Witcher 2
PRODUCT_ID = "1207658930"
PLATFORM = "windows"
OLD_BUILD_ID = "49999910531550131"
NEW_BUILD_ID = "56452082907692588"

# Base directory
OUTPUT_DIR = Path("witcher2_patches")


def save_raw_manifest(raw_bytes: bytes, manifest_hash: str, manifest_type: str, base_dir: Path):
    """
    Save raw zlib-compressed manifest to meta/ folder using galaxy_path structure.
    
    Args:
        raw_bytes: Raw bytes from API (zlib-compressed)
        manifest_hash: Hash identifier for the manifest
        manifest_type: 'root' or 'depot'
        base_dir: Base directory for patches
    """
    # Use galaxy_path structure: meta/{hash[:2]}/{hash[2:4]}/{hash}
    meta_dir = base_dir / "meta" / manifest_hash[:2] / manifest_hash[2:4]
    meta_dir.mkdir(parents=True, exist_ok=True)
    
    meta_file = meta_dir / manifest_hash
    meta_file.write_bytes(raw_bytes)
    
    print(f"       ✓ Saved raw manifest: meta/{manifest_hash[:2]}/{manifest_hash[2:4]}/{manifest_hash}")
    return meta_file


def save_debug_manifest(manifest_dict: dict, manifest_hash: str, manifest_type: str, base_dir: Path):
    """
    Save decompressed JSON manifest to debug/ folder.
    
    Args:
        manifest_dict: Decompressed manifest data
        manifest_hash: Hash identifier for the manifest
        manifest_type: 'root' or 'depot'
        base_dir: Base directory for patches
    """
    debug_dir = base_dir / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    
    debug_file = debug_dir / f"{manifest_hash}_manifest.json"
    with open(debug_file, 'w', encoding='utf-8') as f:
        json.dump(manifest_dict, f, indent=2)
    
    print(f"       ✓ Saved debug JSON: debug/{manifest_hash}_manifest.json")
    return debug_file


def download_patch_chunk(
    api: GalaxyAPI,
    product_id: str,
    chunk_md5: str,
    chunk_size: int,
    client_id: str,
    client_secret: str,
    base_dir: Path,
    create_store_copy: bool = True
) -> Path:
    """
    Download a patch chunk to depot/ folder.
    
    Args:
        api: GalaxyAPI instance
        product_id: Product ID
        chunk_md5: Chunk compressedMd5 hash
        chunk_size: Expected chunk size
        client_id: Client ID from patch manifest
        client_secret: Client secret from patch manifest
        base_dir: Base directory for patches
        create_store_copy: If True, create copy/symlink in store/ folder
        
    Returns:
        Path to downloaded chunk
    """
    # Get secure link
    secure_urls = api.get_patch_secure_link(
        product_id=product_id,
        chunk_hash=chunk_md5,
        client_id=client_id,
        client_secret=client_secret
    )
    
    if not secure_urls:
        raise RuntimeError(f"Failed to get secure link for {chunk_md5}")
    
    # Build chunk URL
    chunk_path = utils.galaxy_path(chunk_md5)
    chunk_url = secure_urls[0].replace("{GALAXY_PATH}", chunk_path)
    
    # Download chunk
    response = api.session.get(chunk_url, timeout=30)
    response.raise_for_status()
    
    chunk_data = response.content
    
    # Verify MD5
    actual_md5 = hashlib.md5(chunk_data).hexdigest()
    if actual_md5 != chunk_md5:
        raise ValueError(f"Chunk MD5 mismatch: {actual_md5} != {chunk_md5}")
    
    # Save to depot/ folder (V2 structure)
    depot_dir = base_dir / "depot" / "patches" / chunk_md5 / chunk_md5[:2] / chunk_md5[2:4]
    depot_dir.mkdir(parents=True, exist_ok=True)
    depot_file = depot_dir / chunk_md5
    depot_file.write_bytes(chunk_data)
    
    # Optionally create store/ copy for easier access
    if create_store_copy:
        store_dir = base_dir / "store" / chunk_md5[:2] / chunk_md5[2:4]
        store_dir.mkdir(parents=True, exist_ok=True)
        store_file = store_dir / chunk_md5
        
        # Try symlink first, fallback to copy
        try:
            if not store_file.exists():
                store_file.symlink_to(depot_file)
        except (OSError, NotImplementedError):
            # Symlinks not supported, copy instead
            store_file.write_bytes(chunk_data)
    
    return depot_file


def main():
    """Main patch download workflow with V2 structure."""
    print("=" * 80)
    print("The Witcher 2: Patch Download with V2 Structure")
    print("=" * 80)
    
    # Initialize API
    print("\n1. Initializing API...")
    auth = AuthManager()
    if not auth.is_authenticated():
        print("ERROR: Not authenticated. Run 'galaxy-dl login' first.")
        return 1
    
    api = GalaxyAPI(auth)
    print("✓ Authenticated")
    
    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Get build information
    print("\n2. Getting build information...")
    builds_data = api.get_all_product_builds(PRODUCT_ID, PLATFORM)
    
    if not builds_data or not builds_data.get("items"):
        print("ERROR: Failed to get builds")
        return 1
    
    builds = builds_data["items"]
    old_build = next((b for b in builds if b.get("build_id") == OLD_BUILD_ID), None)
    new_build = next((b for b in builds if b.get("build_id") == NEW_BUILD_ID), None)
    
    if not old_build or not new_build:
        print(f"ERROR: Could not find builds")
        return 1
    
    print(f"✓ Old build: {OLD_BUILD_ID}")
    print(f"✓ New build: {NEW_BUILD_ID}")
    
    # Query for patch availability
    print("\n3. Querying for patch availability...")
    patch_info = api.get_patch_info(PRODUCT_ID, OLD_BUILD_ID, NEW_BUILD_ID)
    
    if not patch_info or 'error' in patch_info:
        print("✗ No patch available")
        return 1
    
    print(f"✓ Patch available")
    
    # Download root patch manifest (with raw bytes)
    print("\n4. Downloading root patch manifest...")
    patch_link = patch_info.get('link')
    if not patch_link:
        print("ERROR: No patch link in patch_info")
        return 1
    
    result = api.get_patch_manifest(patch_link, return_raw=True)
    if not result or not isinstance(result, tuple):
        print("ERROR: Failed to download root manifest")
        return 1
    
    raw_root, root_manifest = result
    assert isinstance(raw_root, bytes), "Expected bytes for raw_root"
    assert isinstance(root_manifest, dict), "Expected dict for root_manifest"
    
    # Calculate manifest hash (use MD5 of raw bytes)
    root_hash = hashlib.md5(raw_root).hexdigest()
    
    print(f"   Root manifest hash: {root_hash}")
    print(f"   Algorithm: {root_manifest.get('algorithm')}")
    print(f"   Depots: {len(root_manifest.get('depots', []))}")
    
    # Save root manifest
    save_raw_manifest(raw_root, root_hash, 'root', OUTPUT_DIR)
    save_debug_manifest(root_manifest, root_hash, 'root', OUTPUT_DIR)
    
    # Find English depot
    print("\n5. Finding English depot...")
    depots = root_manifest.get('depots', [])
    en_depot = None
    
    for depot in depots:
        languages = depot.get('languages', [])
        # Flexible language matching
        if any(lang.startswith('en') for lang in languages):
            en_depot = depot
            break
    
    if not en_depot:
        print("ERROR: No English depot found")
        return 1
    
    depot_manifest_id = en_depot.get('manifest')
    print(f"✓ Found English depot")
    print(f"   Depot manifest ID: {depot_manifest_id}")
    print(f"   Languages: {en_depot.get('languages')}")
    
    # Download depot patch manifest (with raw bytes)
    print("\n6. Downloading depot patch manifest...")
    result = api.get_patch_depot_manifest(depot_manifest_id, return_raw=True)
    
    if not result or not isinstance(result, tuple):
        print("ERROR: Failed to download depot manifest")
        return 1
    
    raw_depot, depot_manifest = result
    assert isinstance(raw_depot, bytes), "Expected bytes for raw_depot"
    assert isinstance(depot_manifest, dict), "Expected dict for depot_manifest"
    
    print(f"   Depot manifest hash: {depot_manifest_id}")
    print(f"   Items: {len(depot_manifest.get('depot', {}).get('items', []))}")
    
    # Save depot manifest
    save_raw_manifest(raw_depot, depot_manifest_id, 'depot', OUTPUT_DIR)
    save_debug_manifest(depot_manifest, depot_manifest_id, 'depot', OUTPUT_DIR)
    
    # Download patch chunks
    print("\n7. Downloading patch chunks...")
    items = depot_manifest.get('depot', {}).get('items', [])
    
    if not items:
        print("WARNING: No patch items found")
        return 0
    
    # Get client credentials from root manifest
    client_id = root_manifest.get('clientId')
    client_secret = root_manifest.get('clientSecret')
    
    if not client_id or not client_secret:
        print("ERROR: Missing client credentials in root manifest")
        return 1
    
    total_chunks = sum(len(item.get('chunks', [])) for item in items)
    chunk_count = 0
    
    print(f"   Total items: {len(items)}")
    print(f"   Total chunks: {total_chunks}")
    
    for item_idx, item in enumerate(items, 1):
        file_path = item.get('path', 'unknown')
        chunks = item.get('chunks', [])
        
        print(f"\n   [{item_idx}/{len(items)}] {file_path}")
        print(f"       Source MD5: {item.get('md5Before')}")
        print(f"       Target MD5: {item.get('md5After')}")
        print(f"       Chunks: {len(chunks)}")
        
        for chunk in chunks:
            chunk_md5 = chunk.get('compressedMd5')
            chunk_size = chunk.get('compressedSize')
            
            try:
                chunk_file = download_patch_chunk(
                    api=api,
                    product_id=PRODUCT_ID,
                    chunk_md5=chunk_md5,
                    chunk_size=chunk_size,
                    client_id=client_id,
                    client_secret=client_secret,
                    base_dir=OUTPUT_DIR,
                    create_store_copy=True
                )
                
                chunk_count += 1
                print(f"       ✓ [{chunk_count}/{total_chunks}] Downloaded: {chunk_md5} ({chunk_size:,} bytes)")
                
            except Exception as e:
                print(f"       ✗ Failed to download {chunk_md5}: {e}")
    
    # Save summary
    print("\n8. Saving summary...")
    summary = {
        "product_id": PRODUCT_ID,
        "from_build_id": OLD_BUILD_ID,
        "to_build_id": NEW_BUILD_ID,
        "algorithm": root_manifest.get('algorithm'),
        "root_manifest_hash": root_hash,
        "depot_manifest_hash": depot_manifest_id,
        "total_items": len(items),
        "total_chunks": total_chunks,
        "downloaded_chunks": chunk_count
    }
    
    summary_file = OUTPUT_DIR / "patch_summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    
    print(f"✓ Saved summary: {summary_file}")
    
    # Print directory tree
    print("\n" + "=" * 80)
    print("DOWNLOAD COMPLETE")
    print("=" * 80)
    print(f"\nDirectory structure:")
    print(f"  {OUTPUT_DIR}/")
    print(f"  ├── meta/")
    print(f"  │   ├── {root_hash[:2]}/{root_hash[2:4]}/{root_hash} (root manifest, zlib)")
    print(f"  │   └── {depot_manifest_id[:2]}/{depot_manifest_id[2:4]}/{depot_manifest_id} (depot manifest, zlib)")
    print(f"  ├── debug/")
    print(f"  │   ├── {root_hash}_manifest.json")
    print(f"  │   └── {depot_manifest_id}_manifest.json")
    print(f"  ├── depot/patches/{depot_manifest_id}/")
    print(f"  │   └── [chunk folders with patch deltas]")
    print(f"  ├── store/")
    print(f"  │   └── [chunk folders with patch deltas]")
    print(f"  └── patch_summary.json")
    
    print(f"\nStatistics:")
    print(f"  Files with patches: {len(items)}")
    print(f"  Total chunks: {total_chunks}")
    print(f"  Downloaded: {chunk_count}")
    
    return 0


if __name__ == "__main__":
    exit(main())
