#!/usr/bin/env python3
"""
Validate Game Archive

Validates that downloaded game archives match the manifest specifications.

V1 Validation:
- Checks files from main.bin against manifest MD5 hashes
- Reads data at specified offsets/lengths and computes MD5

V2 Validation:
- Checks downloaded chunks against manifest MD5 hashes
- Verifies both compressed MD5 and uncompressed MD5
- Validates chunk decompression integrity

Usage:
    python validate_game.py v1 <game_id> <timestamp> <game_name> [--platform PLATFORM] [--sample N]
    python validate_game.py v2 <game_id> <repository_id> <game_name> [--sample N]
    
    --platform: Platform to validate (windows, osx, linux). Default: windows (V1 only)
    --sample: Number of files/chunks to randomly sample. Default: all
    --random-seed: Seed for random sampling (for reproducibility). Default: None

Examples:
    python validate_game.py v1 1207658930 37794096 "The Witcher 2"
    python validate_game.py v1 1207658930 37794096 "The Witcher 2" --platform windows --sample 100
    python validate_game.py v2 1207658930 e518c17d90805e8e3998a35fac8b8505 "The Witcher 2"
    python validate_game.py v2 1207658930 e518c17d90805e8e3998a35fac8b8505 "The Witcher 2" --sample 500 --random-seed 42
"""

import sys
import os
import json
import hashlib
import argparse
import random
import zlib
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class FileMapping:
    """Represents a file entry from a manifest."""
    path: str
    offset: int
    size: int
    hash: str
    manifest_uuid: str
    support: bool = False
    
    def __repr__(self):
        return f"FileMapping(path={self.path!r}, offset={self.offset}, size={self.size}, hash={self.hash[:8]}...)"


@dataclass
class ChunkMapping:
    """Represents a chunk entry from a V2 manifest."""
    compressed_md5: str
    compressed_size: int
    md5: str
    size: int
    file_path: str = ""  # Which file this chunk belongs to
    manifest_id: str = ""
    
    def __repr__(self):
        return f"ChunkMapping(md5={self.compressed_md5[:8]}..., size={self.compressed_size})"


def decompress_if_needed(data: bytes) -> dict:
    """Try to decompress zlib, fall back to plain JSON."""
    try:
        return json.loads(zlib.decompress(data))
    except:
        return json.loads(data.decode('utf-8'))


