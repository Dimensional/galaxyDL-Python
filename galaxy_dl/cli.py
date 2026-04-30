#!/usr/bin/env python3
"""
Command-line interface for galaxy_dl

Minimal CLI utility for authentication and basic product info.
For full functionality, see the examples/ folder.
"""

import argparse
import logging
import sys

from galaxy_dl.api import GalaxyAPI
from galaxy_dl.auth import AuthManager
from galaxy_dl import constants


def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def cmd_login(args):
    """Handle login command."""
    # GUI login if --gui flag is set
    if args.gui:
        try:
            from galaxy_dl.gui_login import gui_login
        except ImportError:
            print("✗ GUI login requires PySide6")
            print("\nInstall with: pip install galaxy-dl[gui]")
            return 1
        
        print("Opening GUI browser for GOG authentication...")
        print("Please sign in and authorize the application in the browser window.")
        print()
        
        code = gui_login()
        
        if not code:
            print("\n✗ Login cancelled or failed")
            return 1
        
        print(f"\n✓ Authorization code captured!")
        
        # Continue with normal login flow using captured code
        auth = AuthManager(config_path=args.config)
        
        print("Authenticating with GOG...")
        
        if auth.login_with_code(code):
            print(f"✓ Successfully authenticated!")
            print(f"✓ Credentials saved to: {auth.config_path}")
            print(f"\nYou can now use:")
            print(f"  - galaxy-dl library         (list your games)")
            print(f"  - galaxy-dl info <GAME_ID>  (show builds)")
            print(f"  - examples/*.py scripts     (download/validate)")
            print(f"\nAll commands and examples will automatically use these credentials.")
            return 0
        else:
            print("✗ Authentication failed")
            return 1
    
    # Manual login (original behavior)
    # If no code provided, show instructions
    if not args.code:
        auth = AuthManager(config_path=args.config)
        
        print("=" * 80)
        print("GOG AUTHENTICATION INSTRUCTIONS")
        print("=" * 80)
        print("\nOption 1: GUI Login (Easier!)")
        print("  Install: pip install galaxy-dl[gui]")
        print("  Run:     galaxy-dl login --gui")
        print("\nOption 2: Manual Login")
        print("\nStep 1: Visit this URL in your browser:")
        print(f"\n  {auth.get_oauth_url()}")
        print("\nStep 2: Log in to your GOG account")
        print("\nStep 3: After successful login, you'll be redirected to a page.")
        print("        The URL will look like:")
        print("        https://embed.gog.com/on_login_success?origin=client&code=XXXXXXX...")
        print("\nStep 4: Copy EITHER:")
        print("        a) The entire URL from the address bar, OR")
        print("        b) Just the code after 'code=' (it's very long!)")
        print("\nStep 5: Run this command:")
        print("        galaxy-dl login <YOUR_CODE_OR_URL>")
        print("\n" + "=" * 80)
        return 1
    
    auth = AuthManager(config_path=args.config)
    
    # Try to extract code from URL first (in case user pasted full URL)
    code = auth.extract_code_from_url(args.code)
    
    # If extraction failed, assume it's already just the code
    if not code:
        code = args.code
    
    print("Authenticating with GOG...")
    
    if auth.login_with_code(code):
        print(f"✓ Successfully authenticated!")
        print(f"✓ Credentials saved to: {auth.config_path}")
        print(f"\nYou can now use:")
        print(f"  - galaxy-dl library         (list your games)")
        print(f"  - galaxy-dl info <GAME_ID>  (show builds)")
        print(f"  - examples/*.py scripts     (download/validate)")
        print(f"\nAll commands and examples will automatically use these credentials.")
        return 0
    else:
        print("✗ Authentication failed")
        print("\nMake sure you:")
        print("  1. Visited the OAuth URL and logged into GOG")
        print("  2. Copied the 'code=' parameter from the redirect URL")
        print("  3. Provided the complete code (it's very long)")
        return 1


