#!/usr/bin/env python3
"""
Archive Game - Complete 1:1 CDN Mirror

Downloads all content from GOG Galaxy CDN in original format:
- Depot/repository JSONs (zlib compressed)
- Manifest JSONs (as received)
- All chunks/blobs (compressed)

Usage:
    V2: python archive_game.py v2 <game_id> <build_id>
    V1: python archive_game.py v1 <game_id> <repository_id>

Example:
    python archive_game.py v2 1207658930 92ab42631ff4742b309bb62c175e6306
"""

import os
import sys
import json
import zlib
from galaxy_dl import GalaxyDownloader, constants
from galaxy_dl.auth import AuthManager
from galaxy_dl.api import GalaxyAPI


def decompress_if_needed(data: bytes) -> dict:
    """Try to decompress zlib, fall back to plain JSON."""
    try:
        return json.loads(zlib.decompress(data))
    except:
        return json.loads(data.decode('utf-8'))


def archive_v2_build(downloader: GalaxyDownloader, game_id: str, build_id: str, game_name: str):
    """Archive V2 build mirroring CDN structure."""
    print(f"\n=== Archiving V2 Build ===")
    print(f"Game: {game_name} ({game_id})")
    print(f"Build: {build_id}")
    
    # Base: <game_name>/v2/
    base_dir = os.path.join(game_name, "v2")
    debug_dir = os.path.join(base_dir, "debug")
    os.makedirs(base_dir, exist_ok=True)
    os.makedirs(debug_dir, exist_ok=True)
    
    # 1. Download depot: v2/meta/92/ab/92ab42631ff4742b309bb62c175e6306
    print("\n[1/3] Downloading depot metadata...")
    depot_dir = os.path.join(base_dir, "meta", build_id[:2], build_id[2:4])
    os.makedirs(depot_dir, exist_ok=True)
    depot_path = os.path.join(depot_dir, build_id)
    
    downloader.download_raw_depot(build_id, depot_path)
    
    with open(depot_path, 'rb') as f:
        depot_json = decompress_if_needed(f.read())
    
    # Save human-readable JSON to debug folder
    debug_depot_path = os.path.join(debug_dir, f"{build_id}_depot.json")
    with open(debug_depot_path, 'w') as f:
        json.dump(depot_json, f, indent=2)
    
    print(f"   ✓ {depot_path}")
    print(f"   ✓ {debug_depot_path}")
    
    # 2. Download all manifests: v2/meta/79/a1/79a1f5fd...
    print(f"\n[2/3] Downloading {len(depot_json['depots'])} manifest(s)...")
    
    all_chunks = {}
    for depot in depot_json['depots']:
        manifest_id = depot['manifest']
        manifest_dir = os.path.join(base_dir, "meta", manifest_id[:2], manifest_id[2:4])
        os.makedirs(manifest_dir, exist_ok=True)
        manifest_path = os.path.join(manifest_dir, manifest_id)
        
        downloader.download_raw_manifest(manifest_id, manifest_path, generation=2)
        
        with open(manifest_path, 'rb') as f:
            manifest_json = decompress_if_needed(f.read())
        
        # Save human-readable JSON to debug folder
        debug_manifest_path = os.path.join(debug_dir, f"{manifest_id}_manifest.json")
        with open(debug_manifest_path, 'w') as f:
            json.dump(manifest_json, f, indent=2)
        
        # Collect chunks
        for item in manifest_json['depot']['items']:
            if item['type'] == 'DepotFile':
                for chunk in item.get('chunks', []):
                    all_chunks[chunk['compressedMd5']] = chunk
        
        print(f"   ✓ {manifest_path}")
        print(f"   ✓ {debug_manifest_path}")
    
    # 3. Download all chunks: v2/store/2e/0d/2e0dc2f5...
    print(f"\n[3/3] Downloading {len(all_chunks)} unique chunks...")
    
    total_size = sum(c['compressedSize'] for c in all_chunks.values())
    print(f"   Total: {total_size:,} bytes ({total_size/1024/1024:.2f} MB)")
    
    for i, (md5, chunk_info) in enumerate(all_chunks.items(), 1):
        chunk_dir = os.path.join(base_dir, "store", md5[:2], md5[2:4])
        os.makedirs(chunk_dir, exist_ok=True)
        chunk_path = os.path.join(chunk_dir, md5)
        
        if os.path.exists(chunk_path):
            print(f"   [{i}/{len(all_chunks)}] Exists: {md5}")
        else:
            downloader.download_raw_chunk(md5, chunk_path)
            print(f"   [{i}/{len(all_chunks)}] Downloaded: {chunk_path}")
    
    print(f"\n✓ Complete: {base_dir}")



