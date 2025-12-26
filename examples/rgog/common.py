"""
Common data structures and utilities for RGOG format operations.

This module contains all binary structure definitions, helper functions,
and shared utilities used across RGOG pack/unpack operations.
"""

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple
import zlib
import json


# Constants
RGOG_MAGIC = b"RGOG"
RGOG_VERSION = 0x0002
ARCHIVE_TYPE_BASE = 0x01
ARCHIVE_TYPE_PATCH = 0x02
SECTION_ALIGNMENT = 64
DEFAULT_PART_SIZE = 2 * 1024 * 1024 * 1024  # 2 GiB

# OS Codes
OS_NULL = 0
OS_WINDOWS = 1
OS_MAC = 2
OS_LINUX = 3

OS_NAMES = {
    OS_NULL: "null",
    OS_WINDOWS: "Windows",
    OS_MAC: "Mac",
    OS_LINUX: "Linux",
}


@dataclass
class RGOGHeader:
    """
    RGOG Archive Header (128 bytes).
    
    Contains archive metadata including version, part information,
    and offsets to all major sections within the archive.
    """
    magic: bytes = RGOG_MAGIC  # 4 bytes: "RGOG"
    version: int = RGOG_VERSION  # 2 bytes: 0x0002
    archive_type: int = ARCHIVE_TYPE_BASE  # 1 byte: 0x01=Base, 0x02=Patch
    reserved1: int = 0  # 1 byte
    part_number: int = 0  # 4 bytes: Current part (0 for main)
    total_parts: int = 1  # 4 bytes: Total parts in archive
    total_build_count: int = 0  # 2 bytes: Total builds across all parts
    total_chunk_count: int = 0  # 4 bytes: Total chunks across all parts
    local_chunk_count: int = 0  # 4 bytes: Chunks in this part only
    
    # Section offsets and sizes (all uint64)
    product_metadata_offset: int = 0
    product_metadata_size: int = 0
    build_metadata_offset: int = 0
    build_metadata_size: int = 0
    build_files_offset: int = 0
    build_files_size: int = 0
    chunk_metadata_offset: int = 0
    chunk_metadata_size: int = 0
    chunk_files_offset: int = 0
    chunk_files_size: int = 0
    
    def to_bytes(self) -> bytes:
        """Serialize header to 128-byte binary format."""
        data = struct.pack(
            "<4sHBBIIHIIQQQQQQQQQQ",
            self.magic,
            self.version,
            self.archive_type,
            self.reserved1,
            self.part_number,
            self.total_parts,
            self.total_build_count,
            self.total_chunk_count,
            self.local_chunk_count,
            self.product_metadata_offset,
            self.product_metadata_size,
            self.build_metadata_offset,
            self.build_metadata_size,
            self.build_files_offset,
            self.build_files_size,
            self.chunk_metadata_offset,
            self.chunk_metadata_size,
            self.chunk_files_offset,
            self.chunk_files_size,
        )
        # Pad to 128 bytes
        padding = b'\x00' * (128 - len(data))
        return data + padding
    
    @classmethod
    def from_bytes(cls, data: bytes) -> "RGOGHeader":
        """Deserialize header from 128-byte binary format."""
        if len(data) < 128:
            raise ValueError(f"Header data too short: {len(data)} bytes")
        
        unpacked = struct.unpack("<4sHBBIIHIIQQQQQQQQQQ", data[:106])
        
        return cls(
            magic=unpacked[0],
            version=unpacked[1],
            archive_type=unpacked[2],
            reserved1=unpacked[3],
            part_number=unpacked[4],
            total_parts=unpacked[5],
            total_build_count=unpacked[6],
            total_chunk_count=unpacked[7],
            local_chunk_count=unpacked[8],
            product_metadata_offset=unpacked[9],
            product_metadata_size=unpacked[10],
            build_metadata_offset=unpacked[11],
            build_metadata_size=unpacked[12],
            build_files_offset=unpacked[13],
            build_files_size=unpacked[14],
            chunk_metadata_offset=unpacked[15],
            chunk_metadata_size=unpacked[16],
            chunk_files_offset=unpacked[17],
            chunk_files_size=unpacked[18],
        )


