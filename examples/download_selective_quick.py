#!/usr/bin/env python3
"""
Quick Selective Download

Non-interactive script for downloading specific files from a game build.
Useful for automation and scripting.

Usage:
    python download_selective_quick.py <product_id> <build_id> <pattern> [options]

Examples:
    # Download all executables
    python download_selective_quick.py 1207658924 12345 "*.exe"
    
    # Download all files in data directory
    python download_selective_quick.py 1207658924 12345 "data/*"
    
    # Download specific extensions
    python download_selective_quick.py 1207658924 12345 "*.exe,*.dll" --extension-mode
    
    # Download from specific build with platform
    python download_selective_quick.py 1207658924 12345 "*.pak" --platform linux

Arguments:
    product_id: GOG product ID
    build_id: Build ID to download from
    pattern: Wildcard pattern, regex, or comma-separated extensions
    
Options:
    --platform PLATFORM: Platform (windows/osx/linux), default: windows
    --regex: Treat pattern as regex instead of wildcard
    --extension-mode: Treat pattern as comma-separated extensions
    --output DIR: Output directory, default: ./downloads/<product_id>/<build_id>
    --no-verify: Skip hash verification
    --workers N: Number of download workers, default: 8
    --show-only: Show matching files without downloading
"""

import sys
import os
import re
import fnmatch
import argparse
from typing import List
from galaxy_dl import GalaxyAPI, GalaxyDownloader, AuthManager
from galaxy_dl.models import DepotItem


