#!/usr/bin/env python3
"""
Selective File Download Example

This example demonstrates how to download specific files or groups of files
from a game build. You can filter files by:
- Path patterns (wildcards: *.exe, *.dll, data/*)
- Regular expressions
- File extensions
- Size ranges
- Manual selection

Usage:
    python download_selective_files.py

Features:
    - Interactive game and build selection
    - Browse all files in a build
    - Filter files by various criteria
    - Download only selected files
    - Works with both V1 and V2 manifests
    - Handles SFC (Small Files Container) extraction
"""

import os
import re
import fnmatch
from typing import List, Optional, Set
from galaxy_dl import GalaxyAPI, GalaxyDownloader, AuthManager
from galaxy_dl.models import DepotItem


def format_size(size: int) -> str:
    """Format size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def filter_by_pattern(items: List[DepotItem], pattern: str) -> List[DepotItem]:
    """
    Filter items by wildcard pattern.
    
    Examples:
        *.exe - all executables
        *.dll - all DLL files
        data/* - all files in data directory
        */config.* - all config files in any subdirectory
    """
    return [item for item in items if fnmatch.fnmatch(item.path.lower(), pattern.lower())]


def filter_by_regex(items: List[DepotItem], regex: str) -> List[DepotItem]:
    """Filter items by regular expression pattern."""
    try:
        pattern = re.compile(regex, re.IGNORECASE)
        return [item for item in items if pattern.search(item.path)]
    except re.error as e:
        print(f"Invalid regex: {e}")
        return []


def filter_by_extension(items: List[DepotItem], extensions: List[str]) -> List[DepotItem]:
    """
    Filter items by file extension.
    
    Args:
        extensions: List of extensions (e.g., ['.exe', '.dll', '.txt'])
    """
    extensions = [ext.lower() if ext.startswith('.') else f'.{ext.lower()}' for ext in extensions]
    return [item for item in items if any(item.path.lower().endswith(ext) for ext in extensions)]


def filter_by_size(items: List[DepotItem], min_size: Optional[int] = None, 
                  max_size: Optional[int] = None) -> List[DepotItem]:
    """Filter items by size range (in bytes)."""
    filtered = items
    if min_size is not None:
        filtered = [item for item in filtered if item.total_size_uncompressed >= min_size]
    if max_size is not None:
        filtered = [item for item in filtered if item.total_size_uncompressed <= max_size]
    return filtered


def filter_by_directory(items: List[DepotItem], directory: str) -> List[DepotItem]:
    """Filter items by directory path."""
    directory = directory.replace('\\', '/').rstrip('/')
    return [item for item in items if item.path.replace('\\', '/').startswith(directory + '/')]


def show_items_summary(items: List[DepotItem], show_details: bool = False):
    """Display summary of items."""
    print(f"\nFound {len(items)} file(s)")
    
    if not items:
        return
    
    total_size_uncompressed = sum(item.total_size_uncompressed for item in items)
    total_size_compressed = sum(item.total_size_compressed for item in items)
    
    print(f"Total uncompressed size: {format_size(total_size_uncompressed)}")
    print(f"Total compressed size: {format_size(total_size_compressed)}")
    
    if show_details and len(items) <= 50:
        print("\nFiles:")
        for idx, item in enumerate(items, 1):
            size_str = format_size(item.total_size_uncompressed)
            flags = ""
            if item.is_in_sfc:
                flags = " [in SFC]"
            elif item.is_small_files_container:
                flags = " [SFC container]"
            elif item.is_v1_blob:
                flags = " [V1 blob]"
            print(f"  {idx:3d}. {item.path:<60} {size_str:>10}{flags}")
    elif len(items) > 50:
        print(f"\n(Showing first 20 of {len(items)} files)")
        for idx, item in enumerate(items[:20], 1):
            size_str = format_size(item.total_size_uncompressed)
            print(f"  {idx:3d}. {item.path:<60} {size_str:>10}")
        print(f"  ... and {len(items) - 20} more files")


def select_game(api: GalaxyAPI) -> Optional[dict]:
    """Interactive game selection."""
    print("=== Your Game Library ===\n")
    game_ids = api.get_owned_games()
    
    # Get games with details
    games = api.get_owned_games_with_details(limit=30)
    
    if not games:
        print("No games found in library!")
        return None
    
    for idx, game in enumerate(games, 1):
        print(f"{idx:2d}. {game.get('title', 'Unknown')}")
    
    if len(game_ids) > 30:
        print(f"\n... and {len(game_ids) - 30} more")
    
    # Selection
    try:
        choice = int(input(f"\nSelect game (1-{len(games)}) or 0 to enter product ID: "))
        
        if choice == 0:
            product_id = input("Enter GOG product ID: ").strip()
            title = input("Enter game title (for display): ").strip() or "Unknown Game"
            return {'id': int(product_id), 'title': title}
        
        if 1 <= choice <= len(games):
            return games[choice - 1]
        
        print("Invalid choice!")
        return None
    except (ValueError, KeyError):
        print("Invalid input!")
        return None


def select_build(api: GalaxyAPI, product_id: str, platform: str):
    """Interactive build selection."""
    print(f"\nFetching builds for {platform}...")
    builds_data = api.get_all_product_builds(product_id, platform)
    
    if not builds_data or "items" not in builds_data:
        print("No builds found!")
        return None
    
    builds = builds_data["items"]
    print(f"\nFound {len(builds)} build(s):")
    
    # Show up to 10 most recent builds
    for idx, build in enumerate(builds[:10], 1):
        build_id = build.get("build_id", "unknown")
        generation = build.get("generation", "?")
        version = build.get("version_name", "")
        date = build.get("date_published", "")[:10]  # Just date part
        
        info = f"{idx:2d}. Build {build_id} (Gen {generation})"
        if version:
            info += f" - v{version}"
        if date:
            info += f" - {date}"
        print(info)
    
    if len(builds) > 10:
        print(f"\n... and {len(builds) - 10} more builds")
    
    # Selection
    try:
        choice = int(input(f"\nSelect build (1-{min(10, len(builds))}): "))
        if 1 <= choice <= min(10, len(builds)):
            return builds[choice - 1]
        
        print("Invalid choice!")
        return None
    except ValueError:
        print("Invalid input!")
        return None


def get_all_depot_items(api: GalaxyAPI, manifest) -> List[DepotItem]:
    """
    Get all depot items from all depots in a manifest.
    
    Returns a flat list of all DepotItem objects.
    """
    all_items = []
    
    # For V2 manifests with depot references
    if manifest.generation == 2 and manifest.depots:
        print(f"\nLoading {len(manifest.depots)} depot(s)...")
        for depot_idx, depot in enumerate(manifest.depots, 1):
            print(f"  Depot {depot_idx}/{len(manifest.depots)}: {depot.manifest} ", end='')
            items = api.get_depot_items(depot.manifest, is_dependency=False)
            
            # Set product_id for all items
            for item in items:
                item.product_id = depot.product_id
            
            print(f"({len(items)} items)")
            all_items.extend(items)
    
    # For V1 manifests or already loaded items
    elif manifest.items:
        all_items = manifest.items
    
    return all_items


def interactive_filter_menu(items: List[DepotItem]) -> List[DepotItem]:
    """Interactive filtering menu."""
    current_items = items[:]
    filter_history = []
    
    while True:
        print("\n" + "=" * 70)
        print("FILE FILTER MENU")
        print("=" * 70)
        show_items_summary(current_items, show_details=False)
        
        print("\nFilter Options:")
        print("  1. Filter by wildcard pattern (e.g., *.exe, data/*, *.dll)")
        print("  2. Filter by regular expression")
        print("  3. Filter by file extension(s)")
        print("  4. Filter by size range")
        print("  5. Filter by directory")
        print("  6. Show detailed file list")
        print("  7. Reset filters (show all files)")
        print("  8. Undo last filter")
        print("  9. Done - proceed with current selection")
        print("  0. Cancel")
        
        choice = input("\nSelect option (0-9): ").strip()
        
        if choice == '1':
            pattern = input("Enter wildcard pattern (e.g., *.exe, data/*): ").strip()
            if pattern:
                filter_history.append(current_items[:])
                current_items = filter_by_pattern(current_items, pattern)
                print(f"Applied pattern filter: {pattern}")
        
        elif choice == '2':
            regex = input("Enter regex pattern: ").strip()
            if regex:
                filter_history.append(current_items[:])
                current_items = filter_by_regex(current_items, regex)
                print(f"Applied regex filter: {regex}")
        
        elif choice == '3':
            exts = input("Enter extension(s) (comma-separated, e.g., exe,dll,txt): ").strip()
            if exts:
                ext_list = [e.strip() for e in exts.split(',')]
                filter_history.append(current_items[:])
                current_items = filter_by_extension(current_items, ext_list)
                print(f"Applied extension filter: {ext_list}")
        
        elif choice == '4':
            min_input = input("Minimum size in MB (or blank for no minimum): ").strip()
            max_input = input("Maximum size in MB (or blank for no maximum): ").strip()
            
            min_size = int(float(min_input) * 1024 * 1024) if min_input else None
            max_size = int(float(max_input) * 1024 * 1024) if max_input else None
            
            if min_size or max_size:
                filter_history.append(current_items[:])
                current_items = filter_by_size(current_items, min_size, max_size)
                print(f"Applied size filter: {min_input or '0'}MB - {max_input or 'unlimited'}MB")
        
        elif choice == '5':
            directory = input("Enter directory path (e.g., data, bin, textures): ").strip()
            if directory:
                filter_history.append(current_items[:])
                current_items = filter_by_directory(current_items, directory)
                print(f"Applied directory filter: {directory}")
        
        elif choice == '6':
            show_items_summary(current_items, show_details=True)
            input("\nPress Enter to continue...")
        
        elif choice == '7':
            filter_history.append(current_items[:])
            current_items = items[:]
            print("Filters reset - showing all files")
        
        elif choice == '8':
            if filter_history:
                current_items = filter_history.pop()
                print("Undid last filter")
            else:
                print("No filters to undo")
        
        elif choice == '9':
            if not current_items:
                print("No files selected! Apply filters or reset to select files.")
                continue
            return current_items
        
        elif choice == '0':
            return []
        
        else:
            print("Invalid option!")


def main():
    # Authenticate
    auth = AuthManager()
    
    if not auth.is_authenticated():
        print("Not authenticated. Please run list_library.py first.")
        return
    
    api = GalaxyAPI(auth)
    
    # Step 1: Select game
    selected_game = select_game(api)
    if not selected_game:
        return
    
    product_id = str(selected_game['id'])
    game_title = selected_game['title']
    print(f"\nSelected: {game_title}")
    
    # Step 2: Select platform
    platform = input("\nPlatform (windows/osx/linux) [windows]: ").strip().lower() or "windows"
    
    # Step 3: Select build
    selected_build = select_build(api, product_id, platform)
    if not selected_build:
        return
    
    print(f"\nSelected build: {selected_build.get('build_id')}")
    
    # Step 4: Get manifest
    print(f"\nFetching manifest...")
    manifest = api.get_manifest_from_build(product_id, selected_build, platform)
    
    if not manifest:
        print("Failed to get manifest!")
        return
    
    print(f"Manifest loaded!")
    print(f"  Generation: {manifest.generation}")
    print(f"  Build ID: {manifest.build_id}")
    print(f"  Depots: {len(manifest.depots)}")
    
    # Step 5: Get all items from all depots
    all_items = get_all_depot_items(api, manifest)
    
    if not all_items:
        print("No files found in manifest!")
        return
    
    # Separate SFC containers from regular files for display
    sfc_containers = [item for item in all_items if item.is_small_files_container]
    regular_files = [item for item in all_items if not item.is_small_files_container]
    
    print(f"\nTotal files in manifest: {len(all_items)}")
    print(f"  Regular files: {len(regular_files)}")
    print(f"  SFC containers: {len(sfc_containers)}")
    print(f"  Files in SFC: {sum(1 for item in all_items if item.is_in_sfc)}")
    
    # Step 6: Filter files
    print("\n" + "=" * 70)
    print("Would you like to download all files or select specific files?")
    print("=" * 70)
    print("  1. Download ALL files")
    print("  2. Select specific files (interactive filtering)")
    print("  3. Quick filter examples:")
    print("     - *.exe (all executables)")
    print("     - *.dll (all DLLs)")
    print("     - data/* (all files in data directory)")
    print("     - *.pak (all PAK archives)")
    print("  0. Cancel")
    
    choice = input("\nSelect option (0-3): ").strip()
    
    if choice == '0':
        print("Cancelled.")
        return
    
    elif choice == '1':
        selected_items = all_items
    
    elif choice == '2':
        selected_items = interactive_filter_menu(all_items)
        if not selected_items:
            print("No files selected. Cancelled.")
            return
    
    elif choice == '3':
        pattern = input("Enter wildcard pattern: ").strip()
        if not pattern:
            print("No pattern provided. Cancelled.")
            return
        selected_items = filter_by_pattern(all_items, pattern)
        if not selected_items:
            print(f"No files match pattern: {pattern}")
            return
    
    else:
        print("Invalid option!")
        return
    
    # Check if we need SFC containers
    needs_sfc = any(item.is_in_sfc for item in selected_items)
    if needs_sfc and sfc_containers:
        print("\nNote: Some selected files are inside SFC containers.")
        print("SFC containers will be downloaded and extracted automatically.")
        # Add SFC containers to download list
        for sfc in sfc_containers:
            if sfc not in selected_items:
                selected_items.append(sfc)
    
    # Step 7: Summary and confirmation
    print("\n" + "=" * 70)
    print("DOWNLOAD SUMMARY")
    print("=" * 70)
    print(f"Game: {game_title}")
    print(f"Build: {selected_build.get('build_id')}")
    print(f"Platform: {platform}")
    print(f"Generation: {manifest.generation}")
    show_items_summary(selected_items, show_details=False)
    
    # Show sample files
    print("\nSample files to download:")
    for item in selected_items[:10]:
        print(f"  - {item.path}")
    if len(selected_items) > 10:
        print(f"  ... and {len(selected_items) - 10} more")
    
    # Step 8: Set output directory
    default_dir = os.path.join("./downloads", product_id, selected_build.get('build_id', 'unknown'))
    output_dir = input(f"\nOutput directory [{default_dir}]: ").strip() or default_dir
    
    print(f"\nFiles will be downloaded to: {output_dir}")
    
    # Step 9: Confirm
    confirm = input("\nProceed with download? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Download cancelled.")
        return
    
    # Step 10: Download
    print("\n" + "=" * 70)
    print("STARTING DOWNLOAD")
    print("=" * 70)
    
    os.makedirs(output_dir, exist_ok=True)
    downloader = GalaxyDownloader(api, max_workers=8)
    
    # Download with progress
    results = downloader.download_depot_items(
        selected_items,
        output_dir,
        verify_hash=True,
        delete_sfc_after_extraction=True  # Clean up SFC containers after extraction
    )
    
    # Step 11: Results
    print("\n" + "=" * 70)
    print("DOWNLOAD COMPLETE")
    print("=" * 70)
    
    successful = sum(1 for path in results.values() if path is not None)
    failed = len(results) - successful
    
    print(f"Successfully downloaded: {successful}/{len(results)} files")
    if failed > 0:
        print(f"Failed: {failed} files")
        print("\nFailed files:")
        for item_path, result_path in results.items():
            if result_path is None:
                print(f"  - {item_path}")
    
    print(f"\nFiles saved to: {output_dir}")


if __name__ == "__main__":
    main()
