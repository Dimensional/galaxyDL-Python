#!/usr/bin/env python3
"""
Command-line interface for galaxy_dl

Provides easy CLI access to Galaxy download functionality
"""

import argparse
import logging
import sys
from pathlib import Path

from galaxy_dl import GalaxyAPI, AuthManager, GalaxyDownloader
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
    auth = AuthManager(config_path=args.config)
    
    if auth.login_with_code(args.code):
        print("✓ Successfully authenticated!")
        return 0
    else:
        print("✗ Authentication failed")
        return 1


def cmd_info(args):
    """Handle info command to show product information."""
    auth = AuthManager(config_path=args.config)
    
    if not auth.is_authenticated():
        print("✗ Not authenticated. Please run 'login' first.")
        return 1
    
    api = GalaxyAPI(auth)
    
    print(f"Getting information for product {args.product_id}...")
    
    # Get builds
    builds = api.get_product_builds(args.product_id, args.platform)
    
    if not builds or "items" not in builds:
        print("✗ No builds found")
        return 1
    
    print(f"\n✓ Found {len(builds['items'])} builds:")
    
    for idx, build in enumerate(builds["items"][:5]):  # Show first 5
        build_id = build.get("build_id", "unknown")
        version = build.get("version_name", "unknown")
        date = build.get("date_published", "unknown")
        print(f"  {idx + 1}. Build {build_id} - Version {version} - {date}")
    
    return 0


def cmd_download(args):
    """Handle download command."""
    auth = AuthManager(config_path=args.config)
    
    if not auth.is_authenticated():
        print("✗ Not authenticated. Please run 'login' first.")
        return 1
    
    api = GalaxyAPI(auth)
    downloader = GalaxyDownloader(api, max_workers=args.threads)
    
    print(f"Downloading manifest {args.manifest_hash}...")
    
    # Get depot items
    depot_items = api.get_depot_items(args.manifest_hash)
    
    if not depot_items:
        print("✗ No depot items found")
        return 1
    
    print(f"✓ Found {len(depot_items)} items to download")
    
    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Download items
    completed = 0
    failed = 0
    
    for idx, item in enumerate(depot_items):
        print(f"\n[{idx + 1}/{len(depot_items)}] Downloading: {item.path}")
        
        try:
            def progress(downloaded, total):
                if total > 0:
                    percent = (downloaded / total) * 100
                    print(f"  Progress: {percent:.1f}%", end='\r')
            
            output_path = downloader.download_item(
                item,
                str(output_dir),
                verify_hash=not args.no_verify,
                progress_callback=progress if not args.quiet else None
            )
            
            print(f"  ✓ Saved to: {output_path}")
            completed += 1
            
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            failed += 1
            
            if not args.continue_on_error:
                return 1
    
    print(f"\n{'='*60}")
    print(f"Download complete: {completed} succeeded, {failed} failed")
    
    return 0 if failed == 0 else 1


def cmd_list_items(args):
    """Handle list-items command to show depot items."""
    auth = AuthManager(config_path=args.config)
    
    if not auth.is_authenticated():
        print("✗ Not authenticated. Please run 'login' first.")
        return 1
    
    api = GalaxyAPI(auth)
    
    print(f"Getting depot items for manifest {args.manifest_hash}...")
    
    depot_items = api.get_depot_items(args.manifest_hash)
    
    if not depot_items:
        print("✗ No depot items found")
        return 1
    
    print(f"\n✓ Found {len(depot_items)} items:\n")
    
    total_compressed = 0
    total_uncompressed = 0
    
    for idx, item in enumerate(depot_items):
        size_str = f"{item.total_size_compressed:,} bytes"
        if item.total_size_compressed != item.total_size_uncompressed:
            size_str += f" (compressed from {item.total_size_uncompressed:,})"
        
        print(f"{idx + 1:4}. {item.path}")
        print(f"      Size: {size_str}")
        print(f"      Chunks: {len(item.chunks)}")
        if item.md5:
            print(f"      MD5: {item.md5}")
        print()
        
        total_compressed += item.total_size_compressed
        total_uncompressed += item.total_size_uncompressed
    
    print(f"{'='*60}")
    print(f"Total compressed size: {total_compressed:,} bytes")
    print(f"Total uncompressed size: {total_uncompressed:,} bytes")
    
    return 0


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Galaxy DL - GOG Galaxy CDN Downloader",
        formatter_class=argparse.RawDescriptionHelpFormatter
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
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Login command
    login_parser = subparsers.add_parser("login", help="Authenticate with GOG")
    login_parser.add_argument("code", help="OAuth authorization code")
    login_parser.set_defaults(func=cmd_login)
    
    # Info command
    info_parser = subparsers.add_parser("info", help="Get product information")
    info_parser.add_argument("product_id", help="GOG product ID")
    info_parser.add_argument(
        "--platform",
        default=constants.PLATFORM_WINDOWS,
        choices=constants.PLATFORMS,
        help="Platform"
    )
    info_parser.set_defaults(func=cmd_info)
    
    # List items command
    list_parser = subparsers.add_parser("list-items", help="List depot items in manifest")
    list_parser.add_argument("manifest_hash", help="Manifest hash")
    list_parser.set_defaults(func=cmd_list_items)
    
    # Download command
    download_parser = subparsers.add_parser("download", help="Download depot items")
    download_parser.add_argument("manifest_hash", help="Manifest hash to download")
    download_parser.add_argument(
        "--output", "-o",
        default="./downloads",
        help="Output directory (default: ./downloads)"
    )
    download_parser.add_argument(
        "--threads", "-t",
        type=int,
        default=4,
        help="Number of download threads (default: 4)"
    )
    download_parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip hash verification"
    )
    download_parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue downloading even if some items fail"
    )
    download_parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress progress output"
    )
    download_parser.set_defaults(func=cmd_download)
    
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

