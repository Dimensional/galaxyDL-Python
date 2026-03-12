#!/usr/bin/env python3
"""
Audit manifest files to verify chunk MD5 coverage.
Compares what's in manifests vs what's in RGOG archives.
"""

import json
import sys
import zlib
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Set, Optional

# Import from rgog module
sys.path.insert(0, str(Path(__file__).parent))
from rgog.common import RGOGHeader, bytes_to_md5, resolve_first_part, get_all_parts


@dataclass
class ManifestChunk:
    """Chunk info from manifest."""
    compressed_md5: str
    decompressed_md5: Optional[str]
    compressed_size: int
    decompressed_size: int
    source: str  # Which manifest file


@dataclass
class ArchiveChunk:
    """Chunk info from RGOG archive."""
    compressed_md5: str
    offset: int
    size: int
    part_file: str


def collect_manifest_chunks(dependencies_dir: Path) -> Dict[str, ManifestChunk]:
    """Collect all chunks from manifest JSON files."""
    manifest_chunks = {}
    
    # Check both dependencies/debug/, dependencies/v2/meta/, and flat directory
    search_paths = [
        dependencies_dir / "debug",
        dependencies_dir / "v2" / "meta",
        dependencies_dir  # Also check flat directory
    ]
    
    manifest_files = []
    for search_path in search_paths:
        if search_path.exists():
            manifest_files.extend(search_path.glob("*_manifest.json"))
    
    print(f"\nScanning {len(manifest_files)} manifest files...")
    
    total_chunks = 0
    chunks_with_decompressed = 0
    chunks_without_decompressed = 0
    
    for manifest_file in manifest_files:
        try:
            with open(manifest_file, 'r', encoding='utf-8') as f:
                manifest_data = json.load(f)
            
            if 'depot' not in manifest_data:
                continue
            
            depot = manifest_data['depot']
            
            # Process depot.items[].chunks[]
            if 'items' in depot:
                for item in depot['items']:
                    if 'chunks' not in item:
                        continue
                        
                    for chunk in item['chunks']:
                        compressed_md5 = chunk.get('compressedMd5', '')
                        decompressed_md5 = chunk.get('md5')  # May be None/missing
                        compressed_size = chunk.get('compressedSize', 0)
                        decompressed_size = chunk.get('size', 0)
                    
                        total_chunks += 1
                        
                        if decompressed_md5:
                            chunks_with_decompressed += 1
                        else:
                            chunks_without_decompressed += 1
                        
                        # Store by compressed MD5
                        if compressed_md5 not in manifest_chunks:
                            manifest_chunks[compressed_md5] = ManifestChunk(
                                compressed_md5=compressed_md5,
                                decompressed_md5=decompressed_md5,
                                compressed_size=compressed_size,
                                decompressed_size=decompressed_size,
                                source=manifest_file.name
                            )
            
            # Process depot.smallFilesContainer.chunks[]
            if 'smallFilesContainer' in depot and 'chunks' in depot['smallFilesContainer']:
                for chunk in depot['smallFilesContainer']['chunks']:
                    compressed_md5 = chunk.get('compressedMd5', '')
                    decompressed_md5 = chunk.get('md5')  # May be None/missing
                    compressed_size = chunk.get('compressedSize', 0)
                    decompressed_size = chunk.get('size', 0)
                
                    total_chunks += 1
                    
                    if decompressed_md5:
                        chunks_with_decompressed += 1
                    else:
                        chunks_without_decompressed += 1
                    
                    # Store by compressed MD5
                    if compressed_md5 not in manifest_chunks:
                        manifest_chunks[compressed_md5] = ManifestChunk(
                            compressed_md5=compressed_md5,
                            decompressed_md5=decompressed_md5,
                            compressed_size=compressed_size,
                            decompressed_size=decompressed_size,
                            source=manifest_file.name
                        )
        
        except Exception as e:
            print(f"  ⚠ Error reading {manifest_file.name}: {e}")
    
    print(f"\nManifest Statistics:")
    print(f"  Total chunk entries: {total_chunks}")
    print(f"  Unique chunks (by compressed MD5): {len(manifest_chunks)}")
    print(f"  Chunks with decompressed MD5: {chunks_with_decompressed}")
    print(f"  Chunks WITHOUT decompressed MD5: {chunks_without_decompressed}")
    
    return manifest_chunks


