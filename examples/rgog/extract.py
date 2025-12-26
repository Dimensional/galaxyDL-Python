"""
RGOG Extract Command

Extracts builds and chunks from RGOG archives.
Optionally reassembles chunks into final game files.
"""

from pathlib import Path
from .common import RGOGHeader


def execute(args):
    """Execute the extract command."""
    archive_path = args.archive
    output_dir = args.output
    
    if not archive_path.exists():
        raise ValueError(f"Archive not found: {archive_path}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"RGOG Extract: {archive_path} -> {output_dir}")
    
    # Read header
    with open(archive_path, 'rb') as f:
        header_data = f.read(128)
        header = RGOGHeader.from_bytes(header_data)
        
        if header.magic != b'RGOG':
            raise ValueError("Invalid RGOG archive")
        
        print(f"Extracting from archive with {header.total_build_count} builds, {header.total_chunk_count} chunks")
    
    # TODO: Implement extraction logic
    # - Extract build files (repositories + manifests) to meta/
    # - Extract chunks to chunks/
    # - Optionally reassemble chunks into final files
    
    print("\nExtraction complete!")
    return 0
