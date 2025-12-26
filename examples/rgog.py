#!/usr/bin/env python3
"""
RGOG - Reproducible GOG Archive Tool

A command-line tool for creating, listing, extracting, and verifying
RGOG (Reproducible GOG) archives following the RGOG Format Specification v2.0.

Usage:
    rgog.py pack <input_dir> -o <output.rgog> [--max-part-size SIZE]
    rgog.py list <archive.rgog> [--detailed] [--build BUILD_ID]
    rgog.py extract <archive.rgog> -o <output_dir> [--build BUILD_ID] [--chunks-only]
    rgog.py verify <archive.rgog> [--build BUILD_ID]
    rgog.py info <archive.rgog>

Commands:
    pack      Create an RGOG archive from a GOG v2 directory structure
    list      List contents of an RGOG archive
    extract   Extract builds and/or chunks from an RGOG archive
    verify    Verify MD5 checksums of all data in an RGOG archive
    info      Display statistics and information about an RGOG archive
"""

import argparse
import sys
from pathlib import Path

# Import subcommands
from rgog import pack, list as list_cmd, extract, verify, info


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="RGOG - Reproducible GOG Archive Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Pack command
    pack_parser = subparsers.add_parser('pack', help='Create an RGOG archive')
    pack_parser.add_argument('input_dir', type=Path, help='Input directory (GOG v2 structure)')
    pack_parser.add_argument('-o', '--output', type=Path, required=True, help='Output RGOG file')
    pack_parser.add_argument('--max-part-size', type=str, default='2GB',
                           help='Maximum size per part (e.g., 2GB, 4GB, 10GB). Default: 2GB')
    pack_parser.add_argument('--type', type=str, choices=['base', 'patch'], default='base',
                           help='Archive type. Default: base')
    pack_parser.add_argument('--build', type=int, help='Pack only specific build ID')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List archive contents')
    list_parser.add_argument('archive', type=Path, help='RGOG archive file')
    list_parser.add_argument('--detailed', action='store_true',
                           help='Show detailed build information (decompresses repositories)')
    list_parser.add_argument('--build', type=int, help='Show specific build details')
    
    # Extract command
    extract_parser = subparsers.add_parser('extract', help='Extract from archive')
    extract_parser.add_argument('archive', type=Path, help='RGOG archive file')
    extract_parser.add_argument('-o', '--output', type=Path, required=True, help='Output directory')
    extract_parser.add_argument('--build', type=int, help='Extract specific build only')
    extract_parser.add_argument('--chunks-only', action='store_true',
                              help='Extract only chunk files')
    extract_parser.add_argument('--reassemble', action='store_true',
                              help='Reassemble chunks into final files (requires manifest data)')
    
    # Verify command
    verify_parser = subparsers.add_parser('verify', help='Verify archive integrity')
    verify_parser.add_argument('archive', type=Path, help='RGOG archive file')
    verify_parser.add_argument('--build', type=int, help='Verify specific build only')
    verify_parser.add_argument('--quick', action='store_true',
                             help='Quick verify (check structure only, skip MD5)')
    verify_parser.add_argument('--detailed', action='store_true',
                             help='Show detailed verification of each file')
    
    # Info command
    info_parser = subparsers.add_parser('info', help='Show archive information')
    info_parser.add_argument('archive', type=Path, help='RGOG archive file')
    info_parser.add_argument('--stats', action='store_true',
                           help='Show detailed statistics')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Execute command
    try:
        if args.command == 'pack':
            return pack.execute(args)
        elif args.command == 'list':
            return list_cmd.execute(args)
        elif args.command == 'extract':
            return extract.execute(args)
        elif args.command == 'verify':
            return verify.execute(args)
        elif args.command == 'info':
            return info.execute(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
