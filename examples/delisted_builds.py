"""
Access delisted builds using gogdb.org data.

This example shows how to:
- Use repository_id from gogdb.org for delisted V1 builds
- Use manifest links for delisted V2 builds
- Get manifests without querying builds API
"""

from galaxy_dl import GalaxyAPI, AuthManager


def main():
    auth = AuthManager()
    
    if not auth.is_authenticated():
        print("Not authenticated. Please run list_library.py first.")
        return
    
    api = GalaxyAPI(auth)
    
    print("=== Accessing Delisted Builds ===\n")
    print("This example shows how to access builds that are no longer")
    print("listed in the GOG builds API using data from gogdb.org\n")
    
    print("Options:")
    print("1. V1 build with repository_id from gogdb.org")
    print("2. V2 build with manifest link")
    print("3. Direct manifest URL")
    
    choice = input("\nSelect option (1-3): ").strip()
    
    if choice == "1":
        # V1 with repository_id
        print("\n=== V1 Build with Repository ID ===")
        print("On gogdb.org, find the 'Repository timestamp' for the build")
        print("Example: https://www.gogdb.org/product/1207658924#builds\n")
        
        product_id = input("Enter product ID: ").strip()
        repository_id = input("Enter repository_id (repository timestamp): ").strip()
        platform = input("Enter platform (windows/osx/linux) [windows]: ").strip() or "windows"
        
        print(f"\nFetching V1 manifest for {product_id}/{repository_id}...")
        
        manifest = api.get_manifest_direct(
            product_id=product_id,
            generation=1,
            repository_id=repository_id,
            platform=platform
        )
        
        if manifest:
            print("\n✓ Manifest loaded successfully!")
            print(f"Generation: {manifest.generation}")
            print(f"Repository ID: {manifest.repository_id}")
            print(f"Install Directory: {manifest.install_directory}")
            print(f"Depots: {len(manifest.depots)}")
        else:
            print("\n✗ Failed to load manifest")
    
    elif choice == "2":
        # V2 with manifest link
        print("\n=== V2 Build with Manifest Link ===")
        print("From gogdb.org build data or cached information\n")
        
        product_id = input("Enter product ID: ").strip()
        manifest_link = input("Enter manifest link URL: ").strip()
        build_id = input("Enter build_id (optional): ").strip() or None
        
        print(f"\nFetching V2 manifest...")
        
        manifest = api.get_manifest_direct(
            product_id=product_id,
            generation=2,
            manifest_link=manifest_link,
            build_id=build_id
        )
        
        if manifest:
            print("\n✓ Manifest loaded successfully!")
            print(f"Generation: {manifest.generation}")
            print(f"Build ID: {manifest.build_id}")
            print(f"Install Directory: {manifest.install_directory}")
            print(f"Depots: {len(manifest.depots)}")
        else:
            print("\n✗ Failed to load manifest")
    
    elif choice == "3":
        # Direct URL
        print("\n=== Direct Manifest URL ===")
        print("Paste the full manifest URL from gogdb.org or other source\n")
        
        url = input("Enter manifest URL: ").strip()
        
        print(f"\nFetching manifest...")
        manifest_json = api.get_manifest_by_url(url)
        
        if manifest_json:
            print("\n✓ Manifest JSON loaded successfully!")
            print(f"Keys: {', '.join(manifest_json.keys())}")
            if "baseProductId" in manifest_json:
                print(f"Product ID: {manifest_json['baseProductId']}")
            if "buildId" in manifest_json:
                print(f"Build ID: {manifest_json['buildId']}")
        else:
            print("\n✗ Failed to load manifest")
    
    else:
        print("Invalid choice!")


if __name__ == "__main__":
    main()
