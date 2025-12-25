#!/usr/bin/env python3
"""
Download patches between two GOG Galaxy builds

Downloads patch manifests and delta chunks in V2-compatible CDN mirror structure.

DIRECTORY STRUCTURE:
--------------------
The script creates a directory structure matching GOG's V2 CDN layout:

<output_dir>/
├── meta/                           # Manifest files (zlib compressed)
│   ├── {hash[:2]}/
│   │   └── {hash[2:4]}/
│   │       └── {hash}              # Root patch manifest (zlib compressed JSON)
│   └── {hash[:2]}/
│       └── {hash[2:4]}/
│           └── {hash}              # Depot patch manifest (zlib compressed JSON)
│
├── debug/                          # Human-readable manifests
│   ├── {root_hash}_manifest.json   # Decompressed root manifest
│   └── {depot_hash}_manifest.json  # Decompressed depot patch diffs
│
├── depot/patches/                  # Patch delta chunks
│   └── {hash[:2]}/
│       └── {hash[2:4]}/
│           └── {hash}              # .delta file (xdelta3 format)
│
└── patch_summary.json              # Download summary and metadata

FILE TYPES:
-----------
- meta/*.json: Raw zlib-compressed manifest JSONs (as downloaded from CDN)
- debug/*.json: Decompressed, pretty-printed manifests for inspection
- depot/patches/*: xdelta3 delta files for binary patching
- patch_summary.json: Metadata about the patch download

MANIFEST CONTENTS:
------------------
- Root manifest: Contains patch metadata, algorithm, depot references
- Depot manifest: Contains DepotDiff items with:
  * File path
  * Source MD5 (md5Before)
  * Target MD5 (md5After)
  * Delta chunks (compressedMd5, compressedSize)

USAGE:
------
    python download_patches.py <product_id> <from_build_id> <to_build_id> [output_dir] [--workers N]
    
EXAMPLES:
---------
    # Download Witcher 2 patch from build A to B
    python download_patches.py 1207658930 49999910531550131 56452082907692588
    
    # Custom output directory with 16 parallel workers
    python download_patches.py 1207658930 49999910531550131 56452082907692588 witcher2_patches --workers 16
    
    # Download to specific directory with fewer workers (slower internet)
    python download_patches.py 1716751705 55274589103253930 56111111111111111 tunic_patches --workers 4

NOTES:
------
- Requires authentication (run 'galaxy-dl login' first)
- Only V2 builds support patches (V1 builds don't have patch manifests)
- Delta files use xdelta3 format and require xdelta3 tool to apply
- The structure matches GOG CDN exactly for archival purposes
"""

import os
import sys
import json
import hashlib
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from galaxy_dl import GalaxyAPI, AuthManager, Manifest, Patch, utils


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
        manifest_type: 'root' or 'depot' - used in filename
        base_dir: Base directory for patches
    """
    debug_dir = base_dir / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    
    debug_file = debug_dir / f"{manifest_hash}_{manifest_type}.json"
    with open(debug_file, 'w', encoding='utf-8') as f:
        json.dump(manifest_dict, f, indent=2)
    
    print(f"       ✓ Saved debug JSON: debug/{manifest_hash}_{manifest_type}.json")
    return debug_file


def download_patch_chunk(
    api: GalaxyAPI,
    product_id: str,
    chunk_md5: str,
    chunk_size: int,
    client_id: str,
    client_secret: str,
    base_dir: Path
) -> Path:
    """
    Download a patch chunk to depot/patches/ folder.
    
    Args:
        api: GalaxyAPI instance
        product_id: Product ID
        chunk_md5: Chunk compressedMd5 hash
        chunk_size: Expected chunk size
        client_id: Client ID from patch manifest
        client_secret: Client secret from patch manifest
        base_dir: Base directory for patches
        
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
    
    # Save to depot/patches/ folder
    depot_dir = base_dir / "depot" / "patches" / chunk_md5[:2] / chunk_md5[2:4]
    depot_dir.mkdir(parents=True, exist_ok=True)
    depot_file = depot_dir / chunk_md5
    depot_file.write_bytes(chunk_data)
    
    return depot_file


