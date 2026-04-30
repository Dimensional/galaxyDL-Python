#!/usr/bin/env python3
"""
Download Web Files Example

Demonstrates downloading non-Galaxy files (installers, extras, patches).
This is separate from Galaxy CDN depot downloads and handles simple HTTP files.

Features:
- Parallel downloads (8 workers) for large files (>50 MB) with range request support
- Chunk-by-chunk MD5 verification (10 MiB chunks matching GOG's standard)
- Automatic XML checksum generation and saving
- Fast library searching with lightweight JSON cache (library_cache.json)

IMPORTANT: For fast searches, first build the library cache:
    galaxy-dl cache-update
    
NOTE: This uses LibraryCache (lightweight JSON index) for fast slug lookups,
      NOT gog_library.db (comprehensive SQLite database from list_library.py).
      The JSON cache is optimized for quick game ID resolution during downloads.

Usage:
    python download_web.py <game_id_or_slug_or_pattern>
    
Examples:
    # By game ID
    python download_web.py 1207658924
    
    # By slug (lgogdownloader style - FAST with cache)
    python download_web.py the_witcher_3
    python download_web.py beneath_the_steel_sky
    python download_web.py doom_3
    
    # By exact title (case-insensitive)
    python download_web.py "The Witcher 3"
    
    # By regex pattern
    python download_web.py "^Witcher.*"
    python download_web.py ".*Final Fantasy.*"
"""

import sys
import os
import re
from pathlib import Path

# Add parent directory to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent))

from galaxy_dl import GalaxyAPI, AuthManager, WebDownloader, LibraryCache
from galaxy_dl.utils import filter_games_by_pattern


def format_size(size_bytes: float) -> str:
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


def resolve_game_id(api: GalaxyAPI, cache: LibraryCache, identifier: str) -> tuple:
    """
    Resolve game identifier (ID, slug, title, or pattern) to game ID, title, and slug.
    
    Uses local cache for fast lookups, falling back to API if needed.
    
    Args:
        api: GalaxyAPI instance
        cache: LibraryCache instance
        identifier: Game ID, slug, title, or regex pattern
        
    Returns:
        Tuple of (game_id, title, slug)
    """
    # Try as numeric ID first
    try:
        game_id = int(identifier)
        print(f"Looking up game ID {game_id}...")
        details = api.get_game_details(game_id)
        
        # Check if game has downloadable content
        if not details or not isinstance(details, dict) or not details.get("title"):
            print(f"Game {game_id} details not available (API returned empty list)")
            print("This might be a package ID or DLC entry.\n")
            raise ValueError("Invalid game ID")
        
        title = details.get('title', 'Unknown Game')
        
        # Try to get slug from cache first (more reliable than game_details)
        games = cache.load()
        cached_game = games.get(str(game_id))
        slug = cached_game.get('slug', str(game_id)) if cached_game else str(game_id)
        
        print(f"✓ Found: {title}\n")
        return game_id, title, slug
    except (ValueError, TypeError):
        pass
    
    # Load cache (update if stale or missing)
    games = cache.load()
    age = cache.get_age_days()
    
    if not games:
        # Cache is empty or doesn't exist
        print("Building library cache for first time...")
        print("Run 'galaxy-dl cache-update' to refresh later.\n")
        games = cache.update_from_api(api)
    elif age is None or age > 7:
        # Cache exists but is old or corrupted
        if age is not None:
            print(f"Updating stale library cache ({age:.1f} days old)...")
        else:
            print("Updating library cache (cache file corrupted)...")
        print("Run 'galaxy-dl cache-update' to refresh manually.\n")
        games = cache.update_from_api(api)
    else:
        # Cache is fresh
        print(f"Using cached library ({len(games)} games, {age:.1f} days old)\n")
    
    # Try slug lookup (fast, lgogdownloader style)
    identifier_lower = identifier.lower().replace(' ', '_')
    game = cache.find_by_slug(identifier_lower)
    if game:
        print(f"✓ Found by slug: {game['title']}\n")
        return game['id'], game['title'], game['slug']
    
    # Try exact title match (case-insensitive)
    game = cache.find_by_title(identifier)
    if game:
        print(f"✓ Found by title: {game['title']}\n")
        return game['id'], game['title'], game['slug']
    
    # Try pattern matching
    print(f"Searching for pattern: '{identifier}'...")
    try:
        matches = cache.search(identifier, use_regex=True, case_sensitive=False)
        
        if not matches:
            print(f"\n✗ No games match: '{identifier}'")
            print("\nTry:")
            print("  - A game slug (e.g., 'the_witcher_3')")
            print("  - An exact title (e.g., 'The Witcher 3')")
            print("  - A regex pattern (e.g., '^Witcher.*')")
            print("  - A numeric game ID")
            sys.exit(1)
        
        if len(matches) == 1:
            game = matches[0]
            print(f"\n✓ Found match: {game['title']}\n")
            return game['id'], game['title'], game['slug']
        
        # Multiple matches - let user choose
        print(f"\n✓ Found {len(matches)} games matching '{identifier}':\n")
        for idx, game in enumerate(matches, 1):
            print(f"  {idx}. {game['title']}")
            print(f"      Slug: {game['slug']}, ID: {game['id']}")
        
        print("\nEnter number to select, or 'q' to quit: ", end='')
        choice = input().strip()
        
        if choice.lower() == 'q':
            sys.exit(0)
        
        try:
            selection = int(choice)
            if 1 <= selection <= len(matches):
                game = matches[selection - 1]
                print(f"\nSelected: {game['title']}\n")
                return game['id'], game['title'], game['slug']
        except ValueError:
            pass
        
        print("✗ Invalid selection")
        sys.exit(1)
        
    except Exception as e:
        print(f"\n✗ Error searching: {e}")
        sys.exit(1)


