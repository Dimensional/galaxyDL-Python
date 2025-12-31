"""
RGOG Unpack Command

Unpacks RGOG archives to recreate the original GOG Galaxy v2 directory structure.
This is the opposite of the pack command - it extracts repository files, manifests,
and chunks back to their original locations. Supports multi-threaded extraction.
"""

import json
import zlib
import multiprocessing
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from .common import (
    RGOGHeader, ProductMetadata, BuildMetadata, ChunkMetadata,
    SECTION_ALIGNMENT,
    bytes_to_md5, align_to_boundary,
)


@dataclass
class ChunkExtractionTask:
    """A chunk extraction task."""
    part_path: Path
    chunk_index: int
    chunk_id: str
    offset: int
    size: int
    output_path: Path


class ExtractionStats:
    """Thread-safe statistics tracker for extraction."""
    def __init__(self):
        self.lock = Lock()
        self.extracted = 0
        self.errors = 0
    
    def add_extracted(self):
        with self.lock:
            self.extracted += 1
    
    def add_error(self):
        with self.lock:
            self.errors += 1
    
    def get_stats(self):
        with self.lock:
            return (self.extracted, self.errors)


def extract_chunk_worker(task: ChunkExtractionTask) -> tuple:
    """Worker function to extract a single chunk."""
    try:
        # Read chunk data from archive
        with open(task.part_path, 'rb') as f:
            f.seek(task.offset)
            chunk_data = f.read(task.size)
        
        # Create directory if needed
        task.output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write chunk file
        with open(task.output_path, 'wb') as cf:
            cf.write(chunk_data)
        
        return (task.chunk_index, True, None)
    
    except Exception as e:
        return (task.chunk_index, False, str(e))



def read_header(f) -> RGOGHeader:
    """Read and parse RGOG header from file."""
    header_data = f.read(128)
    return RGOGHeader.from_bytes(header_data)


def read_product_metadata(f, header: RGOGHeader) -> ProductMetadata:
    """Read and parse product metadata."""
    f.seek(header.product_metadata_offset)
    product_data = f.read(header.product_metadata_size)
    return ProductMetadata.from_bytes(product_data)


def read_build_metadata_list(f, header: RGOGHeader) -> List[BuildMetadata]:
    """Read all build metadata entries."""
    builds = []
    f.seek(header.build_metadata_offset)
    
    # Read the entire build metadata section
    build_metadata_data = f.read(header.build_metadata_size)
    
    # Parse build entries
    offset = 0
    while offset < len(build_metadata_data):
        # Check if we have enough data for the base header
        if offset + 48 > len(build_metadata_data):
            break
        
        # Parse the build metadata (which includes all manifests)
        build_meta = BuildMetadata.from_bytes(build_metadata_data[offset:])
        builds.append(build_meta)
        
        # Move offset forward by build size (48 + 56 * manifest_count)
        offset += build_meta.size()
    
    return builds


def read_chunk_metadata_list(f, header: RGOGHeader) -> List[ChunkMetadata]:
    """Read all chunk metadata entries."""
    chunks = []
    f.seek(header.chunk_metadata_offset)
    
    # Each chunk metadata is 32 bytes
    chunk_count = header.chunk_metadata_size // 32
    for _ in range(chunk_count):
        chunk_data = f.read(32)
        if len(chunk_data) < 32:
            break
        chunk_meta = ChunkMetadata.from_bytes(chunk_data)
        chunks.append(chunk_meta)
    
    return chunks


