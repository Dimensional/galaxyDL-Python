"""
Galaxy API Client
Based on heroic-gogdl api.py and lgogdownloader galaxyapi.cpp
Provides access to GOG Galaxy content-system API
"""

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
                          generation: str = constants.GENERATION_2) -> Dict[str, Any]:
        """
        Get available builds for a product.
        
        Args:
            product_id: GOG product ID
            platform: Platform (windows, osx, linux)
            generation: Generation version (1 or 2)
            
        Returns:
            JSON data containing builds information
        """
        url = constants.BUILDS_URL.format(
            product_id=product_id,
            platform=platform,
            generation=generation
        )
        
        self.logger.info(f"Getting builds for product {product_id}")
        return self._get_response_json(url)

    def get_manifest_v1(self, product_id: str, build_id: str, 
                       manifest_id: str = "repository",
                       platform: str = constants.PLATFORM_WINDOWS) -> Dict[str, Any]:
        """
        Get v1 manifest data.
        
        Args:
            product_id: GOG product ID
            build_id: Build ID
            manifest_id: Manifest ID (default: "repository")
            platform: Platform
            
        Returns:
            V1 manifest JSON data
        """
        url = constants.MANIFEST_V1_URL.format(
            product_id=product_id,
            platform=platform,
            build_id=build_id,
            manifest_id=manifest_id
        )
        
        self.logger.info(f"Getting v1 manifest for {product_id}/{build_id}")
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
                       generation: str = constants.GENERATION_2) -> List[str]:
        """
        Get secure download links for a product.
        
        Args:
            product_id: GOG product ID
            path: Path parameter (default: "/")
            generation: Generation version
            
        Returns:
            List of CDN URLs
        """
        # Check cache
        cache_key = f"{product_id}:{path}:{generation}"
        if cache_key in self._secure_link_cache:
            return self._secure_link_cache[cache_key]
        
        url = constants.SECURE_LINK_URL.format(
            product_id=product_id,
            generation=generation,
            path=quote(path)
        )
        
        self.logger.info(f"Getting secure link for product {product_id}")
        response = self._get_response_json(url)
        
        if "urls" in response:
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


import json  # Move import to top in real implementation

