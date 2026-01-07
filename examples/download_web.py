#!/usr/bin/env python3
"""
Download Web Files Example

Demonstrates downloading non-Galaxy files (installers, extras, patches).
This is separate from Galaxy CDN depot downloads and handles simple HTTP files.

Usage:
    python download_web.py <game_id>
    
Example:
    python download_web.py 1207658924
"""

import sys
import os
from pathlib import Path

# Add parent directory to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent))

from galaxy_dl import GalaxyAPI, AuthManager, WebDownloader


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def progress_callback(downloaded: int, total: int):
    """Simple progress callback."""
    if total > 0:
        percent = (downloaded / total) * 100
        print(f"\r  Progress: {format_size(downloaded)} / {format_size(total)} ({percent:.1f}%)", end='', flush=True)
    else:
        print(f"\r  Downloaded: {format_size(downloaded)}", end='', flush=True)


def main():
    if len(sys.argv) < 2:
        print("Usage: python download_web.py <game_id>")
        print("Example: python download_web.py 1207658924")
        sys.exit(1)
    
    game_id = int(sys.argv[1])
    
    # Initialize
    print("Initializing...")
    auth = AuthManager()
    api = GalaxyAPI(auth)
    web_dl = WebDownloader(auth)
    
    # Get game details
    print(f"\nFetching game details for ID {game_id}...")
    details = api.get_game_details(game_id)
    
    if not details:
        print("Failed to get game details!")
        sys.exit(1)
    
    title = details.get('title', 'Unknown Game')
    print(f"\n{'='*60}")
    print(f"Game: {title}")
    print(f"{'='*60}")
    
    # Show available downloads
    print("\n=== AVAILABLE DOWNLOADS ===\n")
    
    # Installers
    installers_count = 0
    downloads = details.get('downloads', [])
    if downloads:
        print("INSTALLERS:")
        for item in downloads:
            lang = item.get('language', 'unknown')
            lang_full = item.get('language_full', lang)
            
            # Count files across all platforms
            for platform, files in item.items():
                if platform in ['language', 'language_full']:
                    continue
                if isinstance(files, list):
                    for file_entry in files:
                        installers_count += 1
                        name = file_entry.get('name', 'Unknown')
                        size = file_entry.get('size', 0)
                        version = file_entry.get('version', 'N/A')
                        print(f"  [{installers_count}] {name}")
                        print(f"      Language: {lang_full}")
                        print(f"      Platform: {platform}")
                        print(f"      Version: {version}")
                        print(f"      Size: {format_size(int(size))}")
    
    # Extras
    extras = details.get('extras', [])
    if extras:
        print(f"\nEXTRAS ({len(extras)} items):")
        for idx, extra in enumerate(extras, 1):
            name = extra.get('name', 'Unknown')
            size = extra.get('size', 0)
            type_name = extra.get('type', 'extra')
            print(f"  [{installers_count + idx}] {name}")
            print(f"      Type: {type_name}")
            print(f"      Size: {format_size(int(size))}")
    
    if installers_count == 0 and len(extras) == 0:
        print("No downloadable files found for this game.")
        return
    
    # Let user select what to download
    print(f"\n{'='*60}")
    print("Enter file numbers to download (comma-separated) or 'all' for everything:")
    print("Example: 1,3,5 or all")
    
    choice = input("\nYour choice: ").strip().lower()
    
    # Parse selection
    selected_indices = []
    if choice == 'all':
        selected_indices = list(range(1, installers_count + len(extras) + 1))
    else:
        try:
            selected_indices = [int(x.strip()) for x in choice.split(',')]
        except ValueError:
            print("Invalid input!")
            return
    
    # Collect files to download
    files_to_download = []
    
    # Add installers
    file_idx = 0
    for item in downloads:
        for platform, files in item.items():
            if platform in ['language', 'language_full']:
                continue
            if isinstance(files, list):
                for file_entry in files:
                    file_idx += 1
                    if file_idx in selected_indices:
                        files_to_download.append({
                            'entry': file_entry,
                            'type': 'installer',
                            'name': file_entry.get('name', 'Unknown')
                        })
    
    # Add extras
    for idx, extra in enumerate(extras, installers_count + 1):
        if idx in selected_indices:
            files_to_download.append({
                'entry': extra,
                'type': 'extra',
                'name': extra.get('name', 'Unknown')
            })
    
    if not files_to_download:
        print("No files selected!")
        return
    
    # Create output directory
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
    output_base = f"./downloads/{safe_title}"
    
    # Download selected files
    print(f"\n{'='*60}")
    print(f"Downloading {len(files_to_download)} file(s)...")
    print(f"{'='*60}\n")
    
    for idx, item in enumerate(files_to_download, 1):
        file_entry = item['entry']
        file_type = item['type']
        name = item['name']
        
        print(f"[{idx}/{len(files_to_download)}] {name}")
        
        # Determine output directory
        if file_type == 'installer':
            output_dir = os.path.join(output_base, "installers")
        else:
            output_dir = os.path.join(output_base, "extras")
        
        try:
            downloaded_path = web_dl.download_from_game_details(
                file_entry,
                output_dir=output_dir,
                verify_checksum=True,
                progress_callback=progress_callback
            )
            print(f"\n  ✓ Saved to: {downloaded_path}\n")
            
        except Exception as e:
            print(f"\n  ✗ Failed: {e}\n")
    
    print(f"{'='*60}")
    print("Download complete!")
    print(f"Files saved to: {output_base}")


if __name__ == "__main__":
    main()
