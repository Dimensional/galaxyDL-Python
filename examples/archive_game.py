#!/usr/bin/env python3
"""
Archive Game - Complete 1:1 CDN Mirror

Downloads all content from GOG Galaxy CDN in original format:
- Depot/repository JSONs (zlib compressed)
- Manifest JSONs (as received)
- All chunks/blobs (compressed)

Usage:
    V2 (with build lookup):    python archive_game.py v2 <game_id> --build-id <build_id> [<game_name>] [--platform <windows|osx|linux>]
    V2 (direct repository):    python archive_game.py v2 <game_id> --repository-id <repo_hash> [<game_name>]
    
    V1 (with build lookup):    python archive_game.py v1 <game_id> --build-id <build_id> [<game_name>] [--platform <windows|osx|linux>]
    V1 (direct repository):    python archive_game.py v1 <game_id> --repository-id <timestamp> [<game_name>] [--platform <windows|osx|linux>]

Examples:
    # Current builds (look up from API)
    python archive_game.py v2 1207658930 --build-id 56452082907692588 "The Witcher 2"
    python archive_game.py v1 1207658930 --build-id 56452082907692588 "The Witcher 2" --platform windows
    
    # Delisted builds (use repository ID directly)
    python archive_game.py v2 1207658930 --repository-id e518c17d90805e8e3998a35fac8b8505 "The Witcher 2"
    python archive_game.py v1 1207658930 --repository-id 37794096 "The Witcher 2" --platform osx
"""

import os
import sys
import json
import zlib
import argparse
from galaxy_dl import GalaxyDownloader, constants
from galaxy_dl.auth import AuthManager
from galaxy_dl.api import GalaxyAPI


def decompress_if_needed(data: bytes) -> dict:
    """Try to decompress zlib, fall back to plain JSON."""
    try:
        return json.loads(zlib.decompress(data))
    except:
        return json.loads(data.decode('utf-8'))


def get_repository_from_build(api: GalaxyAPI, game_id: str, build_id: str, platform: str, generation: int) -> str:
    """
    Look up a build in the API and extract the repository ID/hash.
    
    Args:
        api: Galaxy API instance
        game_id: Product ID
        build_id: Build ID to look up
        platform: Platform (windows, osx, linux)
        generation: 1 for V1, 2 for V2
    
    Returns:
        Repository ID (V1: timestamp string, V2: hash from link URL)
    
    Raises:
        ValueError: If build not found or missing expected fields
    """
    print(f"\nLooking up build {build_id} in API...")
    
    # Query the appropriate generation endpoint
    gen_str = str(generation)
    builds = api.get_product_builds(game_id, platform, gen_str)
    
    if not builds.get('items'):
        raise ValueError(f"No builds found for product {game_id} (platform: {platform})")
    
    # Find the matching build
    matching_build = None
    for build in builds['items']:
        if build.get('build_id') == build_id:
            matching_build = build
            break
    
    if not matching_build:
        raise ValueError(
            f"Build {build_id} not found in API results.\n"
            f"If this is a delisted build, use --repository-id instead of --build-id"
        )
    
    print(f"  ✓ Found build: {matching_build.get('version_name', 'Unknown version')}")
    
    # Extract repository ID based on generation
    if generation == 2:
        # V2: Extract hash from link URL
        link = matching_build.get('link')
        if not link:
            raise ValueError(f"Build {build_id} missing 'link' field")
        
        # Extract hash from URL: .../v2/meta/e5/18/e518c17d90805e8e3998a35fac8b8505
        repo_hash = link.split('/')[-1]
        print(f"  ✓ Repository hash: {repo_hash}")
        return repo_hash
    
    else:  # generation == 1
        # V1: Use legacy_build_id (repository timestamp)
        repo_id = matching_build.get('legacy_build_id')
        if not repo_id:
            raise ValueError(f"Build {build_id} missing 'legacy_build_id' field")
        
        print(f"  ✓ Repository ID: {repo_id}")
        return str(repo_id)


def archive_v2_build(downloader: GalaxyDownloader, game_id: str, repository_id: str, game_name: str):
    """Archive V2 build mirroring CDN structure.
    
    Args:
        repository_id: The depot/repository hash (e.g., e518c17d90805e8e3998a35fac8b8505)
    """
    """Archive V2 build mirroring CDN structure.
    
    Args:
        repository_id: The depot/repository hash (e.g., e518c17d90805e8e3998a35fac8b8505)
    """
    print(f"\n=== Archiving V2 Build ===")
    print(f"Game: {game_name} ({game_id})")
    print(f"Repository: {repository_id}")
    
    # Base: <game_name>/v2/
    base_dir = os.path.join(game_name, "v2")
    debug_dir = os.path.join(base_dir, "debug")
    os.makedirs(base_dir, exist_ok=True)
    os.makedirs(debug_dir, exist_ok=True)
    
    # 1. Download depot: v2/meta/92/ab/92ab42631ff4742b309bb62c175e6306
    print("\n[1/3] Downloading depot metadata...")
    depot_dir = os.path.join(base_dir, "meta", repository_id[:2], repository_id[2:4])
    os.makedirs(depot_dir, exist_ok=True)
    depot_path = os.path.join(depot_dir, repository_id)
    
    downloader.download_raw_depot(repository_id, depot_path)
    
    with open(depot_path, 'rb') as f:
        depot_json = decompress_if_needed(f.read())
    
    # Save human-readable JSON to debug folder
    debug_depot_path = os.path.join(debug_dir, f"{repository_id}_depot.json")
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
            downloader.download_raw_chunk(md5, chunk_path, product_id=game_id)
            print(f"   [{i}/{len(all_chunks)}] Downloaded: {chunk_path}")
    
    print(f"\n✓ Complete: {base_dir}")



