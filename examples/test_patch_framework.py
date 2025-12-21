"""
Test patch framework - demonstrates patch detection and download capability

This example shows how to:
1. Compare two manifests
2. Detect patch availability
3. Get patch information
4. Prepare for patch downloads (actual download left as exercise)
"""

from galaxy_dl import GalaxyAPI, AuthManager, Manifest, Patch, ManifestDiff

def test_patch_framework():
    """
    Test the patch detection framework.
    
    This tests the complete patch workflow:
    - Query patch availability
    - Download patch manifests
    - Generate diff with patches
    """
    
    print("=" * 70)
    print("Testing Patch Framework")
    print("=" * 70)
    
    # Initialize API
    auth = AuthManager()
    if not auth.is_authenticated():
        print("ERROR: Not authenticated. Run 'galaxy-dl login' first.")
        return
    
    api = GalaxyAPI(auth)
    
    # Test data - these are example build IDs
    # Replace with real product ID and build IDs for actual testing
    product_id = "1207658924"  # Example: GOG product
    
    print("\n1. Testing Patch API Methods")
    print("-" * 70)
    
    # Example: Query for patches between builds
    # (This will fail with fake build IDs but demonstrates the API)
    from_build = "1000"
    to_build = "1001"
    
    print(f"\nQuerying patch availability:")
    print(f"  Product: {product_id}")
    print(f"  From build: {from_build}")
    print(f"  To build: {to_build}")
    
    try:
        patch_info = api.get_patch_info(product_id, from_build, to_build)
        
        if patch_info and not patch_info.get('error'):
            print(f"✓ Patch available!")
            print(f"  Link: {patch_info.get('link', 'N/A')}")
            
            # Download patch manifest
            patch_link = patch_info.get('link')
            if patch_link:
                print(f"\nDownloading patch manifest...")
                patch_data = api.get_patch_manifest(patch_link)
                
                if patch_data:
                    print(f"✓ Patch manifest downloaded")
                    print(f"  Algorithm: {patch_data.get('algorithm', 'N/A')}")
                    print(f"  Depots: {len(patch_data.get('depots', []))}")
        else:
            print("✗ No patch available (expected with fake build IDs)")
            
    except Exception as e:
        print(f"✗ Patch query failed (expected): {e}")
    
    print("\n2. Testing Patch Model Classes")
    print("-" * 70)
    
    # Test FilePatchDiff creation
    from galaxy_dl.models import FilePatchDiff
    
    patch_json = {
        "md5_source": "abc123",
        "md5_target": "def456",
        "path_source": "game.exe",
        "path_target": "game.exe",
        "md5": "patch123",
        "chunks": [
            {"compressedMd5": "chunk1", "md5": "unchunk1", "compressedSize": 1024, "size": 2048}
        ]
    }
    
    patch_diff = FilePatchDiff.from_json(patch_json)
    print(f"\n✓ FilePatchDiff created:")
    print(f"  Source: {patch_diff.source_path} (MD5: {patch_diff.md5_source})")
    print(f"  Target: {patch_diff.target_path} (MD5: {patch_diff.md5_target})")
    print(f"  Chunks: {len(patch_diff.chunks)}")
    
    print("\n3. Testing ManifestDiff")
    print("-" * 70)
    
    # Create a simple diff to test
    diff = ManifestDiff()
    print(f"\n✓ ManifestDiff created: {diff}")
    
    # Add some example items
    from galaxy_dl.models import DepotItem
    
    new_item = DepotItem(path="new_file.dat", md5="new123")
    diff.new.append(new_item)
    
    changed_item = DepotItem(path="changed_file.dat", md5="changed456")
    diff.changed.append(changed_item)
    
    diff.patched.append(patch_diff)
    
    print(f"\n✓ Updated diff: {diff}")
    print("\n  Details:")
    print(f"    New files: {len(diff.new)}")
    print(f"    Changed files: {len(diff.changed)}")
    print(f"    Patched files: {len(diff.patched)}")
    print(f"    Deleted files: {len(diff.deleted)}")
    
    print("\n4. Testing Secure Link for Patches")
    print("-" * 70)
    
    try:
        # Test getting secure link with patch root
        print(f"\nGetting secure link with patch root...")
        links = api.get_secure_link(
            product_id,
            path="/",
            generation=2,
            root_path="/patches/store"
        )
        
        if links:
            print(f"✓ Got {len(links)} secure link(s) for patches")
            print(f"  First link: {links[0][:80]}...")
        else:
            print("✗ No secure links (may require valid product)")
            
    except Exception as e:
        print(f"✗ Secure link failed: {e}")
    
    print("\n" + "=" * 70)
    print("Patch Framework Test Complete!")
    print("=" * 70)
    print("\nNext steps:")
    print("  1. Use real product ID and build IDs to test with actual patches")
    print("  2. Download patch chunks using secure links")
    print("  3. Save .delta files for later application")
    print("  4. Optionally: Apply patches with pyxdelta or external tool")
    print()


if __name__ == "__main__":
    test_patch_framework()
