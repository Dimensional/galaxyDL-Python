"""
Manage GOG game dependencies separately from game files.

This script handles downloading and managing redistributables (MSVC, DirectX, etc.)
in a separate location for archival purposes.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from galaxy_dl.api import GalaxyAPI
from galaxy_dl.auth import AuthManager
from galaxy_dl.dependencies import DependencyManager


# Global symbol variables (set by setup_symbols)
SYMBOL_CHECK = '[OK]'
SYMBOL_ERROR = '[ERROR]'
SYMBOL_INSTALLED = 'X'
SYMBOL_NOT_INSTALLED = ' '


def detect_unicode_support(force_ascii=False):
    """
    Detect if the terminal supports Unicode output.
    
    Args:
        force_ascii: If True, force ASCII mode regardless of terminal support
    
    Returns:
        True if Unicode is supported, False otherwise
    """
    # Check for explicit force ASCII flag
    if force_ascii:
        return False
    
    # Check for environment variable to force ASCII mode
    if os.environ.get('FORCE_ASCII', '').lower() in ('1', 'true', 'yes'):
        return False
    
    # Check if stdout encoding supports Unicode
    try:
        encoding = sys.stdout.encoding or ''
        if encoding.lower() in ('utf-8', 'utf8'):
            return True
        
        # Try to encode a Unicode character
        '✓'.encode(encoding)
        return True
    except (UnicodeEncodeError, AttributeError, LookupError):
        return False


def setup_symbols(force_ascii=False):
    """
    Set up symbol variables based on Unicode support.
    
    Args:
        force_ascii: If True, force ASCII mode
    """
    global SYMBOL_CHECK, SYMBOL_ERROR, SYMBOL_INSTALLED, SYMBOL_NOT_INSTALLED
    
    use_unicode = detect_unicode_support(force_ascii)
    
    if use_unicode:
        SYMBOL_CHECK = '✓'
        SYMBOL_ERROR = '✗'
        SYMBOL_INSTALLED = '✓'
        SYMBOL_NOT_INSTALLED = ' '
    else:
        SYMBOL_CHECK = '[OK]'
        SYMBOL_ERROR = '[ERROR]'
        SYMBOL_INSTALLED = 'X'
        SYMBOL_NOT_INSTALLED = ' '


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
        print(f"{SYMBOL_CHECK} Dependency system initialized in: {dep_manager.base_path}")
        print(f"{SYMBOL_CHECK} Repository metadata saved")
        print(f"{SYMBOL_CHECK} {len(dep_manager.repository.dependencies)} dependencies available")
        return 0
    else:
        print(f"{SYMBOL_ERROR} Failed to initialize dependency system")
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
        print(f"{SYMBOL_ERROR} Failed to initialize dependency system")
        return 1
    
    # Load depot/repository file to get dependencies
    file_path = Path(args.file_path)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        return 1
    
    with open(file_path, 'r') as f:
        try:
            data = json.load(f)
        except:
            # Try decompressing first
            import zlib
            f.seek(0)
            content = f.read()
            if isinstance(content, str):
                content = content.encode()
            decompressed = zlib.decompress(content)
            data = json.loads(decompressed)
    
    # Detect version and extract dependencies
    version = data.get("version")
    dependency_ids = []
    
    if version == 1:
        # V1: Extract from redist objects in product.depots array
        print("Detected V1 format (repository.json)")
        product = data.get("product", {})
        depots = product.get("depots", [])
        for depot in depots:
            if "redist" in depot:
                dependency_ids.append(depot["redist"])
    elif version == 2:
        # V2: Extract from dependencies array
        print("Detected V2 format (depot.json)")
        dependency_ids = data.get("dependencies", [])
    else:
        print(f"Error: Unknown or missing version field: {version}")
        return 1
    
    if not dependency_ids:
        print("No dependencies found.")
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
        print(f"{SYMBOL_ERROR} Failed to initialize dependency system")
        return 1
    
    # Load depot/repository file
    file_path = Path(args.file_path)
    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        return 1
    
    with open(file_path, 'r') as f:
        try:
            data = json.load(f)
        except:
            # Try decompressing first
            import zlib
            f.seek(0)
            content = f.read()
            if isinstance(content, str):
                content = content.encode()
            decompressed = zlib.decompress(content)
            data = json.loads(decompressed)
    
    # Detect version and extract dependencies
    version = data.get("version")
    dependency_ids = []
    
    if version == 1:
        # V1: Extract from redist objects in product.depots array
        print("Detected V1 format (repository.json)")
        product = data.get("product", {})
        depots = product.get("depots", [])
        for depot in depots:
            if "redist" in depot:
                dependency_ids.append(depot["redist"])
    elif version == 2:
        # V2: Extract from dependencies array
        print("Detected V2 format (depot.json)")
        dependency_ids = data.get("dependencies", [])
    else:
        print(f"Error: Unknown or missing version field: {version}")
        return 1
    
    if not dependency_ids:
        print("No dependencies found.")
        return 0
    
    # Get all dependencies (include_redist=True to show everything)
    deps = dep_manager.get_dependencies_for_game(
        dependency_ids,
        include_redist=True
    )
    
    if not deps:
        print("No matching dependencies found in repository.")
        return 0
    
    print(f"\nDownloading {len(deps)} dependencies...")
    print("=" * 80)
    
    success_count = 0
    for dep in deps:
        if dep_manager.download_dependency(dep):
            success_count += 1
    
    print("=" * 80)
    print(f"\n{SYMBOL_CHECK} Successfully downloaded {success_count}/{len(deps)} dependencies")
    
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
        print(f"{SYMBOL_ERROR} Failed to initialize dependency system")
        return 1
    
    deps = sorted(dep_manager.repository.dependencies.values(), key=lambda d: d.id)
    
    print(f"\nTotal dependencies in repository: {len(deps)}")
    print("=" * 80)
    
    for dep in deps:
        installed = SYMBOL_INSTALLED if dep.id in dep_manager.installed else SYMBOL_NOT_INSTALLED
        size_mb = dep.compressed_size / (1024 * 1024)
        redist = "(redist)" if dep.is_redist else ""
        print(f"[{installed}] {dep.id:25} {size_mb:8.2f} MB  {redist}")
    
    print("=" * 80)
    return 0


def cmd_download_all(args):
    """Download all available dependencies."""
    # Setup authentication
    auth_manager = AuthManager()
    if not auth_manager.is_authenticated():
        print("Error: Not authenticated. Run 'galaxy-dl login' first.")
        return 1
    
    api = GalaxyAPI(auth_manager)
    
    # Initialize dependency manager
    dep_manager = DependencyManager(api, base_path=args.path)
    if not dep_manager.initialize():
        print(f"{SYMBOL_ERROR} Failed to initialize dependency system")
        return 1
    
    deps = sorted(dep_manager.repository.dependencies.values(), key=lambda d: d.id)
    
    print(f"\nDownloading all {len(deps)} dependencies...")
    print("=" * 80)
    
    success_count = 0
    for dep in deps:
        if dep_manager.download_dependency(dep):
            success_count += 1
    
    print("=" * 80)
    print(f"\n{SYMBOL_CHECK} Successfully downloaded {success_count}/{len(deps)} dependencies")
    
    if success_count < len(deps):
        return 1
    
    return 0


def cmd_download(args):
    """Download a specific dependency by name."""
    # Setup authentication
    auth_manager = AuthManager()
    if not auth_manager.is_authenticated():
        print("Error: Not authenticated. Run 'galaxy-dl login' first.")
        return 1
    
    api = GalaxyAPI(auth_manager)
    
    # Initialize dependency manager
    dep_manager = DependencyManager(api, base_path=args.path)
    if not dep_manager.initialize():
        print(f"{SYMBOL_ERROR} Failed to initialize dependency system")
        return 1
    
    # Get the dependency
    dep = dep_manager.repository.get_dependency(args.dependency_name)
    if not dep:
        print(f"Error: Dependency '{args.dependency_name}' not found.")
        print(f"\nAvailable dependencies:")
        for dep_id in sorted(dep_manager.repository.dependencies.keys()):
            print(f"  - {dep_id}")
        return 1
    
    # Download it
    print(f"Downloading {dep.id}...")
    size_mb = dep.compressed_size / (1024 * 1024)
    print(f"Size: {size_mb:.2f} MB")
    print(f"Path: {dep.executable_path}")
    print("=" * 80)
    
    if dep_manager.download_dependency(dep):
        print("=" * 80)
        print(f"\n{SYMBOL_CHECK} Successfully downloaded {dep.id}")
        return 0
    else:
        print("=" * 80)
        print(f"\n{SYMBOL_ERROR} Failed to download {dep.id}")
        return 1


def cmd_update(args):
    """Update the dependency repository from GOG."""
    # Setup authentication
    auth_manager = AuthManager()
    if not auth_manager.is_authenticated():
        print("Error: Not authenticated. Run 'galaxy-dl login' first.")
        return 1
    
    api = GalaxyAPI(auth_manager)
    
    # Initialize dependency manager (this will fetch latest repository)
    print("Fetching latest dependency repository from GOG...")
    dep_manager = DependencyManager(api, base_path=args.path)
    if not dep_manager.initialize():
        print(f"{SYMBOL_ERROR} Failed to update dependency repository")
        return 1
    
    print(f"\n{SYMBOL_CHECK} Repository updated successfully")
    print(f"Build ID: {dep_manager.repository.repository.get('build_id', 'unknown')}")
    print(f"Total dependencies: {len(dep_manager.repository.dependencies)}")
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
    
    parser.add_argument(
        '--ascii',
        action='store_true',
        help='Force ASCII output (disable Unicode symbols)'
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
        'file_path',
        help='Path to depot/repository JSON file (V1: repository.json, V2: *_depot.json)'
    )
    
    # Download game dependencies
    parser_download = subparsers.add_parser(
        'download-game',
        help='Download dependencies for a specific game'
    )
    parser_download.add_argument(
        'file_path',
        help='Path to depot/repository JSON file (V1: repository.json, V2: *_depot.json)'
    )
    
    # List all dependencies
    parser_list_all = subparsers.add_parser(
        'list-all',
        help='List all available dependencies in repository'
    )
    
    # Download all dependencies
    parser_download_all = subparsers.add_parser(
        'download-all',
        help='Download all available dependencies (66 total)'
    )
    
    # Download specific dependency
    parser_download = subparsers.add_parser(
        'download',
        help='Download a specific dependency by name'
    )
    parser_download.add_argument(
        'dependency_name',
        help='Name of the dependency to download (e.g., MSVC2010_x64, DirectX)'
    )
    
    # Update dependency repository
    parser_update = subparsers.add_parser(
        'update',
        help='Update the dependency repository from GOG'
    )
    
    args = parser.parse_args()
    
    setup_logging(args.verbose)
    
    # Setup symbol variables based on --ascii flag
    setup_symbols(force_ascii=args.ascii)
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Route to command
    commands = {
        'init': cmd_init,
        'list-game': cmd_list_game,
        'download-game': cmd_download_game,
        'list-all': cmd_list_all,
        'download-all': cmd_download_all,
        'download': cmd_download,
        'update': cmd_update,
    }
    
    return commands[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
