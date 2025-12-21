#!/usr/bin/env python3
"""
Test Generation Auto-Detection

Demonstrates auto-detection by trying both V1 and V2 download methods:
- V1: /content-system/v1/manifests/{game_id}/{platform}/{timestamp}/repository.json
- V2: /content-system/v2/meta/{hash[:2]}/{hash[2:4]}/{hash}

The system tries both and uses whichever succeeds.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from galaxy_dl import GalaxyAPI, AuthManager


def test_v1_auto_detect():
    """Test auto-detection with a V1 repository timestamp."""
    print("=" * 80)
    print("TEST 1: Auto-Detect V1 (The Witcher 2 Windows)")
    print("=" * 80)
    
    auth = AuthManager()
    if not auth.is_authenticated():
        print("Not authenticated. Run: galaxy-dl login")
        return
    
    api = GalaxyAPI(auth)
    
    # The Witcher 2 V1 Windows build
    product_id = "1207658930"
    repository_id = "37794096"  # V1 timestamp
    platform = "windows"
    
    print(f"\nProduct ID: {product_id}")
    print(f"Repository ID: {repository_id} (looks like V1 timestamp)")
    print(f"Platform: {platform}")
    print(f"\nCalling get_manifest_direct with generation=None...")
    
    try:
        manifest = api.get_manifest_direct(
            product_id=product_id,
            repository_id=repository_id,
            platform=platform
            # generation=None (implicit) - will auto-detect!
        )
        
        if manifest:
            print(f"\n✓ SUCCESS!")
            print(f"  Auto-detected: V{manifest.generation}")
            print(f"  Repository ID: {manifest.repository_id}")
            print(f"  Install Directory: {manifest.install_directory}")
            print(f"  Depots: {len(manifest.depots)}")
            print(f"  Total files: {len(manifest.items)}")
        else:
            print("\n✗ FAIL: Could not load manifest")
            
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()


def test_v2_auto_detect():
    """Test auto-detection with a V2 depot hash."""
    print("\n" + "=" * 80)
    print("TEST 2: Auto-Detect V2 (The Witcher 2 Depot)")
    print("=" * 80)
    
    auth = AuthManager()
    if not auth.is_authenticated():
        print("Not authenticated. Run: galaxy-dl login")
        return
    
    api = GalaxyAPI(auth)
    
    # The Witcher 2 V2 depot hash
    product_id = "1207658930"
    repository_id = "e518c17d90805e8e3998a35fac8b8505"  # V2 depot hash
    
    print(f"\nProduct ID: {product_id}")
    print(f"Repository ID: {repository_id} (looks like V2 hash)")
    print(f"\nCalling get_manifest_direct with generation=None...")
    
    try:
        manifest = api.get_manifest_direct(
            product_id=product_id,
            repository_id=repository_id
            # generation=None (implicit) - will auto-detect!
        )
        
        if manifest:
            print(f"\n✓ SUCCESS!")
            print(f"  Auto-detected: V{manifest.generation}")
            print(f"  Base Product ID: {manifest.base_product_id}")
            print(f"  Install Directory: {manifest.install_directory}")
            print(f"  Depots: {len(manifest.depots)}")
            if manifest.dependencies:
                print(f"  Dependencies: {', '.join(manifest.dependencies)}")
        else:
            print("\n✗ FAIL: Could not load manifest")
            
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()


def test_explicit_generation():
    """Test that explicit generation still works."""
    print("\n" + "=" * 80)
    print("TEST 3: Explicit Generation (should still work)")
    print("=" * 80)
    
    auth = AuthManager()
    if not auth.is_authenticated():
        print("Not authenticated. Run: galaxy-dl login")
        return
    
    api = GalaxyAPI(auth)
    
    # Test V1 with explicit generation
    print("\nTest 3a: Explicit V1")
    try:
        manifest = api.get_manifest_direct(
            product_id="1207658930",
            generation=1,
            repository_id="37794096",
            platform="windows"
        )
        if manifest and manifest.generation == 1:
            print(f"  ✓ Explicit V1 works (repo_id={manifest.repository_id})")
        else:
            print(f"  ✗ Explicit V1 failed")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")
    
    # Test V2 with explicit generation
    print("\nTest 3b: Explicit V2")
    try:
        manifest = api.get_manifest_direct(
            product_id="1207658930",
            generation=2,
            repository_id="e518c17d90805e8e3998a35fac8b8505"
        )
        if manifest and manifest.generation == 2:
            print(f"  ✓ Explicit V2 works (base_id={manifest.base_product_id})")
        else:
            print(f"  ✗ Explicit V2 failed")
    except Exception as e:
        print(f"  ✗ ERROR: {e}")


def main():
    print("Generation Auto-Detection Test Suite")
    print("Tests both auto-detection and explicit generation parameters\n")
    
    # Test 1: V1 auto-detection
    test_v1_auto_detect()
    
    # Test 2: V2 auto-detection
    test_v2_auto_detect()
    
    # Test 3: Explicit generation (backwards compatibility)
    test_explicit_generation()
    
    print("\n" + "=" * 80)
    print("All tests completed!")
    print("=" * 80)
    print("\nSummary:")
    print("- Auto-detection tries V1 first, then V2")
    print("- V1 identified by: numeric timestamp in URL path")
    print("- V2 identified by: hex hash with 2-level prefix")
    print("- Explicit generation parameter still works as before")


if __name__ == "__main__":
    main()
