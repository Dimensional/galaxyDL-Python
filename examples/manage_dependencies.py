"""
Manage GOG game dependencies separately from game files.

This script handles downloading and managing redistributables (MSVC, DirectX, etc.)
in a separate location for archival purposes.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from galaxy_dl.api import GalaxyAPI
from galaxy_dl.auth import AuthManager
from galaxy_dl.dependencies import DependencyManager


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def cmd_init(args):
    """Initialize dependency system."""
    # Setup authentication
    auth_manager = AuthManager()
    if not auth_manager.is_authenticated():
        print("Error: Not authenticated. Run 'galaxy-dl login' first.")
        return 1
    
    api = GalaxyAPI(auth_manager)
    
    # Initialize dependency manager
    dep_manager = DependencyManager(api, base_path=args.path)
    
    if dep_manager.initialize():
        print(f"✓ Dependency system initialized in: {dep_manager.base_path}")
        print(f"✓ Repository metadata saved")
        print(f"✓ {len(dep_manager.repository.dependencies)} dependencies available")
        return 0
    else:
        print("✗ Failed to initialize dependency system")
        return 1


def cmd_list_game(args):
    """List dependencies for a specific game."""
    # Setup authentication
    auth_manager = AuthManager()
    if not auth_manager.is_authenticated():
        print("Error: Not authenticated. Run 'galaxy-dl login' first.")
        return 1
    
    api = GalaxyAPI(auth_manager)
    
    # Initialize dependency manager
    dep_manager = DependencyManager(api, base_path=args.path)
    if not dep_manager.initialize():
        print("✗ Failed to initialize dependency system")
        return 1
    
    # Load depot manifest to get dependencies
    depot_path = Path(args.depot_manifest)
    if not depot_path.exists():
        print(f"Error: Depot manifest not found: {depot_path}")
        return 1
    
    with open(depot_path, 'r') as f:
        try:
            depot = json.load(f)
        except:
            # Try decompressing first
            import zlib
            f.seek(0)
            content = f.read()
            if isinstance(content, str):
                content = content.encode()
            decompressed = zlib.decompress(content)
            depot = json.loads(decompressed)
    
    dependency_ids = depot.get("dependencies", [])
    
    if not dependency_ids:
        print("No dependencies found in depot manifest.")
        return 0
    
    dep_manager.list_dependencies(dependency_ids)
    return 0


def cmd_download_game(args):
    """Download dependencies for a specific game."""
    # Setup authentication
    auth_manager = AuthManager()
    if not auth_manager.is_authenticated():
        print("Error: Not authenticated. Run 'galaxy-dl login' first.")
        return 1
    
    api = GalaxyAPI(auth_manager)
    
    # Initialize dependency manager
    dep_manager = DependencyManager(api, base_path=args.path)
    if not dep_manager.initialize():
        print("✗ Failed to initialize dependency system")
        return 1
    
    # Load depot manifest
    depot_path = Path(args.depot_manifest)
    if not depot_path.exists():
        print(f"Error: Depot manifest not found: {depot_path}")
        return 1
    
    with open(depot_path, 'r') as f:
        try:
            depot = json.load(f)
        except:
            # Try decompressing first
            import zlib
            f.seek(0)
            content = f.read()
            if isinstance(content, str):
                content = content.encode()
            decompressed = zlib.decompress(content)
            depot = json.loads(decompressed)
    
    dependency_ids = depot.get("dependencies", [])
    
    if not dependency_ids:
        print("No dependencies found in depot manifest.")
        return 0
    
    # Get dependencies
    deps = dep_manager.get_dependencies_for_game(
        dependency_ids,
        include_redist=args.include_redist
    )
    
    if not deps:
        print("No dependencies to download (all may be __redist bundles).")
        print("Use --include-redist to download Windows installer bundles.")
        return 0
    
    print(f"\nDownloading {len(deps)} dependencies...")
    print("=" * 80)
    
    success_count = 0
    for dep in deps:
        if dep_manager.download_dependency(dep):
            success_count += 1
    
    print("=" * 80)
    print(f"\n✓ Successfully downloaded {success_count}/{len(deps)} dependencies")
    
    if success_count < len(deps):
        return 1
    
    return 0


def cmd_list_all(args):
    """List all available dependencies in repository."""
    # Setup authentication
    auth_manager = AuthManager()
    if not auth_manager.is_authenticated():
        print("Error: Not authenticated. Run 'galaxy-dl login' first.")
        return 1
    
    api = GalaxyAPI(auth_manager)
    
    # Initialize dependency manager
    dep_manager = DependencyManager(api, base_path=args.path)
    if not dep_manager.initialize():
        print("✗ Failed to initialize dependency system")
        return 1
    
    deps = sorted(dep_manager.repository.dependencies.values(), key=lambda d: d.id)
    
    print(f"\nTotal dependencies in repository: {len(deps)}")
    print("=" * 80)
    
    for dep in deps:
        installed = "✓" if dep.id in dep_manager.installed else " "
        size_mb = dep.compressed_size / (1024 * 1024)
        redist = "(redist)" if dep.is_redist else ""
        print(f"[{installed}] {dep.id:25} {size_mb:8.2f} MB  {redist}")
    
    print("=" * 80)
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Manage GOG game dependencies separately from game files"
    )
    
    parser.add_argument(
        '--path',
        default='./dependencies',
        help='Base path for dependency storage (default: ./dependencies)'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Init command
    parser_init = subparsers.add_parser(
        'init',
        help='Initialize dependency system and download repository metadata'
    )
    
    # List game dependencies
    parser_list_game = subparsers.add_parser(
        'list-game',
        help='List dependencies for a specific game'
    )
    parser_list_game.add_argument(
        'depot_manifest',
        help='Path to game depot manifest JSON file'
    )
    
    # Download game dependencies
    parser_download = subparsers.add_parser(
        'download-game',
        help='Download dependencies for a specific game'
    )
    parser_download.add_argument(
        'depot_manifest',
        help='Path to game depot manifest JSON file'
    )
    parser_download.add_argument(
        '--include-redist',
        action='store_true',
        help='Include __redist dependencies (Windows installer bundles)'
    )
    
    # List all dependencies
    parser_list_all = subparsers.add_parser(
        'list-all',
        help='List all available dependencies in repository'
    )
    
    args = parser.parse_args()
    
    setup_logging(args.verbose)
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Route to command
    commands = {
        'init': cmd_init,
        'list-game': cmd_list_game,
        'download-game': cmd_download_game,
        'list-all': cmd_list_all,
    }
    
    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
