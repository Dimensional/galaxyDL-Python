"""
RGOG Verify Command

Verifies the integrity of RGOG archives by checking MD5 checksums
and validating binary structure. Supports multi-threaded verification
and full decompression verification.
"""

import hashlib
import struct
import zlib
import json
import multiprocessing
import heapq
from pathlib import Path
from typing import Dict, Set, Tuple, List, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from .common import RGOGHeader, bytes_to_md5, resolve_first_part, get_all_parts


@dataclass
class ChunkInfo:
    """Information about a chunk from build records."""
    compressed_md5: bytes
    decompressed_md5: Optional[bytes] = None
    compressed_size: Optional[int] = None
    decompressed_size: Optional[int] = None


@dataclass
class VerificationTask:
    """A chunk verification task."""
    part_path: Path
    chunk_index: int
    compressed_md5: bytes
    offset: int
    compressed_size: int
    decompressed_md5: Optional[bytes] = None


@dataclass(order=True)
class VerificationResult:
    """Result of a verification task (ordered by chunk_index for priority queue)."""
    chunk_index: int
    part_name: str = field(compare=False)
    success: bool = field(compare=False)
    error_message: Optional[str] = field(default=None, compare=False)
    compressed_md5_str: Optional[str] = field(default=None, compare=False)
    decompressed_md5_str: Optional[str] = field(default=None, compare=False)


class VerificationStats:
    """Thread-safe statistics tracker."""
    def __init__(self):
        self.lock = Lock()
        self.errors = 0
        self.verified_compressed = 0
        self.verified_decompressed = 0
    
    def add_error(self):
        with self.lock:
            self.errors += 1
    
    def add_verified_compressed(self):
        with self.lock:
            self.verified_compressed += 1
    
    def add_verified_decompressed(self):
        with self.lock:
            self.verified_decompressed += 1
    
    def get_stats(self) -> Tuple[int, int, int]:
        with self.lock:
            return (self.errors, self.verified_compressed, self.verified_decompressed)


