"""
RGOG Pack Command

Creates RGOG archives from GOG Galaxy v2 directory structures.
Implements the complete packing workflow with metadata-first layout.
"""

import zlib
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

from .common import (
    RGOGHeader, ProductMetadata, BuildMetadata, ManifestEntry, ChunkMetadata,
    ARCHIVE_TYPE_BASE, ARCHIVE_TYPE_PATCH, SECTION_ALIGNMENT, DEFAULT_PART_SIZE,
    OS_WINDOWS, OS_MAC, OS_LINUX, OS_NULL,
    md5_to_bytes, bytes_to_md5, align_to_boundary, get_padding,
    identify_and_parse_meta_file, parse_manifest_file, find_depot_manifest_file,
    languages_to_bitflags, sort_files_alphanumeric, calculate_metadata_size,
)


@dataclass
class RepositoryInfo:
    """Information about a repository file."""
    path: Path
    filename: str
    build_id: int
    product_id: int
    platform: str
    depot_ids: List[str]
    offline_depot_id: Optional[str]
    depot_languages: Dict[str, List[str]]  # Map depot_id -> language list
    file_size: int


@dataclass
class ChunkInfo:
    """Information about a chunk file."""
    path: Path
    filename: str  # MD5 hex string
    compressed_md5: bytes  # 16-byte binary
    file_size: int
    part_number: int = 0


@dataclass
class PartAssignment:
    """Chunk assignment for a specific part."""
    part_number: int
    chunks: List[ChunkInfo]
    total_size: int


def parse_size_string(size_str: str) -> int:
    """
    Parse human-readable size string to bytes.
    
    Examples: '2GB', '4GiB', '10G', '500MB'
    """
    size_str = size_str.upper().strip()
    
    multipliers = {
        'KB': 1024,
        'KIB': 1024,
        'K': 1024,
        'MB': 1024 * 1024,
        'MIB': 1024 * 1024,
        'M': 1024 * 1024,
        'GB': 1024 * 1024 * 1024,
        'GIB': 1024 * 1024 * 1024,
        'G': 1024 * 1024 * 1024,
        'TB': 1024 * 1024 * 1024 * 1024,
        'TIB': 1024 * 1024 * 1024 * 1024,
        'T': 1024 * 1024 * 1024 * 1024,
    }
    
    for suffix, multiplier in multipliers.items():
        if size_str.endswith(suffix):
            try:
                value = float(size_str[:-len(suffix)])
                return int(value * multiplier)
            except ValueError:
                pass
    
    # Try parsing as plain number
    try:
        return int(size_str)
    except ValueError:
        raise ValueError(f"Invalid size string: {size_str}")


def scan_repositories(meta_dir: Path) -> List[RepositoryInfo]:
    """
    Scan and identify repository files in the meta directory.
    Ignores depot manifest files (not needed for packing).
    
    Returns sorted list of RepositoryInfo objects.
    """
    repositories = []
    
    # Find all files in meta directory
    meta_files = list(meta_dir.rglob('*'))
    
    for file_path in meta_files:
        if not file_path.is_file():
            continue
        
        try:
            # Read and decompress file
            with open(file_path, 'rb') as f:
                compressed_data = f.read()
            
            try:
                decompressed_data = zlib.decompress(compressed_data)
            except zlib.error:
                continue  # Not a zlib file, skip
            
            # Identify and parse meta file
            repo_data = identify_and_parse_meta_file(decompressed_data)
            if repo_data:  # Only returns data if it's a repository file
                # Map platform string to OS code
                platform = repo_data.get('platform', '').lower()
                os_code = {
                    'windows': OS_WINDOWS,
                    'osx': OS_MAC,
                    'mac': OS_MAC,
                    'linux': OS_LINUX,
                }.get(platform, OS_NULL)
                
                repositories.append(RepositoryInfo(
                    path=file_path,
                    filename=file_path.name,
                    build_id=repo_data['buildId'],
                    product_id=repo_data['productId'],
                    platform=platform,
                    depot_ids=repo_data['depotIds'],
                    offline_depot_id=repo_data.get('offlineDepotId'),
                    depot_languages=repo_data.get('depotLanguages', {}),
                    file_size=len(compressed_data),
                ))
                
        except Exception as e:
            print(f"Warning: Failed to process {file_path}: {e}")
            continue
    
    # Sort by filename
    repositories.sort(key=lambda r: r.filename.lower())
    return repositories