@dataclass
class ProductMetadata:
    """
    Product-level metadata (variable size, 8-byte aligned).
    
    Contains GOG product ID and product name.
    """
    product_id: int  # uint64
    product_name: str  # UTF-8 string
    
    def to_bytes(self) -> bytes:
        """Serialize to binary format with 8-byte alignment."""
        name_bytes = self.product_name.encode('utf-8')
        name_size = len(name_bytes)
        
        # Calculate padding to 8-byte boundary
        total_size = 8 + 4 + name_size
        padding_needed = (8 - (total_size % 8)) % 8
        
        data = struct.pack("<QI", self.product_id, name_size)
        data += name_bytes
        data += b'\x00' * padding_needed
        
        return data
    
    @classmethod
    def from_bytes(cls, data: bytes) -> "ProductMetadata":
        """Deserialize from binary format."""
        product_id, name_size = struct.unpack("<QI", data[:12])
        product_name = data[12:12+name_size].decode('utf-8')
        return cls(product_id=product_id, product_name=product_name)


@dataclass
class ManifestEntry:
    """
    Manifest entry within a build (48 bytes).
    
    Describes a single depot manifest with language flags.
    """
    depot_id: bytes  # 16-byte binary MD5
    offset: int  # uint64 (relative to BuildFilesOffset)
    size: int  # uint64
    languages1: int  # uint64 (bits 0-63)
    languages2: int  # uint64 (bits 64-127)
    
    def to_bytes(self) -> bytes:
        """Serialize to 48-byte binary format."""
        return struct.pack(
            "<16sQQQQ",
            self.depot_id,
            self.offset,
            self.size,
            self.languages1,
            self.languages2,
        )
    
    @classmethod
    def from_bytes(cls, data: bytes) -> "ManifestEntry":
        """Deserialize from 48-byte binary format."""
        unpacked = struct.unpack("<16sQQQQ", data[:48])
        return cls(
            depot_id=unpacked[0],
            offset=unpacked[1],
            size=unpacked[2],
            languages1=unpacked[3],
            languages2=unpacked[4],
        )


@dataclass
class BuildMetadata:
    """
    Build metadata entry (48 bytes base + 48 bytes per manifest).
    
    Describes a single build including repository and associated manifests.
    """
    build_id: int  # uint64
    os: int  # uint8 (0=null, 1=Windows, 2=Mac, 3=Linux)
    repository_id: bytes  # 16-byte binary MD5
    repository_offset: int  # uint64 (relative to BuildFilesOffset)
    repository_size: int  # uint64
    manifests: List[ManifestEntry] = field(default_factory=list)
    
    def to_bytes(self) -> bytes:
        """Serialize to binary format (48 + 48*n bytes)."""
        manifest_count = len(self.manifests)
        
        # Build header (48 bytes)
        data = struct.pack(
            "<QB3x16sQQH2x",
            self.build_id,
            self.os,
            self.repository_id,
            self.repository_offset,
            self.repository_size,
            manifest_count,
        )
        
        # Manifest entries
        for manifest in self.manifests:
            data += manifest.to_bytes()
        
        return data
    
    @classmethod
    def from_bytes(cls, data: bytes) -> "BuildMetadata":
        """Deserialize from binary format."""
        # Parse build header
        unpacked = struct.unpack("<QB3x16sQQH2x", data[:48])
        
        build_id = unpacked[0]
        os = unpacked[1]
        repository_id = unpacked[2]
        repository_offset = unpacked[3]
        repository_size = unpacked[4]
        manifest_count = unpacked[5]
        
        # Parse manifests
        manifests = []
        offset = 48
        for _ in range(manifest_count):
            manifest = ManifestEntry.from_bytes(data[offset:offset+48])
            manifests.append(manifest)
            offset += 48
        
        return cls(
            build_id=build_id,
            os=os,
            repository_id=repository_id,
            repository_offset=repository_offset,
            repository_size=repository_size,
            manifests=manifests,
        )
    
    def size(self) -> int:
        """Calculate total size in bytes."""
        return 48 + 48 * len(self.manifests)


