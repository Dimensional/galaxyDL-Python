"""
V1 Download Example - Two Approaches

This example demonstrates both ways to download V1 game files:
1. Download whole main.bin blob
2. Extract individual files using range requests
"""

from galaxy_dl import GalaxyAPI, GalaxyDownloader, AuthManager


def main():
    # Authenticate
    auth = AuthManager()
    
    if not auth.is_authenticated():
        print("Not authenticated. Please run list_library.py first.")
        return
    
    api = GalaxyAPI(auth)
    downloader = GalaxyDownloader(api, max_workers=4)
    
    # Get product ID and build
    product_id = input("Enter GOG product ID: ").strip()
    build_id = input("Enter V1 build ID (or press Enter to use latest V1): ").strip()
    platform = input("Enter platform (windows/osx/linux) [windows]: ").strip() or "windows"
    
    # Get manifest
    if build_id:
        manifest = api.get_manifest(product_id, build_id, platform)
    else:
        # Get all builds and find first V1 build
        builds_data = api.get_all_product_builds(product_id, platform)
        v1_builds = [b for b in builds_data.get("items", []) if b.get("generation") == 1]
        
        if not v1_builds:
            print("No V1 builds found for this game!")
            return
        
        print(f"\nFound {len(v1_builds)} V1 builds. Using the newest one:")
        print(f"  Build ID: {v1_builds[0].get('build_id')}")
        print(f"  Date: {v1_builds[0].get('date_published')}")
        print(f"  Repository ID: {v1_builds[0].get('legacy_build_id')}")
        
        manifest = api.get_manifest_from_build(product_id, v1_builds[0], platform)
    
    if not manifest or manifest.generation != 1:
        print("This is not a V1 manifest!")
        return
    
    print(f"\nV1 Manifest loaded:")
    print(f"  Files: {len(manifest.items)}")
    print(f"  Total size: {sum(item.v1_size for item in manifest.items):,} bytes")
    
    # Ask which download method to use
    print("\nDownload methods:")
    print("1. Download whole main.bin blob (faster, but large)")
    print("2. Extract individual files using range requests (slower, but selective)")
    
    choice = input("\nSelect method (1 or 2): ").strip()
    
    if choice == "1":
        # Method 1: Download whole blob
        print("\nDownloading whole main.bin blob...")
        
        # Create a dummy DepotItem for main.bin
        from galaxy_dl.models import DepotItem
        
        # Get total size from manifest
        total_size = manifest.depots[0].size if manifest.depots else 0
        blob_path = manifest.items[0].v1_blob_path if manifest.items else "main.bin"
        
        blob_item = DepotItem(
            path=f"main.bin",
            product_id=product_id,
            is_v1_blob=True,
            v1_blob_path=blob_path,
            total_size_uncompressed=total_size
        )
        
        output_dir = input("Enter output directory [./downloads]: ").strip() or "./downloads"
        
        def blob_progress(downloaded, total):
            percent = (downloaded / total * 100) if total > 0 else 0
            print(f"\rProgress: {downloaded:,} / {total:,} bytes ({percent:.1f}%)", end="")
        
        output_path = downloader.download_item(blob_item, output_dir, progress_callback=blob_progress)
        print(f"\n\nBlob downloaded to: {output_path}")
        print("You can now extract files using offset/size info from the manifest.")
        
    elif choice == "2":
        # Method 2: Extract individual files
        print("\nExtracting individual files...")
        
        # Optionally filter by file extension
        filter_ext = input("Filter by extension (e.g., .exe, .dll) or press Enter for all: ").strip()
        
        items_to_download = manifest.items
        if filter_ext:
            items_to_download = [item for item in manifest.items if item.path.endswith(filter_ext)]
            print(f"Filtered to {len(items_to_download)} files with extension {filter_ext}")
        
        if not items_to_download:
            print("No files to download!")
            return
        
        # Show first 10 files
        print("\nFiles to download (showing first 10):")
        for i, item in enumerate(items_to_download[:10]):
            print(f"  {item.path} ({item.v1_size:,} bytes)")
        if len(items_to_download) > 10:
            print(f"  ... and {len(items_to_download) - 10} more")
        
        output_dir = input("\nEnter output directory [./downloads]: ").strip() or "./downloads"
        confirm = input(f"Download {len(items_to_download)} files? (y/n): ").strip().lower()
        
        if confirm != 'y':
            print("Cancelled.")
            return
        
        def file_progress(path, downloaded, total):
            print(f"  {path}: {downloaded:,} / {total:,} bytes")
        
        results = downloader.download_v1_files(manifest, output_dir, progress_callback=file_progress)
        
        successful = sum(1 for path in results.values() if path is not None)
        print(f"\nDownload complete: {successful}/{len(results)} files successful")
        
    else:
        print("Invalid choice!")


if __name__ == "__main__":
    main()
