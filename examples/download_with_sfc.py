#!/usr/bin/env python3
"""
Example: Download game with SFC support

Demonstrates downloading a game using the new SFC (Small Files Container) support.
This will automatically:
1. Download the SFC container
2. Extract license/metadata files from it
3. Download regular game files
4. Optionally delete the SFC after extraction
"""

import os
import sys
from galaxy_dl import GalaxyDownloader
from galaxy_dl.auth import AuthManager


def main():
    # Initialize
    print("Initializing...")
    auth = AuthManager()
    if not auth.is_authenticated():
        print("Not authenticated. Please run authentication first.")
        sys.exit(1)
    
    downloader = GalaxyDownloader(auth.get_auth_token())
    
    # Example: Download DREDGE build
    game_id = "1744110647"  # DREDGE
    build_id = "59047276156524906"
    platform = "windows"
    
    # Get build info
    api = downloader.api
    builds = api.get_product_builds(game_id, platform, "2")
    
    build = None
    for b in builds.get('items', []):
        if b.get('build_id') == build_id:
            build = b
            break
    
    if not build:
        print(f"Build {build_id} not found")
        sys.exit(1)
    
    # Get repository hash from build link
    depot_hash = build['link'].split('/')[-1]
    print(f"Depot hash: {depot_hash}")
    
    # Get depot metadata
    depot_json = api.get_depot_v2(depot_hash)
    
    # Process first manifest as example
    first_depot = depot_json['depots'][0]
    manifest_hash = first_depot['manifest']
    product_id = first_depot['productId']
    
    print(f"\nDownloading manifest: {manifest_hash}")
    items = api.get_depot_items(manifest_hash, is_dependency=False)
    
    # Set product IDs
    for item in items:
        item.product_id = product_id
    
    # Show what will be downloaded
    print(f"\nFound {len(items)} items:")
    sfc_count = sum(1 for item in items if item.is_small_files_container)
    in_sfc_count = sum(1 for item in items if item.is_in_sfc)
    regular_count = len(items) - sfc_count - in_sfc_count
    
    print(f"  - {sfc_count} SFC containers")
    print(f"  - {in_sfc_count} files in SFC")
    print(f"  - {regular_count} regular files")
    
    # Download to output directory
    output_dir = os.path.join("downloads", game_id, depot_hash)
    print(f"\nDownloading to: {output_dir}")
    
    results = downloader.download_depot_items(
        items,
        output_dir,
        verify_hash=True,
        delete_sfc_after_extraction=True  # Delete SFC after extracting files
    )
    
    # Show results
    successful = sum(1 for path in results.values() if path is not None)
    print(f"\nCompleted: {successful}/{len(results)} files downloaded")
    
    # Show extracted files
    extracted_files = [path for item in items if item.is_in_sfc 
                      for path in [results.get(item.path)] if path]
    if extracted_files:
        print(f"\nExtracted from SFC:")
        for path in extracted_files:
            print(f"  - {path}")


if __name__ == "__main__":
    main()