def scan_chunks(chunks_dir: Path) -> List[ChunkInfo]:
    """
    Scan all chunk files in the store directory.
    
    Chunk files are stored in nested structure: store/{hex0:2}/{hex2:2}/{fullhash}
    Returns sorted list of ChunkInfo objects.
    """
    chunks = []
    
    # Find all files in nested store directory structure
    # Pattern: store/XX/YY/hash (where XX = first 2 hex chars, YY = next 2 hex chars)
    chunk_files = list(chunks_dir.rglob('*/*/*'))
    
    for chunk_path in chunk_files:
        if not chunk_path.is_file():
            continue
        
        filename = chunk_path.name  # Just the MD5 hash
        
        # Skip if not a valid MD5 hex string (32 chars)
        if len(filename) != 32:
            continue
        
        # Verify it matches the expected path structure: store/{hex0:2}/{hex2:2}/{fullhash}
        # chunk_path.parent.parent.parent should be chunks_dir (3 levels deep)
        if chunk_path.parent.parent.parent != chunks_dir:
            continue
        
        try:
            # Convert filename (MD5 hex) to binary
            compressed_md5 = md5_to_bytes(filename)
            file_size = chunk_path.stat().st_size
            
            chunks.append(ChunkInfo(
                path=chunk_path,
                filename=filename,
                compressed_md5=compressed_md5,
                file_size=file_size,
            ))
        except Exception as e:
            print(f"Warning: Failed to process chunk {chunk_path}: {e}")
            continue
    
    # Sort by filename (alphanumeric)
    chunks.sort(key=lambda c: c.filename.lower())
    return chunks


def get_chunks_for_build(
    meta_dir: Path,
    chunks_dir: Path,
    repository: RepositoryInfo,
) -> List[ChunkInfo]:
    """
    Get filtered and deduplicated chunks for a specific build.
    
    Parses depot manifests to extract chunk lists, deduplicates,
    and returns only chunks that exist on disk.
    
    Note: Skips offlineDepot chunks as they cannot be downloaded currently.
    """
    all_chunk_ids = set()
    
    # Process each depot manifest referenced by the repository
    for depot_id in repository.depot_ids:
        # Skip offlineDepot chunks (manifest is preserved but chunks not downloadable)
        if depot_id == repository.offline_depot_id:
            print(f"  Depot {depot_id} (offlineDepot): Skipped (chunks not downloadable)")
            continue
        
        manifest_path = find_depot_manifest_file(meta_dir, depot_id)
        if not manifest_path:
            print(f"  Warning: Depot manifest {depot_id} not found, skipping")
            continue
        
        try:
            # Read and decompress manifest
            with open(manifest_path, 'rb') as f:
                compressed_data = f.read()
            
            decompressed_data = zlib.decompress(compressed_data)
            manifest_data = parse_manifest_file(decompressed_data)
            
            # Add chunks to set (automatic deduplication)
            for chunk_id in manifest_data.get('chunks', []):
                all_chunk_ids.add(chunk_id.lower())
            
            print(f"  Depot {depot_id}: {len(manifest_data.get('chunks', []))} chunks")
            
        except Exception as e:
            print(f"  Warning: Failed to process depot {depot_id}: {e}")
            continue
    
    print(f"  Total unique chunks needed: {len(all_chunk_ids)}")
    
    # Find chunk files that match the IDs
    chunks = []
    for chunk_id in sorted(all_chunk_ids):  # Alphanumeric sort
        # Construct path using nested structure: store/{hex0:2}/{hex2:2}/{fullhash}
        # Example: 0030af763e1a09ab307d84a24d0066a2 -> store/00/30/0030af763e1a09ab307d84a24d0066a2
        chunk_path = chunks_dir / chunk_id[:2] / chunk_id[2:4] / chunk_id
        
        if not chunk_path.exists():
            print(f"  Warning: Chunk file {chunk_id} not found")
            continue
        
        try:
            compressed_md5 = md5_to_bytes(chunk_id)
            file_size = chunk_path.stat().st_size
            
            chunks.append(ChunkInfo(
                path=chunk_path,
                filename=chunk_id,
                compressed_md5=compressed_md5,
                file_size=file_size,
            ))
        except Exception as e:
            print(f"  Warning: Failed to process chunk {chunk_id}: {e}")
            continue
    
    print(f"  Found {len(chunks)} chunk files on disk")
    return chunks