def archive_v1_build(downloader: GalaxyDownloader, game_id: str, timestamp: str, game_name: str, platform: str = "windows"):
    """Archive V1 build mirroring CDN structure."""
    print(f"\n=== Archiving V1 Build ===")
    print(f"Game: {game_name} ({game_id})")
    print(f"Timestamp: {timestamp}")
    
    # Base: <game_name>/v1/manifests/{game_id}/{platform}/{timestamp}/
    base_dir = os.path.join(game_name, "v1", "manifests", game_id, platform, timestamp)
    os.makedirs(base_dir, exist_ok=True)
    
    # 1. Download repository.json
    print("\n[1/2] Downloading repository metadata...")
    repo_path = os.path.join(base_dir, "repository.json")
    downloader.download_raw_repository(game_id, platform, timestamp, repo_path)
    
    with open(repo_path, 'rb') as f:
        repo_json = decompress_if_needed(f.read())
    
    print(f"   ✓ {repo_path}")
    
    # 2. Download manifests from depot list
    print("\n[2/3] Downloading manifest files...")
    
    for depot in repo_json.get('product', {}).get('depots', []):
        manifest_id = depot.get('manifest')
        if not manifest_id:
            continue
        
        manifest_path = os.path.join(base_dir, manifest_id)
        
        # V1 manifests are plain JSON at: v1/manifests/{game_id}/{platform}/{timestamp}/{manifest_id}
        downloader.download_raw_manifest(manifest_id, manifest_path, generation=1,
                                        game_id=game_id, platform=platform, timestamp=timestamp)
        print(f"   ✓ {manifest_path}")
    
    # 3. Download main.bin using authenticated secure links with parallel downloads
    # V1 depots use different path: v1/depots/{game_id}/{platform}/{timestamp}/main.bin
    print("\n[3/3] Downloading main.bin (depot) with parallel downloads...")
    depot_dir = os.path.join(game_name, "v1", "depots", game_id, platform, timestamp)
    os.makedirs(depot_dir, exist_ok=True)
    main_bin_path = os.path.join(depot_dir, "main.bin")
    
    try:
        # Use 4 parallel workers for faster downloads (50 MiB chunks each)
        downloader.download_main_bin(game_id, platform, timestamp, main_bin_path, num_workers=4)
        print(f"   ✓ {main_bin_path}")
    except Exception as e:
        print(f"   ✗ Failed to download main.bin: {e}")
        print("   Note: main.bin requires authentication - ensure you're logged in")
    
    print(f"\n✓ Manifests: {base_dir}")
    print(f"✓ Depot: {depot_dir}")


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    
    build_type = sys.argv[1].lower()
    game_id = sys.argv[2]
    build_id = sys.argv[3]
    game_name = sys.argv[4] if len(sys.argv) > 4 else f"game_{game_id}"
    
    print("Initializing...")
    auth = AuthManager()
    downloader = GalaxyDownloader(GalaxyAPI(auth))
    
    if build_type == "v2":
        archive_v2_build(downloader, game_id, build_id, game_name)
    elif build_type == "v1":
        archive_v1_build(downloader, game_id, build_id, game_name)
    else:
        print(f"ERROR: Unknown type '{build_type}'. Use 'v1' or 'v2'.")
        sys.exit(1)


if __name__ == "__main__":
    main()