def unpack_build_files(
    f,
    header: RGOGHeader,
    builds: List[BuildMetadata],
    output_dir: Path,
    create_debug: bool = True,
):
    """
    Unpack repository files and depot manifests to meta/ directory.
    Optionally create human-readable debug copies.
    """
    meta_dir = output_dir / 'meta'
    meta_dir.mkdir(parents=True, exist_ok=True)
    
    if create_debug:
        debug_dir = output_dir / 'debug'
        debug_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nUnpacking build files to {meta_dir}")
    
    for build in builds:
        # Extract repository file
        repo_filename = bytes_to_md5(build.repository_id)
        repo_path = meta_dir / repo_filename
        
        f.seek(header.build_files_offset + build.repository_offset)
        repo_data = f.read(build.repository_size)
        
        # Write compressed repository file
        with open(repo_path, 'wb') as rf:
            rf.write(repo_data)
        
        print(f"  Extracted repository: {repo_filename} ({build.repository_size} bytes)")
        
        # Create human-readable debug copy if requested
        if create_debug:
            try:
                decompressed = zlib.decompress(repo_data)
                # Parse and pretty-print JSON for readability
                json_data = json.loads(decompressed)
                debug_path = debug_dir / f"{repo_filename}_repository.json"
                with open(debug_path, 'w', encoding='utf-8') as df:
                    json.dump(json_data, df, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"    Warning: Failed to create debug copy: {e}")
        
        # Extract depot manifests for this build
        for manifest in build.manifests:
            depot_filename = bytes_to_md5(manifest.depot_id)
            depot_path = meta_dir / depot_filename
            
            f.seek(header.build_files_offset + manifest.offset)
            depot_data = f.read(manifest.size)
            
            # Write compressed depot manifest file
            with open(depot_path, 'wb') as mf:
                mf.write(depot_data)
            
            print(f"  Extracted depot manifest: {depot_filename} ({manifest.size} bytes)")
            
            # Create human-readable debug copy if requested
            if create_debug:
                try:
                    decompressed = zlib.decompress(depot_data)
                    # Parse and pretty-print JSON for readability
                    json_data = json.loads(decompressed)
                    debug_path = debug_dir / f"{depot_filename}_manifest.json"
                    with open(debug_path, 'w', encoding='utf-8') as df:
                        json.dump(json_data, df, indent=2, ensure_ascii=False)
                except Exception as e:
                    print(f"    Warning: Failed to create debug copy: {e}")


def unpack_chunk_files(
    part_path: Path,
    header: RGOGHeader,
    chunks: List[ChunkMetadata],
    output_dir: Path,
    thread_count: int = 1,
):
    """
    Unpack chunk files to store/ directory using nested structure.
    Structure: store/{hex0:2}/{hex2:2}/{fullhash}
    """
    store_dir = output_dir / 'store'
    store_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nUnpacking {len(chunks)} chunk files to {store_dir}")
    
    # Build extraction tasks
    tasks = []
    for i, chunk in enumerate(chunks, 1):
        chunk_id = bytes_to_md5(chunk.compressed_md5)
        
        # Create nested directory structure path
        # Example: 0030af763e1a09ab307d84a24d0066a2 -> store/00/30/0030af763e1a09ab307d84a24d0066a2
        subdir1 = chunk_id[:2]
        subdir2 = chunk_id[2:4]
        chunk_path = store_dir / subdir1 / subdir2 / chunk_id
        
        # Offset is absolute
        absolute_offset = header.chunk_files_offset + chunk.offset
        
        tasks.append(ChunkExtractionTask(
            part_path=part_path,
            chunk_index=i,
            chunk_id=chunk_id,
            offset=absolute_offset,
            size=chunk.size,
            output_path=chunk_path
        ))
    
    stats = ExtractionStats()
    
    if thread_count > 1 and len(tasks) > 10:
        # Multi-threaded extraction
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            futures = {executor.submit(extract_chunk_worker, task): task for task in tasks}
            
            last_progress = 0
            for future in as_completed(futures):
                chunk_index, success, error = future.result()
                
                if success:
                    stats.add_extracted()
                else:
                    stats.add_error()
                    print(f"  ✗ Chunk {chunk_index}: {error}")
                
                # Update progress every 100 chunks
                extracted, errors = stats.get_stats()
                total_processed = extracted + errors
                if total_processed % 100 == 0 or total_processed == len(tasks):
                    if total_processed != last_progress:
                        print(f"  Progress: {total_processed}/{len(tasks)} chunks extracted")
                        last_progress = total_processed
    else:
        # Single-threaded extraction
        for i, task in enumerate(tasks, 1):
            chunk_index, success, error = extract_chunk_worker(task)
            
            if success:
                stats.add_extracted()
            else:
                stats.add_error()
                print(f"  ✗ Chunk {chunk_index}: {error}")
            
            if i % 100 == 0 or i == len(tasks):
                print(f"  Progress: {i}/{len(tasks)} chunks extracted")


def unpack_part_0(
    archive_path: Path,
    output_dir: Path,
    create_debug: bool = True,
    chunks_only: bool = False,
    thread_count: int = 1,
):
    """Unpack Part 1 (main part with all metadata)."""
    with open(archive_path, 'rb') as f:
        # Read header
        header = read_header(f)
        
        print(f"RGOG Archive Part 1")
        print(f"  Total builds: {header.total_build_count}")
        print(f"  Total chunks (all parts): {header.total_chunk_count}")
        print(f"  Local chunks (this part): {header.local_chunk_count}")
        
        # Read product metadata
        product = read_product_metadata(f, header)
        print(f"  Product: {product.product_name} (ID: {product.product_id})")
        
        if not chunks_only:
            # Read and unpack build files
            builds = read_build_metadata_list(f, header)
            unpack_build_files(f, header, builds, output_dir, create_debug)
        
        # Read chunk metadata
        if header.local_chunk_count > 0:
            chunks = read_chunk_metadata_list(f, header)
    
    # Unpack chunks (outside the with block for threading)
    if header.local_chunk_count > 0:
        unpack_chunk_files(archive_path, header, chunks, output_dir, thread_count)