def archive_v1_build(downloader: GalaxyDownloader, game_id: str, repository_id: str, game_name: str, platform: str = "windows"):
    """Archive V1 build mirroring CDN structure.
    
    Args:
        repository_id: The repository timestamp (e.g., 37794096)
    """
    print(f"\n=== Archiving V1 Build ===")
    print(f"Game: {game_name} ({game_id})")
    print(f"Platform: {platform}")
    print(f"Repository: {repository_id}")
    
    # Base: <game_name>/v1/manifests/{game_id}/{platform}/{timestamp}/
    base_dir = os.path.join(game_name, "v1", "manifests", game_id, platform, repository_id)
    os.makedirs(base_dir, exist_ok=True)
    
    # 1. Download repository.json
    print("\n[1/2] Downloading repository metadata...")
    repo_path = os.path.join(base_dir, "repository.json")
    downloader.download_raw_repository(game_id, platform, repository_id, repo_path)
    
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
                                        game_id=game_id, platform=platform, timestamp=repository_id)
        print(f"   ✓ {manifest_path}")
    
    # 3. Download main.bin using authenticated secure links with parallel downloads
    # V1 depots use different path: v1/depots/{game_id}/{platform}/{timestamp}/main.bin
    print("\n[3/3] Downloading main.bin (depot) with parallel downloads...")
    depot_dir = os.path.join(game_name, "v1", "depots", game_id, platform, repository_id)
    os.makedirs(depot_dir, exist_ok=True)
    main_bin_path = os.path.join(depot_dir, "main.bin")
    
    try:
        # Use 4 parallel workers for faster downloads (50 MiB chunks each)
        downloader.download_main_bin(game_id, platform, repository_id, main_bin_path, num_workers=4)
        print(f"   ✓ {main_bin_path}")
    except Exception as e:
        print(f"   ✗ Failed to download main.bin: {e}")
        print("   Note: main.bin requires authentication - ensure you're logged in")
    
    print(f"\n✓ Manifests: {base_dir}")
    print(f"✓ Depot: {depot_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Archive GOG Galaxy game builds in CDN mirror structure",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Current builds (look up from API)
  %(prog)s v2 1207658930 --build-id 56452082907692588 "The Witcher 2"
  %(prog)s v1 1207658930 --build-id 56452082907692588 "The Witcher 2" --platform windows
  
  # Delisted builds (use repository ID directly)
  %(prog)s v2 1207658930 --repository-id e518c17d90805e8e3998a35fac8b8505 "The Witcher 2"
  %(prog)s v1 1207658930 --repository-id 37794096 "The Witcher 2" --platform osx
"""
    )
    
    parser.add_argument("build_type", choices=["v1", "v2"], 
                       help="Build type (V1 or V2)")
    parser.add_argument("game_id", help="GOG product ID")
    
    # Mutually exclusive group for build lookup vs direct repository ID
    id_group = parser.add_mutually_exclusive_group(required=True)
    id_group.add_argument("--build-id", metavar="BUILD_ID",
                         help="Build ID to look up in API (for current builds)")
    id_group.add_argument("--repository-id", metavar="REPO_ID",
                         help="Repository ID/hash to use directly (for delisted builds)")
    
    parser.add_argument("game_name", nargs="?", 
                       help="Game name for directory structure (default: game_<id>)")
    parser.add_argument("--platform", default="windows",
                       choices=["windows", "osx", "linux"],
                       help="Platform (default: windows)")
    
    args = parser.parse_args()
    
    # Determine game name
    game_name = args.game_name if args.game_name else f"game_{args.game_id}"
    
    # Initialize API
    print("Initializing...")
    auth = AuthManager()
    api = GalaxyAPI(auth)
    downloader = GalaxyDownloader(api)
    
    # Determine repository ID
    if args.build_id:
        # Look up build in API to get repository ID
        generation = 2 if args.build_type == "v2" else 1
        try:
            repository_id = get_repository_from_build(
                api, args.game_id, args.build_id, args.platform, generation
            )
        except ValueError as e:
            print(f"\nERROR: {e}")
            sys.exit(1)
    else:
        # Use repository ID directly
        repository_id = args.repository_id
        print(f"\nUsing repository ID directly: {repository_id}")
    
    # Archive the build
    if args.build_type == "v2":
        archive_v2_build(downloader, args.game_id, repository_id, game_name)
    else:  # v1
        archive_v1_build(downloader, args.game_id, repository_id, game_name, args.platform)


if __name__ == "__main__":
    main()