def group_builds(
    repositories: List[RepositoryInfo],
) -> Dict[int, RepositoryInfo]:
    """
    Group repositories by build ID.
    
    Returns dict mapping build_id -> RepositoryInfo
    """
    build_map = {}
    for repo in repositories:
        build_map[repo.build_id] = repo
    
    return build_map


def write_part_0(
    output_path: Path,
    archive_type: int,
    total_parts: int,
    total_build_count: int,
    total_chunk_count: int,
    product_metadata: ProductMetadata,
    build_map: Dict[int, RepositoryInfo],
    repositories: List[RepositoryInfo],
    part_assignment: Optional[PartAssignment],
    meta_dir: Path,
):
    """Write Part 0 of the archive (main part with all metadata)."""
    print(f"  Writing Part 1: {output_path}")
    
    with open(output_path, 'wb') as f:
        # Step 1: Write placeholder header
        header = RGOGHeader(
            archive_type=archive_type,
            part_number=0,
            total_parts=total_parts,
            total_build_count=total_build_count,
            total_chunk_count=total_chunk_count,
            local_chunk_count=len(part_assignment.chunks) if part_assignment else 0,
        )
        f.write(header.to_bytes())
        
        # Step 2: Write Product Metadata
        product_offset = f.tell()
        product_data = product_metadata.to_bytes()
        f.write(product_data)
        f.write(get_padding(f.tell()))
        product_size = f.tell() - product_offset
        
        # Step 3: Write Build Metadata (placeholders)
        build_metadata_offset = f.tell()
        build_metadata_list = []
        
        for build_id in sorted(build_map.keys()):
            repo = build_map[build_id]
            
            # Map platform string to OS code
            os_code = {
                'windows': OS_WINDOWS,
                'osx': OS_MAC,
                'mac': OS_MAC,
                'linux': OS_LINUX,
            }.get(repo.platform.lower(), OS_NULL)
            
            # Create build metadata with depot manifests
            build_meta = BuildMetadata(
                build_id=build_id,
                os=os_code,
                repository_id=md5_to_bytes(repo.filename),
                repository_offset=0,  # Placeholder
                repository_size=0,    # Placeholder
                manifests=[],  # Will populate with depot manifests
            )
            
            # Add manifest entries for each depot
            for depot_id in repo.depot_ids:
                # Get languages for this depot and encode to bitflags
                lang_list = repo.depot_languages.get(depot_id, [])
                languages1, languages2 = languages_to_bitflags(lang_list)
                
                # Create placeholder ManifestEntry (will update with actual offsets later)
                manifest_entry = ManifestEntry(
                    depot_id=md5_to_bytes(depot_id),
                    offset=0,  # Placeholder
                    size=0,    # Placeholder
                    languages1=languages1,
                    languages2=languages2,
                )
                build_meta.manifests.append(manifest_entry)
            
            build_metadata_list.append(build_meta)
            f.write(build_meta.to_bytes())
        
        f.write(get_padding(f.tell()))
        build_metadata_size = f.tell() - build_metadata_offset
        
        # Step 4: Write Build Files (repositories and depot manifests)
        build_files_offset = f.tell()
        repo_offsets = {}
        depot_offsets = {}
        
        # Write repositories
        for repo in repositories:
            offset = f.tell() - build_files_offset
            with open(repo.path, 'rb') as rf:
                data = rf.read()
                f.write(data)
            repo_offsets[repo.filename] = (offset, len(data))
        
        # Write depot manifests for each build
        for repo in repositories:
            for depot_id in repo.depot_ids:
                # Find depot manifest file
                manifest_path = find_depot_manifest_file(meta_dir, depot_id)
                if not manifest_path:
                    print(f"  Warning: Depot manifest {depot_id} not found for build {repo.build_id}")
                    continue
                
                # Write depot manifest
                offset = f.tell() - build_files_offset
                with open(manifest_path, 'rb') as mf:
                    data = mf.read()
                    f.write(data)
                
                # Key by (build_id, depot_id) to avoid conflicts
                depot_offsets[(repo.build_id, depot_id)] = (offset, len(data))
        
        f.write(get_padding(f.tell()))
        build_files_size = f.tell() - build_files_offset
        
        # Step 5: Update Build Metadata with actual offsets
        current_pos = f.tell()
        f.seek(build_metadata_offset)
        
        for build_meta in build_metadata_list:
            # Get repository info by filename
            repo_filename = bytes_to_md5(build_meta.repository_id)
            if repo_filename in repo_offsets:
                repo_off, repo_size = repo_offsets[repo_filename]
                build_meta.repository_offset = repo_off
                build_meta.repository_size = repo_size
            
            # Update depot manifest offsets
            for manifest in build_meta.manifests:
                depot_id_str = bytes_to_md5(manifest.depot_id)
                key = (build_meta.build_id, depot_id_str)
                if key in depot_offsets:
                    depot_off, depot_size = depot_offsets[key]
                    manifest.offset = depot_off
                    manifest.size = depot_size
            
            # Write updated build metadata
            f.write(build_meta.to_bytes())
        
        f.seek(current_pos)
        
        # Step 6: Write Chunk Metadata (placeholders)
        chunk_metadata_offset = f.tell()
        chunk_metadata_list = []
        
        if part_assignment:
            for chunk in part_assignment.chunks:
                chunk_meta = ChunkMetadata(
                    compressed_md5=chunk.compressed_md5,
                    offset=0,  # Placeholder
                    size=0,    # Placeholder
                )
                chunk_metadata_list.append(chunk_meta)
                f.write(chunk_meta.to_bytes())
        
        f.write(get_padding(f.tell()))
        chunk_metadata_size = f.tell() - chunk_metadata_offset
        
        # Step 7: Write Chunk Files
        chunk_files_offset = f.tell()
        
        if part_assignment:
            for i, chunk in enumerate(part_assignment.chunks):
                offset = f.tell() - chunk_files_offset
                with open(chunk.path, 'rb') as cf:
                    data = cf.read()
                    f.write(data)
                
                # Update metadata
                chunk_metadata_list[i].offset = offset
                chunk_metadata_list[i].size = len(data)
        
        f.write(get_padding(f.tell()))
        chunk_files_size = f.tell() - chunk_files_offset
        
        # Step 8: Update Chunk Metadata with actual offsets
        current_pos = f.tell()
        f.seek(chunk_metadata_offset)
        for chunk_meta in chunk_metadata_list:
            f.write(chunk_meta.to_bytes())
        f.seek(current_pos)
        
        # Step 9: Update Header with all offsets
        header.product_metadata_offset = product_offset
        header.product_metadata_size = product_size
        header.build_metadata_offset = build_metadata_offset
        header.build_metadata_size = build_metadata_size
        header.build_files_offset = build_files_offset
        header.build_files_size = build_files_size
        header.chunk_metadata_offset = chunk_metadata_offset
        header.chunk_metadata_size = chunk_metadata_size
        header.chunk_files_offset = chunk_files_offset
        header.chunk_files_size = chunk_files_size
        
        f.seek(0)
        f.write(header.to_bytes())


