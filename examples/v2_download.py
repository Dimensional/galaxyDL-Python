"""
V2 Download Example - Two Approaches

This example demonstrates both ways to download V2 game files:
1. Download raw compressed chunks (~10MB pieces)
2. Download, decompress, and assemble into game files
"""

from galaxy_dl import GalaxyAPI, GalaxyDownloader, AuthManager
import os


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
    build_id = input("Enter V2 build ID (or press Enter to use latest V2): ").strip()
    platform = input("Enter platform (windows/osx/linux) [windows]: ").strip() or "windows"
    
    # Get manifest
    if build_id:
        manifest = api.get_manifest(product_id, build_id, platform)
    else:
        # Get all builds and find first V2 build
        builds_data = api.get_all_product_builds(product_id, platform)
        v2_builds = [b for b in builds_data.get("items", []) if b.get("generation") == 2]
        
        if not v2_builds:
            print("No V2 builds found for this game!")
            return
        
        print(f"\nFound {len(v2_builds)} V2 builds. Using the newest one:")
        print(f"  Build ID: {v2_builds[0].get('build_id')}")
        print(f"  Date: {v2_builds[0].get('date_published')}")
        print(f"  Version: {v2_builds[0].get('version_name', 'N/A')}")
        
        manifest = api.get_manifest_from_build(product_id, v2_builds[0], platform)
    
    if not manifest or manifest.generation != 2:
        print("This is not a V2 manifest!")
        return
    
    # For V2, we need to get the actual depot items
    # Let's fetch the first depot and its items as an example
    if not manifest.depots:
        print("No depots found in manifest!")
        return
    
    depot = manifest.depots[0]
    print(f"\nV2 Manifest loaded:")
    print(f"  Depot Product ID: {depot.product_id}")
    print(f"  Languages: {', '.join(depot.languages)}")
    print(f"  Compressed size: {depot.compressed_size:,} bytes")
    print(f"  Uncompressed size: {depot.size:,} bytes")
    
    # Note: To get actual depot items, we'd need to fetch the depot manifest
    # This is a simplified example - in real use, you'd fetch depot items from the depot manifest
    print("\nNote: This example shows the concept. In practice, you'd fetch depot items")
    print("from the depot manifest URL to get the actual file list with chunks.")
    
    # Ask which download method to use
    print("\nDownload methods:")
    print("1. Download raw compressed chunks (~10MB pieces, no decompression)")
    print("2. Download, decompress, and assemble into game files (ready to use)")
    
    choice = input("\nSelect method (1 or 2): ").strip()
    
    if choice == "1":
        # Method 1: Download raw chunks
        print("\nRaw chunk mode:")
        print("- Chunks saved as compressed files")
        print("- Includes metadata (chunks.json) for later assembly")
        print("- Frontend can process later or implement custom decompression")
        
        # This is a conceptual example - you'd iterate through depot items
        print("\nTo download raw chunks:")
        print("  downloader.download_item(item, output_dir, raw_mode=True)")
        print("\nThis creates a directory with:")
        print("  - chunk_0000.dat, chunk_0001.dat, ... (compressed chunks)")
        print("  - chunks.json (metadata for assembly)")
        
    elif choice == "2":
        # Method 2: Process and assemble
        print("\nProcessed mode (default):")
        print("- Downloads chunks")
        print("- Decompresses using zlib")
        print("- Assembles into final game files")
        print("- Files ready to use immediately")
        
        print("\nTo download and assemble:")
        print("  downloader.download_item(item, output_dir, raw_mode=False)")
        print("\nOr to assemble previously downloaded raw chunks:")
        print("  downloader.assemble_v2_chunks(chunks_dir, output_path)")
        
    else:
        print("Invalid choice!")
        return
    
    # Example workflow
    print("\n" + "="*60)
    print("Example Workflow:")
    print("="*60)
    
    if choice == "1":
        print("""
# Download raw chunks for later processing
for item in depot_items:
    chunks_dir = downloader.download_item(
        item, 
        output_dir="./raw_chunks",
        raw_mode=True,
        verify_hash=True
    )
    # Returns: "./raw_chunks/path/to/file.exe.chunks/"
    # Contains: chunk_0000.dat, chunk_0001.dat, chunks.json

# Later, assemble when needed
for chunks_dir in chunk_directories:
    output_path = downloader.assemble_v2_chunks(
        chunks_dir,
        output_path="./game/path/to/file.exe",
        verify_hash=True
    )
        """)
    else:
        print("""
# Download, decompress, and assemble in one step
for item in depot_items:
    output_path = downloader.download_item(
        item,
        output_dir="./game",
        raw_mode=False,  # Default
        verify_hash=True
    )
    # Returns: "./game/path/to/file.exe" (ready to use)
        """)
    
    print("\n" + "="*60)
    print("Use Cases:")
    print("="*60)
    
    if choice == "1":
        print("""
Raw chunk mode is useful for:
- Caching chunks for faster reinstalls
- Implementing custom decompression logic
- Minimizing processing during download
- Storing chunks for multiple games efficiently
- Building download resumption features
        """)
    else:
        print("""
Processed mode is useful for:
- Direct installation (files ready immediately)
- Simple download-and-play workflow
- When you don't need chunk caching
- Standard game installation process
        """)


if __name__ == "__main__":
    main()