def format_size(size: float) -> str:
    """Format size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def load_repository(repo_path: Path) -> List[str]:
    """Load repository.json and extract manifest UUIDs."""
    if not repo_path.exists():
        raise FileNotFoundError(f"Repository file not found: {repo_path}")
    
    with open(repo_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Repository structure is product.depots
    product = data.get('product', {})
    manifests = product.get('depots', [])
    
    # Extract manifest filenames (they include .json extension)
    manifest_uuids = []
    for m in manifests:
        if 'manifest' in m:
            manifest_file = m['manifest']
            # Remove .json extension to get UUID
            if manifest_file.endswith('.json'):
                manifest_file = manifest_file[:-5]
            manifest_uuids.append(manifest_file)
    
    print(f"Found {len(manifest_uuids)} manifest(s) in repository")
    return manifest_uuids


def load_manifest(manifest_path: Path, manifest_uuid: str) -> List[FileMapping]:
    """Load a manifest JSON file and extract file mappings."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")
    
    with open(manifest_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    files = []
    for file_data in data.get('depot', {}).get('files', []):
        # Skip directory entries (size 0, no offset/url)
        if file_data.get('size', 0) == 0 or 'offset' not in file_data:
            continue
        
        files.append(FileMapping(
            path=file_data['path'],
            offset=file_data['offset'],
            size=file_data['size'],
            hash=file_data.get('hash', ''),
            manifest_uuid=manifest_uuid,
            support=file_data.get('support', False)
        ))
    
    return files


def build_file_mapping(manifests_dir: Path, manifest_uuids: List[str]) -> List[FileMapping]:
    """Build complete file mapping from all manifests."""
    all_files = []
    
    for uuid in manifest_uuids:
        manifest_path = manifests_dir / f"{uuid}.json"
        try:
            files = load_manifest(manifest_path, uuid)
            all_files.extend(files)
            print(f"  Loaded {len(files)} files from manifest {uuid}")
        except FileNotFoundError as e:
            print(f"  WARNING: {e}")
            continue
    
    print(f"\nTotal files across all manifests: {len(all_files)}")
    return all_files


def compute_file_hash(file_handle, offset: int, size: int) -> str:
    """Read a file from an open file handle and compute its MD5 hash.
    
    Args:
        file_handle: Open file handle (must be opened in binary mode)
        offset: Byte offset to start reading from
        size: Number of bytes to read
    
    Returns:
        MD5 hex digest of the data
    """
    md5 = hashlib.md5()
    
    file_handle.seek(offset)
    
    # Read in chunks to handle large files
    remaining = size
    chunk_size = 1024 * 1024  # 1 MB chunks
    
    while remaining > 0:
        to_read = min(chunk_size, remaining)
        chunk = file_handle.read(to_read)
        
        if not chunk:
            raise ValueError(f"Unexpected EOF at offset {offset + (size - remaining)}")
        
        md5.update(chunk)
        remaining -= len(chunk)
    
    return md5.hexdigest()


def validate_v1_build(game_id: str, timestamp: str, game_name: str, platform: str = "windows",
                      sample_size: int = None, random_seed: int = None):
    """Validate a V1 build by checking files against main.bin."""
    
    # Construct paths
    base_dir = Path(game_name)
    manifests_dir = base_dir / "v1" / "manifests" / game_id / platform / timestamp
    depots_dir = base_dir / "v1" / "depots" / game_id / platform / timestamp
    repo_path = manifests_dir / "repository.json"
    main_bin_path = depots_dir / "main.bin"
    
    # Check if main.bin exists
    if not main_bin_path.exists():
        print(f"ERROR: main.bin not found at {main_bin_path}")
        print("Please download the archive first using archive_game.py")
        return False
    
    print(f"Validating V1 build:")
    print(f"  Game ID: {game_id}")
    print(f"  Platform: {platform}")
    print(f"  Timestamp: {timestamp}")
    print(f"  main.bin: {main_bin_path}")
    print()
    
    # Load repository to get manifest UUIDs
    print("Loading repository...")
    try:
        manifest_uuids = load_repository(repo_path)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return False
    
    # Build complete file mapping
    print("\nBuilding file mapping...")
    file_mappings = build_file_mapping(manifests_dir, manifest_uuids)
    
    if not file_mappings:
        print("ERROR: No files found in manifests")
        return False
    
    # Determine which files to validate
    if sample_size is not None and sample_size < len(file_mappings):
        if random_seed is not None:
            random.seed(random_seed)
        files_to_validate = random.sample(file_mappings, sample_size)
        print(f"\nRandomly selected {sample_size} files to validate")
        if random_seed is not None:
            print(f"Random seed: {random_seed}")
    else:
        files_to_validate = file_mappings
        print(f"\nValidating all {len(files_to_validate)} files")
    
    # Sort by offset for sequential disk reads (much faster!)
    files_to_validate.sort(key=lambda f: f.offset)
    print(f"Files sorted by offset for efficient sequential reading")
    
    print()
    print("="*80)
    print("VALIDATION PROGRESS")
    print("="*80)
    print()
    
    # Validate files - open main.bin once and keep it open
    passed = 0
    failed = 0
    errors = 0
    total_bytes_validated = 0
    
    with open(main_bin_path, 'rb') as main_bin:
        for i, file_mapping in enumerate(files_to_validate, 1):
            try:
                # Compute hash from main.bin (using open file handle)
                computed_hash = compute_file_hash(main_bin, file_mapping.offset, file_mapping.size)
                
                # Compare with manifest hash
                if computed_hash == file_mapping.hash:
                    passed += 1
                    status = "✓ PASS"
                else:
                    failed += 1
                    status = "✗ FAIL"
                    print(f"\n{status} [{i}/{len(files_to_validate)}] {file_mapping.path}")
                    print(f"  Expected: {file_mapping.hash}")
                    print(f"  Got:      {computed_hash}")
                    print(f"  Offset: {file_mapping.offset:,}, Size: {format_size(file_mapping.size)}")
                
                total_bytes_validated += file_mapping.size
                
                # Show progress every 10 files
                if i % 10 == 0 or i == len(files_to_validate):
                    print(f"Progress: {i}/{len(files_to_validate)} files validated "
                          f"({passed} passed, {failed} failed, {errors} errors)")
            
            except Exception as e:
                errors += 1
                print(f"\n✗ ERROR [{i}/{len(files_to_validate)}] {file_mapping.path}")
                print(f"  {type(e).__name__}: {e}")
                print(f"  Offset: {file_mapping.offset:,}, Size: {format_size(file_mapping.size)}")
    
    # Print summary
    print()
    print("="*80)
    print("VALIDATION SUMMARY")
    print("="*80)
    print()
    
    total = len(files_to_validate)
    print(f"Total files validated: {total:,}")
    print(f"  ✓ Passed: {passed:,} ({passed/total*100:.2f}%)")
    print(f"  ✗ Failed: {failed:,} ({failed/total*100:.2f}%)")
    print(f"  ✗ Errors: {errors:,} ({errors/total*100:.2f}%)")
    print(f"\nTotal data validated: {format_size(total_bytes_validated)} ({total_bytes_validated:,} bytes)")
    
    if failed == 0 and errors == 0:
        print("\n✓✓✓ ALL FILES VALIDATED SUCCESSFULLY ✓✓✓")
        return True
    else:
        print("\n✗✗✗ VALIDATION FAILED ✗✗✗")
        return False


def validate_v2_build(game_id: str, repository_id: str, game_name: str,
                      sample_size: int = None, random_seed: int = None):
    """Validate a V2 build by checking chunks against manifests."""
    
    # Construct paths
    base_dir = Path(game_name) / "v2"
    depot_dir = base_dir / "meta" / repository_id[:2] / repository_id[2:4]
    depot_path = depot_dir / repository_id
    store_dir = base_dir / "store"
    
    # Check if depot exists
    if not depot_path.exists():
        print(f"ERROR: Depot file not found at {depot_path}")
        print("Please download the archive first using archive_game.py")
        return False
    
    print(f"Validating V2 build:")
    print(f"  Game ID: {game_id}")
    print(f"  Repository: {repository_id}")
    print(f"  Depot: {depot_path}")
    print()
    
    # Load depot
    print("Loading depot...")
    with open(depot_path, 'rb') as f:
        depot_json = decompress_if_needed(f.read())
    
    manifests = depot_json.get('depots', [])
    print(f"Found {len(manifests)} manifest(s) in depot")
    
    # Load all manifests and collect chunks
    print("\nLoading manifests and collecting chunks...")
    all_chunks = {}
    
    for depot in manifests:
        manifest_id = depot['manifest']
        manifest_dir = base_dir / "meta" / manifest_id[:2] / manifest_id[2:4]
        manifest_path = manifest_dir / manifest_id
        
        if not manifest_path.exists():
            print(f"  WARNING: Manifest not found: {manifest_path}")
            continue
        
        with open(manifest_path, 'rb') as f:
            manifest_json = decompress_if_needed(f.read())
        
        # Collect chunks from this manifest
        chunk_count = 0
        for item in manifest_json['depot']['items']:
            if item['type'] == 'DepotFile':
                file_path = item.get('path', 'unknown')
                for chunk in item.get('chunks', []):
                    md5 = chunk['compressedMd5']
                    if md5 not in all_chunks:
                        all_chunks[md5] = ChunkMapping(
                            compressed_md5=md5,
                            compressed_size=chunk['compressedSize'],
                            md5=chunk['md5'],
                            size=chunk['size'],
                            file_path=file_path,
                            manifest_id=manifest_id
                        )
                        chunk_count += 1
        
        print(f"  ✓ Loaded manifest {manifest_id}: {chunk_count} unique chunks")
    
    print(f"\nTotal unique chunks across all manifests: {len(all_chunks)}")
    
    if not all_chunks:
        print("ERROR: No chunks found in manifests")
        return False
    
    # Determine which chunks to validate
    chunks_list = list(all_chunks.values())
    if sample_size is not None and sample_size < len(chunks_list):
        if random_seed is not None:
            random.seed(random_seed)
        chunks_to_validate = random.sample(chunks_list, sample_size)
        print(f"\nRandomly selected {sample_size} chunks to validate")
        if random_seed is not None:
            print(f"Random seed: {random_seed}")
    else:
        chunks_to_validate = chunks_list
        print(f"\nValidating all {len(chunks_to_validate)} chunks")
    
    print()
    print("="*80)
    print("VALIDATION PROGRESS")
    print("="*80)
    print()
    
    # Validate chunks
    passed = 0
    failed = 0
    errors = 0
    total_compressed_bytes = 0
    total_uncompressed_bytes = 0
    
    for i, chunk in enumerate(chunks_to_validate, 1):
        md5 = chunk.compressed_md5
        chunk_path = store_dir / md5[:2] / md5[2:4] / md5
        
        try:
            # Check if chunk file exists
            if not chunk_path.exists():
                errors += 1
                print(f"\n✗ ERROR [{i}/{len(chunks_to_validate)}] Chunk not found: {md5}")
                print(f"  Path: {chunk_path}")
                continue
            
            # Read compressed chunk
            with open(chunk_path, 'rb') as f:
                compressed_data = f.read()
            
            # Verify compressed size
            actual_compressed_size = len(compressed_data)
            if actual_compressed_size != chunk.compressed_size:
                failed += 1
                print(f"\n✗ FAIL [{i}/{len(chunks_to_validate)}] Compressed size mismatch: {md5}")
                print(f"  Expected: {chunk.compressed_size:,} bytes")
                print(f"  Got:      {actual_compressed_size:,} bytes")
                print(f"  File: {chunk.file_path}")
                continue
            
            # Verify compressed MD5
            compressed_md5_actual = hashlib.md5(compressed_data).hexdigest()
            if compressed_md5_actual != md5:
                failed += 1
                print(f"\n✗ FAIL [{i}/{len(chunks_to_validate)}] Compressed MD5 mismatch")
                print(f"  Expected: {md5}")
                print(f"  Got:      {compressed_md5_actual}")
                print(f"  File: {chunk.file_path}")
                continue
            
            # Decompress and verify uncompressed data
            try:
                uncompressed_data = zlib.decompress(compressed_data, 15)
            except zlib.error as e:
                errors += 1
                print(f"\n✗ ERROR [{i}/{len(chunks_to_validate)}] Decompression failed: {md5}")
                print(f"  Error: {e}")
                print(f"  File: {chunk.file_path}")
                continue
            
            # Verify uncompressed size
            actual_uncompressed_size = len(uncompressed_data)
            if actual_uncompressed_size != chunk.size:
                failed += 1
                print(f"\n✗ FAIL [{i}/{len(chunks_to_validate)}] Uncompressed size mismatch: {md5}")
                print(f"  Expected: {chunk.size:,} bytes")
                print(f"  Got:      {actual_uncompressed_size:,} bytes")
                print(f"  File: {chunk.file_path}")
                continue
            
            # Verify uncompressed MD5
            uncompressed_md5_actual = hashlib.md5(uncompressed_data).hexdigest()
            if uncompressed_md5_actual != chunk.md5:
                failed += 1
                print(f"\n✗ FAIL [{i}/{len(chunks_to_validate)}] Uncompressed MD5 mismatch")
                print(f"  Expected: {chunk.md5}")
                print(f"  Got:      {uncompressed_md5_actual}")
                print(f"  File: {chunk.file_path}")
                continue
            
            # All checks passed
            passed += 1
            total_compressed_bytes += actual_compressed_size
            total_uncompressed_bytes += actual_uncompressed_size
            
            # Show progress every 50 chunks
            if i % 50 == 0 or i == len(chunks_to_validate):
                print(f"Progress: {i}/{len(chunks_to_validate)} chunks validated "
                      f"({passed} passed, {failed} failed, {errors} errors)")
        
        except Exception as e:
            errors += 1
            print(f"\n✗ ERROR [{i}/{len(chunks_to_validate)}] {md5}")
            print(f"  {type(e).__name__}: {e}")
            print(f"  File: {chunk.file_path}")
    
    # Print summary
    print()
    print("="*80)
    print("VALIDATION SUMMARY")
    print("="*80)
    print()
    
    total = len(chunks_to_validate)
    print(f"Total chunks validated: {total:,}")
    print(f"  ✓ Passed: {passed:,} ({passed/total*100:.2f}%)")
    print(f"  ✗ Failed: {failed:,} ({failed/total*100:.2f}%)")
    print(f"  ✗ Errors: {errors:,} ({errors/total*100:.2f}%)")
    print(f"\nCompressed data validated:   {format_size(total_compressed_bytes)} ({total_compressed_bytes:,} bytes)")
    print(f"Uncompressed data validated: {format_size(total_uncompressed_bytes)} ({total_uncompressed_bytes:,} bytes)")
    
    if total_uncompressed_bytes > 0:
        ratio = total_compressed_bytes / total_uncompressed_bytes * 100
        print(f"Compression ratio: {ratio:.2f}%")
    
    if failed == 0 and errors == 0:
        print("\n✓✓✓ ALL CHUNKS VALIDATED SUCCESSFULLY ✓✓✓")
        return True
    else:
        print("\n✗✗✗ VALIDATION FAILED ✗✗✗")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Validate game archive by checking files/chunks against manifests"
    )
    parser.add_argument("build_type", choices=["v1", "v2"], help="Build type")
    parser.add_argument("game_id", help="Game ID")
    parser.add_argument("identifier", help="V1: Build timestamp, V2: Repository hash")
    parser.add_argument("game_name", help="Game name (for directory structure)")
    parser.add_argument("--platform", default="windows", 
                       choices=["windows", "osx", "linux"],
                       help="Platform to validate (V1 only, default: windows)")
    parser.add_argument("--sample", type=int, metavar="N",
                       help="Number of files/chunks to randomly sample (default: all)")
    parser.add_argument("--random-seed", type=int, metavar="SEED",
                       help="Random seed for reproducible sampling")
    
    args = parser.parse_args()
    
    if args.build_type == "v1":
        success = validate_v1_build(
            args.game_id,
            args.identifier,
            args.game_name,
            platform=args.platform,
            sample_size=args.sample,
            random_seed=args.random_seed
        )
        sys.exit(0 if success else 1)
    elif args.build_type == "v2":
        success = validate_v2_build(
            args.game_id,
            args.identifier,
            args.game_name,
            sample_size=args.sample,
            random_seed=args.random_seed
        )
        sys.exit(0 if success else 1)
    else:
        print(f"ERROR: Unsupported build type: {args.build_type}")
        sys.exit(1)


if __name__ == "__main__":
    main()