def format_size(size: int) -> str:
    """Format size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def filter_items(items: List[DepotItem], pattern: str, mode: str = 'wildcard') -> List[DepotItem]:
    """
    Filter items by pattern.
    
    Args:
        items: List of depot items
        pattern: Pattern to match
        mode: 'wildcard', 'regex', or 'extension'
    """
    if mode == 'wildcard':
        return [item for item in items if fnmatch.fnmatch(item.path.lower(), pattern.lower())]
    
    elif mode == 'regex':
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
            return [item for item in items if compiled.search(item.path)]
        except re.error as e:
            print(f"Error: Invalid regex: {e}")
            sys.exit(1)
    
    elif mode == 'extension':
        extensions = [ext.strip() for ext in pattern.split(',')]
        extensions = [ext.lower() if ext.startswith('.') else f'.{ext.lower()}' for ext in extensions]
        return [item for item in items if any(item.path.lower().endswith(ext) for ext in extensions)]
    
    return []


def get_all_depot_items(api: GalaxyAPI, manifest) -> List[DepotItem]:
    """Get all depot items from all depots in a manifest."""
    all_items = []
    
    if manifest.generation == 2 and manifest.depots:
        print(f"Loading {len(manifest.depots)} depot(s)...")
        for depot_idx, depot in enumerate(manifest.depots, 1):
            items = api.get_depot_items(depot.manifest, is_dependency=False)
            
            # Set product_id for all items
            for item in items:
                item.product_id = depot.product_id
            
            print(f"  Depot {depot_idx}/{len(manifest.depots)}: {len(items)} items")
            all_items.extend(items)
    
    elif manifest.items:
        all_items = manifest.items
    
    return all_items


def main():
    parser = argparse.ArgumentParser(
        description='Download specific files from a GOG game build',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 1207658924 12345 "*.exe"
  %(prog)s 1207658924 12345 "data/*" --platform linux
  %(prog)s 1207658924 12345 "exe,dll" --extension-mode
  %(prog)s 1207658924 12345 "\\.(pak|vpk)$" --regex
  %(prog)s 1207658924 12345 "*.pak" --show-only
        """
    )
    
    parser.add_argument('product_id', help='GOG product ID')
    parser.add_argument('build_id', help='Build ID to download')
    parser.add_argument('pattern', help='Filter pattern (wildcard, regex, or extensions)')
    parser.add_argument('--platform', default='windows', 
                       choices=['windows', 'osx', 'linux'],
                       help='Platform (default: windows)')
    parser.add_argument('--regex', action='store_true',
                       help='Treat pattern as regex')
    parser.add_argument('--extension-mode', action='store_true',
                       help='Treat pattern as comma-separated extensions')
    parser.add_argument('--output', help='Output directory')
    parser.add_argument('--no-verify', action='store_true',
                       help='Skip hash verification')
    parser.add_argument('--workers', type=int, default=8,
                       help='Number of download workers (default: 8)')
    parser.add_argument('--show-only', action='store_true',
                       help='Show matching files without downloading')
    
    args = parser.parse_args()
    
    # Authenticate
    print("Authenticating...")
    auth = AuthManager()
    
    if not auth.is_authenticated():
        print("Error: Not authenticated. Please run authentication first:")
        print("  python examples/list_library.py")
        sys.exit(1)
    
    api = GalaxyAPI(auth)
    
    # Get builds
    print(f"Fetching builds for product {args.product_id} ({args.platform})...")
    builds_data = api.get_all_product_builds(args.product_id, args.platform)
    
    if not builds_data or "items" not in builds_data:
        print("Error: No builds found!")
        sys.exit(1)
    
    # Find matching build
    build = None
    for b in builds_data["items"]:
        if b.get("build_id") == args.build_id:
            build = b
            break
    
    if not build:
        print(f"Error: Build {args.build_id} not found!")
        print(f"Available builds:")
        for b in builds_data["items"][:5]:
            print(f"  - {b.get('build_id')}")
        sys.exit(1)
    
    print(f"Found build: {args.build_id} (Gen {build.get('generation', '?')})")
    
    # Get manifest
    print("Fetching manifest...")
    manifest = api.get_manifest_from_build(args.product_id, build, args.platform)
    
    if not manifest:
        print("Error: Failed to get manifest!")
        sys.exit(1)
    
    print(f"Manifest loaded (Generation {manifest.generation})")
    
    # Get all items
    print("Loading depot items...")
    all_items = get_all_depot_items(api, manifest)
    
    if not all_items:
        print("Error: No files found in manifest!")
        sys.exit(1)
    
    print(f"Total files: {len(all_items)}")
    
    # Filter items
    if args.extension_mode:
        mode = 'extension'
        print(f"Filtering by extensions: {args.pattern}")
    elif args.regex:
        mode = 'regex'
        print(f"Filtering by regex: {args.pattern}")
    else:
        mode = 'wildcard'
        print(f"Filtering by pattern: {args.pattern}")
    
    selected_items = filter_items(all_items, args.pattern, mode)
    
    if not selected_items:
        print(f"No files match pattern: {args.pattern}")
        sys.exit(0)
    
    # Check for SFC dependencies
    sfc_containers = [item for item in all_items if item.is_small_files_container]
    needs_sfc = any(item.is_in_sfc for item in selected_items)
    
    if needs_sfc and sfc_containers:
        print(f"Note: Adding {len(sfc_containers)} SFC container(s) for extraction")
        for sfc in sfc_containers:
            if sfc not in selected_items:
                selected_items.append(sfc)
    
    # Display results
    total_size_uncompressed = sum(item.total_size_uncompressed for item in selected_items)
    total_size_compressed = sum(item.total_size_compressed for item in selected_items)
    
    print(f"\nMatched {len(selected_items)} file(s):")
    print(f"  Uncompressed: {format_size(total_size_uncompressed)}")
    print(f"  Compressed: {format_size(total_size_compressed)}")
    
    # Show files
    print("\nFiles:")
    for idx, item in enumerate(selected_items[:20], 1):
        size = format_size(item.total_size_uncompressed)
        print(f"  {idx:3d}. {item.path:<50} {size:>10}")
    
    if len(selected_items) > 20:
        print(f"  ... and {len(selected_items) - 20} more files")
    
    # Show only mode
    if args.show_only:
        print("\n[Show-only mode - not downloading]")
        return
    
    # Set output directory
    if args.output:
        output_dir = args.output
    else:
        output_dir = os.path.join("./downloads", args.product_id, args.build_id)
    
    print(f"\nOutput directory: {output_dir}")
    
    # Download
    print("\nStarting download...")
    os.makedirs(output_dir, exist_ok=True)
    
    downloader = GalaxyDownloader(api, max_workers=args.workers)
    
    results = downloader.download_depot_items(
        selected_items,
        output_dir,
        verify_hash=not args.no_verify,
        delete_sfc_after_extraction=True
    )
    
    # Results
    successful = sum(1 for path in results.values() if path is not None)
    failed = len(results) - successful
    
    print("\n" + "=" * 70)
    print(f"Download complete: {successful}/{len(results)} successful")
    
    if failed > 0:
        print(f"Failed: {failed} files")
        for item_path, result_path in results.items():
            if result_path is None:
                print(f"  - {item_path}")
        sys.exit(1)
    
    print(f"Files saved to: {output_dir}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
        sys.exit(130)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
