"""
Interactive build selector for a game.

This example shows how to:
- List all available builds for a game
- Display V1 vs V2 generation
- Let user select a build
- Get the manifest for selected build
"""

from galaxy_dl import GalaxyAPI, AuthManager


def main():
    # Authenticate
    auth = AuthManager()
    
    if not auth.is_authenticated():
        print("Not authenticated. Please run list_library.py first or provide OAuth code.")
        return
    
    api = GalaxyAPI(auth)
    
    # Get product ID from user
    product_id = input("Enter GOG product ID (e.g., 1207658924): ").strip()
    platform = input("Enter platform (windows/osx/linux) [windows]: ").strip() or "windows"
    
    # Get all builds
    print(f"\nFetching builds for product {product_id} on {platform}...")
    builds_data = api.get_all_product_builds(product_id, platform)
    
    if not builds_data or "items" not in builds_data:
        print("No builds found!")
        return
    
    builds = builds_data["items"]
    print(f"\nFound {len(builds)} builds:\n")
    
    # Display builds
    for idx, build in enumerate(builds):
        build_id = build.get("build_id", "unknown")
        generation = build.get("generation", "?")
        date = build.get("date_published", "unknown date")
        version = build.get("version_name", "")
        legacy_id = build.get("legacy_build_id", "")
        
        print(f"{idx + 1}. Build {build_id} (Gen {generation})")
        print(f"   Date: {date}")
        if version:
            print(f"   Version: {version}")
        if legacy_id and generation == 1:
            print(f"   Repository ID: {legacy_id}")
        print()
    
    # Let user select
    try:
        choice = int(input(f"Select build (1-{len(builds)}): "))
        if choice < 1 or choice > len(builds):
            print("Invalid choice!")
            return
    except ValueError:
        print("Invalid input!")
        return
    
    selected_build = builds[choice - 1]
    
    # Get manifest using the efficient method
    print(f"\nFetching manifest for build {selected_build.get('build_id')}...")
    manifest = api.get_manifest_from_build(product_id, selected_build, platform)
    
    if manifest:
        print(f"\nManifest loaded successfully!")
        print(f"Generation: {manifest.generation}")
        print(f"Build ID: {manifest.build_id}")
        if manifest.repository_id:
            print(f"Repository ID: {manifest.repository_id}")
        print(f"Install Directory: {manifest.install_directory}")
        print(f"Depots: {len(manifest.depots)}")
        
        # Show depot info
        for depot in manifest.depots:
            print(f"\nDepot:")
            print(f"  Product ID: {depot.product_id}")
            print(f"  Languages: {', '.join(depot.languages)}")
            if depot.os_bitness:
                print(f"  Bitness: {', '.join(depot.os_bitness)}")
            print(f"  Size: {depot.size:,} bytes")
    else:
        print("Failed to load manifest!")


if __name__ == "__main__":
    main()