def main():
    if len(sys.argv) < 2:
        print("Usage: python download_web.py <game_id_or_slug_or_pattern>")
        print("\nFor fast searches, first build the library cache:")
        print("  galaxy-dl cache-update")
        print("\nExamples:")
        print("  python download_web.py 1207658924                    # By game ID")
        print("  python download_web.py the_witcher_3                 # By slug (FAST)")
        print("  python download_web.py doom_3                        # By slug")
        print("  python download_web.py \"The Witcher 3\"               # By exact title")
        print("  python download_web.py \"^Witcher.*\"                   # By regex pattern")
        print("  python download_web.py \".*Final Fantasy.*\"            # Pattern matching")
        sys.exit(1)
    
    identifier = sys.argv[1]
    
    # Initialize
    print("Initializing...")
    auth = AuthManager()
    api = GalaxyAPI(auth)
    web_dl = WebDownloader(auth, max_workers=8)  # Enable parallel downloads (8 workers)
    cache = LibraryCache()
    
    # Resolve identifier to game ID
    game_id, title, slug = resolve_game_id(api, cache, identifier)
    
    # Get game details
    print(f"Fetching game details...")
    details = api.get_game_details(game_id)
    
    if not details:
        print("Failed to get game details!")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"Game: {title}")
    print(f"Slug: {slug}")
    print(f"ID:   {game_id}")
    print(f"{'='*60}")
    
    # Show available downloads
    print("\n=== AVAILABLE DOWNLOADS ===\n")
    
    # Installers
    # downloads is a list of [language_string, {platform: [files]}] tuples
    installers_count = 0
    downloads = details.get('downloads', [])
    if downloads:
        print("INSTALLERS:")
        for lang, platforms in downloads:
            # platforms is a dict like {"windows": [...], "mac": [...]}
            for platform, files in platforms.items():
                for file_entry in files:
                    installers_count += 1
                    name = file_entry.get('name', 'Unknown')
                    size_str = file_entry.get('size', '0')
                    version = file_entry.get('version', 'N/A')
                    print(f"  [{installers_count}] {name}")
                    print(f"      Language: {lang}")
                    print(f"      Platform: {platform}")
                    print(f"      Version: {version}")
                    print(f"      Size: {size_str}")
    
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
    # downloads is a list of [language, {platform: [files]}] tuples
    file_idx = 0
    for lang, platforms in downloads:
        for platform, files in platforms.items():
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
        
        # Get and display downlink info
        try:
            downlink_info = web_dl.get_downlink_info(file_entry["manualUrl"])
            download_url = downlink_info["downlink"]
            checksum_url = downlink_info.get("checksum", "")
            
            print(f"  Download URL: {download_url}")
            if checksum_url:
                print(f"  Checksum XML: {checksum_url}")
            else:
                print(f"  Checksum XML: [Not available from GOG]")
        except Exception as e:
            print(f"  ✗ Failed to get download URLs: {e}\n")
            continue
        
        # Determine output directory
        if file_type == 'installer':
            output_dir = os.path.join(output_base, "installers")
        else:
            output_dir = os.path.join(output_base, "extras")
        
        # Get checksum info if available
        if checksum_url:
            checksum_info = web_dl.get_checksum_info(checksum_url)
            expected_md5 = checksum_info.get("md5")
            num_chunks = len(checksum_info.get("chunks", []))
            if expected_md5:
                print(f"  Expected MD5: {expected_md5}")
                if num_chunks > 0:
                    print(f"  Verification chunks: {num_chunks} (10 MiB each)")
            else:
                print(f"  Warning: Checksum XML exists but no MD5 found")
        else:
            expected_md5 = None
            num_chunks = 0
            print(f"  No GOG checksum - will generate MD5 during download")
        
        try:
            downloaded_path = web_dl.download_from_game_details(
                file_entry,
                output_dir=output_dir,
                verify_checksum=True,
                progress_callback=progress_callback
            )
            
            # Show verification status
            print()  # New line after progress
            if checksum_url and expected_md5:
                print(f"  ✓ All {num_chunks} chunks verified")
                print(f"  ✓ File MD5 verified: {expected_md5}")
            else:
                print(f"  ✓ Generated checksums")
            print(f"  ✓ Saved to: {downloaded_path}")
            print(f"  ✓ Checksum XML: {downloaded_path}.xml\n")
            
        except Exception as e:
            print(f"\n  ✗ Failed: {e}\n")
    
    print(f"{'='*60}")
    print("Download complete!")
    print(f"Files saved to: {output_base}")


if __name__ == "__main__":
    main()
