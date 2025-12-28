"""
RGOG Info Command

Displays detailed information and statistics about RGOG archives.
"""

from pathlib import Path
from .common import RGOGHeader, ProductMetadata, resolve_first_part, get_all_parts


def execute(args):
    """Execute the info command."""
    archive_path = args.archive
    
    if not archive_path.exists():
        raise ValueError(f"Archive not found: {archive_path}")
    
    # Read from specified part (product metadata now in all parts)
    first_part_path, header = resolve_first_part(archive_path)
    
    # Calculate total archive size across all parts
    all_parts = get_all_parts(first_part_path, header.total_parts)
    total_size = sum(part.stat().st_size for part in all_parts)
    
    print(f"RGOG Archive Information: {first_part_path.stem.rsplit('_', 1)[0] if header.total_parts > 1 else first_part_path.name}")
    print(f"Total size: {total_size / (1024**3):.2f} GB ({header.total_parts} part{'s' if header.total_parts > 1 else ''})")
    
    # Read header and product metadata from the part
    with open(archive_path, 'rb') as f:
        header_data = f.read(128)
        current_header = RGOGHeader.from_bytes(header_data)
        
        if current_header.magic != b'RGOG':
            raise ValueError("Invalid RGOG archive")
        
        # Read product metadata
        product_name = "Unknown"
        product_id = 0
        if current_header.product_metadata_offset > 0:
            f.seek(current_header.product_metadata_offset)
            product_data = f.read(current_header.product_metadata_size)
            product = ProductMetadata.from_bytes(product_data)
            product_name = product.product_name
            product_id = product.product_id
        
        print(f"\nProduct:")
        print(f"  Name: {product_name}")
        print(f"  ID: {product_id}")
        
        print(f"\nHeader:")
        print(f"  Magic: {current_header.magic.decode('ascii')}")
        print(f"  Version: {current_header.version}")
        print(f"  Type: {current_header.archive_type} ({'Base' if current_header.archive_type == 1 else 'Patch'})")
        print(f"  Total Parts: {current_header.total_parts}")
        
        print(f"\nCounts:")
        print(f"  Total Builds: {current_header.total_build_count}")
        print(f"  Total Chunks: {current_header.total_chunk_count}")
        print(f"  Local Chunks: {current_header.local_chunk_count}")
        
        # Calculate total chunk data size across all parts
        total_chunk_data_size = 0
        for part_path in all_parts:
            with open(part_path, 'rb') as pf:
                part_header_data = pf.read(128)
                part_header = RGOGHeader.from_bytes(part_header_data)
                total_chunk_data_size += part_header.chunk_files_size
        
        print(f"\nSections:")
        print(f"  Product Metadata: offset={current_header.product_metadata_offset}, size={current_header.product_metadata_size}")
        print(f"  Build Metadata: offset={current_header.build_metadata_offset}, size={current_header.build_metadata_size}")
        print(f"  Build Files: offset={current_header.build_files_offset}, size={current_header.build_files_size}")
        print(f"  Chunk Metadata: offset={current_header.chunk_metadata_offset}, size={current_header.chunk_metadata_size}")
        print(f"  Chunk Files (all parts): size={total_chunk_data_size} ({total_chunk_data_size / (1024**3):.2f} GB)")
        
        # Calculate metadata overhead
        total_metadata = (
            128 +  # Header
            current_header.product_metadata_size +
            current_header.build_metadata_size +
            current_header.chunk_metadata_size
        )
        total_data = current_header.build_files_size + current_header.chunk_files_size
        local_size = total_metadata + total_data
        
        if args.stats and local_size > 0:
            print(f"\nStatistics:")
            print(f"  Metadata: {total_metadata / (1024**2):.2f} MB ({total_metadata / local_size * 100:.3f}%)")
            print(f"  Data: {total_data / (1024**3):.2f} GB ({total_data / local_size * 100:.2f}%)")
            print(f"  Avg chunk size: {current_header.chunk_files_size / current_header.local_chunk_count / (1024**2):.2f} MB")
    
    return 0