def write_part_n(
    output_path: Path,
    archive_type: int,
    part_number: int,
    total_parts: int,
    total_build_count: int,
    total_chunk_count: int,
    part_assignment: PartAssignment,
):
    """Write Part N (additional parts with only chunks)."""
    print(f"  Writing Part {part_number + 1}: {output_path}")
    
    with open(output_path, 'wb') as f:
        # Step 1: Write placeholder header
        header = RGOGHeader(
            archive_type=archive_type,
            part_number=part_number,
            total_parts=total_parts,
            total_build_count=total_build_count,
            total_chunk_count=total_chunk_count,
            local_chunk_count=len(part_assignment.chunks),
        )
        f.write(header.to_bytes())
        
        # Step 2: Write Chunk Metadata (placeholders)
        chunk_metadata_offset = f.tell()
        chunk_metadata_list = []
        
        for chunk in part_assignment.chunks:
            chunk_meta = ChunkMetadata(
                compressed_md5=chunk.compressed_md5,
                offset=0,  # Placeholder
                size=0,    # Placeholder
            )
            chunk_metadata_list.append(chunk_meta)
            f.write(chunk_meta.to_bytes())
        
        f.write(get_padding(f.tell()))
        chunk_metadata_size = f.tell() - chunk_metadata_offset
        
        # Step 3: Write Chunk Files
        chunk_files_offset = f.tell()
        
        for i, chunk in enumerate(part_assignment.chunks):
            offset = f.tell() - chunk_files_offset
            with open(chunk.path, 'rb') as cf:
                data = cf.read()
                f.write(data)
            
            # Update metadata
            chunk_metadata_list[i].offset = offset
            chunk_metadata_list[i].size = len(data)
        
        f.write(get_padding(f.tell()))
        chunk_files_size = f.tell() - chunk_files_offset
        
        # Step 4: Update Chunk Metadata
        current_pos = f.tell()
        f.seek(chunk_metadata_offset)
        for chunk_meta in chunk_metadata_list:
            f.write(chunk_meta.to_bytes())
        f.seek(current_pos)
        
        # Step 5: Update Header
        header.chunk_metadata_offset = chunk_metadata_offset
        header.chunk_metadata_size = chunk_metadata_size
        header.chunk_files_offset = chunk_files_offset
        header.chunk_files_size = chunk_files_size
        
        f.seek(0)
        f.write(header.to_bytes())


