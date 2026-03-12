#!/usr/bin/env python3
"""
Extract manifest files from RGOG build records and save them for inspection.
"""

import json
import sys
import zlib
import struct
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from rgog.common import RGOGHeader, resolve_first_part, bytes_to_md5


def extract_manifests(rgog_path: Path, output_dir: Path):
    """Extract all manifests from RGOG build records."""
    
    result = resolve_first_part(rgog_path)
    if not result:
        print(f"✗ Could not find RGOG archive at {rgog_path}")
        return
    
    first_part, header = result
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    total_repositories = 0
    total_manifests = 0
    total_chunks_found = 0
    chunks_with_decompressed = 0
    chunks_without_decompressed = 0
    
    print(f"Extracting from first part only (build records only stored in first RGOG file)...")
    print(f"Reading: {first_part.name}")
    
    if header.total_build_count == 0:
        print("  ⚠ No build records found in archive")
        return
    
    print(f"  Found {header.total_build_count} builds with metadata")
    
    # Read build metadata and extract files
    with open(first_part, 'rb') as f:
        # Seek to build metadata section
        f.seek(header.build_metadata_offset)
        
        for i in range(header.total_build_count):
            # Read build metadata header (48 bytes)
            build_header = f.read(48)
            if len(build_header) != 48:
                print(f"  ⚠ Incomplete build header at build {i}")
                continue
            
            # Parse: build_id (8) + os (1) + padding (3) + repository_id (16) + offset (8) + size (8) + manifest_count (2) + padding (2)
            build_id, os, repo_md5, repo_offset, repo_size, manifest_count = struct.unpack('<QB3x16sQQH2x', build_header)
            
            repo_filename = bytes_to_md5(repo_md5)
            
            # Extract repository file
            current_pos = f.tell()
            absolute_offset = header.build_files_offset + repo_offset
            f.seek(absolute_offset)
            repo_data = f.read(repo_size)
            f.seek(current_pos)
            
            if len(repo_data) == repo_size:
                try:
                    # Decompress repository (it's zlib compressed)
                    decompressed_repo = zlib.decompress(repo_data)
                    repo_json = json.loads(decompressed_repo)
                    
                    # Save repository
                    output_file = output_dir / f"{repo_filename}_repository.json"
                    with open(output_file, 'w', encoding='utf-8') as out_f:
                        json.dump(repo_json, out_f, indent=2)
                    total_repositories += 1
                    print(f"  ✓ Build {build_id}: Saved {repo_filename}_repository.json")
                    
                except Exception as e:
                    print(f"  ⚠ Build {build_id}: Error extracting repository {repo_filename}: {e}")
            
            # Read manifest entries (56 bytes each)
            for j in range(manifest_count):
                manifest_data = f.read(56)
                if len(manifest_data) != 56:
                    print(f"  ⚠ Build {build_id}: Incomplete manifest entry {j}")
                    continue
                
                # Parse: depot_id (16) + offset (8) + size (8) + languages1 (8) + languages2 (8) + product_id (8)
                depot_id, depot_offset, depot_size, lang1, lang2, product_id = struct.unpack('<16sQQQQQ', manifest_data)
                depot_id_str = bytes_to_md5(depot_id)
                
                # Extract depot manifest
                current_pos = f.tell()
                absolute_offset = header.build_files_offset + depot_offset
                f.seek(absolute_offset)
                depot_data = f.read(depot_size)
                f.seek(current_pos)
                
                if len(depot_data) != depot_size:
                    print(f"  ⚠ Build {build_id}: Incomplete depot data for {depot_id_str}")
                    continue
                
                try:
                    # Decompress and parse manifest JSON
                    decompressed_data = zlib.decompress(depot_data)
                    manifest_json = json.loads(decompressed_data)
                    
                    # Save manifest
                    output_file = output_dir / f"{depot_id_str}_manifest.json"
                    with open(output_file, 'w', encoding='utf-8') as out_f:
                        json.dump(manifest_json, out_f, indent=2)
                    total_manifests += 1
                    
                    # Count chunks
                    depot = manifest_json.get('depot', {})
                    for item in depot.get('items', []):
                        if 'chunks' in item:
                            for chunk in item['chunks']:
                                total_chunks_found += 1
                                if chunk.get('md5'):
                                    chunks_with_decompressed += 1
                                else:
                                    chunks_without_decompressed += 1
                    
                    print(f"    ✓ Manifest {j+1}/{manifest_count}: {depot_id_str}_manifest.json")
                    
                except Exception as e:
                    print(f"  ⚠ Build {build_id}: Error extracting manifest {depot_id_str}: {e}")
    
                except Exception as e:
                    print(f"  ⚠ Build {build_id}: Error extracting manifest {depot_id_str}: {e}")
    
    print(f"\n{'='*80}")
    print(f"Extraction Complete")
    print(f"{'='*80}")
    print(f"  Total repositories extracted: {total_repositories}")
    print(f"  Total manifests extracted: {total_manifests}")
    print(f"  Total chunk entries: {total_chunks_found}")
    print(f"  Chunks with decompressed MD5: {chunks_with_decompressed} ({chunks_with_decompressed*100//max(total_chunks_found,1)}%)")
    print(f"  Chunks WITHOUT decompressed MD5: {chunks_without_decompressed} ({chunks_without_decompressed*100//max(total_chunks_found,1)}%)")
    print(f"\nFiles saved to: {output_dir}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_rgog_manifests.py <path_to_rgog_file> [output_dir]")
        print("\nExample:")
        print("  python extract_rgog_manifests.py ../Ignore/DREDGE_1.rgog")
        print("  python extract_rgog_manifests.py ../Ignore/DREDGE_1.rgog extracted_manifests/")
        sys.exit(1)
    
    rgog_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("extracted_manifests")
    
    extract_manifests(rgog_path, output_dir)


if __name__ == "__main__":
    main()