def main(product_id: str, from_build_id: str, to_build_id: str, output_dir: Path, num_workers: int = 8, language: str | None = None):
    """Main patch download workflow with V2 structure."""
    print("=" * 80)
    print("GOG Galaxy Patch Download")
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
    output_dir.mkdir(exist_ok=True)
    
    # Query for patch availability (we don't need to get build info first)
    print("\n2. Querying for patch availability...")
    print(f"   Product: {product_id}")
    print(f"   From build: {from_build_id}")
    print(f"   To build: {to_build_id}")
    
    patch_info = api.get_patch_info(product_id, from_build_id, to_build_id)
    
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
    save_raw_manifest(raw_root, root_hash, 'root', output_dir)
    save_debug_manifest(root_manifest, root_hash, 'root', output_dir)
    
    # Find matching depot(s)
    print("\n5. Finding depot(s)...")
    depots = root_manifest.get('depots', [])
    
    if language:
        print(f"   Language filter: {language}")
        matching_depots = [
            d for d in depots 
            if any(lang.startswith(language) for lang in d.get('languages', []))
        ]
    else:
        print("   No language filter (downloading all depots)")
        matching_depots = depots
    
    if not matching_depots:
        if language:
            print(f"ERROR: No depot found for language '{language}'")
        else:
            print("ERROR: No depots found in patch manifest")
        return 1
    
    print(f"✓ Found {len(matching_depots)} depot(s)")
    for depot in matching_depots:
        print(f"   - {depot.get('manifest')}: {depot.get('languages', [])}")
    
    # Get client credentials from root manifest
    client_id = root_manifest.get('clientId')
    client_secret = root_manifest.get('clientSecret')
    
    if not client_id or not client_secret:
        print("ERROR: Missing client credentials in root manifest")
        return 1
    
    # Process each depot
    all_stats = {'downloaded': 0, 'skipped': 0, 'failed': 0}
    
    for depot_idx, depot in enumerate(matching_depots, 1):
        depot_manifest_id = depot.get('manifest')
        depot_languages = depot.get('languages', [])
        
        print(f"\n6. Processing depot {depot_idx}/{len(matching_depots)}: {depot_languages}")
        print(f"   Depot manifest ID: {depot_manifest_id}")
        
        # Download depot patch manifest (with raw bytes)
        result = api.get_patch_depot_manifest(depot_manifest_id, return_raw=True)
        
        if not result or not isinstance(result, tuple):
            print(f"   ERROR: Failed to download depot manifest {depot_manifest_id}")
            continue
        
        raw_depot, depot_manifest = result
        assert isinstance(raw_depot, bytes), "Expected bytes for raw_depot"
        assert isinstance(depot_manifest, dict), "Expected dict for depot_manifest"
        
        print(f"   Items: {len(depot_manifest.get('depot', {}).get('items', []))}")
        
        # Save depot manifest
        save_raw_manifest(raw_depot, depot_manifest_id, 'depot', output_dir)
        save_debug_manifest(depot_manifest, depot_manifest_id, 'depot', output_dir)
        
        # Download patch chunks
        print(f"\n7. Downloading patch chunks for depot {depot_idx}/{len(matching_depots)}...")
        items = depot_manifest.get('depot', {}).get('items', [])
        
        if not items:
            print("   WARNING: No patch items found in this depot")
            continue
        
        total_chunks = sum(len(item.get('chunks', [])) for item in items)
        
        print(f"   Total items: {len(items)}")
        print(f"   Total chunks: {total_chunks}")
        
        if total_chunks == 0:
            print("   No chunks to download for this depot")
            continue
        
        # Collect all chunks to download
        chunk_tasks = []
        for item in items:
            file_path = item.get('path', 'unknown')
            for chunk in item.get('chunks', []):
                chunk_tasks.append({
                    'md5': chunk.get('compressedMd5'),
                    'size': chunk.get('compressedSize'),
                    'file_path': file_path
                })
        
        # Thread-safe counters
        stats = {'downloaded': 0, 'skipped': 0, 'failed': 0, 'completed': 0}
        stats_lock = Lock()
        
        def download_chunk_task(chunk_info):
            """Download a single patch chunk (thread-safe)."""
            chunk_md5 = chunk_info['md5']
            chunk_size = chunk_info['size']
            file_path = chunk_info['file_path']
            
            # Check if already exists
            depot_dir = output_dir / "depot" / "patches" / chunk_md5[:2] / chunk_md5[2:4]
            depot_file = depot_dir / chunk_md5
            
            if depot_file.exists():
                with stats_lock:
                    stats['skipped'] += 1
                return ('skipped', chunk_md5, file_path, chunk_size)
            
            try:
                chunk_file = download_patch_chunk(
                    api=api,
                    product_id=product_id,
                    chunk_md5=chunk_md5,
                    chunk_size=chunk_size,
                    client_id=client_id,
                    client_secret=client_secret,
                    base_dir=output_dir
                )
                
                with stats_lock:
                    stats['downloaded'] += 1
                return ('downloaded', chunk_md5, file_path, chunk_size)
                
            except Exception as e:
                with stats_lock:
                    stats['failed'] += 1
                return ('failed', chunk_md5, file_path, str(e))
        
        # Download chunks in parallel
        print(f"\n   Downloading with {num_workers} workers...")
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(download_chunk_task, chunk) for chunk in chunk_tasks]
            
            for future in as_completed(futures):
                result = future.result()
                status = result[0]
                
                with stats_lock:
                    stats['completed'] += 1
                    current = stats['completed']
                
                if status == 'downloaded':
                    _, md5, path, size = result
                    print(f"   [{current}/{total_chunks}] ✓ Downloaded: {md5} ({size:,} bytes) - {path}")
                elif status == 'skipped':
                    _, md5, path, size = result
                    print(f"   [{current}/{total_chunks}] = Exists: {md5} ({size:,} bytes) - {path}")
                elif status == 'failed':
                    _, md5, path, error = result
                    print(f"   [{current}/{total_chunks}] ✗ Failed: {md5} - {error}")
        
        # Update cumulative stats
        all_stats['downloaded'] += stats['downloaded']
        all_stats['skipped'] += stats['skipped']
        all_stats['failed'] += stats['failed']
        
        print(f"\n   Depot {depot_idx} stats:")
        print(f"     Downloaded: {stats['downloaded']}")
        print(f"     Skipped: {stats['skipped']}")
        print(f"     Failed: {stats['failed']}")
    
    # Save summary
    print("\n8. Saving summary...")
    summary = {
        "product_id": product_id,
        "from_build_id": from_build_id,
        "to_build_id": to_build_id,
        "algorithm": root_manifest.get('algorithm'),
        "root_manifest_hash": root_hash,
        "depot_manifests": [d.get('manifest') for d in matching_depots],
        "total_depots": len(matching_depots),
        "total_chunks": all_stats['downloaded'] + all_stats['skipped'] + all_stats['failed'],
        "downloaded_chunks": all_stats['downloaded'],
        "skipped_chunks": all_stats['skipped'],
        "failed_chunks": all_stats['failed']
    }
    
    summary_file = output_dir / "patch_summary.json"
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    
    print(f"✓ Saved summary: {summary_file}")
    
    # Print directory tree
    print("\n" + "=" * 80)
    print("DOWNLOAD COMPLETE")
    print("=" * 80)
    print(f"\nDirectory structure:")
    print(f"  {output_dir}/")
    print(f"  ├── meta/")
    print(f"  │   ├── {root_hash[:2]}/{root_hash[2:4]}/{root_hash} (root manifest, zlib)")
    for depot in matching_depots:
        depot_hash = depot.get('manifest')
        print(f"  │   ├── {depot_hash[:2]}/{depot_hash[2:4]}/{depot_hash} (depot manifest, zlib)")
    print(f"  ├── debug/")
    print(f"  │   ├── {root_hash}_root.json")
    for depot in matching_depots:
        depot_hash = depot.get('manifest')
        print(f"  │   ├── {depot_hash}_depot.json")
    print(f"  ├── depot/patches/")
    print(f"  │   └── [chunk folders with patch deltas]")
    print(f"  └── patch_summary.json")
    
    print(f"\nStatistics:")
    print(f"  Total depots: {len(matching_depots)}")
    print(f"  Downloaded: {all_stats['downloaded']}")
    print(f"  Skipped: {all_stats['skipped']}")
    print(f"  Failed: {all_stats['failed']}")
    
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Download GOG Galaxy patches between two builds",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("product_id", help="GOG product ID")
    parser.add_argument("from_build_id", help="Source build ID")
    parser.add_argument("to_build_id", help="Target build ID")
    parser.add_argument("output_dir", nargs="?", default="patches",
                       help="Output directory (default: patches)")
    parser.add_argument("--workers", type=int, default=8,
                       help="Number of parallel download workers (default: 8)")
    parser.add_argument("--language", type=str, default=None,
                       help="Language filter (e.g., 'en', 'de', 'fr'). If not specified, downloads all languages.")
    
    args = parser.parse_args()
    
    exit(main(
        product_id=args.product_id,
        from_build_id=args.from_build_id,
        to_build_id=args.to_build_id,
        output_dir=Path(args.output_dir),
        num_workers=args.workers,
        language=args.language
    ))
