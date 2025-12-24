"""
Dependency management for GOG redistributables.

Handles downloading and managing game dependencies (MSVC runtimes, DirectX, etc.)
separately from game files for archival purposes.
"""

import hashlib
import json
import logging
import zlib
from pathlib import Path
from typing import Dict, List, Optional, Set

from galaxy_dl.api import GalaxyAPI
from galaxy_dl import constants


class DependencyInfo:
    """Information about a single dependency."""
    
    def __init__(self, dependency_id: str, depot_data: dict):
        self.id = dependency_id
        self.manifest_hash = depot_data.get("manifest", "")
        self.size = depot_data.get("size", 0)
        self.compressed_size = depot_data.get("compressedSize", 0)
        self.executable_path = depot_data.get("executable", {}).get("path", "")
        self.executable_args = depot_data.get("executable", {}).get("argument", "")
        
        # Determine if this is a __redist (Windows installer bundle) or game-specific dependency
        self.is_redist = self.executable_path.startswith("__redist")
    
    def __repr__(self):
        return f"DependencyInfo(id={self.id}, manifest={self.manifest_hash}, size={self.size})"


class DependencyRepository:
    """
    Manages the GOG dependency repository.
    
    The repository contains metadata about all available dependencies
    and their download locations.
    """
    
    def __init__(self, api: GalaxyAPI):
        self.logger = logging.getLogger("galaxy_dl.dependencies")
        self.api = api
        self.repository: Optional[dict] = None
        self.dependencies: Dict[str, DependencyInfo] = {}
    
    def load(self) -> bool:
        """
        Load the dependency repository from GOG API.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info("Fetching dependency repository from GOG...")
            
            # Step 1: Get repository metadata
            repo_url = f"{constants.GOG_CONTENT_SYSTEM}/dependencies/repository?generation=2"
            response = self.api.session.get(repo_url, timeout=constants.DEFAULT_TIMEOUT)
            response.raise_for_status()
            
            repo_meta = response.json()
            
            # Step 2: Get actual repository manifest
            if "repository_manifest" not in repo_meta:
                self.logger.error("No repository_manifest in response")
                return False
            
            manifest_url = repo_meta["repository_manifest"]
            self.logger.debug(f"Fetching repository manifest from {manifest_url}")
            
            response = self.api.session.get(manifest_url, timeout=constants.DEFAULT_TIMEOUT)
            response.raise_for_status()
            
            # Repository manifest is zlib compressed
            try:
                decompressed = zlib.decompress(response.content)
                self.repository = json.loads(decompressed)
            except:
                # Fallback: try as plain JSON
                self.repository = response.json()
            
            # Validate repository was loaded
            if not self.repository:
                self.logger.error("Empty repository data")
                return False
            
            # Store build_id for tracking
            self.repository["build_id"] = repo_meta.get("build_id", "")
            
            # Parse dependency metadata
            if "depots" in self.repository:
                for depot in self.repository["depots"]:
                    dep_id = depot.get("dependencyId", "")
                    if dep_id:
                        self.dependencies[dep_id] = DependencyInfo(dep_id, depot)
            
            self.logger.info(f"Loaded {len(self.dependencies)} dependencies from repository")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to load dependency repository: {e}")
            return False
    
    def get_dependency(self, dependency_id: str) -> Optional[DependencyInfo]:
        """Get information about a specific dependency."""
        return self.dependencies.get(dependency_id)
    
    def filter_dependencies(self, dependency_ids: List[str], include_redist: bool = False) -> List[DependencyInfo]:
        """
        Filter dependencies based on IDs and redist status.
        
        Args:
            dependency_ids: List of dependency IDs to include
            include_redist: Whether to include __redist dependencies (Windows installer bundles)
        
        Returns:
            List of DependencyInfo objects
        """
        filtered = []
        for dep_id in dependency_ids:
            dep = self.get_dependency(dep_id)
            if dep:
                # Filter by redist status
                if include_redist or not dep.is_redist:
                    filtered.append(dep)
        
        return filtered


class DependencyManager:
    """
    Manages dependency downloads for archival purposes.
    
    Downloads dependencies to a separate location from game files,
    preserving the CDN structure for archival.
    """
    
    def __init__(self, api: GalaxyAPI, base_path: str = "./dependencies"):
        """
        Initialize dependency manager.
        
        Args:
            api: GalaxyAPI instance
            base_path: Base path for dependency storage (default: ./dependencies)
        """
        self.logger = logging.getLogger("galaxy_dl.dependencies")
        self.api = api
        self.base_path = Path(base_path)
        self.repository = DependencyRepository(api)
        
        # Track installed dependencies (simple set for backward compatibility)
        self.installed_manifest_path = self.base_path / "installed.json"
        self.installed: Set[str] = set()
        
        # Secure link for dependency downloads (cached)
        self.secure_link: Optional[List[dict]] = None
    
    def initialize(self) -> bool:
        """
        Initialize dependency system.
        
        Returns:
            True if successful, False otherwise
        """
        # Create base directory structure
        self.base_path.mkdir(parents=True, exist_ok=True)
        (self.base_path / "v2" / "meta").mkdir(parents=True, exist_ok=True)
        (self.base_path / "v2" / "store").mkdir(parents=True, exist_ok=True)
        (self.base_path / "debug").mkdir(parents=True, exist_ok=True)
        
        # Load repository
        if not self.repository.load():
            return False
        
        # Save repository metadata for archival (with build_id in filename)
        build_id = self.repository.repository.get('build_id', 'unknown')
        repo_path = self.base_path / f"repository_{build_id}.json"
        with open(repo_path, 'w') as f:
            json.dump(self.repository.repository, f, indent=2)
        
        self.logger.info(f"Saved repository metadata to {repo_path}")
        
        # Load installed manifest
        self._load_installed_manifest()
        
        return True
    
    def _load_installed_manifest(self):
        """Load the list of already installed dependencies."""
        if self.installed_manifest_path.exists():
            try:
                with open(self.installed_manifest_path, 'r') as f:
                    data = json.load(f)
                    self.installed = set(data.get("installed", []))
                    self.logger.debug(f"Loaded {len(self.installed)} installed dependencies")
            except Exception as e:
                self.logger.warning(f"Failed to load installed manifest: {e}")
                self.installed = set()
    
    def _save_installed_manifest(self):
        """Save the list of installed dependencies."""
        # Ensure repository was loaded
        if not self.repository.repository:
            self.logger.warning("Cannot save manifest: repository not loaded")
            return
        
        data = {
            "installed": sorted(list(self.installed)),
            "build_id": self.repository.repository.get("build_id", ""),
            "repository_manifest": self.repository.repository.get("repository_manifest", "")
        }
        
        with open(self.installed_manifest_path, 'w') as f:
            json.dump(data, f, indent=2)
    
    def _get_dependency_secure_link(self) -> Optional[List[dict]]:
        """
        Get secure link for dependency downloads.
        
        Dependencies use a different endpoint (open_link) that doesn't require product_id.
        The link is valid for a longer period and can be reused for all dependencies.
        
        Returns:
            List of CDN endpoint dicts or None if failed
        """
        if self.secure_link:
            return self.secure_link
        
        try:
            # Dependencies use open_link endpoint (no product_id required)
            url = f"{constants.GOG_CONTENT_SYSTEM}/open_link?generation=2&_version=2&path=/dependencies/store/"
            
            self.logger.debug(f"Fetching dependency secure link from {url}")
            
            response = self.api.session.get(url, timeout=constants.DEFAULT_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            self.secure_link = data.get("urls", [])
            
            if not self.secure_link:
                self.logger.error("No URLs in secure link response")
                return None
            
            self.logger.debug(f"Got {len(self.secure_link)} CDN endpoints")
            return self.secure_link
            
        except Exception as e:
            self.logger.error(f"Failed to get dependency secure link: {e}")
            return None
    
    def _download_chunk(self, chunk_md5: str, chunk_size: int) -> Optional[bytes]:
        """
        Download a single dependency chunk.
        
        Args:
            chunk_md5: MD5 hash of the compressed chunk
            chunk_size: Expected size of compressed chunk
        
        Returns:
            Chunk data or None if failed
        """
        # Get secure link
        endpoints = self._get_dependency_secure_link()
        if not endpoints:
            return None
        
        # Use first endpoint (heroic-gogdl pattern)
        endpoint = endpoints[0]
        
        # Build chunk path (same as game chunks)
        chunk_path = f"{chunk_md5[:2]}/{chunk_md5[2:4]}/{chunk_md5}"
        
        # Construct URL
        url = endpoint.get("url", "")
        if not url:
            self.logger.error("No URL in endpoint")
            return None
        
        # Add chunk path
        url = f"{url}/{chunk_path}"
        
        self.logger.debug(f"Downloading chunk {chunk_md5} from {url}")
        
        try:
            response = self.api.session.get(url, timeout=constants.DEFAULT_TIMEOUT)
            response.raise_for_status()
            
            chunk_data = response.content
            
            # Verify size
            if len(chunk_data) != chunk_size:
                self.logger.error(f"Chunk size mismatch: expected {chunk_size}, got {len(chunk_data)}")
                return None
            
            # Verify MD5
            actual_md5 = hashlib.md5(chunk_data).hexdigest()
            if actual_md5 != chunk_md5:
                self.logger.error(f"Chunk MD5 mismatch: expected {chunk_md5}, got {actual_md5}")
                return None
            
            return chunk_data
            
        except Exception as e:
            self.logger.error(f"Failed to download chunk {chunk_md5}: {e}")
            return None
    
    def get_dependencies_for_game(self, dependency_ids: List[str], include_redist: bool = False) -> List[DependencyInfo]:
        """
        Get dependency information for a specific game.
        
        Args:
            dependency_ids: List of dependency IDs from game manifest
            include_redist: Whether to include __redist dependencies
        
        Returns:
            List of DependencyInfo objects
        """
        return self.repository.filter_dependencies(dependency_ids, include_redist)
    
    def get_dependency_manifest(self, dependency: DependencyInfo) -> Optional[dict]:
        """
        Fetch and parse a dependency's manifest.
        
        Args:
            dependency: DependencyInfo object
        
        Returns:
            Parsed manifest dict or None if failed
        """
        try:
            # Get manifest from CDN (always V2 format, even for V1 games)
            # Dependencies use the same hash path structure as game manifests
            hash_path = f"{dependency.manifest_hash[:2]}/{dependency.manifest_hash[2:4]}/{dependency.manifest_hash}"
            url = f"{constants.GOG_CDN}/content-system/v2/dependencies/meta/{hash_path}"
            
            self.logger.debug(f"Fetching manifest for {dependency.id} from {url}")
            
            response = self.api.session.get(url, timeout=constants.DEFAULT_TIMEOUT)
            response.raise_for_status()
            
            # Try decompression (zlib with default window size)
            try:
                decompressed = zlib.decompress(response.content)
                manifest = json.loads(decompressed)
            except:
                # Fallback: try as plain JSON
                try:
                    manifest = response.json()
                except:
                    self.logger.error(f"Failed to parse manifest for {dependency.id}")
                    return None
            
            return manifest
            
        except Exception as e:
            self.logger.error(f"Failed to fetch manifest for {dependency.id}: {e}")
            return None
    
    def download_dependency(self, dependency: DependencyInfo, verify: bool = True) -> bool:
        """
        Download a single dependency for archival.
        
        Args:
            dependency: DependencyInfo object
            verify: Whether to verify downloads
        
        Returns:
            True if successful, False otherwise
        """
        self.logger.info(f"Downloading dependency: {dependency.id}")
        
        # Check if already installed
        if dependency.id in self.installed:
            self.logger.info(f"Dependency {dependency.id} already installed")
            return True
        
        # Get manifest
        manifest = self.get_dependency_manifest(dependency)
        if not manifest:
            return False
        
        # Save manifest metadata for archival
        hash_path = f"{dependency.manifest_hash[:2]}/{dependency.manifest_hash[2:4]}/{dependency.manifest_hash}"
        meta_dir = self.base_path / "v2" / "meta" / dependency.manifest_hash[:2] / dependency.manifest_hash[2:4]
        meta_dir.mkdir(parents=True, exist_ok=True)
        
        meta_path = meta_dir / dependency.manifest_hash
        with open(meta_path, 'wb') as f:
            # Save as compressed (original format)
            compressed = zlib.compress(json.dumps(manifest).encode('utf-8'))
            f.write(compressed)
        
        # Also save debug version
        debug_path = self.base_path / "debug" / f"{dependency.manifest_hash}_manifest.json"
        with open(debug_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        self.logger.info(f"Saved manifest metadata for {dependency.id}")
        
        # Download chunks
        if "depot" not in manifest or "items" not in manifest["depot"]:
            self.logger.warning(f"No depot items in manifest for {dependency.id}")
            self.installed.add(dependency.id)
            self._save_installed_manifest()
            return True
        
        total_chunks = 0
        downloaded_chunks = 0
        failed_chunks = 0
        
        # Count total chunks
        for item in manifest["depot"]["items"]:
            if item.get("type") == "DepotFile" and "chunks" in item:
                total_chunks += len(item["chunks"])
        
        self.logger.info(f"Downloading {total_chunks} chunks for {dependency.id}")
        
        # Download all chunks
        for item in manifest["depot"]["items"]:
            if item.get("type") != "DepotFile":
                continue
            
            if "chunks" not in item:
                continue
            
            for chunk in item["chunks"]:
                # Dependencies have both compressedMd5 and md5 fields
                chunk_md5 = chunk.get("compressedMd5") or chunk.get("md5")
                chunk_compressed_size = chunk.get("compressedSize", 0)
                
                if not chunk_md5:
                    self.logger.warning("Chunk missing MD5, skipping")
                    failed_chunks += 1
                    continue
                
                # Check if chunk already exists
                chunk_path = self.base_path / "v2" / "store" / chunk_md5[:2] / chunk_md5[2:4] / chunk_md5
                if chunk_path.exists():
                    # Verify existing chunk
                    if verify:
                        with open(chunk_path, 'rb') as f:
                            existing_md5 = hashlib.md5(f.read()).hexdigest()
                            if existing_md5 == chunk_md5:
                                downloaded_chunks += 1
                                continue
                            else:
                                self.logger.warning(f"Existing chunk {chunk_md5} failed verification, re-downloading")
                    else:
                        downloaded_chunks += 1
                        continue
                
                # Download chunk
                chunk_data = self._download_chunk(chunk_md5, chunk_compressed_size)
                if not chunk_data:
                    failed_chunks += 1
                    continue
                
                # Save chunk
                chunk_path.parent.mkdir(parents=True, exist_ok=True)
                with open(chunk_path, 'wb') as f:
                    f.write(chunk_data)
                
                downloaded_chunks += 1
                
                if downloaded_chunks % 10 == 0:
                    self.logger.info(f"Progress: {downloaded_chunks}/{total_chunks} chunks")
        
        self.logger.info(f"Downloaded {downloaded_chunks}/{total_chunks} chunks, {failed_chunks} failed")
        
        if failed_chunks > 0:
            self.logger.warning(f"Some chunks failed to download for {dependency.id}")
            return False
        
        # Mark as installed
        self.installed.add(dependency.id)
        self._save_installed_manifest()
        
        return True
    
    def list_dependencies(self, dependency_ids: List[str]) -> None:
        """
        List dependencies for a game.
        
        Args:
            dependency_ids: List of dependency IDs
        """
        deps = self.get_dependencies_for_game(dependency_ids, include_redist=True)
        
        print(f"\nFound {len(deps)} dependencies:")
        print("=" * 80)
        
        for dep in deps:
            installed = "✓" if dep.id in self.installed else " "
            size_mb = dep.compressed_size / (1024 * 1024)
            print(f"[{installed}] {dep.id:20} {size_mb:8.2f} MB  {dep.executable_path}")
        
        print("=" * 80)