@dataclass
class ChunkMetadata:
    """
    Chunk metadata entry (32 bytes).
    
    Describes a single chunk file with MD5 checksum and location.
    """
    compressed_md5: bytes  # 16-byte binary MD5
    offset: int  # uint64 (relative to ChunkFilesOffset in this part)
    size: int  # uint64
    
    def to_bytes(self) -> bytes:
        """Serialize to 32-byte binary format."""
        return struct.pack("<16sQQ", self.compressed_md5, self.offset, self.size)
    
    @classmethod
    def from_bytes(cls, data: bytes) -> "ChunkMetadata":
        """Deserialize from 32-byte binary format."""
        unpacked = struct.unpack("<16sQQ", data[:32])
        return cls(
            compressed_md5=unpacked[0],
            offset=unpacked[1],
            size=unpacked[2],
        )


# Helper Functions

def md5_to_bytes(md5_hex: str) -> bytes:
    """Convert MD5 hex string to 16-byte binary."""
    return bytes.fromhex(md5_hex)


def bytes_to_md5(md5_bytes: bytes) -> str:
    """Convert 16-byte binary MD5 to hex string."""
    return md5_bytes.hex()


def align_to_boundary(offset: int, boundary: int = SECTION_ALIGNMENT) -> int:
    """Calculate next aligned offset."""
    remainder = offset % boundary
    if remainder == 0:
        return offset
    return offset + (boundary - remainder)


def get_padding(offset: int, boundary: int = SECTION_ALIGNMENT) -> bytes:
    """Get padding bytes to reach next alignment boundary."""
    aligned = align_to_boundary(offset, boundary)
    padding_size = aligned - offset
    return b'\x00' * padding_size


def identify_and_parse_meta_file(data: bytes) -> Optional[dict]:
    """
    Identify and parse a decompressed meta file.
    
    Returns dict with repository data if it's a repository file, None if it's a depot manifest.
    Repository files contain: buildId, depots, platform, baseProductId
    Depot manifest files contain: depot.manifest (different structure)
    
    Returns dict with keys: productId, buildId, platform, depotIds
    """
    try:
        json_data = json.loads(data)
        
        # Repository files have buildId and depots array at root level
        if 'buildId' in json_data and 'depots' in json_data:
            return {
                'productId': json_data.get('baseProductId'),
                'buildId': json_data.get('buildId'),
                'platform': json_data.get('platform', ''),
                'depotIds': [depot.get('manifest') for depot in json_data.get('depots', [])],
            }
        else:
            # It's a depot manifest, return None (pack doesn't need these)
            return None
    except (json.JSONDecodeError, KeyError):
        return None


def parse_repository_file(data: bytes) -> dict:
    """
    Parse a decompressed repository JSON file.
    DEPRECATED: Use identify_and_parse_meta_file() instead.
    
    Returns dict with keys: productId, buildId, os, depotIds
    """
    try:
        repo_data = json.loads(data)
        return {
            'productId': repo_data.get('baseProductId'),
            'buildId': repo_data.get('buildId'),
            'platform': repo_data.get('platform', ''),
            'depotIds': [depot.get('manifest') for depot in repo_data.get('depots', [])],
        }
    except (json.JSONDecodeError, KeyError) as e:
        raise ValueError(f"Invalid repository JSON: {e}")


def parse_manifest_file(data: bytes) -> dict:
    """
    Parse a decompressed depot manifest JSON file.
    
    Returns dict with keys: depotId, languages, chunks
    """
    try:
        manifest_data = json.loads(data)
        depot = manifest_data.get('depot', {})
        
        # Extract chunk list
        chunks = []
        for item in depot.get('items', []):
            if 'chunks' in item:
                for chunk in item['chunks']:
                    if 'compressedMd5' in chunk:
                        chunks.append(chunk['compressedMd5'])
        
        return {
            'depotId': depot.get('manifest'),
            'languages': depot.get('languages', []),
            'chunks': chunks,
        }
    except (json.JSONDecodeError, KeyError) as e:
        raise ValueError(f"Invalid manifest JSON: {e}")