def calculate_part_assignments(
    chunks: List[ChunkInfo],
    base_metadata_size: int,
    max_part_size: int = DEFAULT_PART_SIZE
) -> List[PartAssignment]:
    """
    Calculate which chunks belong in which part based on size limits.
    
    Args:
        chunks: List of all chunks (sorted)
        base_metadata_size: Size of header + product + build metadata
        max_part_size: Maximum size per part in bytes
        
    Returns:
        List of PartAssignment objects
    """
    parts = []
    current_part = 0
    current_chunks = []
    current_size = base_metadata_size if current_part == 0 else 128  # Header size
    
    for chunk in chunks:
        chunk_overhead = 32  # ChunkMetadata size
        chunk_total = chunk_overhead + chunk.file_size
        
        # Check if adding this chunk would exceed limit
        if current_size + chunk_total > max_part_size and current_chunks:
            # Finalize current part
            parts.append(PartAssignment(
                part_number=current_part,
                chunks=current_chunks,
                total_size=current_size,
            ))
            
            # Start new part
            current_part += 1
            current_chunks = []
            current_size = 128  # Just header for Part 1+
        
        # Add chunk to current part
        chunk.part_number = current_part
        current_chunks.append(chunk)
        current_size += chunk_total
    
    # Add final part
    if current_chunks:
        parts.append(PartAssignment(
            part_number=current_part,
            chunks=current_chunks,
            total_size=current_size,
        ))
    
    return parts


