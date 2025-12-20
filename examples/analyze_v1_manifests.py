#!/usr/bin/env python3
"""
Analyze V1 Manifest Files

Compares two V1 manifest JSON files to identify:
- Total size and file counts
- Gaps in offset ranges (unused space in main.bin)
- Files that appear in both platforms (by hash)
- Platform-exclusive files
- Whether gaps align with platform-exclusive data

Usage:
    python analyze_v1_manifests.py <manifest1.json> <manifest2.json>
    python analyze_v1_manifests.py windows_manifest.json mac_manifest.json
"""

import sys
import json
from typing import List, Dict, Tuple, Set
from dataclasses import dataclass


@dataclass
class FileEntry:
    """Represents a file entry in the manifest."""
    path: str
    offset: int
    size: int
    hash: str
    url: str
    executable: bool = False
    
    @property
    def end_offset(self) -> int:
        """Calculate the end offset of this file."""
        return self.offset + self.size
    
    def __repr__(self):
        return f"FileEntry(path={self.path!r}, offset={self.offset}, size={self.size}, hash={self.hash[:8]}...)"


@dataclass
class Gap:
    """Represents a gap in the file layout."""
    start: int
    end: int
    
    @property
    def size(self) -> int:
        return self.end - self.start
    
    def __repr__(self):
        return f"Gap(start={self.start:,}, size={self.size:,} bytes)"


