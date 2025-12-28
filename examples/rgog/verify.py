"""
RGOG Verify Command

Verifies the integrity of RGOG archives by checking MD5 checksums
and validating binary structure.
"""

import hashlib
import struct
from pathlib import Path
from .common import RGOGHeader, bytes_to_md5, resolve_first_part, get_all_parts


def execute(args):
    """Execute the verify command."""
    archive_path = args.archive
    
    if not archive_path.exists():
        raise ValueError(f"Archive not found: {archive_path}")
    
    # Auto-redirect to first part and get all parts
    first_part_path, header = resolve_first_part(archive_path)
    
    if first_part_path != archive_path:
        print(f"Note: Redirecting to first part: {first_part_path}\n")
    
    all_parts = get_all_parts(first_part_path, header.total_parts)
    
    print(f"RGOG Verify: {first_part_path.stem.rsplit('_', 1)[0] if header.total_parts > 1 else first_part_path.name}")
    print(f"Verifying {len(all_parts)} part(s)...")
    
    # Verify each part's header
    for part_path in all_parts:
        with open(part_path, 'rb') as f:
            header_data = f.read(128)
            part_header = RGOGHeader.from_bytes(header_data)
            
            if part_header.magic != b'RGOG':
                print(f"✗ Part {part_path.name}: Invalid magic number")
                return 1
        
        print(f"✓ Part {part_path.name}: Header valid")
    
    print(f"\nArchive Summary:")
    print(f"  Total Parts: {header.total_parts}")
    print(f"  Builds: {header.total_build_count}")
    print(f"  Total Chunks: {header.total_chunk_count}")
    
    if not args.quick:
        errors = 0
        
        # Verify build files (compressed repository JSON) - only in first part
        if header.total_build_count > 0:
            print(f"\nVerifying {header.total_build_count} build file(s)...")
            
            with open(first_part_path, 'rb') as f:
                # Seek to build metadata section
                f.seek(header.build_metadata_offset)
                
                for i in range(header.total_build_count):
                    # Read build metadata header (48 bytes)
                    build_header = f.read(48)
                    if len(build_header) != 48:
                        print(f"✗ Build {i + 1}: Failed to read metadata")
                        errors += 1
                        continue
                    
                    # Parse: build_id (8) + os (1) + padding (3) + repository_id (16) + offset (8) + size (8) + manifest_count (2) + padding (2)
                    build_id, os, repo_md5, repo_offset, repo_size, manifest_count = struct.unpack('<QB3x16sQQH2x', build_header)
                    
                    # Read manifest entries (48 bytes each)
                    manifests = []
                    for j in range(manifest_count):
                        manifest_data = f.read(48)
                        if len(manifest_data) != 48:
                            print(f"✗ Build {i + 1}: Failed to read manifest {j + 1}")
                            errors += 1
                            continue
                        # Parse: depot_id (16) + offset (8) + size (8) + languages1 (8) + languages2 (8)
                        depot_id, depot_offset, depot_size, lang1, lang2 = struct.unpack('<16sQQQQ', manifest_data)
                        manifests.append((depot_id, depot_offset, depot_size))
                    
                    # Read repository file
                    current_pos = f.tell()
                    absolute_offset = header.build_files_offset + repo_offset
                    f.seek(absolute_offset)
                    repo_data = f.read(repo_size)
                    f.seek(current_pos)
                    
                    if len(repo_data) != repo_size:
                        print(f"✗ Build {i + 1}: Size mismatch (expected {repo_size}, got {len(repo_data)})")
                        errors += 1
                        continue
                    
                    # Calculate MD5
                    actual_md5 = hashlib.md5(repo_data).digest()
                    
                    if actual_md5 != repo_md5:
                        expected = bytes_to_md5(repo_md5)
                        got = bytes_to_md5(actual_md5)
                        print(f"✗ Build {i + 1}: MD5 mismatch (expected {expected}, got {got})")
                        errors += 1
                        continue
                    
                    if args.detailed:
                        md5_str = bytes_to_md5(repo_md5)
                        print(f"  ✓ Build {i + 1} repository: {md5_str} ({repo_size} bytes)")
                    
                    # Verify depot manifests
                    for j, (depot_id, depot_offset, depot_size) in enumerate(manifests):
                        current_pos = f.tell()
                        absolute_offset = header.build_files_offset + depot_offset
                        f.seek(absolute_offset)
                        depot_data = f.read(depot_size)
                        f.seek(current_pos)
                        
                        if len(depot_data) != depot_size:
                            print(f"✗ Build {i + 1}, Depot {j + 1}: Size mismatch (expected {depot_size}, got {len(depot_data)})")
                            errors += 1
                            continue
                        
                        # Calculate MD5
                        actual_depot_md5 = hashlib.md5(depot_data).digest()
                        
                        if actual_depot_md5 != depot_id:
                            expected = bytes_to_md5(depot_id)
                            got = bytes_to_md5(actual_depot_md5)
                            print(f"✗ Build {i + 1}, Depot {j + 1}: MD5 mismatch (expected {expected}, got {got})")
                            errors += 1
                            continue
                        
                        if args.detailed:
                            depot_md5_str = bytes_to_md5(depot_id)
                            print(f"    ✓ Depot {j + 1}: {depot_md5_str} ({depot_size} bytes)")
                
                if errors == 0:
                    print(f"✓ All {header.total_build_count} build file(s) verified successfully")
        
        # Verify chunk MD5 checksums across all parts
        if header.total_chunk_count > 0:
            print(f"\nVerifying {header.total_chunk_count} chunks across {len(all_parts)} part(s)...")
            
            # Verify chunks in each part
            for part_path in all_parts:
                with open(part_path, 'rb') as f:
                    # Read part header to get chunk info
                    part_header_data = f.read(128)
                    part_header = RGOGHeader.from_bytes(part_header_data)
                    
                    if part_header.local_chunk_count == 0:
                        continue
                    
                    # Seek to chunk metadata section
                    f.seek(part_header.chunk_metadata_offset)
                    
                    for i in range(part_header.local_chunk_count):
                        # Read chunk metadata entry (32 bytes)
                        chunk_meta = f.read(32)
                        if len(chunk_meta) != 32:
                            print(f"✗ Part {part_path.name}, Chunk {i + 1}: Failed to read metadata")
                            errors += 1
                            continue
                        
                        # Parse: compressed_md5 (16) + offset (8) + compressed_size (8)
                        compressed_md5, offset, compressed_size = struct.unpack('<16sQQ', chunk_meta)
                        
                        # Offset is relative to chunk_files_offset, make it absolute
                        absolute_offset = part_header.chunk_files_offset + offset
                        
                        # Read chunk data
                        current_pos = f.tell()
                        f.seek(absolute_offset)
                        chunk_data = f.read(compressed_size)
                        f.seek(current_pos)
                        
                        if len(chunk_data) != compressed_size:
                            print(f"✗ Part {part_path.name}, Chunk {i + 1}: Size mismatch (expected {compressed_size}, got {len(chunk_data)})")
                            errors += 1
                            continue
                        
                        # Calculate MD5
                        actual_md5 = hashlib.md5(chunk_data).digest()
                        
                        if actual_md5 != compressed_md5:
                            expected = bytes_to_md5(compressed_md5)
                            got = bytes_to_md5(actual_md5)
                            print(f"✗ Part {part_path.name}, Chunk {i + 1}: MD5 mismatch (expected {expected}, got {got})")
                            errors += 1
                            continue
                        
                        # Detailed output for each chunk
                        if args.detailed:
                            md5_str = bytes_to_md5(compressed_md5)
                            print(f"  ✓ Part {part_path.name}, Chunk {i + 1}: {md5_str} ({compressed_size} bytes)")
            
            if errors == 0:
                print(f"✓ All {header.total_chunk_count} chunks verified successfully")
        
        # Final result
        if errors > 0:
            print(f"\n✗ Verification failed: {errors} error(s) found")
            return 1
    
    return 0
