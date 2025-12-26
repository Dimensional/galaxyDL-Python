"""
RGOG Info Command

Displays detailed information and statistics about RGOG archives.
"""

from pathlib import Path
from .common import RGOGHeader, ProductMetadata


def execute(args):
    """Execute the info command."""
    archive_path = args.archive
    
    if not archive_path.exists():
        raise ValueError(f"Archive not found: {archive_path}")
    
    print(f"RGOG Archive Information: {archive_path}")
    print(f"File size: {archive_path.stat().st_size / (1024**3):.2f} GB")
    
    # Read header
    with open(archive_path, 'rb') as f:
        header_data = f.read(128)
        header = RGOGHeader.from_bytes(header_data)
        
        if header.magic != b'RGOG':
            raise ValueError("Invalid RGOG archive")
        
        print(f"\nHeader:")
        print(f"  Magic: {header.magic.decode('ascii')}")
        print(f"  Version: {header.version}")
        print(f"  Type: {header.archive_type} ({'Base' if header.archive_type == 1 else 'Patch'})")
        print(f"  Part: {header.part_number} of {header.total_parts}")
        
        print(f"\nCounts:")
        print(f"  Total Builds: {header.total_build_count}")
        print(f"  Total Chunks: {header.total_chunk_count}")
        print(f"  Local Chunks: {header.local_chunk_count}")
        
        print(f"\nSections:")
        print(f"  Product Metadata: offset={header.product_metadata_offset}, size={header.product_metadata_size}")
        print(f"  Build Metadata: offset={header.build_metadata_offset}, size={header.build_metadata_size}")
        print(f"  Build Files: offset={header.build_files_offset}, size={header.build_files_size}")
        print(f"  Chunk Metadata: offset={header.chunk_metadata_offset}, size={header.chunk_metadata_size}")
        print(f"  Chunk Files: offset={header.chunk_files_offset}, size={header.chunk_files_size}")
        
        # Calculate metadata overhead
        total_metadata = (
            128 +  # Header
            header.product_metadata_size +
            header.build_metadata_size +
            header.chunk_metadata_size
        )
        total_data = header.build_files_size + header.chunk_files_size
        total_size = total_metadata + total_data
        
        if args.stats and total_size > 0:
            print(f"\nStatistics:")
            print(f"  Metadata: {total_metadata / (1024**2):.2f} MB ({total_metadata / total_size * 100:.3f}%)")
            print(f"  Data: {total_data / (1024**3):.2f} GB ({total_data / total_size * 100:.2f}%)")
            print(f"  Avg chunk size: {header.chunk_files_size / header.local_chunk_count / (1024**2):.2f} MB")
    
    return 0