def collect_chunk_info_from_builds(first_part_path: Path, header: RGOGHeader) -> Dict[bytes, ChunkInfo]:
    """
    Parse all build records to collect chunk information.
    
    Returns a dictionary mapping compressed_md5 -> ChunkInfo with decompressed MD5.
    """
    chunk_map: Dict[bytes, ChunkInfo] = {}
    
    if header.total_build_count == 0:
        return chunk_map
    
    with open(first_part_path, 'rb') as f:
        # Seek to build metadata section
        f.seek(header.build_metadata_offset)
        
        for i in range(header.total_build_count):
            # Read build metadata header (48 bytes)
            build_header = f.read(48)
            if len(build_header) != 48:
                continue
            
            # Parse: build_id (8) + os (1) + padding (3) + repository_id (16) + offset (8) + size (8) + manifest_count (2) + padding (2)
            build_id, os, repo_md5, repo_offset, repo_size, manifest_count = struct.unpack('<QB3x16sQQH2x', build_header)
            
            # Read manifest entries (56 bytes each)
            manifests = []
            for j in range(manifest_count):
                manifest_data = f.read(56)
                if len(manifest_data) != 56:
                    continue
                # Parse: depot_id (16) + offset (8) + size (8) + languages1 (8) + languages2 (8) + product_id (8)
                depot_id, depot_offset, depot_size, lang1, lang2, product_id = struct.unpack('<16sQQQQQ', manifest_data)
                manifests.append((depot_id, depot_offset, depot_size))
            
            # Process each depot manifest to extract chunk information
            for depot_id, depot_offset, depot_size in manifests:
                current_pos = f.tell()
                absolute_offset = header.build_files_offset + depot_offset
                f.seek(absolute_offset)
                depot_data = f.read(depot_size)
                f.seek(current_pos)
                
                if len(depot_data) != depot_size:
                    continue
                
                try:
                    # Decompress and parse manifest JSON
                    decompressed_data = zlib.decompress(depot_data)
                    manifest_json = json.loads(decompressed_data)
                    
                    # Extract chunks from manifest
                    depot = manifest_json.get('depot', {})
                    
                    # Process depot.items[].chunks[]
                    for item in depot.get('items', []):
                        if 'chunks' in item:
                            for chunk in item['chunks']:
                                compressed_md5_str = chunk.get('compressedMd5')
                                decompressed_md5_str = chunk.get('md5')
                                compressed_size = chunk.get('compressedSize')
                                decompressed_size = chunk.get('size')
                                
                                if compressed_md5_str:
                                    compressed_md5 = bytes.fromhex(compressed_md5_str)
                                    decompressed_md5 = bytes.fromhex(decompressed_md5_str) if decompressed_md5_str else None
                                    
                                    # Add or update chunk info
                                    if compressed_md5 not in chunk_map:
                                        chunk_map[compressed_md5] = ChunkInfo(
                                            compressed_md5=compressed_md5,
                                            decompressed_md5=decompressed_md5,
                                            compressed_size=compressed_size,
                                            decompressed_size=decompressed_size
                                        )
                                    elif decompressed_md5 and not chunk_map[compressed_md5].decompressed_md5:
                                        # Update if we didn't have decompressed info before
                                        chunk_map[compressed_md5].decompressed_md5 = decompressed_md5
                                        chunk_map[compressed_md5].decompressed_size = decompressed_size
                    
                    # Process depot.smallFilesContainer.chunks[]
                    sfc = depot.get('smallFilesContainer', {})
                    if 'chunks' in sfc:
                        for chunk in sfc['chunks']:
                            compressed_md5_str = chunk.get('compressedMd5')
                            decompressed_md5_str = chunk.get('md5')
                            compressed_size = chunk.get('compressedSize')
                            decompressed_size = chunk.get('size')
                            
                            if compressed_md5_str:
                                compressed_md5 = bytes.fromhex(compressed_md5_str)
                                decompressed_md5 = bytes.fromhex(decompressed_md5_str) if decompressed_md5_str else None
                                
                                # Add or update chunk info
                                if compressed_md5 not in chunk_map:
                                    chunk_map[compressed_md5] = ChunkInfo(
                                        compressed_md5=compressed_md5,
                                        decompressed_md5=decompressed_md5,
                                        compressed_size=compressed_size,
                                        decompressed_size=decompressed_size
                                    )
                                elif decompressed_md5 and not chunk_map[compressed_md5].decompressed_md5:
                                    # Update if we didn't have decompressed info before
                                    chunk_map[compressed_md5].decompressed_md5 = decompressed_md5
                                    chunk_map[compressed_md5].decompressed_size = decompressed_size
                                        
                except (zlib.error, json.JSONDecodeError, KeyError):
                    # Skip invalid manifests
                    continue
    
    return chunk_map