def cmd_info(args):
    """Handle info command to show product information."""
    auth = AuthManager(config_path=args.config)
    
    if not auth.is_authenticated():
        print("✗ Not authenticated. Please run 'galaxy-dl login' first.")
        return 1
    
    api = GalaxyAPI(auth)
    
    print(f"Getting information for product {args.product_id}...")
    
    # Get builds
    builds = api.get_all_product_builds(args.product_id, args.platform)
    
    if not builds or "items" not in builds:
        print("✗ No builds found")
        return 1
    
    print(f"\n✓ Found {len(builds['items'])} builds:")
    
    for idx, build in enumerate(builds["items"][:10]):  # Show first 10
        build_id = build.get("build_id", "unknown")
        version = build.get("version_name", "unknown")
        generation = build.get("generation", "unknown")
        date = build.get("date_published", "unknown")
        legacy = build.get("legacy_build_id", "")
        
        gen_str = f"V{generation}" if generation != "unknown" else "V?"
        legacy_str = f" (legacy: {legacy})" if legacy else ""
        
        print(f"  {idx + 1}. [{gen_str}] Build {build_id} - {version} - {date}{legacy_str}")
    
    if len(builds["items"]) > 10:
        print(f"  ... and {len(builds['items']) - 10} more")
    
    print(f"\nFor download/validation, use the scripts in examples/")
    
    return 0


def cmd_cache_update(args):
    """Handle cache-update command to refresh library cache."""
    from galaxy_dl.library_cache import LibraryCache
    
    auth = AuthManager(config_path=args.config)
    
    if not auth.is_authenticated():
        print("✗ Not authenticated. Please run 'galaxy-dl login' first.")
        return 1
    
    api = GalaxyAPI(auth)
    cache = LibraryCache()
    
    # Check if update needed
    if not args.force:
        age = cache.get_age_days()
        if age is not None and age < 1:
            print(f"✓ Cache is fresh ({age:.1f} days old)")
            print("\nUse --force to update anyway")
            return 0
    
    print("Updating library cache (fast lookup index)...")
    print("This builds a lightweight JSON index for quick slug/title searches.")
    print("(DLC entries and unavailable games will be skipped)")
    print("")
    print("NOTE: This is separate from 'python examples/list_library.py'")
    print("      which creates gog_library.db for comprehensive archival.\n")
    
    try:
        # Get total count before update
        game_ids = api.get_owned_games()
        total_entries = len(game_ids) if game_ids else 0
        
        games = cache.update_from_api(api)
        
        skipped = total_entries - len(games)
        
        print(f"\n✓ Successfully cached {len(games)} games")
        if skipped > 0:
            print(f"  (Skipped {skipped} DLC/unavailable entries)")
        print(f"Cache location: {cache.cache_path}")
        print("\nYou can now use fast searches in examples/download_web.py:")
        print("  python examples/download_web.py witcher_3")
        print("  python examples/download_web.py \"^Doom.*\"")
        
        return 0
        
    except Exception as e:
        print(f"✗ Error updating cache: {e}")
        return 1


