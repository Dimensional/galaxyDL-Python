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
    # If no code provided, show instructions
    if not args.code:
        print("=" * 80)
        print("GOG AUTHENTICATION INSTRUCTIONS")
        print("=" * 80)
        print("\nStep 1: Visit this URL in your browser:")
        print("\n  https://auth.gog.com/auth?client_id=46899977096215655&")
        print("  redirect_uri=https%3A%2F%2Fembed.gog.com%2Fon_login_success%3Forigin%3Dclient&")
        print("  response_type=code&layout=client2")
        print("\nStep 2: Log in to your GOG account")
        print("\nStep 3: After successful login, you'll be redirected to a blank page.")
        print("        The URL will look like:")
        print("        https://embed.gog.com/on_login_success?origin=client&code=XXXXXXX...")
        print("\nStep 4: Copy the entire code after 'code=' (it's very long!)")
        print("\nStep 5: Run this command:")
        print("        galaxy-dl login <YOUR_CODE>")
        print("\n" + "=" * 80)
        return 1
    
    auth = AuthManager(config_path=args.config)
    
    print("Authenticating with GOG...")
    
    if auth.login_with_code(args.code):
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


def cmd_library(args):
    """Handle library command to show owned games."""
    auth = AuthManager(config_path=args.config)
    
    if not auth.is_authenticated():
        print("✗ Not authenticated. Please run 'galaxy-dl login' first.")
        return 1
    
    api = GalaxyAPI(auth)
    
    print("Fetching your game library...")
    
    try:
        game_ids = api.get_owned_games()
        
        if not game_ids:
            print("✗ No games found in library")
            return 1
        
        print(f"\n✓ Found {len(game_ids)} games in your library")
        
        if args.details:
            print("\nFetching game details (this may take a moment)...\n")
            for idx, game_id in enumerate(game_ids[:args.limit], 1):
                try:
                    details = api.get_game_details(game_id)
                    title = details.get("title", "Unknown")
                    print(f"{idx:4}. {title} (ID: {game_id})")
                except Exception as e:
                    print(f"{idx:4}. Game ID: {game_id} (Error: {e})")
            
            if len(game_ids) > args.limit:
                print(f"\n... and {len(game_ids) - args.limit} more games")
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
    login_parser.set_defaults(func=cmd_login)
    
    # Library command
    library_parser = subparsers.add_parser("library", help="List owned games")
    library_parser.add_argument(
        "--details",
        action="store_true",
        help="Fetch game titles (slower)"
    )
    library_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum games to show (default: 50)"
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
