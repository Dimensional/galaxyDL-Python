#!/usr/bin/env python3
"""
Archive Game - Complete 1:1 CDN Mirror

Downloads all content from GOG Galaxy CDN in original format:
- Depot/repository JSONs (zlib compressed)
- Manifest JSONs (as received)
- All chunks/blobs (compressed)

NOTE: A single build may contain multiple products (base game + DLC + toolkits).
      Chunks are organized by product_id to prevent MD5 collisions between products.
      Example: Cyberpunk 2077 includes base game (1423049311), REDMod (1597316373), 
               and other components in one depot.

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
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
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


def archive_v2_build(downloader: GalaxyDownloader, game_id: str, repository_id: str, game_name: str, num_workers: int = 8, dry_run: bool = False):
    """Archive V2 build mirroring CDN structure.
    
    Args:
        repository_id: The depot/repository hash (e.g., e518c17d90805e8e3998a35fac8b8505)
        num_workers: Number of parallel download threads (default: 8)
        dry_run: If True, download manifests only, skip chunks (default: False)
    """
    print(f"\n=== Archiving V2 Build ===")
    if dry_run:
        print(f"[DRY RUN MODE - Manifests only, no chunks]")
    print(f"Game: {os.path.join(game_name, game_id)}")
    print(f"Repository: {repository_id}")
    print(f"Workers: {num_workers}")
    
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
    
    depot_url = downloader.api.get_depot_url(repository_id)
    print(f"   URL: {depot_url}")
    downloader.download_raw_depot(repository_id, depot_path)
    
    with open(depot_path, 'rb') as f:
        depot_json = decompress_if_needed(f.read())
    
    # Extract platform from depot metadata
    platform = depot_json.get('platform', 'unknown')
    print(f"   Platform: {platform}")
    
    # Save human-readable JSON to debug folder
    debug_depot_path = os.path.join(debug_dir, f"{repository_id}_depot.json")
    with open(debug_depot_path, 'w') as f:
        json.dump(depot_json, f, indent=2)
    
    print(f"   ✓ {depot_path}")
    print(f"   ✓ {debug_depot_path}")
    
    # 2. Download all manifests: v2/meta/79/a1/79a1f5fd...
    manifest_count = len(depot_json['depots'])
    
    print(f"\n[2/3] Downloading {manifest_count} manifest(s)...")
    
    # Note: offlineDepot is intentionally skipped
    # It contains metadata (e.g., project.json) that is not available via CDN store paths
    # Neither lgogdownloader nor heroic-gogdl download offlineDepot content
    if 'offlineDepot' in depot_json:
        offline_depot = depot_json['offlineDepot']
        manifest_id = offline_depot['manifest']
        
        print(f"   ℹ Skipping offlineDepot manifest {manifest_id} (metadata not available via CDN)")
        
        # Still save the manifest JSON for reference
        manifest_dir = os.path.join(base_dir, "meta", manifest_id[:2], manifest_id[2:4])
        os.makedirs(manifest_dir, exist_ok=True)
        manifest_path = os.path.join(manifest_dir, manifest_id)
        
        manifest_url = downloader.api.get_manifest_url(manifest_id, generation=2)
        print(f"   URL: {manifest_url}")
        try:
            downloader.download_raw_manifest(manifest_id, manifest_path, generation=2)
            
            with open(manifest_path, 'rb') as f:
                manifest_json = decompress_if_needed(f.read())
            
            # Save human-readable JSON to debug folder
            debug_manifest_path = os.path.join(debug_dir, f"{manifest_id}_offlineDepot_manifest.json")
            with open(debug_manifest_path, 'w') as f:
                json.dump(manifest_json, f, indent=2)
            
            print(f"   ✓ Saved offlineDepot manifest (chunks not downloadable)")
        except Exception as e:
            print(f"   ⚠ Could not download offlineDepot manifest: {e}")
    
    # Organize chunks by product_id to download all instances
    # Format: {product_id: {md5: chunk_data}}
    chunks_by_product = {}
    
    # Process regular depots
    for depot in depot_json['depots']:
        manifest_id = depot['manifest']
        depot_product_id = depot.get('productId', game_id)  # Get depot's product ID
        
        manifest_dir = os.path.join(base_dir, "meta", manifest_id[:2], manifest_id[2:4])
        os.makedirs(manifest_dir, exist_ok=True)
        manifest_path = os.path.join(manifest_dir, manifest_id)
        
        manifest_url = downloader.api.get_manifest_url(manifest_id, generation=2)
        print(f"   URL: {manifest_url}")
        downloader.download_raw_manifest(manifest_id, manifest_path, generation=2)
        
        with open(manifest_path, 'rb') as f:
            manifest_json = decompress_if_needed(f.read())
        
        # Save human-readable JSON to debug folder
        debug_manifest_path = os.path.join(debug_dir, f"{manifest_id}_manifest.json")
        with open(debug_manifest_path, 'w') as f:
            json.dump(manifest_json, f, indent=2)
        
        # Initialize product_id dict if not exists
        if depot_product_id not in chunks_by_product:
            chunks_by_product[depot_product_id] = {}
        
        product_chunks = chunks_by_product[depot_product_id]
        
        # Collect chunks from smallFilesContainer first (if present)
        # These are the primary source for small files
        if 'smallFilesContainer' in manifest_json['depot']:
            sfc = manifest_json['depot']['smallFilesContainer']
            for chunk in sfc.get('chunks', []):
                if chunk['compressedMd5'] not in product_chunks:
                    product_chunks[chunk['compressedMd5']] = {
                        'chunk': chunk,
                        'product_id': depot_product_id,
                        'is_sfc': True
                    }
        
        # Collect chunks from depot items
        # For items with sfcRef, we collect their chunks opportunistically
        # (they may or may not exist on CDN - SFC is the guaranteed source)
        for item in manifest_json['depot']['items']:
            if item['type'] == 'DepotFile':
                has_sfc_ref = 'sfcRef' in item
                for chunk in item.get('chunks', []):
                    if chunk['compressedMd5'] not in product_chunks:
                        product_chunks[chunk['compressedMd5']] = {
                            'chunk': chunk,
                            'product_id': depot_product_id,
                            'is_sfc': False,
                            'has_sfc_fallback': has_sfc_ref  # CDN chunk may not exist; SFC has the file
                        }
        
        print(f"   ✓ {manifest_path}")
        print(f"   ✓ {debug_manifest_path}")
    
    # 3. Download chunks organized by product_id
    print(f"\n[3/3] Downloading chunks (organized by product_id)...")
    print(f"   Products found: {len(chunks_by_product)}")
    for product_id in chunks_by_product:
        print(f"     - {product_id}: {len(chunks_by_product[product_id])} chunks")
    
    if dry_run:
        total_chunks = sum(len(chunks) for chunks in chunks_by_product.values())
        total_size = sum(
            c['chunk']['compressedSize'] 
            for chunks in chunks_by_product.values() 
            for c in chunks.values()
        )
        print(f"   [DRY RUN] Would download {total_chunks} total chunks ({total_size/1024/1024:.2f} MB)")
        print(f"\n✓ Dry run complete: manifests downloaded, chunks skipped")
        print(f"\n✓ Complete: {base_dir}")
        return
    
    # Process each product_id sequentially
    for product_idx, (product_id, product_chunks) in enumerate(chunks_by_product.items(), 1):
        print(f"\n--- Product {product_idx}/{len(chunks_by_product)}: {product_id} ---")
        
        total_size = sum(c['chunk']['compressedSize'] for c in product_chunks.values())
        print(f"   Chunks: {len(product_chunks)}")
        print(f"   Total size: {total_size:,} bytes ({total_size/1024/1024:.2f} MB)")
        
        # Separate chunks by type for this product
        sfc_chunks = [(md5, data) for md5, data in product_chunks.items() if data.get('is_sfc', False)]
        regular_chunks = [(md5, data) for md5, data in product_chunks.items() if not data.get('is_sfc', False) and not data.get('has_sfc_fallback', False)]
        sfc_fallback_chunks = [(md5, data) for md5, data in product_chunks.items() if data.get('has_sfc_fallback', False)]
        
        print(f"   SFC: {len(sfc_chunks)}, Regular: {len(regular_chunks)}, SFC-fallback: {len(sfc_fallback_chunks)}")
        
        # Thread-safe stats for this product
        stats = {'downloaded': 0, 'skipped': 0, 'failed': 0}
        stats_lock = Lock()
        
        def download_chunk(chunk_task):
            """Download a single chunk (thread-safe) with retry logic."""
            md5, chunk_data = chunk_task
            chunk_info = chunk_data['chunk']
            product_id = chunk_data['product_id']
            has_sfc_fallback = chunk_data.get('has_sfc_fallback', False)
            chunk_type = "SFC" if chunk_data.get('is_sfc') else ("SFC-fallback" if has_sfc_fallback else "Regular")
            
            # Define paths but don't create directories yet
            chunk_dir = os.path.join(base_dir, "store", product_id, md5[:2], md5[2:4])
            chunk_path = os.path.join(chunk_dir, md5)
            
            if os.path.exists(chunk_path):
                with stats_lock:
                    stats['skipped'] += 1
                return ('skipped', md5, chunk_type)
            
            # Retry logic for transient network errors
            max_retries = 3
            retry_delay = 1  # seconds
            last_error = None
            
            for attempt in range(max_retries):
                try:
                    # Download chunk data (doesn't create files)
                    chunk_bytes = downloader.download_raw_chunk(
                        md5, 
                        product_id=product_id,
                        size_compressed=chunk_info['compressedSize']
                    )
                    
                    # Only create directory and write file after successful download
                    os.makedirs(chunk_dir, exist_ok=True)
                    with open(chunk_path, 'wb') as f:
                        f.write(chunk_bytes)
                    
                    with stats_lock:
                        stats['downloaded'] += 1
                    return ('downloaded', chunk_path, chunk_type)
                    
                except (ConnectionResetError, ConnectionAbortedError, 
                        ConnectionError, TimeoutError, OSError) as e:
                    # Check if it's a connection-related OSError (e.g., errno 10054 on Windows)
                    if isinstance(e, OSError) and e.errno not in [10053, 10054, 104]:
                        # Not a connection termination error, don't retry
                        last_error = e
                        break
                        
                    last_error = e
                    # Transient network errors - retry
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                    # Final attempt failed - fall through to error handling below
                        
                except Exception as e:
                    # Non-retryable errors (HTTP 404, 403, etc.)
                    last_error = e
                    break  # Don't retry for non-network errors
            
            # If we get here, all retries failed or we hit a non-retryable error
            if has_sfc_fallback:
                with stats_lock:
                    stats['skipped'] += 1
                return ('sfc_fallback', md5, None)
            else:
                error_msg = f"product {product_id} - {last_error}"
                if isinstance(last_error, (ConnectionResetError, ConnectionAbortedError, ConnectionError, TimeoutError)):
                    error_msg += f" (after {max_retries} attempts)"
                with stats_lock:
                    stats['failed'] += 1
                return ('failed', md5, error_msg)
        
        # Download chunks in parallel for this product
        all_chunk_tasks = sfc_chunks + regular_chunks + sfc_fallback_chunks
        
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(download_chunk, task) for task in all_chunk_tasks]
            
            completed = 0
            for future in as_completed(futures):
                result = future.result()
                status, identifier, extra = result
                
                completed += 1
                
                if status == 'downloaded':
                    print(f"   [{completed}/{len(all_chunk_tasks)}] Downloaded: {identifier} ({extra})")
                elif status == 'skipped':
                    print(f"   [{completed}/{len(all_chunk_tasks)}] Exists: {identifier} ({extra})")
                elif status == 'sfc_fallback':
                    print(f"   [{completed}/{len(all_chunk_tasks)}] Not on CDN: {identifier} (file in SFC)")
                elif status == 'failed':
                    print(f"   [{completed}/{len(all_chunk_tasks)}] FAILED: {identifier} ({extra})")
        
        print(f"   Product {product_id}: Downloaded {stats['downloaded']}, Skipped {stats['skipped']}, Failed {stats['failed']}")
    
    print(f"\n✓ All products complete!")
    print(f"\n✓ Archive location: {base_dir}")



def archive_v1_build(downloader: GalaxyDownloader, game_id: str, repository_id: str, game_name: str, platform: str = None, num_workers: int = 8, dry_run: bool = False):
    """Archive V1 build mirroring CDN structure.
    
    Args:
        repository_id: The repository timestamp (e.g., 37794096)
        platform: Platform (windows/osx/linux) - if None, will try to auto-detect
        num_workers: Number of parallel download workers (default: 8)
        dry_run: If True, download manifests only, skip main.bin (default: False)
    """
    print(f"\n=== Archiving V1 Build ===")
    if dry_run:
        print(f"[DRY RUN MODE - Manifests only, no main.bin]")
    print(f"Game: {os.path.join(game_name, game_id)}")
    print(f"Repository: {repository_id}")
    
    # If platform not provided, try all platforms to find which one has this repository
    if platform is None:
        print("\nAuto-detecting platform...")
        for test_platform in ['windows', 'osx', 'linux']:
            test_base_dir = os.path.join(game_name, "v1", "manifests", game_id, test_platform, repository_id)
            test_repo_path = os.path.join(test_base_dir, "repository.json")
            try:
                # Try to download repository.json to test if it exists
                os.makedirs(test_base_dir, exist_ok=True)
                downloader.download_raw_repository(game_id, test_platform, repository_id, test_repo_path)
                # If successful, we found the platform
                platform = test_platform
                print(f"   ✓ Platform detected: {platform}")
                # Parse the repository JSON to confirm
                with open(test_repo_path, 'rb') as f:
                    repo_json = decompress_if_needed(f.read())
                systems = repo_json.get('product', {}).get('depots', [{}])[0].get('systems', [])
                if systems:
                    print(f"   ✓ Confirmed from depot systems: {systems}")
                break
            except Exception:
                # Clean up failed attempt
                if os.path.exists(test_repo_path):
                    os.remove(test_repo_path)
                continue
        
        if platform is None:
            raise ValueError(f"Could not auto-detect platform for repository {repository_id}. Please specify --platform.")
    
    print(f"Platform: {platform}")
    
    # Base: <game_name>/v1/manifests/{game_id}/{platform}/{timestamp}/
    base_dir = os.path.join(game_name, "v1", "manifests", game_id, platform, repository_id)
    os.makedirs(base_dir, exist_ok=True)
    
    # 1. Download repository.json
    print("\n[1/2] Downloading repository metadata...")
    repo_path = os.path.join(base_dir, "repository.json")
    repo_url = downloader.api.get_repository_url(game_id, platform, repository_id)
    print(f"   URL: {repo_url}")
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
        manifest_url = downloader.api.get_manifest_url(manifest_id, game_id=game_id, platform=platform, timestamp=repository_id, generation=1)
        print(f"   URL: {manifest_url}")
        downloader.download_raw_manifest(manifest_id, manifest_path, generation=1,
                                        game_id=game_id, platform=platform, timestamp=repository_id)
        print(f"   ✓ {manifest_path}")
    
    # 3. Download main.bin using authenticated secure links with parallel downloads
    # V1 depots use different path: v1/depots/{game_id}/{platform}/{timestamp}/main.bin
    if dry_run:
        print("\n[3/3] Skipping main.bin download (dry run)")
        print(f"   [DRY RUN] Would download main.bin to: v1/depots/{game_id}/{platform}/{repository_id}/main.bin")
        print(f"\n✓ Dry run complete: manifests downloaded, main.bin skipped")
    else:
        print("\n[3/3] Downloading main.bin (depot) with parallel downloads...")
        depot_dir = os.path.join(game_name, "v1", "depots", game_id, platform, repository_id)
        os.makedirs(depot_dir, exist_ok=True)
        main_bin_path = os.path.join(depot_dir, "main.bin")
        
        try:
            # Get and display secure link
            endpoints = downloader.api.get_secure_link(game_id, "/", generation=1, return_full_response=True)
            if endpoints:
                endpoint = endpoints[0]
                params = endpoint["parameters"].copy()
                secure_url = downloader.api._merge_url_with_params(endpoint["url_format"], params)
                print(f"   Secure URL: {secure_url}")
            
            # Use parallel workers for faster downloads (50 MiB chunks each)
            downloader.download_main_bin(game_id, platform, repository_id, main_bin_path, num_workers=num_workers)
            print(f"   ✓ {main_bin_path}")
        except Exception as e:
            print(f"   ✗ Failed to download main.bin: {e}")
            print("   Note: main.bin requires authentication - ensure you're logged in")
        
        print(f"\n✓ Depot: {depot_dir}")
    
    print(f"\n✓ Manifests: {base_dir}")


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
    parser.add_argument("--platform",
                       choices=["windows", "osx", "linux"],
                       help="Platform (required for --build-id and V1 --repository-id; auto-detected for V2 --repository-id)")
    parser.add_argument("--workers", type=int, default=8,
                       help="Number of parallel download workers (default: 8)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Download manifests only, skip chunks/main.bin")
    
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
        # Build ID lookup requires platform for API call
        if not args.platform:
            print("\nERROR: --platform is required when using --build-id")
            print("Tip: Use --repository-id instead to skip platform requirement for V2 builds")
            sys.exit(1)
        
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
        if args.build_type == "v2":
            print("   Platform will be auto-detected from depot metadata")
        elif not args.platform:
            print("   Platform will be auto-detected by testing all platforms")
    
    # Archive the build
    if args.build_type == "v2":
        archive_v2_build(downloader, args.game_id, repository_id, game_name, num_workers=args.workers, dry_run=args.dry_run)
    else:  # v1
        archive_v1_build(downloader, args.game_id, repository_id, game_name, args.platform, num_workers=args.workers, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