def execute(args):
    """Execute the pack command."""
    input_dir = args.input_dir
    output_path = args.output
    max_part_size = parse_size_string(args.max_part_size)
    archive_type = ARCHIVE_TYPE_BASE if args.type == 'base' else ARCHIVE_TYPE_PATCH
    target_build_id = getattr(args, 'build', None)
    
    print(f"RGOG Pack: {input_dir} -> {output_path}")
    print(f"Max part size: {max_part_size / (1024**3):.2f} GB")
    if target_build_id:
        print(f"Target build ID: {target_build_id}")
    
    # Validate input directory
    if not input_dir.exists():
        raise ValueError(f"Input directory does not exist: {input_dir}")
    
    # Require v2 subdirectory for GOG Galaxy v2 format
    v2_dir = input_dir / 'v2'
    if not v2_dir.exists():
        raise ValueError(f"v2 directory not found: {v2_dir}\nRGOG only supports GOG Galaxy v2 format")
    
    input_dir = v2_dir
    print(f"Using v2 directory: {input_dir}")
    
    meta_dir = input_dir / 'meta'
    chunks_dir = input_dir / 'store'
    
    if not meta_dir.exists():
        raise ValueError(f"Meta directory not found: {meta_dir}")
    if not chunks_dir.exists():
        raise ValueError(f"Store directory not found: {chunks_dir}")
    
    print("\n[1/5] Scanning files...")
    repositories = scan_repositories(meta_dir)
    
    # Filter for specific build if requested
    if target_build_id:
        repositories = [r for r in repositories if r.build_id == target_build_id]
        if not repositories:
            raise ValueError(f"Build ID {target_build_id} not found in repositories")
        print(f"  Found repository for build {target_build_id}")
        
        # Get chunks specific to this build
        print(f"  Processing depot manifests for build {target_build_id}...")
        chunks = get_chunks_for_build(meta_dir, chunks_dir, repositories[0])
    else:
        # Pack all chunks
        chunks = scan_chunks(chunks_dir)
        print(f"  Found {len(repositories)} repositories")
        print(f"  Found {len(chunks)} chunks")
    
    if not repositories:
        raise ValueError("No repository files found")
    
    # Extract product info from first repository
    first_repo = repositories[0]
    product_id = first_repo.product_id
    product_name = input_dir.name  # Use directory name as product name
    
    # Group repositories by build ID
    print("\n[2/5] Processing build metadata...")
    build_map = group_builds(repositories)
    total_builds = len(build_map)
    print(f"  Organized {total_builds} builds")
    
    # Calculate metadata sizes (manifests list is empty now)
    build_metadata_size = calculate_metadata_size(total_builds, [0] * total_builds)
    product_metadata = ProductMetadata(product_id=product_id, product_name=product_name)
    product_metadata_size = align_to_boundary(len(product_metadata.to_bytes()))
    
    base_metadata_size = 128 + product_metadata_size + build_metadata_size
    
    # Calculate part assignments
    print("\n[3/5] Calculating part assignments...")
    part_assignments = calculate_part_assignments(chunks, base_metadata_size, max_part_size)
    total_parts = len(part_assignments)
    print(f"  Archive will be split into {total_parts} part(s)")
    
    # Write Part 0
    print("\n[4/5] Writing archive...")
    write_part_0(
        output_path,
        archive_type,
        total_parts,
        total_builds,
        len(chunks),
        product_metadata,
        build_map,
        repositories,
        part_assignments[0] if part_assignments else None,
        meta_dir,
    )
    
    # Write additional parts
    for part in part_assignments[1:]:
        part_path = Path(f"{output_path}.{part.part_number}")
        write_part_n(
            part_path,
            archive_type,
            part.part_number,
            total_parts,
            total_builds,
            len(chunks),
            part,
        )
    
    print("\n[5/5] Complete!")
    print(f"\nArchive created successfully:")
    print(f"  Part 1: {output_path} ({output_path.stat().st_size / (1024**3):.2f} GB)")
    for i in range(1, total_parts):
        part_path = Path(f"{output_path}.{i}")
        if part_path.exists():
            print(f"  Part {i + 1}: {part_path} ({part_path.stat().st_size / (1024**3):.2f} GB)")
    
    return 0