def cmd_library(args):
    """Handle library command to show owned games."""
    from galaxy_dl.utils import filter_games_by_pattern
    
    auth = AuthManager(config_path=args.config)
    
    if not auth.is_authenticated():
        print("✗ Not authenticated. Please run 'galaxy-dl login' first.")
        return 1
    
    api = GalaxyAPI(auth)
    
    # Pattern matching requires details
    if args.pattern and not args.details:
        print("✗ --pattern requires --details flag (pattern matching needs game titles)")
        return 1
    
    print("Fetching your game library...")
    
    try:
        game_ids = api.get_owned_games()
        
        if not game_ids:
            print("✗ No games found in library")
            return 1
        
        print(f"\n✓ Found {len(game_ids)} games in your library")
        
        if args.details:
            print("\nFetching game details (this may take a moment)...\n")
            
            # Fetch all games for pattern matching, or limited set otherwise
            fetch_count = len(game_ids) if args.pattern else min(args.limit, len(game_ids))
            
            games = []
            for game_id in game_ids[:fetch_count]:
                try:
                    details = api.get_game_details(game_id)
                    games.append({
                        'id': game_id,
                        'title': details.get("title", "Unknown")
                    })
                except Exception as e:
                    games.append({
                        'id': game_id,
                        'title': f"[Error: {e}]"
                    })
            
            # Apply pattern filter if specified
            if args.pattern:
                try:
                    filtered_games = filter_games_by_pattern(
                        games, 
                        args.pattern, 
                        case_sensitive=args.case_sensitive
                    )
                    print(f"Pattern: '{args.pattern}' (case-{'sensitive' if args.case_sensitive else 'insensitive'})")
                    print(f"Matches: {len(filtered_games)} of {len(games)} games\n")
                    games = filtered_games
                except ValueError as e:
                    print(f"✗ {e}")
                    return 1
            
            # Display results
            if not games:
                print("No games match the pattern")
                return 0
            
            for idx, game in enumerate(games, 1):
                print(f"{idx:4}. {game['title']} (ID: {game['id']})")
            
            if not args.pattern and len(game_ids) > args.limit:
                print(f"\n... and {len(game_ids) - args.limit} more games")
                print("Use --limit to show more, or --pattern to filter")
        else:
            print("\nGame IDs:")
            for idx, game_id in enumerate(game_ids[:args.limit], 1):
                print(f"{idx:4}. {game_id}")
            
            if len(game_ids) > args.limit:
                print(f"\n... and {len(game_ids) - args.limit} more")
            
            print("\nUse --details to fetch game titles")
        
        print(f"\nFor full library browsing, see examples/list_library.py")
        
        return 0
        
    except Exception as e:
        print(f"✗ Error fetching library: {e}")
        return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Galaxy DL - GOG Galaxy CDN Downloader Library\n\n"
                    "This is a minimal CLI for basic authentication and info.\n"
                    "For full download/validation functionality, see examples/",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
               "  galaxy-dl login                   # Show authentication instructions\n"
               "  galaxy-dl login CODE              # Authenticate with OAuth code\n"
               "  galaxy-dl cache-update            # Build/refresh library cache (faster searches)\n"
               "  galaxy-dl library --details       # List owned games\n"
               "  galaxy-dl info 1207658930         # Show builds for a game\n\n"
               "For more: https://github.com/Dimensional/galaxyDL-Python/tree/main/examples"
    )
    
    parser.add_argument(
        "--config",
        default=None,
        help="Path to auth config file (default: ~/.config/galaxy_dl/auth.json)"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Login command
    login_parser = subparsers.add_parser(
        "login", 
        help="Authenticate with GOG",
        description="GOG OAuth2 Authentication\n\n"
                    "Steps:\n"
                    "  1. Visit this URL in your browser:\n"
                    "     https://auth.gog.com/auth?client_id=46899977096215655&\n"
                    "     redirect_uri=https%3A%2F%2Fembed.gog.com%2Fon_login_success%3Forigin%3Dclient&\n"
                    "     response_type=code&layout=client2\n\n"
                    "  2. Log in to your GOG account\n\n"
                    "  3. After login, you'll be redirected to a blank page.\n"
                    "     Copy the 'code=' parameter from the URL\n\n"
                    "  4. Run: galaxy-dl login <CODE>\n\n"
                    "The credentials will be saved to ~/.config/galaxy_dl/auth.json\n"
                    "and automatically used by all examples/",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    login_parser.add_argument(
        "code",
        nargs="?",
        help="OAuth authorization code from GOG (the value after 'code=' in the redirect URL)"
    )
    login_parser.add_argument(
        "--gui",
        action="store_true",
        help="Use GUI browser for login (requires: pip install galaxy-dl[gui])"
    )
    login_parser.set_defaults(func=cmd_login)
    
    # Cache update command
    cache_parser = subparsers.add_parser(
        "cache-update",
        help="Update local library cache",
        description="Update local library cache for faster game lookups.\n\n"
                    "The cache stores game IDs, titles, and slugs locally, enabling\n"
                    "instant searches instead of querying the API each time.\n\n"
                    "Cache location: ~/.config/galaxy_dl/library_cache.json",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    cache_parser.add_argument(
        "--force",
        action="store_true",
        help="Force update even if cache is fresh"
    )
    cache_parser.set_defaults(func=cmd_cache_update)
    
    # Library command
    library_parser = subparsers.add_parser("library", help="List owned games")
    library_parser.add_argument(
        "--details",
        action="store_true",
        help="Fetch game titles (slower)"
    )
    library_parser.add_argument(
        "--pattern",
        type=str,
        help="Filter games by regex pattern (requires --details, Perl syntax)"
    )
    library_parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="Make pattern matching case-sensitive (default: case-insensitive)"
    )
    library_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum games to show (default: 50, ignored when using --pattern)"
    )
    library_parser.set_defaults(func=cmd_library)
    
    # Info command
    info_parser = subparsers.add_parser("info", help="Show available builds for a product")
    info_parser.add_argument("product_id", help="GOG product ID")
    info_parser.add_argument(
        "--platform",
        default=constants.PLATFORM_WINDOWS,
        choices=constants.PLATFORMS,
        help="Platform (default: windows)"
    )
    info_parser.set_defaults(func=cmd_info)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    setup_logging(args.verbose)
    
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 130
    except Exception as e:
        logging.exception("Unexpected error")
        print(f"\n✗ Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
