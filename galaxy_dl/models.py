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
class FilePatchDiff:
    """
    Represents a patch for updating one file to another using xdelta3.
    
    Attributes:
        md5_source: MD5 hash of the source (old) file
        md5_target: MD5 hash of the target (new) file
        source_path: Path to source file
        target_path: Path to target file
        md5: MD5 hash of the patch file itself
        chunks: List of patch chunks to download
        old_file: Reference to old DepotItem (populated during comparison)
        new_file: Reference to new DepotItem (populated during comparison)
    """
    md5_source: str
    md5_target: str
    source_path: str
    target_path: str
    md5: str
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    old_file: Optional[DepotItem] = None
    new_file: Optional[DepotItem] = None

    @classmethod
    def from_json(cls, patch_json: Dict[str, Any]) -> "FilePatchDiff":
        """Create FilePatchDiff from JSON data."""
        return cls(
            md5_source=patch_json.get("md5_source", ""),
            md5_target=patch_json.get("md5_target", ""),
            source_path=patch_json.get("path_source", "").replace("\\", "/"),
            target_path=patch_json.get("path_target", "").replace("\\", "/"),
            md5=patch_json.get("md5", ""),
            chunks=patch_json.get("chunks", [])
        )


@dataclass
class Patch:
    """
    Represents patch information for updating from one build to another.
    
    Attributes:
        patch_data: Raw patch metadata from GOG
        files: List of file patches (FilePatchDiff)
        algorithm: Patch algorithm (should be 'xdelta3')
        from_build_id: Source build ID
        to_build_id: Target build ID
    """
    patch_data: Dict[str, Any] = field(default_factory=dict)
    files: List[FilePatchDiff] = field(default_factory=list)
    algorithm: str = "xdelta3"
    from_build_id: Optional[str] = None
    to_build_id: Optional[str] = None

    @classmethod
    def get(cls, api_client, manifest: "Manifest", old_manifest: "Manifest",
            language: str, dlc_product_ids: List[str]) -> Optional["Patch"]:
        """
        Query GOG API for patch availability and download patch manifests.
        
        Args:
            api_client: GalaxyAPI instance for making requests
            manifest: New/target manifest
            old_manifest: Old/source manifest
            language: Language code (e.g., "en")
            dlc_product_ids: List of DLC product IDs to include
            
        Returns:
            Patch object if patch is available, None otherwise
            
        Note:
            Only works for V2 manifests. Returns None for V1 manifests.
        """
        # Import here to avoid circular dependency
        from galaxy_dl import utils
        
        # V1 manifests don't support patches
        if manifest.generation == 1 or old_manifest.generation == 1:
            return None
        
        # Both manifests must have build IDs
        from_build = old_manifest.build_id
        to_build = manifest.build_id
        if not from_build or not to_build:
            return None
        
        # Query patch availability
        try:
            patch_info = api_client.get_patch_info(
                manifest.base_product_id,
                from_build,
                to_build
            )
            
            if not patch_info or patch_info.get('error'):
                return None
            
            # Download patch metadata manifest
            patch_link = patch_info.get('link')
            if not patch_link:
                return None
            
            patch_data = api_client.get_patch_manifest(patch_link)
            if not patch_data:
                return None
            
            # Verify patch algorithm is supported
            if patch_data.get('algorithm') != 'xdelta3':
                print(f"Unsupported patch algorithm: {patch_data.get('algorithm')}")
                return None
            
            # Get depots we need based on product IDs and language
            all_product_ids = [manifest.base_product_id] + dlc_product_ids
            depots_to_fetch = []
            
            for depot in patch_data.get('depots', []):
                depot_product_id = depot.get('productId')
                depot_languages = depot.get('languages', [])
                
                # Check if this depot matches our product IDs and language
                if depot_product_id in all_product_ids:
                    if language in depot_languages:
                        depots_to_fetch.append(depot)
            
            if not depots_to_fetch:
                return None
            
            # Download and parse patch manifests for each depot
            files = []
            for depot in depots_to_fetch:
                depot_manifest = depot.get('manifest')
                if not depot_manifest:
                    continue
                
                # Download depot patch manifest
                depot_diffs = api_client.get_patch_depot_manifest(depot_manifest)
                if not depot_diffs:
                    print(f"Failed to get patch depot manifest for {depot_manifest}")
                    return None
                
                # Parse DepotDiff items
                for diff in depot_diffs.get('depot', {}).get('items', []):
                    if diff.get('type') == 'DepotDiff':
                        files.append(FilePatchDiff.from_json(diff))
                    else:
                        print(f'Unknown type in patcher: {diff.get("type")}')
                        return None
            
            # Create patch object
            patch = cls(
                patch_data=patch_data,
                files=files,
                algorithm=patch_data.get('algorithm', 'xdelta3'),
                from_build_id=from_build,
                to_build_id=to_build
            )
            
            return patch
            
        except Exception as e:
            print(f"Failed to get patch: {e}")
            return None


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
        items: List of depot items (V1 files or V2 items)
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
    items: List[DepotItem] = field(default_factory=list)  # V1 files or V2 items
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
        """
        Create a Manifest from v1 JSON data.
        
        V1 manifests come in two forms:
        1. Build metadata from builds API with product.depots[] (depot info only)
        2. Actual manifest with depot.files[] (file list with offset/size)
        
        This method handles the actual manifest structure with depot.files[].
        """
        manifest = cls(
            base_product_id=product_id,
            build_id=manifest_json.get("buildId"),
            generation=1,
            version=1,
            install_directory="",  # V1 manifests don't have install directory in manifest JSON
            raw_data=manifest_json
        )
        
        # Parse V1 manifest structure: depot.files[]
        depot_data = manifest_json.get("depot", {})
        if depot_data:
            # Create a single depot representing the main.bin
            depot = Depot(
                product_id=product_id,
                manifest="",  # V1 doesn't have manifest hash in the file list
                languages=["*"],  # Language is determined by which manifest you fetch
                os_bitness=[],
                size=0,  # Will be calculated from files
                compressed_size=0
            )
            manifest.depots.append(depot)
            
            # Parse files - each file is stored in main.bin at a specific offset
            files = depot_data.get("files", [])
            for file_data in files:
                # Create DepotItem for V1 file with offset/size info
                item = DepotItem(
                    path=file_data.get("path", "").lstrip("/"),
                    md5=file_data.get("hash", ""),
                    product_id=product_id,
                    is_v1_blob=True,
                    v1_offset=file_data.get("offset", 0),
                    v1_size=file_data.get("size", 0),
                    v1_blob_path=file_data.get("url", "main.bin"),  # e.g., "1207658930/main.bin"
                    total_size_uncompressed=file_data.get("size", 0)
                )
                manifest.items.append(item)
                depot.size += item.v1_size
        
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

    @classmethod
    def compare(cls, new_manifest: "Manifest", old_manifest: Optional["Manifest"] = None,
                patch: Optional[Patch] = None) -> "ManifestDiff":
        """
        Compare two manifests to determine what has changed.
        
        This creates a diff showing which files are new, changed, or deleted.
        If a patch is available, it will be used for changed files instead of
        downloading full files.
        
        Args:
            new_manifest: Target manifest (what we want)
            old_manifest: Source manifest (what we have), None for fresh install
            patch: Optional patch object for incremental updates
            
        Returns:
            ManifestDiff showing changes needed
            
        Example:
            >>> # Fresh install
            >>> diff = Manifest.compare(manifest)
            >>> 
            >>> # Update with patch
            >>> patch = Patch.get(api, new_manifest, old_manifest, "en", dlc_ids)
            >>> diff = Manifest.compare(new_manifest, old_manifest, patch)
        """
        from galaxy_dl.diff import ManifestDiff
        
        diff = ManifestDiff()
        
        # Fresh install - all files are new
        if not old_manifest:
            diff.new = new_manifest.items
            return diff
        
        # Build lookup dicts
        new_files = {item.path.lower(): item for item in new_manifest.items}
        old_files = {item.path.lower(): item for item in old_manifest.items}
        
        # Find deleted files
        for old_path, old_item in old_files.items():
            if old_path not in new_files:
                diff.deleted.append(old_item)
        
        # Find new and changed files
        for new_path, new_item in new_files.items():
            old_item = old_files.get(new_path)
            
            if not old_item:
                # New file
                diff.new.append(new_item)
            else:
                # File exists in both - check if changed
                # For V1->V2 upgrades, always re-download
                if old_manifest.generation != new_manifest.generation:
                    diff.changed.append(new_item)
                    continue
                
                # Check if we have a patch for this file
                patch_file = None
                if patch:
                    for pf in patch.files:
                        # Match by md5_source (old file hash)
                        old_hash = old_item.md5 or (old_item.chunks[0]["md5_uncompressed"] if old_item.chunks else None)
                        if pf.md5_source == old_hash:
                            patch_file = pf
                            patch_file.old_file = old_item
                            patch_file.new_file = new_item
                            break
                
                if patch_file:
                    # Use patch instead of full download
                    diff.patched.append(patch_file)
                else:
                    # Check if file content changed
                    if cls._file_changed(new_item, old_item):
                        diff.changed.append(new_item)
        
        return diff

    @staticmethod
    def _file_changed(new_item: DepotItem, old_item: DepotItem) -> bool:
        """Check if a file has changed between manifests."""
        # Compare by MD5 if available
        if new_item.md5 and old_item.md5:
            return new_item.md5 != old_item.md5
        
        # Compare by SHA256 if available
        if new_item.sha256 and old_item.sha256:
            return new_item.sha256 != old_item.sha256
        
        # For single-chunk files, compare chunk MD5
        if len(new_item.chunks) == 1 and len(old_item.chunks) == 1:
            return new_item.chunks[0].md5_uncompressed != old_item.chunks[0].md5_uncompressed
        
        # For multi-chunk files, compare chunk count and individual chunks
        if len(new_item.chunks) != len(old_item.chunks):
            return True
        
        for new_chunk, old_chunk in zip(new_item.chunks, old_item.chunks):
            if new_chunk.md5_uncompressed != old_chunk.md5_uncompressed:
                return True
        
        return False