def find_depot_manifest_file(meta_dir: Path, depot_id: str) -> Optional[Path]:
    """
    Find the meta file for a specific depot manifest ID.
    
    Args:
        meta_dir: Path to meta directory
        depot_id: Depot manifest ID (MD5 hex string)
    
    Returns:
        Path to the manifest file, or None if not found
    """
    # Depot manifest files are stored as: meta/XX/YY/{depot_id}
    # where XX and YY are first 4 characters of the ID
    if len(depot_id) >= 4:
        subdir1 = depot_id[:2]
        subdir2 = depot_id[2:4]
        expected_path = meta_dir / subdir1 / subdir2 / depot_id
        if expected_path.exists():
            return expected_path
    
    # Fallback: search entire meta directory
    for meta_file in meta_dir.rglob('*'):
        if meta_file.is_file() and meta_file.name == depot_id:
            return meta_file
    
    return None


def languages_to_bitflags(languages: List[str]) -> Tuple[int, int]:
    """
    Convert language list to 128-bit flags (two uint64s).
    
    Returns (languages1, languages2) tuple.
    """
    # GOG language codes to bit positions (0-83)
    LANGUAGE_MAP = {
        'en-US': 0, 'en-GB': 1, 'fr-FR': 2, 'de-DE': 3, 'es-ES': 4,
        'es-MX': 5, 'pl-PL': 6, 'ru-RU': 7, 'it-IT': 8, 'pt-BR': 9,
        'pt-PT': 10, 'zh-Hans': 11, 'zh-Hant': 12, 'ja-JP': 13, 'ko-KR': 14,
        'tr-TR': 15, 'cs-CZ': 16, 'hu-HU': 17, 'nl-NL': 18, 'sv-SE': 19,
        'nb-NO': 20, 'da-DK': 21, 'fi-FI': 22, 'ar': 23, 'th-TH': 24,
        'el-GR': 25, 'ro-RO': 26, 'uk-UA': 27, 'bg-BG': 28, 'hr-HR': 29,
        'vi-VN': 30, 'id-ID': 31, 'hi-IN': 32, 'he-IL': 33, 'sk-SK': 34,
        'sl-SI': 35, 'sr-Latn': 36, 'lt-LT': 37, 'lv-LV': 38, 'et-EE': 39,
        'is-IS': 40, 'ms-MY': 41, 'fil-PH': 42, 'ca-ES': 43, 'eu-ES': 44,
        'gl-ES': 45, 'cy-GB': 46, 'ga-IE': 47, 'mt-MT': 48, 'af-ZA': 49,
        'sw-KE': 50, 'zu-ZA': 51, 'xh-ZA': 52, 'am-ET': 53, 'bn-BD': 54,
        'gu-IN': 55, 'kn-IN': 56, 'ml-IN': 57, 'mr-IN': 58, 'pa-IN': 59,
        'ta-IN': 60, 'te-IN': 61, 'ne-NP': 62, 'si-LK': 63, 'my-MM': 64,
        'km-KH': 65, 'lo-LA': 66, 'ka-GE': 67, 'hy-AM': 68, 'az-Latn-AZ': 69,
        'kk-KZ': 70, 'uz-Latn-UZ': 71, 'mn-MN': 72, 'bo-CN': 73, 'ug-CN': 74,
        'ps-AF': 75, 'fa-IR': 76, 'ur-PK': 77, 'sd-Arab-PK': 78, 'ks-Arab-IN': 79,
        'dz-BT': 80, 'ti-ET': 81, 'om-ET': 82, 'so-SO': 83,
    }
    
    languages1 = 0
    languages2 = 0
    
    for lang in languages:
        bit_pos = LANGUAGE_MAP.get(lang)
        if bit_pos is not None:
            if bit_pos < 64:
                languages1 |= (1 << bit_pos)
            else:
                languages2 |= (1 << (bit_pos - 64))
    
    return (languages1, languages2)


def sort_files_alphanumeric(file_list: List[Path]) -> List[Path]:
    """
    Sort files alphanumerically by filename (deterministic).
    
    Uses lowercase for case-insensitive sorting.
    """
    return sorted(file_list, key=lambda p: p.name.lower())


def calculate_metadata_size(build_count: int, manifest_counts: List[int]) -> int:
    """
    Calculate total Build Metadata section size.
    
    Args:
        build_count: Number of builds
        manifest_counts: List of manifest counts per build
        
    Returns:
        Total size in bytes (aligned to 64 bytes)
    """
    total = sum(48 + 48 * count for count in manifest_counts)
    return align_to_boundary(total)