def load_manifest(filepath: str) -> Tuple[str, List[FileEntry]]:
    """Load a V1 manifest JSON file and extract file entries."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    depot_name = data.get('depot', {}).get('name', 'Unknown')
    files = []
    
    for file_data in data.get('depot', {}).get('files', []):
        # Skip directory entries (size 0, no offset/url)
        if file_data.get('size', 0) == 0 or 'offset' not in file_data:
            continue
        
        files.append(FileEntry(
            path=file_data['path'],
            offset=file_data['offset'],
            size=file_data['size'],
            hash=file_data.get('hash', ''),
            url=file_data.get('url', ''),
            executable=file_data.get('executable', False)
        ))
    
    return depot_name, files


def find_gaps(files: List[FileEntry]) -> List[Gap]:
    """Find gaps in the file layout by analyzing offset ranges."""
    if not files:
        return []
    
    # Sort files by offset
    sorted_files = sorted(files, key=lambda f: f.offset)
    
    gaps = []
    expected_next = 0
    
    for file_entry in sorted_files:
        if file_entry.offset > expected_next:
            # Found a gap
            gaps.append(Gap(start=expected_next, end=file_entry.offset))
        
        # Update expected next offset
        expected_next = max(expected_next, file_entry.end_offset)
    
    return gaps


def analyze_manifest(name: str, files: List[FileEntry]) -> Dict:
    """Analyze a single manifest and return statistics."""
    total_size = sum(f.size for f in files)
    gaps = find_gaps(files)
    gap_size = sum(g.size for g in gaps)
    
    # Find the maximum offset to determine main.bin size
    if files:
        sorted_files = sorted(files, key=lambda f: f.end_offset, reverse=True)
        main_bin_size = sorted_files[0].end_offset
    else:
        main_bin_size = 0
    
    return {
        'name': name,
        'file_count': len(files),
        'total_file_size': total_size,
        'main_bin_size': main_bin_size,
        'gaps': gaps,
        'gap_count': len(gaps),
        'gap_size': gap_size,
        'utilization': (total_size / main_bin_size * 100) if main_bin_size > 0 else 0
    }


def compare_files(files1: List[FileEntry], files2: List[FileEntry]) -> Dict:
    """Compare two file lists to find shared and exclusive files."""
    # Create hash-based lookups
    hash_to_file1 = {f.hash: f for f in files1 if f.hash}
    hash_to_file2 = {f.hash: f for f in files2 if f.hash}
    
    hashes1 = set(hash_to_file1.keys())
    hashes2 = set(hash_to_file2.keys())
    
    shared_hashes = hashes1 & hashes2
    exclusive1 = hashes1 - hashes2
    exclusive2 = hashes2 - hashes1
    
    # Analyze shared files for offset differences
    shared_files = []
    for hash_val in shared_hashes:
        f1 = hash_to_file1[hash_val]
        f2 = hash_to_file2[hash_val]
        shared_files.append({
            'hash': hash_val,
            'path1': f1.path,
            'path2': f2.path,
            'size': f1.size,
            'offset1': f1.offset,
            'offset2': f2.offset,
            'offset_diff': abs(f1.offset - f2.offset)
        })
    
    return {
        'shared_count': len(shared_hashes),
        'shared_files': shared_files,
        'exclusive1_count': len(exclusive1),
        'exclusive1_hashes': exclusive1,
        'exclusive1_files': [hash_to_file1[h] for h in exclusive1],
        'exclusive2_count': len(exclusive2),
        'exclusive2_hashes': exclusive2,
        'exclusive2_files': [hash_to_file2[h] for h in exclusive2]
    }


def check_gap_alignment(gaps1: List[Gap], exclusive2_files: List[FileEntry], 
                        gaps2: List[Gap], exclusive1_files: List[FileEntry]) -> Dict:
    """Check if gaps in one manifest align with exclusive files in the other."""
    alignments1 = []  # gaps1 that might contain exclusive2 files
    alignments2 = []  # gaps2 that might contain exclusive1 files
    
    # Check if exclusive files from manifest2 could fit in gaps from manifest1
    for gap in gaps1:
        files_in_gap = [f for f in exclusive2_files 
                       if gap.start <= f.offset < gap.end or 
                          gap.start < f.end_offset <= gap.end or
                          (f.offset <= gap.start and f.end_offset >= gap.end)]
        if files_in_gap:
            alignments1.append({
                'gap': gap,
                'files': files_in_gap,
                'total_size': sum(f.size for f in files_in_gap)
            })
    
    # Check if exclusive files from manifest1 could fit in gaps from manifest2
    for gap in gaps2:
        files_in_gap = [f for f in exclusive1_files 
                       if gap.start <= f.offset < gap.end or 
                          gap.start < f.end_offset <= gap.end or
                          (f.offset <= gap.start and f.end_offset >= gap.end)]
        if files_in_gap:
            alignments2.append({
                'gap': gap,
                'files': files_in_gap,
                'total_size': sum(f.size for f in files_in_gap)
            })
    
    return {
        'alignments1': alignments1,
        'alignments2': alignments2
    }


def format_size(size: float) -> str:
    """Format size in human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} PB"


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    
    manifest1_path = sys.argv[1]
    manifest2_path = sys.argv[2]
    
    print("Loading manifests...")
    name1, files1 = load_manifest(manifest1_path)
    name2, files2 = load_manifest(manifest2_path)
    
    print(f"\n{'='*80}")
    print(f"MANIFEST COMPARISON")
    print(f"{'='*80}")
    print(f"Manifest 1: {name1}")
    print(f"Manifest 2: {name2}")
    print(f"{'='*80}\n")
    
    # Analyze individual manifests
    print("Analyzing individual manifests...\n")
    stats1 = analyze_manifest(name1, files1)
    stats2 = analyze_manifest(name2, files2)
    
    print(f"=== {stats1['name']} ===")
    print(f"  Files: {stats1['file_count']:,}")
    print(f"  Total file size: {format_size(stats1['total_file_size'])} ({stats1['total_file_size']:,} bytes)")
    print(f"  main.bin size: {format_size(stats1['main_bin_size'])} ({stats1['main_bin_size']:,} bytes)")
    print(f"  Gaps: {stats1['gap_count']:,} gaps totaling {format_size(stats1['gap_size'])} ({stats1['gap_size']:,} bytes)")
    print(f"  Utilization: {stats1['utilization']:.2f}%")
    
    print(f"\n=== {stats2['name']} ===")
    print(f"  Files: {stats2['file_count']:,}")
    print(f"  Total file size: {format_size(stats2['total_file_size'])} ({stats2['total_file_size']:,} bytes)")
    print(f"  main.bin size: {format_size(stats2['main_bin_size'])} ({stats2['main_bin_size']:,} bytes)")
    print(f"  Gaps: {stats2['gap_count']:,} gaps totaling {format_size(stats2['gap_size'])} ({stats2['gap_size']:,} bytes)")
    print(f"  Utilization: {stats2['utilization']:.2f}%")
    
    # Compare files
    print(f"\n{'='*80}")
    print("COMPARING FILES...")
    print(f"{'='*80}\n")
    comparison = compare_files(files1, files2)
    
    print(f"Shared files (same hash): {comparison['shared_count']:,}")
    print(f"Exclusive to {stats1['name']}: {comparison['exclusive1_count']:,}")
    print(f"Exclusive to {stats2['name']}: {comparison['exclusive2_count']:,}")
    
    # Show top 10 largest gaps
    print(f"\n{'='*80}")
    print(f"TOP 10 LARGEST GAPS")
    print(f"{'='*80}\n")
    
    print(f"=== {stats1['name']} ===")
    if stats1['gaps']:
        sorted_gaps1 = sorted(stats1['gaps'], key=lambda g: g.size, reverse=True)[:10]
        for i, gap in enumerate(sorted_gaps1, 1):
            print(f"  {i}. Offset {gap.start:,} - {gap.end:,}: {format_size(gap.size)} ({gap.size:,} bytes)")
    else:
        print("  No gaps found")
    
    print(f"\n=== {stats2['name']} ===")
    if stats2['gaps']:
        sorted_gaps2 = sorted(stats2['gaps'], key=lambda g: g.size, reverse=True)[:10]
        for i, gap in enumerate(sorted_gaps2, 1):
            print(f"  {i}. Offset {gap.start:,} - {gap.end:,}: {format_size(gap.size)} ({gap.size:,} bytes)")
    else:
        print("  No gaps found")
    
    # Check gap alignments
    if comparison['exclusive1_files'] or comparison['exclusive2_files']:
        print(f"\n{'='*80}")
        print(f"GAP ALIGNMENT ANALYSIS")
        print(f"{'='*80}\n")
        
        alignment = check_gap_alignment(
            stats1['gaps'], comparison['exclusive2_files'],
            stats2['gaps'], comparison['exclusive1_files']
        )
        
        print(f"Checking if exclusive files fit in opposite manifest's gaps...\n")
        
        if alignment['alignments1']:
            print(f"=== Files from {stats2['name']} that align with gaps in {stats1['name']} ===")
            for i, align in enumerate(alignment['alignments1'], 1):
                print(f"  Gap {i}: {align['gap']}")
                print(f"    Contains {len(align['files'])} exclusive files ({format_size(align['total_size'])})")
                for f in align['files'][:5]:  # Show first 5
                    print(f"      - {f.path} ({format_size(f.size)})")
                if len(align['files']) > 5:
                    print(f"      ... and {len(align['files']) - 5} more")
            print()
        
        if alignment['alignments2']:
            print(f"=== Files from {stats1['name']} that align with gaps in {stats2['name']} ===")
            for i, align in enumerate(alignment['alignments2'], 1):
                print(f"  Gap {i}: {align['gap']}")
                print(f"    Contains {len(align['files'])} exclusive files ({format_size(align['total_size'])})")
                for f in align['files'][:5]:  # Show first 5
                    print(f"      - {f.path} ({format_size(f.size)})")
                if len(align['files']) > 5:
                    print(f"      ... and {len(align['files']) - 5} more")
    
    # Show sample of exclusive files
    if comparison['exclusive1_files']:
        print(f"\n{'='*80}")
        print(f"SAMPLE EXCLUSIVE FILES IN {stats1['name']}")
        print(f"{'='*80}\n")
        exclusive1_sorted = sorted(comparison['exclusive1_files'], key=lambda f: f.size, reverse=True)[:10]
        for i, f in enumerate(exclusive1_sorted, 1):
            print(f"  {i}. {f.path}")
            print(f"     Size: {format_size(f.size)}, Offset: {f.offset:,}, Hash: {f.hash[:16]}...")
    
    if comparison['exclusive2_files']:
        print(f"\n{'='*80}")
        print(f"SAMPLE EXCLUSIVE FILES IN {stats2['name']}")
        print(f"{'='*80}\n")
        exclusive2_sorted = sorted(comparison['exclusive2_files'], key=lambda f: f.size, reverse=True)[:10]
        for i, f in enumerate(exclusive2_sorted, 1):
            print(f"  {i}. {f.path}")
            print(f"     Size: {format_size(f.size)}, Offset: {f.offset:,}, Hash: {f.hash[:16]}...")
    
    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}\n")
    
    same_size = stats1['main_bin_size'] == stats2['main_bin_size']
    print(f"main.bin sizes are {'IDENTICAL' if same_size else 'DIFFERENT'}")
    if not same_size:
        diff = abs(stats1['main_bin_size'] - stats2['main_bin_size'])
        print(f"  Difference: {format_size(diff)} ({diff:,} bytes)")
    
    print(f"\nFile overlap: {comparison['shared_count']:,} / {len(files1):,} files share the same hash")
    print(f"Overlap percentage: {(comparison['shared_count'] / max(len(files1), len(files2)) * 100):.2f}%")
    
    if comparison['shared_count'] > 0 and comparison['shared_files']:
        # Check if ALL shared files have different offsets
        different_offsets = sum(1 for f in comparison['shared_files'] if f['offset1'] != f['offset2'])
        print(f"\nShared files with different offsets: {different_offsets:,} / {comparison['shared_count']:,}")
        if different_offsets == comparison['shared_count']:
            print("  → ALL shared files are at different offsets!")
            print("  → Platforms use DIFFERENT main.bin layouts")
        elif different_offsets == 0:
            print("  → ALL shared files are at IDENTICAL offsets!")
            print("  → Platforms might share the same main.bin")
        else:
            print("  → MIXED: Some files share offsets, others don't")


if __name__ == "__main__":
    main()
