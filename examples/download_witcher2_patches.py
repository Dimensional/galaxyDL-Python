"""
Download patches for The Witcher 2 between two builds

This example demonstrates:
1. Getting manifests for old and new builds
2. Querying GOG for patch availability
3. Downloading patch metadata
4. Downloading patch chunks (.delta files)
5. Saving patch information for later application

Builds used:
- Old: Build ID 49999910531550131 (Windows)
- New: Build ID 56452082907692588 (Windows)
"""

import os
import json
import hashlib
from pathlib import Path

from galaxy_dl import GalaxyAPI, AuthManager, Manifest, Patch


# Build information
PRODUCT_ID = "1207658930"  # The Witcher 2
PLATFORM = "windows"
OLD_BUILD = {
    "build_id": "49999910531550131",
    "repository_id": None,  # Will be fetched from builds API
    "published": "unknown"
}
NEW_BUILD = {
    "build_id": "56452082907692588",
    "repository_id": None,  # Will be fetched from builds API
    "published": "unknown"
}

# Directories
OUTPUT_DIR = Path("witcher2_patches")
PATCHES_DIR = OUTPUT_DIR / "patches"
METADATA_FILE = OUTPUT_DIR / "patch_manifest.json"


def main():
    """Main patch download workflow."""
    print("=" * 80)
    print("The Witcher 2: Patch Download Example")
    print("=" * 80)
    
    # Initialize API
    print("\n1. Initializing API...")
    auth = AuthManager()
    if not auth.is_authenticated():
        print("ERROR: Not authenticated. Run 'galaxy-dl login' first.")
        return 1
    
    api = GalaxyAPI(auth)
    print("✓ Authenticated")
    
    # Create output directories
    OUTPUT_DIR.mkdir(exist_ok=True)
    PATCHES_DIR.mkdir(exist_ok=True)
    
    # Get builds to find repository IDs
    print("\n2. Getting build information...")
    builds_data = api.get_all_product_builds(PRODUCT_ID, PLATFORM)
    
    if not builds_data or not builds_data.get("items"):
        print("ERROR: Failed to get builds")
        return 1
    
    builds = builds_data["items"]
    
    # Find our specific builds
    old_build_info = None
    new_build_info = None
    
    for build in builds:
        if build.get("build_id") == OLD_BUILD["build_id"]:
            old_build_info = build
        if build.get("build_id") == NEW_BUILD["build_id"]:
            new_build_info = build
    
    if not old_build_info:
        print(f"ERROR: Could not find old build {OLD_BUILD['build_id']} in builds list")
        print(f"Available builds: {[b.get('build_id') for b in builds[:5]]}")
        return 1
    
    if not new_build_info:
        print(f"ERROR: Could not find new build {NEW_BUILD['build_id']} in builds list")
        print(f"Available builds: {[b.get('build_id') for b in builds[:5]]}")
        return 1
    
    # For V2 builds, use the manifest link; for V1, use legacy_build_id
    old_generation = old_build_info.get("generation", 2)
    new_generation = new_build_info.get("generation", 2)
    
    OLD_BUILD["manifest_link"] = old_build_info.get("link")
    OLD_BUILD["repository_id"] = old_build_info.get("legacy_build_id")
    NEW_BUILD["manifest_link"] = new_build_info.get("link")
    NEW_BUILD["repository_id"] = new_build_info.get("legacy_build_id")
    
    print(f"✓ Old build: {OLD_BUILD['build_id']}")
    print(f"  Link: {OLD_BUILD['manifest_link']}")
    print(f"  Generation: {old_generation}")
    print(f"✓ New build: {NEW_BUILD['build_id']}")
    print(f"  Link: {NEW_BUILD['manifest_link']}")
    print(f"  Generation: {new_generation}")
    
    # Get manifests
    print("\n3. Downloading manifests...")
    print(f"   Old build: {OLD_BUILD['build_id']} ({OLD_BUILD['published']})")
    
    old_manifest = api.get_manifest_direct(
        product_id=PRODUCT_ID,
        manifest_link=OLD_BUILD["manifest_link"],
        repository_id=OLD_BUILD["repository_id"],
        generation=old_generation,
        build_id=OLD_BUILD["build_id"]  # Pass build_id!
    )
    
    if not old_manifest:
        print("ERROR: Failed to get old manifest")
        return 1
    
    print(f"   ✓ Old manifest: Generation {old_manifest.generation}, {len(old_manifest.items)} items")
    print(f"     Build ID: {old_manifest.build_id}")
    print(f"     Base Product ID: {old_manifest.base_product_id}")
    
    print(f"   New build: {NEW_BUILD['build_id']} ({NEW_BUILD['published']})")
    
    new_manifest = api.get_manifest_direct(
        product_id=PRODUCT_ID,
        manifest_link=NEW_BUILD["manifest_link"],
        repository_id=NEW_BUILD["repository_id"],
        generation=new_generation,
        build_id=NEW_BUILD["build_id"]  # Pass build_id!
    )
    
    if not new_manifest:
        print("ERROR: Failed to get new manifest")
        return 1
    
    print(f"   ✓ New manifest: Generation {new_manifest.generation}, {len(new_manifest.items)} items")
    print(f"     Build ID: {new_manifest.build_id}")
    print(f"     Base Product ID: {new_manifest.base_product_id}")
    
    # Check if both are V2 (required for patches)
    if old_manifest.generation != 2 or new_manifest.generation != 2:
        print(f"\nERROR: Patches only work for V2 builds")
        print(f"  Old: V{old_manifest.generation}, New: V{new_manifest.generation}")
        return 1
    
    # Query for patches
    print("\n3. Querying for patch availability...")
    print(f"   From: {OLD_BUILD['build_id']}")
    print(f"   To:   {NEW_BUILD['build_id']}")
    
    # Show the patch query URL
    patch_query_url = f"https://content-system.gog.com/products/{PRODUCT_ID}/patches?_version=4&from_build_id={OLD_BUILD['build_id']}&to_build_id={NEW_BUILD['build_id']}"
    print(f"\n   Patch query URL:")
    print(f"   {patch_query_url}")
    
    # First, manually check what the API returns
    print("\n   Checking patch availability...")
    patch_info = api.get_patch_info(PRODUCT_ID, OLD_BUILD['build_id'], NEW_BUILD['build_id'])
    print(f"   Raw patch_info response: {patch_info}")
    print(f"   Type: {type(patch_info)}")
    print(f"   Truthy: {bool(patch_info)}")
    
    if patch_info:
        print(f"   ✓ Patch info received:")
        for key, value in patch_info.items():
            print(f"     {key}: {value}")
        if 'error' in patch_info:
            print(f"\n✗ API returned error: {patch_info['error']}")
            return 0
        
        # Try to download the patch manifest directly
        patch_link = patch_info.get('link')
        if patch_link:
            print(f"\n   Downloading patch manifest from:")
            print(f"   {patch_link}")
            
            # Debug: Try to see what we're actually getting
            import requests
            response = requests.get(patch_link)
            print(f"   Response status: {response.status_code}")
            print(f"   Response size: {len(response.content)} bytes")
            print(f"   Response content (first 100 bytes): {response.content[:100]}")
            
            # Check if it's zlib compressed
            from galaxy_dl import utils
            is_compressed = utils.is_zlib_compressed(response.content)
            print(f"   Is zlib compressed: {is_compressed}")
            
            if is_compressed:
                import zlib
                from galaxy_dl import constants
                try:
                    decompressed = zlib.decompress(response.content, constants.ZLIB_WINDOW_SIZE)
                    print(f"   Decompressed size: {len(decompressed)} bytes")
                    print(f"   Decompressed content: {decompressed}")
                except Exception as e:
                    print(f"   Failed to decompress: {e}")
            
            patch_data = api.get_patch_manifest(patch_link)
            
            if not patch_data:
                print(f"   ✗ Failed to download/parse patch manifest!")
                return 0
            
            if patch_data:
                print(f"\n   Patch manifest (full JSON):")
                import json as json_module
                json_str = json_module.dumps(patch_data, indent=2)
                print(json_str)
                
                # Try downloading a depot patch manifest
                depots = patch_data.get('depots', [])
                en_depot = None
                for depot in depots:
                    if depot.get('productId') == PRODUCT_ID and 'en-US' in depot.get('languages', []):
                        en_depot = depot
                        break
                
                if en_depot:
                    depot_manifest_id = en_depot.get('manifest')
                    print(f"\n   Downloading English depot patch manifest:")
                    print(f"   Depot manifest ID: {depot_manifest_id}")
                    
                    depot_diffs = api.get_patch_depot_manifest(depot_manifest_id)
                    if depot_diffs:
                        print(f"\n   Depot patch manifest:")
                        depot_json = json_module.dumps(depot_diffs, indent=2)
                        print(depot_json)
                        
                        # Try to download the actual patch chunk
                        items = depot_diffs.get('depot', {}).get('items', [])
                        if items:
                            first_item = items[0]
                            chunks = first_item.get('chunks', [])
                            if chunks:
                                first_chunk = chunks[0]
                                compressed_md5 = first_chunk.get('compressedMd5')
                                print(f"\n   Testing patch chunk download:")
                                print(f"   Chunk compressedMd5: {compressed_md5}")
                                
                                # Construct patch chunk URL
                                patch_chunk_url = api.get_patch_chunk_url(compressed_md5)
                                print(f"   Patch chunk URL: {patch_chunk_url}")
                                
                                # Try downloading it
                                import requests
                                response = requests.get(patch_chunk_url)
                                print(f"   Response status: {response.status_code}")
                                print(f"   Response size: {len(response.content)} bytes")
                                print(f"   Expected compressed size: {first_chunk.get('compressedSize')} bytes")
                                
                                if response.status_code == 200:
                                    print(f"   ✓ Patch chunk downloaded successfully!")
                                else:
                                    print(f"   ✗ Failed to download patch chunk")
                    else:
                        print(f"   ✗ Failed to download depot patch manifest!")
                else:
                    print(f"\n   ✗ No en-US depot found for product {PRODUCT_ID}")
            else:
                print(f"   ✗ Failed to download patch manifest!")
                return 0
    else:
        print(f"   ✗ No patch info returned (empty dict, None, or exception)")
        return 0
    
    print("\n   Creating Patch object...")
    
    # Add try/except to see the actual error
    try:
        patch = Patch.get(
            api_client=api,
            manifest=new_manifest,
            old_manifest=old_manifest,
            language="en",  # Will match en-US, en-GB, etc.
            dlc_product_ids=[]  # No DLC for this example
        )
    except Exception as e:
        print(f"   Exception during Patch.get(): {e}")
        import traceback
        traceback.print_exc()
        patch = None
    
    print(f"   Patch object result: {patch}")
    
    if not patch:
        print("\n✗ No patches available between these builds")
        print("  Possible reasons:")
        print("  - Builds too far apart (GOG doesn't create patches for old updates)")
        print("  - Patches expired/removed")
        print("  - Build IDs incorrect")
        print("\n  Will need to use full downloads instead.")
        return 0
    
    print(f"✓ Patch available!")
    print(f"  Algorithm: {patch.algorithm}")
    print(f"  Files with patches: {len(patch.files)}")
    
    # Calculate total download size
    total_patch_size = sum(
        chunk["compressedSize"] 
        for fp in patch.files 
        for chunk in fp.chunks
    )
    
    print(f"  Total patch download size: ~{total_patch_size / 1024 / 1024:.2f} MB")
    
    # Download patches
    print("\n4. Downloading patch files...")
    patch_metadata = {
        "product_id": PRODUCT_ID,
        "from_build": OLD_BUILD["build_id"],
        "to_build": NEW_BUILD["build_id"],
        "from_published": OLD_BUILD["published"],
        "to_published": NEW_BUILD["published"],
        "algorithm": patch.algorithm,
        "patches": []
    }
    
    downloaded_count = 0
    failed_count = 0
    
    for idx, file_patch in enumerate(patch.files, 1):
        print(f"\n   [{idx}/{len(patch.files)}] {file_patch.target_path}")
        print(f"       Chunks: {len(file_patch.chunks)}")
        
        # Create safe filename for delta
        safe_filename = file_patch.target_path.replace("/", "_").replace("\\", "_")
        delta_path = PATCHES_DIR / f"{safe_filename}.delta"
        
        # Download chunks and concatenate
        try:
            with open(delta_path, 'wb') as delta_file:
                for chunk_idx, chunk in enumerate(file_patch.chunks):
                    chunk_md5 = chunk["compressedMd5"]
                    chunk_size = chunk["compressedSize"]
                    
                    # Get secure link URLs using clientId/clientSecret from patch manifest
                    secure_urls = api.get_patch_secure_link(
                        product_id=PRODUCT_ID,
                        chunk_hash=chunk_md5,
                        client_id=patch.patch_data['clientId'],
                        client_secret=patch.patch_data['clientSecret']
                    )
                    
                    if not secure_urls:
                        raise RuntimeError(f"Failed to get secure link for {chunk_md5}")
                    
                    # Build chunk URL by replacing {GALAXY_PATH} template
                    from galaxy_dl import utils
                    chunk_path = utils.galaxy_path(chunk_md5)
                    chunk_url = secure_urls[0].replace("{GALAXY_PATH}", chunk_path)
                    
                    # Download chunk
                    response = api.session.get(chunk_url, timeout=30)
                    response.raise_for_status()
                    
                    chunk_data = response.content
                    
                    # Verify compressed MD5
                    actual_md5 = hashlib.md5(chunk_data).hexdigest()
                    if actual_md5 != chunk_md5:
                        raise ValueError(f"Chunk MD5 mismatch: {actual_md5} != {chunk_md5}")
                    
                    # Write to delta file
                    delta_file.write(chunk_data)
                    
                    print(f"       Chunk {chunk_idx + 1}/{len(file_patch.chunks)}: {len(chunk_data):,} bytes")
            
            # Verify complete delta file exists
            if not delta_path.exists():
                raise FileNotFoundError(f"Delta file not created: {delta_path}")
            
            downloaded_count += 1
            print(f"       ✓ Saved: {delta_path.name}")
            
            # Add to metadata with chunk hashes for validation
            patch_metadata["patches"].append({
                "source": file_patch.source_path,
                "target": file_patch.target_path,
                "delta_file": f"patches/{delta_path.name}",
                "md5_source": file_patch.md5_source,
                "md5_target": file_patch.md5_target,
                "patch_md5": file_patch.md5,
                "chunks": [
                    {
                        "compressedMd5": chunk["compressedMd5"],
                        "compressedSize": chunk["compressedSize"],
                        "md5": chunk["md5"],
                        "size": chunk["size"]
                    }
                    for chunk in file_patch.chunks
                ],
                "applied": False
            })
            
        except Exception as e:
            failed_count += 1
            print(f"       ✗ Failed: {e}")
    
    # Save metadata
    print(f"\n5. Saving patch metadata...")
    with open(METADATA_FILE, 'w') as f:
        json.dump(patch_metadata, f, indent=2)
    
    print(f"   ✓ Saved: {METADATA_FILE}")
    
    # Validate downloaded patch files
    print(f"\n6. Validating downloaded patches...")
    validation_passed = True
    
    for patch_info in patch_metadata["patches"]:
        delta_path = PATCHES_DIR / Path(patch_info["delta_file"]).name
        
        if not delta_path.exists():
            print(f"   ✗ Missing: {delta_path.name}")
            validation_passed = False
            continue
        
        # For multi-chunk patches, we'd need to validate each chunk separately
        # For single-chunk patches (like this one), validate the entire file
        if len(patch_info["chunks"]) == 1:
            chunk_info = patch_info["chunks"][0]
            expected_md5 = chunk_info["compressedMd5"]
            expected_size = chunk_info["compressedSize"]
            
            actual_size = delta_path.stat().st_size
            actual_md5 = hashlib.md5(delta_path.read_bytes()).hexdigest()
            
            if actual_size != expected_size:
                print(f"   ✗ {delta_path.name}: Size mismatch ({actual_size} != {expected_size})")
                validation_passed = False
            elif actual_md5 != expected_md5:
                print(f"   ✗ {delta_path.name}: MD5 mismatch ({actual_md5} != {expected_md5})")
                validation_passed = False
            else:
                print(f"   ✓ {delta_path.name}: Valid (MD5: {actual_md5})")
        else:
            # Multi-chunk patches would need chunk-by-chunk validation
            print(f"   ⚠ {delta_path.name}: Multi-chunk validation not implemented")
    
    if validation_passed:
        print(f"\n   All patches validated successfully!")
    
    # Summary
    print("\n" + "=" * 80)
    print("Download Summary")
    print("=" * 80)
    print(f"  Patches downloaded: {downloaded_count}/{len(patch.files)}")
    print(f"  Patches failed:     {failed_count}/{len(patch.files)}")
    print(f"  Validation:         {'PASSED' if validation_passed else 'FAILED'}")
    print(f"  Metadata saved:     {METADATA_FILE}")
    print(f"  Patches directory:  {PATCHES_DIR}")
    
    if downloaded_count > 0:
        print("\nNext steps:")
        print("  1. Review patch_manifest.json for patch details")
        print("  2. Apply patches using pyxdelta or xdelta3:")
        print("     - Python: pyxdelta.patch(source, delta, output)")
        print("     - CLI:    xdelta3 -d -s source.file delta.file output.file")
        print("  3. Verify patched files with md5_target hashes")
    
    print("=" * 80)
    
    return 0


if __name__ == "__main__":
    exit(main())