def verify_chunk_worker(task: VerificationTask, full_verify: bool) -> VerificationResult:
    """
    Worker function to verify a single chunk.
    
    Verifies compressed MD5 and optionally decompressed MD5 if full_verify is True.
    """
    try:
        # Read chunk data
        with open(task.part_path, 'rb') as f:
            f.seek(task.offset)
            chunk_data = f.read(task.compressed_size)
        
        if len(chunk_data) != task.compressed_size:
            return VerificationResult(
                chunk_index=task.chunk_index,
                part_name=task.part_path.name,
                success=False,
                error_message=f"Size mismatch (expected {task.compressed_size}, got {len(chunk_data)})"
            )
        
        # Verify compressed MD5
        actual_compressed_md5 = hashlib.md5(chunk_data).digest()
        if actual_compressed_md5 != task.compressed_md5:
            expected = bytes_to_md5(task.compressed_md5)
            got = bytes_to_md5(actual_compressed_md5)
            return VerificationResult(
                chunk_index=task.chunk_index,
                part_name=task.part_path.name,
                success=False,
                error_message=f"Compressed MD5 mismatch (expected {expected}, got {got})"
            )
        
        compressed_md5_str = bytes_to_md5(task.compressed_md5)
        decompressed_md5_str = None
        
        # Verify decompressed MD5 if full verification
        if full_verify and task.decompressed_md5:
            try:
                decompressed_data = zlib.decompress(chunk_data)
                actual_decompressed_md5 = hashlib.md5(decompressed_data).digest()
                
                if actual_decompressed_md5 != task.decompressed_md5:
                    expected = bytes_to_md5(task.decompressed_md5)
                    got = bytes_to_md5(actual_decompressed_md5)
                    return VerificationResult(
                        chunk_index=task.chunk_index,
                        part_name=task.part_path.name,
                        success=False,
                        error_message=f"Decompressed MD5 mismatch (expected {expected}, got {got})",
                        compressed_md5_str=compressed_md5_str
                    )
                
                decompressed_md5_str = bytes_to_md5(task.decompressed_md5)
                
            except zlib.error as e:
                return VerificationResult(
                    chunk_index=task.chunk_index,
                    part_name=task.part_path.name,
                    success=False,
                    error_message=f"Decompression failed: {e}",
                    compressed_md5_str=compressed_md5_str
                )
        
        return VerificationResult(
            chunk_index=task.chunk_index,
            part_name=task.part_path.name,
            success=True,
            compressed_md5_str=compressed_md5_str,
            decompressed_md5_str=decompressed_md5_str
        )
        
    except Exception as e:
        return VerificationResult(
            chunk_index=task.chunk_index,
            part_name=task.part_path.name,
            success=False,
            error_message=f"Unexpected error: {e}"
        )


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
    
    # Determine thread count
    thread_count = args.threads if args.threads > 0 else multiprocessing.cpu_count()
    full_verify = args.full
    
    print(f"RGOG Verify: {first_part_path.stem.rsplit('_', 1)[0] if header.total_parts > 1 else first_part_path.name}")
    print(f"Verifying {len(all_parts)} part(s)...")
    if not args.quick and thread_count > 1:
        print(f"Using {thread_count} threads for verification")
    if full_verify:
        print("Full verification mode: verifying both compressed and decompressed chunks")
    
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
        stats = VerificationStats()
        
        # Collect chunk information from builds for full verification
        chunk_map: Dict[bytes, ChunkInfo] = {}
        if full_verify and header.total_build_count > 0:
            print(f"\nCollecting chunk information from {header.total_build_count} build(s)...")
            chunk_map = collect_chunk_info_from_builds(first_part_path, header)
            chunks_with_decompressed = sum(1 for info in chunk_map.values() if info.decompressed_md5)
            print(f"Found {len(chunk_map)} unique chunks, {chunks_with_decompressed} with decompressed MD5")
        
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
                        stats.add_error()
                        continue
                    
                    # Parse: build_id (8) + os (1) + padding (3) + repository_id (16) + offset (8) + size (8) + manifest_count (2) + padding (2)
                    build_id, os, repo_md5, repo_offset, repo_size, manifest_count = struct.unpack('<QB3x16sQQH2x', build_header)
                    
                    # Read manifest entries (56 bytes each)
                    manifests = []
                    for j in range(manifest_count):
                        manifest_data = f.read(56)
                        if len(manifest_data) != 56:
                            print(f"✗ Build {i + 1}: Failed to read manifest {j + 1}")
                            stats.add_error()
                            continue
                        # Parse: depot_id (16) + offset (8) + size (8) + languages1 (8) + languages2 (8) + product_id (8)
                        depot_id, depot_offset, depot_size, lang1, lang2, product_id = struct.unpack('<16sQQQQQ', manifest_data)
                        manifests.append((depot_id, depot_offset, depot_size))
                    
                    # Read repository file
                    current_pos = f.tell()
                    absolute_offset = header.build_files_offset + repo_offset
                    f.seek(absolute_offset)
                    repo_data = f.read(repo_size)
                    f.seek(current_pos)
                    
                    if len(repo_data) != repo_size:
                        print(f"✗ Build {i + 1}: Size mismatch (expected {repo_size}, got {len(repo_data)})")
                        stats.add_error()
                        continue
                    
                    # Calculate MD5
                    actual_md5 = hashlib.md5(repo_data).digest()
                    
                    if actual_md5 != repo_md5:
                        expected = bytes_to_md5(repo_md5)
                        got = bytes_to_md5(actual_md5)
                        print(f"✗ Build {i + 1}: MD5 mismatch (expected {expected}, got {got})")
                        stats.add_error()
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
                            stats.add_error()
                            continue
                        
                        # Calculate MD5
                        actual_depot_md5 = hashlib.md5(depot_data).digest()
                        
                        if actual_depot_md5 != depot_id:
                            expected = bytes_to_md5(depot_id)
                            got = bytes_to_md5(actual_depot_md5)
                            print(f"✗ Build {i + 1}, Depot {j + 1}: MD5 mismatch (expected {expected}, got {got})")
                            stats.add_error()
                            continue
                        
                        if args.detailed:
                            depot_md5_str = bytes_to_md5(depot_id)
                            print(f"    ✓ Depot {j + 1}: {depot_md5_str} ({depot_size} bytes)")
                
                errors, _, _ = stats.get_stats()
                if errors == 0:
                    print(f"✓ All {header.total_build_count} build file(s) verified successfully")
        
        # Verify chunk MD5 checksums across all parts (multi-threaded)
        if header.total_chunk_count > 0:
            mode_str = "compressed and decompressed" if full_verify else "compressed"
            print(f"\nVerifying {header.total_chunk_count} chunks ({mode_str}) across {len(all_parts)} part(s)...")
            
            # Build task list
            tasks: List[VerificationTask] = []
            global_chunk_index = 1  # Sequential counter across all parts
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
                            stats.add_error()
                            continue
                        
                        # Parse: compressed_md5 (16) + offset (8) + compressed_size (8)
                        compressed_md5, offset, compressed_size = struct.unpack('<16sQQ', chunk_meta)
                        
                        # Offset is relative to chunk_files_offset, make it absolute
                        absolute_offset = part_header.chunk_files_offset + offset
                        
                        # Get decompressed MD5 if available
                        decompressed_md5 = None
                        if full_verify and compressed_md5 in chunk_map:
                            decompressed_md5 = chunk_map[compressed_md5].decompressed_md5
                        
                        tasks.append(VerificationTask(
                            part_path=part_path,
                            chunk_index=global_chunk_index,
                            compressed_md5=compressed_md5,
                            offset=absolute_offset,
                            compressed_size=compressed_size,
                            decompressed_md5=decompressed_md5
                        ))
                        global_chunk_index += 1
            
            # Execute verification tasks in parallel
            if thread_count > 1:
                with ThreadPoolExecutor(max_workers=thread_count) as executor:
                    # Submit all tasks
                    futures = {executor.submit(verify_chunk_worker, task, full_verify): task for task in tasks}
                    
                    # Priority queue to maintain order and next expected chunk index
                    result_queue: List[VerificationResult] = []
                    next_chunk_to_display = 1
                    
                    # Process results as they complete
                    for future in as_completed(futures):
                        result = future.result()
                        
                        # Add to priority queue
                        heapq.heappush(result_queue, result)
                        
                        # Display all results that are now in order
                        while result_queue and result_queue[0].chunk_index == next_chunk_to_display:
                            ordered_result = heapq.heappop(result_queue)
                            
                            if not ordered_result.success:
                                print(f"✗ Part {ordered_result.part_name}, Chunk {ordered_result.chunk_index}: {ordered_result.error_message}")
                                stats.add_error()
                            else:
                                stats.add_verified_compressed()
                                if ordered_result.decompressed_md5_str:
                                    stats.add_verified_decompressed()
                                
                                if args.detailed:
                                    detail_str = f"  ✓ Part {ordered_result.part_name}, Chunk {ordered_result.chunk_index}: {ordered_result.compressed_md5_str}"
                                    if ordered_result.decompressed_md5_str:
                                        detail_str += f" (decompressed: {ordered_result.decompressed_md5_str})"
                                    print(detail_str)
                            
                            next_chunk_to_display += 1
            else:
                # Single-threaded execution
                for task in tasks:
                    result = verify_chunk_worker(task, full_verify)
                    
                    if not result.success:
                        print(f"✗ Part {result.part_name}, Chunk {result.chunk_index}: {result.error_message}")
                        stats.add_error()
                    else:
                        stats.add_verified_compressed()
                        if result.decompressed_md5_str:
                            stats.add_verified_decompressed()
                        
                        if args.detailed:
                            detail_str = f"  ✓ Part {result.part_name}, Chunk {result.chunk_index}: {result.compressed_md5_str}"
                            if result.decompressed_md5_str:
                                detail_str += f" (decompressed: {result.decompressed_md5_str})"
                            print(detail_str)
            
            errors, verified_compressed, verified_decompressed = stats.get_stats()
            if errors == 0:
                success_msg = f"✓ All {header.total_chunk_count} chunks verified successfully"
                if full_verify and verified_decompressed > 0:
                    success_msg += f" ({verified_decompressed} decompressed)"
                print(success_msg)
        
        # Final result
        errors, _, _ = stats.get_stats()
        if errors > 0:
            print(f"\n✗ Verification failed: {errors} error(s) found")
            return 1
    
    return 0
