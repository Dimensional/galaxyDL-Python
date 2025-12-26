"""
RGOG List Command

Lists contents of RGOG archives, optionally showing detailed build information.
"""

from pathlib import Path
from .common import RGOGHeader, ProductMetadata, BuildMetadata, OS_NAMES, bytes_to_md5, decode_languages


def execute(args):
    """Execute the list command."""
    archive_path = args.archive
    
    if not archive_path.exists():
        raise ValueError(f"Archive not found: {archive_path}")
    
    print(f"RGOG Archive: {archive_path}")
    
    # Read header
    with open(archive_path, 'rb') as f:
        header_data = f.read(128)
        header = RGOGHeader.from_bytes(header_data)
        
        # Validate header
        if header.magic != b'RGOG':
            raise ValueError("Invalid RGOG archive: bad magic number")
        
        print(f"\nArchive Info:")
        print(f"  Version: {header.version}")
        print(f"  Type: {'Base Build' if header.archive_type == 1 else 'Patch Collection'}")
        print(f"  Parts: {header.total_parts}")
        print(f"  Builds: {header.total_build_count}")
        print(f"  Chunks: {header.total_chunk_count}")
        
        # Read product metadata
        if header.product_metadata_offset > 0:
            f.seek(header.product_metadata_offset)
            product_data = f.read(header.product_metadata_size)
            product = ProductMetadata.from_bytes(product_data)
            
            print(f"\nProduct:")
            print(f"  ID: {product.product_id}")
            print(f"  Name: {product.product_name}")
        
        # Read build metadata
        if header.build_metadata_offset > 0 and not args.build:
            f.seek(header.build_metadata_offset)
            build_data = f.read(header.build_metadata_size)
            
            print(f"\nBuilds:")
            offset = 0
            while offset < len(build_data):
                # Need at least 48 bytes for build header
                if offset + 48 > len(build_data):
                    break
                    
                build = BuildMetadata.from_bytes(build_data[offset:])
                print(f"  Build {build.build_id}:")
                print(f"    OS: {OS_NAMES.get(build.os, 'Unknown')}")
                
                if args.detailed:
                    # Show repository details
                    repo_id = bytes_to_md5(build.repository_id)
                    print(f"    Repository: {repo_id} ({build.repository_size} bytes)")
                    
                    # Show each manifest
                    print(f"    Manifests: {len(build.manifests)}")
                    for i, manifest in enumerate(build.manifests):
                        depot_id = bytes_to_md5(manifest.depot_id)
                        # Decode language flags to actual language codes
                        lang_codes = decode_languages(manifest.languages1, manifest.languages2)
                        lang_info = ", ".join(lang_codes) if lang_codes else "no languages"
                        print(f"      {i + 1}. Depot {depot_id} ({manifest.size} bytes, {lang_info})")
                else:
                    print(f"    Manifests: {len(build.manifests)}")
                    
                offset += build.size()
    
    return 0
