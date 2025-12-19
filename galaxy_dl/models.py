"""
Data models for Galaxy depot items, chunks, and manifests
Based on heroic-gogdl objects and lgogdownloader structures
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import json


@dataclass
class DepotItemChunk:
    """
    Represents a single chunk of a depot file.
    
    Attributes:
        md5_compressed: MD5 hash of the compressed chunk
        md5_uncompressed: MD5 hash of the uncompressed chunk
        size_compressed: Size of compressed chunk in bytes
        size_uncompressed: Size of uncompressed chunk in bytes
        offset_compressed: Offset within the compressed file
        offset_uncompressed: Offset within the uncompressed file
    """
    md5_compressed: str
    md5_uncompressed: str
    size_compressed: int
    size_uncompressed: int
    offset_compressed: int = 0
    offset_uncompressed: int = 0

    @classmethod
    def from_json(cls, chunk_json: Dict[str, Any], offset_compressed: int = 0, 
                  offset_uncompressed: int = 0) -> "DepotItemChunk":
        """Create a DepotItemChunk from JSON data."""
        return cls(
            md5_compressed=chunk_json.get("compressedMd5", ""),
            md5_uncompressed=chunk_json.get("md5", ""),
            size_compressed=chunk_json.get("compressedSize", 0),
            size_uncompressed=chunk_json.get("size", 0),
            offset_compressed=offset_compressed,
            offset_uncompressed=offset_uncompressed
        )


@dataclass
class DepotItem:
    """
    Represents a file or container in a Galaxy depot.
    
    Attributes:
        path: Relative path of the file
        chunks: List of chunks that make up this file
        total_size_compressed: Total compressed size
        total_size_uncompressed: Total uncompressed size
        md5: MD5 hash of the complete file (optional)
        sha256: SHA256 hash of the complete file (optional)
        product_id: Product ID this item belongs to
        is_dependency: Whether this is a dependency file
        is_small_files_container: Whether this is a small files container
        is_in_sfc: Whether this file is inside a small files container
        sfc_offset: Offset within the small files container
        sfc_size: Size within the small files container
        flags: Additional flags for the item
        is_v1_blob: Whether this is a V1 main.bin blob reference
        v1_offset: Offset within V1 main.bin (for extracting individual files)
        v1_size: Size within V1 main.bin (for extracting individual files)
        v1_blob_md5: MD5 hash of the V1 main.bin blob itself (not extracted file)
        v1_blob_path: Path to main.bin (typically 'main.bin')
    """
    path: str
    chunks: List[DepotItemChunk] = field(default_factory=list)
    total_size_compressed: int = 0
    total_size_uncompressed: int = 0
    md5: Optional[str] = None
    sha256: Optional[str] = None
    product_id: str = ""
    is_dependency: bool = False
    is_small_files_container: bool = False
    is_in_sfc: bool = False
    sfc_offset: int = 0
    sfc_size: int = 0
    flags: List[str] = field(default_factory=list)
    is_v1_blob: bool = False
    v1_offset: int = 0
    v1_size: int = 0
    v1_blob_md5: str = ""
    v1_blob_path: str = "main.bin"

    @classmethod
    def from_json_v2(cls, item_json: Dict[str, Any], product_id: str = "", 
                     is_dependency: bool = False) -> "DepotItem":
        """Create a DepotItem from v2 JSON data."""
        item = cls(
            path=item_json.get("path", ""),
            product_id=product_id,
            is_dependency=is_dependency,
            md5=item_json.get("md5"),
            sha256=item_json.get("sha256"),
            flags=item_json.get("flags", [])
        )
        
        # Check if in small files container
        if "sfcRef" in item_json:
            item.is_in_sfc = True
            item.sfc_offset = item_json["sfcRef"].get("offset", 0)
            item.sfc_size = item_json["sfcRef"].get("size", 0)
        
        # Parse chunks
        chunks_json = item_json.get("chunks", [])
        offset_compressed = 0
        offset_uncompressed = 0
        
        for chunk_json in chunks_json:
            chunk = DepotItemChunk.from_json(chunk_json, offset_compressed, offset_uncompressed)
            item.chunks.append(chunk)
            offset_compressed += chunk.size_compressed
            offset_uncompressed += chunk.size_uncompressed
        
        item.total_size_compressed = offset_compressed
        item.total_size_uncompressed = offset_uncompressed
        
        # If single chunk and no MD5 set, use chunk's MD5
        if len(item.chunks) == 1 and not item.md5:
            item.md5 = item.chunks[0].md5_uncompressed
        
        return item

    @classmethod
    def from_json_sfc(cls, sfc_json: Dict[str, Any], product_id: str = "",
                      is_dependency: bool = False) -> "DepotItem":
        """Create a DepotItem for small files container from JSON data."""
        item = cls(
            path="galaxy_smallfilescontainer",
            product_id=product_id,
            is_dependency=is_dependency,
            is_small_files_container=True,
            md5=sfc_json.get("md5")
        )
        
        # Parse chunks
        chunks_json = sfc_json.get("chunks", [])
        offset_compressed = 0
        offset_uncompressed = 0
        
        for chunk_json in chunks_json:
            chunk = DepotItemChunk.from_json(chunk_json, offset_compressed, offset_uncompressed)
            item.chunks.append(chunk)
            offset_compressed += chunk.size_compressed
            offset_uncompressed += chunk.size_uncompressed
        
        item.total_size_compressed = offset_compressed
        item.total_size_uncompressed = offset_uncompressed
        
        # If single chunk and no MD5 set, use chunk's MD5
        if len(item.chunks) == 1 and not item.md5:
            item.md5 = item.chunks[0].md5_uncompressed
        
        return item


@dataclass
class Depot:
    """
    Represents a Galaxy depot with metadata.
    
    Attributes:
        product_id: Product ID for this depot
        manifest: Manifest hash for this depot
        languages: List of supported languages
        os_bitness: List of supported OS bitness (32/64)
        size: Uncompressed size in bytes
        compressed_size: Compressed size in bytes
    """
    product_id: str
    manifest: str
    languages: List[str] = field(default_factory=list)
    os_bitness: List[str] = field(default_factory=list)
    size: int = 0
    compressed_size: int = 0

    @classmethod
    def from_json(cls, depot_json: Dict[str, Any]) -> "Depot":
        """Create a Depot from JSON data."""
        # V1 depots may have size as string, so explicitly convert to int
        size_value = depot_json.get("size", 0)
        compressed_size_value = depot_json.get("compressedSize", 0)
        
        return cls(
            product_id=depot_json.get("productId", ""),
            manifest=depot_json.get("manifest", ""),
            languages=depot_json.get("languages", []),
            os_bitness=depot_json.get("osBitness", []),
            size=int(size_value) if size_value else 0,
            compressed_size=int(compressed_size_value) if compressed_size_value else 0
        )

    def matches_filters(self, language: Optional[str] = None, 
                       bitness: Optional[str] = None) -> bool:
        """
        Check if this depot matches the given filters.
        
        Args:
            language: Language code to filter by (e.g., "en", "de")
            bitness: OS bitness to filter by (e.g., "64", "32")
            
        Returns:
            True if depot matches all specified filters
        """
        # Check language
        if language:
            lang_match = "*" in self.languages or language in self.languages
            if not lang_match:
                return False
        
        # Check bitness
        if bitness:
            if self.os_bitness:  # Only check if os_bitness is specified
                bitness_match = "*" in self.os_bitness or bitness in self.os_bitness
                if not bitness_match:
                    return False
        
        return True


@dataclass
class Manifest:
    """
    Represents a Galaxy manifest containing depot information.
    
    Attributes:
        base_product_id: Base product ID
        build_id: Build ID from builds API (user-facing ID like "3101")
        repository_id: Repository ID for V1 (legacy_build_id, repository timestamp like "24085618")
        generation: Build generation (1 or 2) - from GOG API builds endpoint
        version: Manifest version (1 or 2) - same as generation, kept for compatibility
        install_directory: Installation directory name
        depots: List of depots in this manifest
        dependencies: List of dependency IDs
        raw_data: Raw JSON data
    
    Note:
        For V1 manifests, repository_id (legacy_build_id) is used in the manifest URL,
        while build_id is the user-facing identifier shown in builds API.
    """
    base_product_id: str
    build_id: Optional[str] = None
    repository_id: Optional[str] = None  # V1 only: legacy_build_id / repository timestamp
    generation: int = 2
    version: int = 2  # Same as generation, kept for compatibility
    install_directory: str = ""
    depots: List[Depot] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_json_v2(cls, manifest_json: Dict[str, Any]) -> "Manifest":
        """Create a Manifest from v2 JSON data."""
        manifest = cls(
            base_product_id=manifest_json.get("baseProductId", ""),
            build_id=manifest_json.get("buildId"),
            generation=2,
            version=2,
            install_directory=manifest_json.get("installDirectory", ""),
            dependencies=manifest_json.get("dependencies", []),
            raw_data=manifest_json
        )
        
        # Parse depots
        for depot_json in manifest_json.get("depots", []):
            depot = Depot.from_json(depot_json)
            manifest.depots.append(depot)
        
        return manifest

    @classmethod
    def from_json_v1(cls, manifest_json: Dict[str, Any], product_id: str) -> "Manifest":
        """Create a Manifest from v1 JSON data."""
        manifest = cls(
            base_product_id=product_id,
            build_id=manifest_json.get("buildId"),
            generation=1,
            version=1,
            install_directory=manifest_json.get("product", {}).get("installDirectory", ""),
            raw_data=manifest_json
        )
        
        # V1 manifests have multiple depots in product.depots
        # Each depot contains language and game ID info
        product_data = manifest_json.get("product", {})
        depots_list = product_data.get("depots", [])
        
        for depot_data in depots_list:
            # Skip redistributable depots (dependencies)
            if depot_data.get("redist"):
                continue
            
            # Check if this depot is for our product or DLC
            game_ids = depot_data.get("gameIDs", [])
            if product_id in game_ids:
                depot = Depot.from_json({
                    "productId": product_id,
                    "manifest": depot_data.get("manifest", ""),
                    "languages": depot_data.get("languages", ["*"]),
                    "size": depot_data.get("size", 0),
                    "compressedSize": depot_data.get("compressedSize", 0)
                })
                manifest.depots.append(depot)
        
        return manifest

    def get_filtered_depots(self, language: Optional[str] = None,
                           bitness: Optional[str] = None,
                           product_ids: Optional[List[str]] = None) -> List[Depot]:
        """
        Get depots filtered by language, bitness, and product IDs.
        
        Args:
            language: Language code to filter by
            bitness: OS bitness to filter by
            product_ids: List of product IDs to include (base product + DLCs)
            
        Returns:
            List of filtered depots
        """
        filtered = []
        
        for depot in self.depots:
            # Filter by product ID if specified
            if product_ids and depot.product_id not in product_ids:
                continue
            
            # Filter by language and bitness
            if depot.matches_filters(language, bitness):
                filtered.append(depot)
        
        return filtered

    def to_json(self) -> str:
        """Serialize manifest to JSON string."""
        return json.dumps(self.raw_data, indent=2)

