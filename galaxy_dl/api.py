"""
Galaxy API Client
Based on heroic-gogdl api.py and lgogdownloader galaxyapi.cpp
Provides access to GOG Galaxy content-system API
"""

import json
import logging
from typing import List, Optional, Dict, Any
from urllib.parse import quote

import requests

from galaxy_dl import constants, utils
from galaxy_dl.auth import AuthManager
from galaxy_dl.models import DepotItem, Manifest


class GalaxyAPI:
    """
    Client for GOG Galaxy API.
    
    Provides methods to access Galaxy content-system endpoints for:
    - Getting product builds
    - Downloading manifests (v1 and v2)
    - Getting secure download links
    - Accessing dependency information
    """

    def __init__(self, auth_manager: AuthManager):
        """
        Initialize Galaxy API client.
        
        Args:
            auth_manager: Authentication manager with valid credentials
        """
        self.auth_manager = auth_manager
        self.logger = logging.getLogger("galaxy_dl.api")
        
        # Setup session
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": constants.USER_AGENT.format(version="0.1.0")
        })
        
        # Set authorization header if authenticated
        auth_header = self.auth_manager.get_auth_header()
        if auth_header:
            self.session.headers["Authorization"] = auth_header
        
        # Cache for secure links
        self._secure_link_cache: Dict[str, List[str]] = {}

    # ========== URL Construction Methods ==========
    
    def get_depot_url(self, build_id: str) -> str:
        """Get depot metadata URL for V2 build (build's link field hash)."""
        return f"{constants.GOG_CDN_ALT}/content-system/v2/meta/{build_id[:2]}/{build_id[2:4]}/{build_id}"
    
    def get_repository_url(self, game_id: str, platform: str, timestamp: str) -> str:
        """Get repository metadata URL for V1 build."""
        return f"{constants.GOG_CDN_ALT}/content-system/v1/manifests/{game_id}/{platform}/{timestamp}/repository.json"
    
    def get_manifest_url(self, manifest_id: str, game_id: Optional[str] = None, platform: Optional[str] = None, timestamp: Optional[str] = None, generation: int = 2) -> str:
        """Get manifest URL (works for both V1 and V2).
        
        For V1: requires game_id, platform, and timestamp
        For V2: only requires manifest_id (hash)
        """
        if generation == 1:
            if not all([game_id, platform, timestamp]):
                raise ValueError("V1 manifests require game_id, platform, and timestamp parameters")
            return f"{constants.GOG_CDN_ALT}/content-system/v1/manifests/{game_id}/{platform}/{timestamp}/{manifest_id}"
        return f"{constants.GOG_CDN_ALT}/content-system/v2/meta/{manifest_id[:2]}/{manifest_id[2:4]}/{manifest_id}"
    
    def get_chunk_url(self, compressed_md5: str) -> str:
        """Get V2 chunk URL using compressedMd5."""
        return f"{constants.GOG_CDN_ALT}/content-system/v2/store/{compressed_md5[:2]}/{compressed_md5[2:4]}/{compressed_md5}"
    
    def download_raw(self, url: str, output_path: str) -> None:
        """
        Download raw content without any processing.
        
        Saves file exactly as received (may be zlib compressed JSON).
        
        Args:
            url: URL to download
            output_path: Path to save the file
        """
        import os
        self._update_auth_header()
        
        response = self.session.get(url, timeout=constants.DEFAULT_TIMEOUT)
        response.raise_for_status()
        
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(response.content)
        
        self.logger.debug(f"Downloaded raw: {output_path} ({len(response.content)} bytes)")
    
    def download_main_bin(self, game_id: str, platform: str, timestamp: str, output_path: str,
                          num_workers: int = 4) -> None:
        """
        Download V1 main.bin file using secure links with parallel byte-range requests.
        
        V1 main.bin files require authenticated secure links and cannot be
        downloaded from static CDN URLs. Uses parallel downloads for better performance.
        
        Args:
            game_id: Product ID
            platform: Platform (e.g., 'windows', 'osx', 'linux')
            timestamp: Build timestamp from repository
            output_path: Path to save main.bin
            num_workers: Number of parallel download threads (default: 4)
        """
        import os
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading
        
        # Get secure link for the V1 depot
        path = f"/{platform}/{timestamp}/"
        self.logger.info(f"Getting secure link for V1 depot: game={game_id}, path={path}")
        secure_links = self.get_secure_link(game_id, path, generation=1, return_full_response=True)
        
        if not secure_links:
            raise RuntimeError(f"Failed to get secure links for game {game_id}")
        
        self.logger.debug(f"Got {len(secure_links)} secure link endpoints")
        
        # Use first endpoint and append main.bin to path
        endpoint = secure_links[0]
        self.logger.debug(f"Using endpoint: {endpoint.get('endpoint_name', 'unknown')}")
        
        params = endpoint["parameters"].copy()
        original_path = params.get("path", "")
        params["path"] = original_path + "/main.bin"
        
        # Merge URL template with parameters
        url = self._merge_url_with_params(endpoint["url_format"], params)
        
        self.logger.info(f"Downloading main.bin from: {url[:100]}...")
        print(f"   URL: {url}")
        
        # First, make a HEAD request to get file size without downloading
        head_response = self.session.head(url, timeout=constants.DEFAULT_TIMEOUT)
        head_response.raise_for_status()
        
        total_size = int(head_response.headers.get('content-length', 0))
        if total_size == 0:
            # Fallback to simple streaming if server doesn't support ranges
            print(f"   Size: Unknown - server doesn't support Content-Length")
            print(f"   Falling back to simple streaming download...")
            return self._download_main_bin_simple(url, output_path)
        
        print(f"   Size: {total_size:,} bytes ({total_size / 1024 / 1024:.2f} MB)")
        
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        
        # Pre-allocate file to avoid fragmentation and ensure we have space
        print(f"   Pre-allocating file space...")
        try:
            with open(output_path, 'wb') as f:
                f.seek(total_size - 1)
                f.write(b'\0')
                f.flush()
            self.logger.debug(f"Pre-allocated {total_size:,} bytes")
        except OSError as e:
            raise RuntimeError(f"Failed to pre-allocate {total_size:,} bytes. Check available disk space.") from e
        
        # Calculate chunk ranges for parallel download (50 MiB per chunk)
        chunk_size = 50 * 1024 * 1024  # 50 MiB
        ranges = []
        for start in range(0, total_size, chunk_size):
            end = min(start + chunk_size - 1, total_size - 1)
            ranges.append((start, end))
        
        print(f"   Downloading with {num_workers} parallel threads ({len(ranges)} chunks)...")
        
        # Thread-safe progress tracking
        downloaded_lock = threading.Lock()
        downloaded_bytes = [0]  # Use list for mutability in closure
        
        def download_range(range_info):
            """Download a specific byte range."""
            start, end = range_info
            chunk_num = ranges.index(range_info)
            
            headers = {'Range': f'bytes={start}-{end}'}
            response = self.session.get(url, headers=headers, stream=True, timeout=constants.DEFAULT_TIMEOUT)
            response.raise_for_status()
            
            # Write to the correct position in file
            chunk_data = response.content
            with open(output_path, 'r+b') as f:
                f.seek(start)
                f.write(chunk_data)
            
            # Update progress
            with downloaded_lock:
                downloaded_bytes[0] += len(chunk_data)
                mb_downloaded = downloaded_bytes[0] / 1024 / 1024
                mb_total = total_size / 1024 / 1024
                progress = (downloaded_bytes[0] / total_size) * 100
                print(f"\r   Progress: {mb_downloaded:.1f} / {mb_total:.1f} MB ({progress:.1f}%) - {len(ranges) - chunk_num} chunks remaining", end='', flush=True)
            
            return len(chunk_data)
        
        # Download ranges in parallel
        total_downloaded = 0
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = {executor.submit(download_range, r): r for r in ranges}
            
            for future in as_completed(futures):
                try:
                    chunk_bytes = future.result()
                    total_downloaded += chunk_bytes
                except Exception as e:
                    self.logger.error(f"Failed to download chunk: {e}")
                    raise
        
        print()  # New line after progress
        
        # Verify we got the expected size
        if total_downloaded != total_size:
            self.logger.warning(f"Size mismatch: expected {total_size:,}, got {total_downloaded:,}")
        
        self.logger.info(f"Downloaded main.bin: {output_path} ({total_downloaded:,} bytes)")
    
    def _download_main_bin_simple(self, url: str, output_path: str) -> None:
        """Fallback simple streaming download when server doesn't support ranges."""
        import os
        
        response = self.session.get(url, stream=True, timeout=constants.DEFAULT_TIMEOUT)
        response.raise_for_status()
        
        chunk_size = 50 * 1024 * 1024  # 50 MiB
        downloaded = 0
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    mb_downloaded = downloaded / 1024 / 1024
                    print(f"\r   Downloaded: {mb_downloaded:.1f} MB", end='', flush=True)
        
        print()
        self.logger.info(f"Downloaded main.bin: {output_path} ({downloaded:,} bytes)")
    
    def _merge_url_with_params(self, url_format: str, parameters: Dict[str, Any]) -> str:
        """Merge URL template with parameters."""
        url = url_format
        for key, value in parameters.items():
            url = url.replace("{" + key + "}", str(value))
        return url

    def _update_auth_header(self) -> None:
        """Update authorization header with fresh token if needed."""
        auth_header = self.auth_manager.get_auth_header()
        if auth_header:
            self.session.headers["Authorization"] = auth_header

    def _get_response(self, url: str, encoding: Optional[str] = None, 
                     max_retries: int = constants.DEFAULT_RETRIES) -> str:
        """
        Get response from URL with retries.
        
        Args:
            url: URL to request
            encoding: Optional Accept-Encoding header value
            max_retries: Maximum number of retries
            
        Returns:
            Response text
        """
        headers = {}
        if encoding:
            headers["Accept-Encoding"] = encoding
        
        self._update_auth_header()
        
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, headers=headers, 
                                           timeout=constants.DEFAULT_TIMEOUT)
                response.raise_for_status()
                
                self.logger.debug(f"Response code for {url}: {response.status_code}")
                return response.text
                
            except requests.RequestException as e:
                self.logger.warning(f"Request failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise
        
        return ""

    def _get_response_json(self, url: str, encoding: Optional[str] = None) -> Dict[str, Any]:
        """
        Get JSON response from URL, handling zlib compression.
        
        Args:
            url: URL to request
            encoding: Optional encoding to request
            
        Returns:
            Parsed JSON data
        """
        self._update_auth_header()
        
        try:
            response = self.session.get(url, timeout=constants.DEFAULT_TIMEOUT)
            response.raise_for_status()
            
            # Check if response is zlib compressed
            if utils.is_zlib_compressed(response.content):
                import zlib
                decompressed = zlib.decompress(response.content, constants.ZLIB_WINDOW_SIZE)
                return json.loads(decompressed)
            else:
                return response.json()
                
        except Exception as e:
            self.logger.error(f"Failed to get JSON from {url}: {e}")
            return {}

    def get_product_builds(self, product_id: str, platform: str = constants.PLATFORM_WINDOWS,
                          generation: str = constants.GENERATION_2,
                          filter_generation: Optional[int] = None) -> Dict[str, Any]:
        """
        Get available builds for a product from a specific generation endpoint.
        
        GOG API Quirky Behavior:
        - generation=1 or missing: Returns ONLY V1 builds (may miss some in gen=2)
        - generation=2: Returns BOTH V1 and V2 builds (may miss some in gen=1)
        - Some builds only appear in one endpoint - use get_all_product_builds() for completeness
        
        Args:
            product_id: GOG product ID
            platform: Platform (windows, osx, linux)
            generation: Generation to query ("1" or "2")
            filter_generation: Optional - filter results to only this generation (1 or 2)
            
        Returns:
            JSON data containing builds information
            
        Note:
            For complete build discovery, use get_all_product_builds() which queries both endpoints.
        """
        url = constants.BUILDS_URL.format(
            product_id=product_id,
            platform=platform,
            generation=generation
        )
        
        self.logger.info(f"Getting builds for product {product_id} (generation={generation})")
        result = self._get_response_json(url)
        
        # Filter by generation if requested
        if filter_generation is not None and "items" in result:
            result["items"] = [
                build for build in result["items"]
                if build.get("generation") == filter_generation
            ]
            result["count"] = len(result["items"])
        
        return result

    def get_all_product_builds(self, product_id: str, 
                              platform: str = constants.PLATFORM_WINDOWS) -> Dict[str, Any]:
        """
        Get ALL available builds (both V1 and V2) for a product.
        
        This queries BOTH generation=1 and generation=2 endpoints because:
        - Some builds only appear in generation=1 query
        - Some builds only appear in generation=2 query
        - We need both to ensure complete build discovery
        
        Args:
            product_id: GOG product ID
            platform: Platform (windows, osx, linux)
            
        Returns:
            JSON data containing all builds merged from both queries
        """
        all_builds = []
        
        # Query generation=1 (may have builds not in gen=2)
        try:
            gen1_result = self.get_product_builds(product_id, platform, constants.GENERATION_1)
            if gen1_result and "items" in gen1_result:
                all_builds.extend(gen1_result["items"])
                self.logger.debug(f"Found {len(gen1_result['items'])} builds in generation=1")
        except Exception as e:
            self.logger.warning(f"Failed to query generation=1 builds: {e}")
        
        # Query generation=2 (may have builds not in gen=1)
        try:
            gen2_result = self.get_product_builds(product_id, platform, constants.GENERATION_2)
            if gen2_result and "items" in gen2_result:
                all_builds.extend(gen2_result["items"])
                self.logger.debug(f"Found {len(gen2_result['items'])} builds in generation=2")
        except Exception as e:
            self.logger.warning(f"Failed to query generation=2 builds: {e}")
        
        if not all_builds:
            self.logger.warning(f"No builds found for product {product_id}")
            return {"total_count": 0, "count": 0, "items": []}
        
        # Merge and deduplicate builds
        merged_builds = self._merge_build_lists(all_builds)
        
        return {
            "total_count": len(merged_builds),
            "count": len(merged_builds),
            "items": merged_builds,
            "has_private_branches": False  # We don't know this when merging
        }

    def _merge_build_lists(self, builds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Merge and deduplicate build lists from multiple queries.
        
        Deduplicates by build_id, keeping the first occurrence.
        Sorts by date_published (newest first).
        
        Args:
            builds: List of build dicts from multiple queries
            
        Returns:
            Deduplicated and sorted list of builds
        """
        seen_build_ids = set()
        unique_builds = []
        
        for build in builds:
            build_id = build.get("build_id")
            if build_id and build_id not in seen_build_ids:
                seen_build_ids.add(build_id)
                unique_builds.append(build)
            elif build_id:
                self.logger.debug(f"Skipping duplicate build_id: {build_id}")
        
        # Sort by date_published, newest first
        unique_builds.sort(
            key=lambda b: b.get("date_published", ""),
            reverse=True
        )
        
        self.logger.info(f"Merged {len(builds)} builds into {len(unique_builds)} unique builds")
        return unique_builds

    def get_manifest_v1(self, product_id: str, repository_id: str, 
                       manifest_id: str = "repository",
                       platform: str = constants.PLATFORM_WINDOWS) -> Dict[str, Any]:
        """
        Get v1 manifest data using repository ID.
        
        Args:
            product_id: GOG product ID
            repository_id: Repository ID (legacy_build_id from builds API, aka repository timestamp)
            manifest_id: Manifest ID (default: "repository")
            platform: Platform
            
        Returns:
            V1 manifest JSON data
            
        Note:
            For delisted builds, you can get repository_id from gogdb.org (shown as "Repository timestamp")
        """
        url = constants.MANIFEST_V1_URL.format(
            product_id=product_id,
            platform=platform,
            repository_id=repository_id,
            manifest_id=manifest_id
        )
        
        self.logger.info(f"Getting v1 manifest for {product_id}/{repository_id}")
        return self._get_response_json(url)

    def get_manifest_v1_direct(self, product_id: str, repository_id: str,
                              platform: str = constants.PLATFORM_WINDOWS) -> Dict[str, Any]:
        """
        Get v1 manifest directly by repository ID (for delisted builds).
        
        This is useful when you have repository ID from external sources like gogdb.org
        and the build is no longer listed in the builds API.
        
        Args:
            product_id: GOG product ID
            repository_id: Repository ID (legacy_build_id, repository timestamp)
            platform: Platform
            
        Returns:
            V1 manifest JSON data
            
        Example:
            >>> # From gogdb.org: Repository timestamp: 24085618
            >>> manifest = api.get_manifest_v1_direct("1207658924", "24085618", "osx")
        """
        url = constants.MANIFEST_V1_REPOSITORY_URL.format(
            product_id=product_id,
            platform=platform,
            repository_id=repository_id
        )
        
        self.logger.info(f"Getting v1 manifest directly: {product_id}/{repository_id}")
        return self._get_response_json(url)

    def get_manifest_by_url(self, url: str) -> Dict[str, Any]:
        """
        Get manifest directly by URL (maximum flexibility for delisted builds).
        
        This allows you to paste URLs directly from gogdb.org or other sources.
        
        Args:
            url: Full manifest URL
            
        Returns:
            Manifest JSON data
            
        Example:
            >>> url = "https://cdn.gog.com/content-system/v1/manifests/1207658924/osx/24085618/repository.json"
            >>> manifest = api.get_manifest_by_url(url)
        """
        self.logger.info(f"Getting manifest from URL: {url}")
        return self._get_response_json(url)

    def get_manifest_v2(self, manifest_hash: str, is_dependency: bool = False) -> Dict[str, Any]:
        """
        Get v2 manifest data.
        
        Args:
            manifest_hash: Manifest hash (will be converted to Galaxy path format)
            is_dependency: Whether this is a dependency manifest
            
        Returns:
            V2 manifest JSON data
        """
        # Convert hash to Galaxy path format if needed
        galaxy_path_str = utils.galaxy_path(manifest_hash)
        
        if is_dependency:
            url = constants.MANIFEST_V2_DEPENDENCIES_URL.format(path=galaxy_path_str)
        else:
            url = constants.MANIFEST_V2_URL.format(path=galaxy_path_str)
        
        self.logger.info(f"Getting v2 manifest: {manifest_hash}")
        data, _ = utils.get_zlib_encoded(self.session, url)
        return data or {}

    def get_depot_items(self, manifest_hash: str, is_dependency: bool = False) -> List[DepotItem]:
        """
        Get depot items from a manifest.
        
        Args:
            manifest_hash: Manifest hash
            is_dependency: Whether this is a dependency
            
        Returns:
            List of DepotItem objects
        """
        manifest_json = self.get_manifest_v2(manifest_hash, is_dependency)
        
        if not manifest_json or "depot" not in manifest_json:
            return []
        
        depot = manifest_json["depot"]
        items = []
        
        # Handle small files container
        if "smallFilesContainer" in depot:
            sfc_item = DepotItem.from_json_sfc(
                depot["smallFilesContainer"],
                is_dependency=is_dependency
            )
            items.append(sfc_item)
        
        # Handle regular items
        for item_json in depot.get("items", []):
            if item_json.get("type") == "DepotFile":
                item = DepotItem.from_json_v2(
                    item_json,
                    is_dependency=is_dependency
                )
                items.append(item)
        
        return items

    def get_secure_link(self, product_id: str, path: str = "/",
                       generation: int = 2, return_full_response: bool = False) -> List[Any]:
        """
        Get secure download links for a product.
        
        Args:
            product_id: GOG product ID
            path: Path parameter (default: "/")
            generation: Generation version (1 for V1, 2 for V2)
            return_full_response: If True, return full endpoint data with url_format and parameters
                                 If False, return just the merged URLs (default for compatibility)
            
        Returns:
            List of CDN URLs (if return_full_response=False)
            or List of endpoint dicts with 'url_format' and 'parameters' (if return_full_response=True)
        """
        # Check cache (only for URL mode, not full response)
        cache_key = f"{product_id}:{path}:{generation}"
        if not return_full_response and cache_key in self._secure_link_cache:
            return self._secure_link_cache[cache_key]
        
        # Build API URL based on generation
        if generation == 2:
            url = f"{constants.GOG_CONTENT_SYSTEM}/products/{product_id}/secure_link?_version=2&generation=2&path={quote(path)}"
        elif generation == 1:
            url = f"{constants.GOG_CONTENT_SYSTEM}/products/{product_id}/secure_link?_version=2&type=depot&path={quote(path)}"
        else:
            raise ValueError(f"Invalid generation: {generation}. Must be 1 or 2.")
        
        self.logger.info(f"Getting secure link for product {product_id} (gen {generation})")
        response = self._get_response_json(url)
        
        if "urls" in response:
            if return_full_response:
                # Return full endpoint data for V1 main.bin downloads
                return response["urls"]
            else:
                # Extract and merge URLs for normal usage
                urls = self._extract_urls_from_response(response)
                self._secure_link_cache[cache_key] = urls
                return urls
        
        return []

    def get_dependency_link(self, path: str = "") -> List[str]:
        """
        Get dependency download links.
        
        Args:
            path: Dependency path
            
        Returns:
            List of CDN URLs
        """
        url = constants.DEPENDENCY_LINK_URL.format(path=quote(path))
        
        self.logger.info("Getting dependency link")
        response = self._get_response_json(url)
        
        if "urls" in response:
            return self._extract_urls_from_response(response)
        
        return []

    def _extract_urls_from_response(self, response: Dict[str, Any],
                                    cdn_priority: Optional[List[str]] = None) -> List[str]:
        """
        Extract and prioritize CDN URLs from secure link response.
        
        Based on lgogdownloader's cdnUrlTemplatesFromJson implementation.
        
        Args:
            response: Secure link JSON response
            cdn_priority: Optional list of CDN endpoint names in priority order
            
        Returns:
            List of CDN URLs sorted by priority
        """
        if "urls" not in response:
            return []
        
        if cdn_priority is None:
            cdn_priority = []
        
        url_priorities = []
        
        for idx, url_info in enumerate(response["urls"]):
            endpoint_name = url_info.get("endpoint_name", "")
            
            # Calculate priority score
            try:
                score = cdn_priority.index(endpoint_name)
            except ValueError:
                # Not in priority list, use position + length of priority list
                score = len(cdn_priority) + idx
            
            # Build URL from url_format and parameters
            url_template = url_info.get("url_format", "")
            parameters = url_info.get("parameters", {})
            
            # Add our own path template
            if "{path}" in url_template:
                parameters["path"] = parameters.get("path", "") + "{GALAXY_PATH}"
            
            url = utils.merge_url_with_params(url_template, parameters)
            
            url_priorities.append((score, url))
        
        # Sort by priority score
        url_priorities.sort(key=lambda x: x[0])
        
        return [url for _, url in url_priorities]

    def get_dependencies_repository(self, generation: str = constants.GENERATION_2) -> Dict[str, Any]:
        """
        Get dependencies repository information.
        
        Args:
            generation: Generation version (1 or 2)
            
        Returns:
            Dependencies repository JSON
        """
        if generation == constants.GENERATION_2:
            url = constants.DEPENDENCIES_URL
        else:
            url = constants.DEPENDENCIES_V1_URL
        
        self.logger.info("Getting dependencies repository")
        response = self._get_response_json(url)
        
        # V2 has additional repository_manifest URL to fetch
        if generation == constants.GENERATION_2 and "repository_manifest" in response:
            manifest_url = response["repository_manifest"]
            return self._get_response_json(manifest_url)
        
        return response

    def get_product_info(self, product_id: str) -> Dict[str, Any]:
        """
        Get detailed product information.
        
        Args:
            product_id: GOG product ID
            
        Returns:
            Product information JSON
        """
        url = f"{constants.GOG_API}/products/{product_id}"
        params = {
            "expand": "downloads,expanded_dlcs,description,screenshots,videos,related_products,changelog",
            "locale": "en-US"
        }
        
        self.logger.info(f"Getting product info for {product_id}")
        
        try:
            response = self.session.get(url, params=params, timeout=constants.DEFAULT_TIMEOUT)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Failed to get product info: {e}")
            return {}

    def get_build_by_id(self, product_id: str, build_id: Optional[str] = None,
                       platform: str = constants.PLATFORM_WINDOWS) -> Optional[Dict[str, Any]]:
        """
        Get specific build by ID or latest build if ID not provided.
        Automatically detects generation from builds response.
        
        Args:
            product_id: GOG product ID
            build_id: Optional build ID. If None, returns latest build.
            platform: Platform (windows, osx, linux)
            
        Returns:
            Build info dict with 'build' and 'generation' keys, or None if not found
        
        Note:
            Queries generation=2 which returns ALL builds (both V1 and V2).
            This ensures we find the build regardless of its generation.
        """
        # Query generation=2 to get ALL builds (V1 and V2)
        builds_json = self.get_all_product_builds(product_id, platform)
        
        if builds_json and "items" in builds_json:
            build_info = self._find_build_in_list(builds_json["items"], build_id)
            if build_info:
                return build_info
        
        self.logger.warning(f"No builds found for product {product_id}")
        return None

    def _find_build_in_list(self, builds: List[Dict[str, Any]], 
                           build_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Find a specific build in builds list or return latest.
        
        Args:
            builds: List of builds from API
            build_id: Optional build ID to find. Can be numeric string (index) or actual build_id
            
        Returns:
            Dict with 'build' and 'generation' keys if found, None otherwise
        """
        if not builds:
            return None
        
        # If no build_id specified, return first (latest) build
        if build_id is None:
            return {
                "build": builds[0],
                "generation": builds[0].get("generation", 2)
            }
        
        # Try to find by exact build_id match
        for build in builds:
            if build.get("build_id") == build_id:
                return {
                    "build": build,
                    "generation": build.get("generation", 2)
                }
        
        # Try to use build_id as index (legacy lgogdownloader behavior)
        try:
            index = int(build_id)
            if 0 <= index < len(builds):
                return {
                    "build": builds[index],
                    "generation": builds[index].get("generation", 2)
                }
        except (ValueError, TypeError):
            pass
        
        return None

    def detect_build_generation(self, product_id: str, build_id: Optional[str] = None,
                               platform: str = constants.PLATFORM_WINDOWS) -> int:
        """
        Detect the generation (1 or 2) of a specific build.
        
        Args:
            product_id: GOG product ID
            build_id: Optional build ID (defaults to latest)
            platform: Platform
            
        Returns:
            Generation number (1 or 2), defaults to 2 if detection fails
        """
        build_info = self.get_build_by_id(product_id, build_id, platform)
        
        if build_info:
            return build_info["generation"]
        
        self.logger.warning(f"Could not detect generation for {product_id}, defaulting to 2")
        return 2

    def get_manifest_from_build(self, product_id: str, build: Dict[str, Any],
                                platform: str = constants.PLATFORM_WINDOWS) -> Optional[Manifest]:
        """
        Get manifest from a build dict (from builds list or cache).
        
        This is ideal for frontends where the user has already selected a build
        from a list, avoiding redundant API queries.
        
        Args:
            product_id: GOG product ID
            build: Build dict from builds API (must contain 'generation' field)
            platform: Platform
            
        Returns:
            Manifest object or None if manifest fetch fails
            
        Example:
            >>> # Frontend workflow
            >>> builds = api.get_all_product_builds("1207658924")
            >>> selected_build = builds["items"][0]  # User selects from list
            >>> manifest = api.get_manifest_from_build("1207658924", selected_build)
        """
        generation = build.get("generation", 2)
        build_id = build.get("build_id")
        
        self.logger.info(f"Getting manifest from build (generation={generation}, build_id={build_id})")
        
        if generation == 1:
            # V1 manifest - use repository_id (legacy_build_id)
            repository_id = build.get("legacy_build_id")
            if not repository_id:
                self.logger.error("V1 build missing legacy_build_id (repository_id)")
                return None
            
            manifest_json = self.get_manifest_v1_direct(product_id, repository_id, platform)
            if not manifest_json:
                return None
            
            manifest = Manifest.from_json_v1(manifest_json, product_id)
            manifest.build_id = build_id
            manifest.repository_id = repository_id
            return manifest
        else:
            # V2 manifest - use link from build
            link = build.get("link")
            if not link:
                self.logger.error("V2 build missing manifest link")
                return None
            
            manifest_json = self._get_response_json(link)
            if not manifest_json:
                return None
            
            manifest = Manifest.from_json_v2(manifest_json)
            manifest.build_id = build_id
            return manifest

    def get_manifest_direct(self, product_id: str,
                          generation: Optional[int] = None,
                          repository_id: Optional[str] = None,
                          manifest_link: Optional[str] = None,
                          build_id: Optional[str] = None,
                          platform: str = constants.PLATFORM_WINDOWS) -> Optional[Manifest]:
        """
        Get manifest directly without querying builds API.
        
        Use this when you have specific build details from external sources (gogdb.org)
        or cached data and want to bypass the builds API query.
        
        NEW: Set generation=None to auto-detect by trying both V1 and V2!
        
        Args:
            product_id: GOG product ID
            generation: Generation (1, 2, or None for auto-detect)
            repository_id: Build identifier (V1 timestamp or V2 hash)
            manifest_link: Optional V2 manifest URL (if known)
            build_id: Optional - for tracking purposes
            platform: Platform (used for V1 only)
            
        Returns:
            Manifest object or None if fetch fails
            
        Example (V1 from gogdb.org):
            >>> # gogdb.org shows: Repository timestamp: 24085618
            >>> manifest = api.get_manifest_direct(
            ...     product_id="1207658924",
            ...     generation=1,
            ...     repository_id="24085618",
            ...     platform="osx"
            ... )
            
        Example (V2 with hash):
            >>> manifest = api.get_manifest_direct(
            ...     product_id="1207658924",
            ...     generation=2,
            ...     repository_id="e518c17d90805e8e3998a35fac8b8505"
            ... )
            
        Example (Auto-detect):
            >>> # Don't know if it's V1 or V2? Let it figure it out!
            >>> manifest = api.get_manifest_direct(
            ...     product_id="1207658924",
            ...     repository_id="37794096",  # Could be V1 timestamp or V2 hash
            ...     platform="windows"
            ... )
            >>> print(f"Auto-detected V{manifest.generation}")
        """
        # Auto-detect generation by trying both V1 and V2
        if generation is None:
            if not repository_id:
                raise ValueError("repository_id required for auto-detection")
            
            self.logger.info(f"Auto-detecting generation for {product_id}/{repository_id}")
            
            # Try V1 first (timestamp in path)
            self.logger.debug(f"Trying V1: repository.json at {repository_id}")
            manifest_json = self.get_manifest_v1_direct(product_id, repository_id, platform)
            
            if manifest_json:
                self.logger.info(f"Auto-detected V1 manifest")
                manifest = Manifest.from_json_v1(manifest_json, product_id)
                manifest.build_id = build_id
                manifest.repository_id = repository_id
                manifest.generation = 1
                return manifest
            
            # Try V2 (hash with 2-level prefix)
            self.logger.debug(f"V1 failed, trying V2: depot hash {repository_id}")
            depot_url = self.get_depot_url(repository_id)
            
            try:
                manifest_json = self._get_response_json(depot_url)
                if manifest_json:
                    self.logger.info(f"Auto-detected V2 manifest")
                    manifest = Manifest.from_json_v2(manifest_json)
                    manifest.build_id = build_id
                    manifest.generation = 2
                    return manifest
            except Exception as e:
                self.logger.debug(f"V2 also failed: {e}")
            
            self.logger.error(f"Could not auto-detect generation - both V1 and V2 failed")
            return None
        
        if generation == 1:
            if not repository_id:
                raise ValueError("repository_id required for V1 manifests")
            
            self.logger.info(f"Getting V1 manifest directly: {product_id}/{repository_id}")
            manifest_json = self.get_manifest_v1_direct(product_id, repository_id, platform)
            
            if not manifest_json:
                return None
            
            manifest = Manifest.from_json_v1(manifest_json, product_id)
            manifest.build_id = build_id
            manifest.repository_id = repository_id
            return manifest
        else:
            # V2 - need either manifest_link or repository_id (depot hash)
            if manifest_link:
                self.logger.info(f"Getting V2 manifest directly: {manifest_link}")
                manifest_json = self._get_response_json(manifest_link)
            elif repository_id:
                # repository_id is the depot hash for V2
                depot_url = self.get_depot_url(repository_id)
                self.logger.info(f"Getting V2 depot directly: {repository_id}")
                manifest_json = self._get_response_json(depot_url)
            else:
                raise ValueError("Either manifest_link or repository_id required for V2 manifests")
            
            if not manifest_json:
                return None
            
            manifest = Manifest.from_json_v2(manifest_json)
            manifest.build_id = build_id
            return manifest

    def get_manifest(self, product_id: str, build_id: Optional[str] = None,
                    platform: str = constants.PLATFORM_WINDOWS) -> Optional[Manifest]:
        """
        Get manifest for a product build, automatically detecting generation.
        
        This method queries the builds API to find the build and detect its generation.
        For better performance in frontends, consider using get_manifest_from_build()
        after letting the user select from a builds list.
        
        Args:
            product_id: GOG product ID
            build_id: Optional build ID (defaults to latest)
            platform: Platform
            
        Returns:
            Manifest object or None if not found
        """
        build_info = self.get_build_by_id(product_id, build_id, platform)
        
        if not build_info:
            return None
        
        # Use get_manifest_from_build for consistency
        return self.get_manifest_from_build(product_id, build_info["build"], platform)

    def get_owned_games(self) -> List[int]:
        """
        Get list of owned game IDs from user's GOG library.
        
        Returns:
            List of product IDs that the authenticated user owns
            
        Example:
            >>> api = GalaxyAPI(auth_manager)
            >>> game_ids = api.get_owned_games()
            >>> print(f"You own {len(game_ids)} games")
            >>> # [1207658691, 1207658713, 1207658805, ...]
        """
        self.logger.info("Getting owned games list")
        
        try:
            response = self._get_response_json(constants.USER_GAMES_URL)
            
            if "owned" in response:
                game_ids = response["owned"]
                self.logger.info(f"Found {len(game_ids)} owned games")
                return game_ids
            else:
                self.logger.warning("No 'owned' field in user games response")
                return []
                
        except Exception as e:
            self.logger.error(f"Failed to get owned games: {e}")
            return []

    def get_game_details(self, game_id: int) -> Dict[str, Any]:
        """
        Get detailed information about a game from user's library.
        
        This returns information about downloads, extras, DLCs, etc.
        Useful for frontends to display game information and download options.
        
        Args:
            game_id: GOG product ID from owned games list
            
        Returns:
            Dictionary containing:
            - title: Game title
            - backgroundImage: Background image URL
            - downloads: Available downloads per language/platform
            - extras: Bonus content (manuals, wallpapers, etc.)
            - dlcs: DLC information
            - tags: Game tags
            - releaseTimestamp: Release date
            - forumLink: Forum URL
            - changelog: Changelog if available
            
        Example:
            >>> details = api.get_game_details(1207658924)
            >>> print(details["title"])
            >>> # "Unreal Tournament 2004 Editor's Choice Edition"
            >>> 
            >>> for lang, platforms in details["downloads"]:
            ...     print(f"Language: {lang}")
            ...     for platform, files in platforms.items():
            ...         print(f"  Platform: {platform} ({len(files)} files)")
        """
        url = constants.GAME_DETAILS_URL.format(game_id=game_id)
        self.logger.info(f"Getting game details for {game_id}")
        
        try:
            return self._get_response_json(url)
        except Exception as e:
            self.logger.error(f"Failed to get game details: {e}")
            return {}

    def get_owned_games_with_details(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get owned games list with full details for each game.
        
        This is a convenience method for frontends that want to display
        a complete game library with all information.
        
        Args:
            limit: Optional limit on number of games to fetch details for
                  (useful for testing or pagination)
            
        Returns:
            List of game detail dictionaries
            
        Example:
            >>> # Get first 10 games with details
            >>> games = api.get_owned_games_with_details(limit=10)
            >>> for game in games:
            ...     print(f"{game['title']} - {len(game['downloads'])} downloads")
        """
        game_ids = self.get_owned_games()
        
        if limit:
            game_ids = game_ids[:limit]
        
        games_with_details = []
        for game_id in game_ids:
            details = self.get_game_details(game_id)
            if details:  # Only add if we got valid details
                details["id"] = game_id  # Add ID for reference
                games_with_details.append(details)
        
        self.logger.info(f"Retrieved details for {len(games_with_details)} games")
        return games_with_details

        self.logger.info(f"Retrieved details for {len(games_with_details)} games")
        return games_with_details