def unpack_part_n(
    archive_path: Path,
    output_dir: Path,
    part_number: int,
    thread_count: int = 1,
):
    """Unpack Part N (additional parts with only chunks)."""
    with open(archive_path, 'rb') as f:
        # Read header
        header = read_header(f)
        
        print(f"\nRGOG Archive Part {part_number}")
        print(f"  Local chunks (this part): {header.local_chunk_count}")
        
        # Read chunk metadata
        if header.local_chunk_count > 0:
            chunks = read_chunk_metadata_list(f, header)
    
    # Unpack chunks (outside the with block for threading)
    if header.local_chunk_count > 0:
        unpack_chunk_files(archive_path, header, chunks, output_dir, thread_count)


def execute(args):
    """Execute the unpack command."""
    archive_path = args.archive
    output_dir = args.output
    create_debug = args.debug
    chunks_only = args.chunks_only
    thread_count = args.threads if args.threads > 0 else multiprocessing.cpu_count()
    
    if not archive_path.exists():
        print(f"Error: Archive file not found: {archive_path}")
        return 1
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Unpacking: {archive_path}")
    print(f"Output directory: {output_dir}")
    print(f"Create debug files: {create_debug}")
    print(f"Chunks only: {chunks_only}")
    if thread_count > 1:
        print(f"Using {thread_count} threads for extraction")
    print()
    
    # Check if this is a multi-part archive
    # Read header to check part number and total parts
    with open(archive_path, 'rb') as f:
        header = read_header(f)
    
    if header.total_parts == 1:
        # Single-file archive
        unpack_part_0(archive_path, output_dir, create_debug, chunks_only, thread_count)
    else:
        # Multi-part archive
        print(f"Multi-part archive detected: {header.total_parts} parts")
        
        # Determine naming pattern and find all parts
        # Common patterns:
        # 1. DREDGE_1.rgog, DREDGE_2.rgog, DREDGE_3.rgog (sequential numbering)
        # 2. GAME.rgog, GAME.part1.rgog, GAME.part2.rgog (part suffix)
        
        archive_parent = archive_path.parent
        archive_name = archive_path.stem  # Filename without .rgog
        
        # Try to detect the naming pattern
        # Check if the current file ends with a number (e.g., DREDGE_1)
        if archive_name[-1].isdigit():
            # Sequential numbering pattern: find base name by removing trailing digits and underscore
            parts = archive_name.rsplit('_', 1)
            if len(parts) == 2 and parts[1].isdigit():
                base_name = parts[0]
                part_0_path = archive_parent / f"{base_name}_1.rgog"
                
                # Unpack Part 0
                if part_0_path.exists():
                    unpack_part_0(part_0_path, output_dir, create_debug, chunks_only, thread_count)
                else:
                    print(f"Error: Part 1 not found: {part_0_path}")
                    return 1
                
                # Unpack additional parts (2, 3, 4, ...)
                for part_num in range(2, header.total_parts + 1):
                    part_path = archive_parent / f"{base_name}_{part_num}.rgog"
                    
                    if part_path.exists():
                        unpack_part_n(part_path, output_dir, part_num, thread_count)
                    else:
                        print(f"Warning: Part {part_num} not found: {part_path}")
            else:
                # Fallback to treating current file as part 0
                unpack_part_0(archive_path, output_dir, create_debug, chunks_only, thread_count)
        else:
            # Part suffix pattern: GAME.rgog, GAME.part1.rgog, GAME.part2.rgog
            part_0_path = archive_path  # First file is GAME.rgog
            
            # Unpack Part 0
            unpack_part_0(part_0_path, output_dir, create_debug, chunks_only, thread_count)
            
            # Unpack additional parts (.part1.rgog, .part2.rgog, ...)
            for part_num in range(1, header.total_parts):
                part_path = archive_parent / f"{archive_name}.part{part_num}.rgog"
                
                if part_path.exists():
                    unpack_part_n(part_path, output_dir, part_num, thread_count)
                else:
                    print(f"Warning: Part {part_num} not found: {part_path}")
    
    print(f"\nUnpacking complete!")
    print(f"Output written to: {output_dir}")
    
    if create_debug and not chunks_only:
        debug_dir = output_dir / 'debug'
        print(f"Human-readable debug files: {debug_dir}")
    
    return 0
