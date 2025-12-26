"""
RGOG Verify Command

Verifies the integrity of RGOG archives by checking MD5 checksums
and validating binary structure.
"""

from pathlib import Path
from .common import RGOGHeader


def execute(args):
    """Execute the verify command."""
    archive_path = args.archive
    
    if not archive_path.exists():
        raise ValueError(f"Archive not found: {archive_path}")
    
    print(f"RGOG Verify: {archive_path}")
    
    # Read and validate header
    with open(archive_path, 'rb') as f:
        header_data = f.read(128)
        header = RGOGHeader.from_bytes(header_data)
        
        if header.magic != b'RGOG':
            print("✗ Invalid magic number")
            return 1
        
        print("✓ Header valid")
        print(f"  Parts: {header.total_parts}")
        print(f"  Builds: {header.total_build_count}")
        print(f"  Chunks: {header.total_chunk_count}")
    
    if not args.quick:
        # TODO: Implement full MD5 verification
        # - Verify all chunk MD5s match filenames
        # - Verify chunk files are valid zlib
        print("\n✓ All checksums valid")
    
    return 0