def collect_archive_chunks(rgog_path: Path) -> Dict[str, ArchiveChunk]:
    """Collect all chunks from RGOG archive."""
    result = resolve_first_part(rgog_path)
    if not result:
        print(f"✗ Could not find RGOG archive at {rgog_path}")
        return {}
    
    first_part, header = result
    total_parts = header.total_parts
    
    all_parts = get_all_parts(first_part, total_parts)
    print(f"\nScanning {len(all_parts)} RGOG archive parts...")
    
    archive_chunks = {}
    total_chunks = 0
    
    for part_path in all_parts:
        with open(part_path, 'rb') as f:
            # Read header
            header_bytes = f.read(128)
            header = RGOGHeader.from_bytes(header_bytes)
            
            # Skip build records (go to chunk metadata start)
            f.seek(header.chunk_metadata_offset)
            
            # Read chunk metadata
            num_chunks = header.chunk_metadata_size // 32
            
            for i in range(num_chunks):
                metadata = f.read(32)
                chunk_md5 = bytes_to_md5(metadata[0:16])
                chunk_offset = int.from_bytes(metadata[16:24], 'little')
                chunk_size = int.from_bytes(metadata[24:32], 'little')
                
                total_chunks += 1
                
                if chunk_md5 not in archive_chunks:
                    archive_chunks[chunk_md5] = ArchiveChunk(
                        compressed_md5=chunk_md5,
                        offset=chunk_offset,
                        size=chunk_size,
                        part_file=part_path.name
                    )
    
    print(f"\nArchive Statistics:")
    print(f"  Total chunks: {total_chunks}")
    print(f"  Unique chunks (by compressed MD5): {len(archive_chunks)}")
    
    return archive_chunks


def compare_chunks(manifest_chunks: Dict[str, ManifestChunk], 
                   archive_chunks: Dict[str, ArchiveChunk]):
    """Compare manifest chunks with archive chunks."""
    
    print("\n" + "="*80)
    print("COMPARISON ANALYSIS")
    print("="*80)
    
    manifest_md5s = set(manifest_chunks.keys())
    archive_md5s = set(archive_chunks.keys())
    
    # Chunks in both
    in_both = manifest_md5s & archive_md5s
    
    # Chunks only in manifests
    only_manifests = manifest_md5s - archive_md5s
    
    # Chunks only in archive
    only_archive = archive_md5s - manifest_md5s
    
    print(f"\nOverlap:")
    print(f"  Chunks in BOTH manifest and archive: {len(in_both)}")
    print(f"  Chunks ONLY in manifests: {len(only_manifests)}")
    print(f"  Chunks ONLY in archive: {len(only_archive)}")
    
    if only_manifests:
        print(f"\n⚠ {len(only_manifests)} chunks in manifests but NOT in archive:")
        for md5 in list(only_manifests)[:10]:
            chunk = manifest_chunks[md5]
            print(f"    {md5} (from {chunk.source})")
        if len(only_manifests) > 10:
            print(f"    ... and {len(only_manifests) - 10} more")
    
    if only_archive:
        print(f"\n⚠ {len(only_archive)} chunks in archive but NOT in manifests:")
        for md5 in list(only_archive)[:10]:
            chunk = archive_chunks[md5]
            print(f"    {md5} (in {chunk.part_file} at offset {chunk.offset})")
        if len(only_archive) > 10:
            print(f"    ... and {len(only_archive) - 10} more")
    
    # Check decompressed MD5 coverage for chunks in both
    if in_both:
        chunks_with_decomp = sum(1 for md5 in in_both if manifest_chunks[md5].decompressed_md5)
        chunks_without_decomp = len(in_both) - chunks_with_decomp
        
        print(f"\nDecompressed MD5 coverage for chunks in both:")
        print(f"  With decompressed MD5: {chunks_with_decomp} ({chunks_with_decomp*100//len(in_both)}%)")
        print(f"  WITHOUT decompressed MD5: {chunks_without_decomp} ({chunks_without_decomp*100//len(in_both)}%)")
        
        if chunks_without_decomp > 0:
            print(f"\nSample chunks WITHOUT decompressed MD5:")
            count = 0
            for md5 in in_both:
                chunk = manifest_chunks[md5]
                if not chunk.decompressed_md5:
                    arch_chunk = archive_chunks[md5]
                    print(f"    {md5}")
                    print(f"      Compressed size: {chunk.compressed_size} bytes")
                    print(f"      Decompressed size: {chunk.decompressed_size} bytes")
                    print(f"      From manifest: {chunk.source}")
                    print(f"      In archive: {arch_chunk.part_file} at offset {arch_chunk.offset}")
                    count += 1
                    if count >= 5:
                        break


def main():
    if len(sys.argv) < 3:
        print("Usage: python audit_manifests.py <manifest_dir> <path_to_rgog_file>")
        print("\nExample:")
        print("  python audit_manifests.py dependencies ../Ignore/DREDGE_1.rgog")
        print("  python audit_manifests.py extracted_manifests ../Ignore/DREDGE_1.rgog")
        sys.exit(1)
    
    manifest_dir = Path(sys.argv[1])
    rgog_path = Path(sys.argv[2])
    
    if not manifest_dir.exists():
        print(f"✗ Manifest directory not found: {manifest_dir}")
        sys.exit(1)
    
    print("="*80)
    print("RGOG MANIFEST AUDIT")
    print("="*80)
    print(f"\nManifest Directory: {manifest_dir}")
    print(f"RGOG Archive: {rgog_path}")
    
    # Collect data
    manifest_chunks = collect_manifest_chunks(manifest_dir)
    archive_chunks = collect_archive_chunks(rgog_path)
    
    # Compare
    compare_chunks(manifest_chunks, archive_chunks)
    
    print("\n" + "="*80)


if __name__ == "__main__":
    main()
