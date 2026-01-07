"""
GOG Web Downloader

Simple downloader for non-Galaxy files (offline installers, extras, patches, language packs).
These files are regular HTTP downloads, not depot-based Galaxy CDN content.

Designed for complete GOG archival alongside the main galaxy_dl library.
"""

import os
import hashlib
import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path

import requests

from galaxy_dl import constants
from galaxy_dl.auth import AuthManager


class WebDownloader:
    """
    Downloader for GOG installers, extras, and other non-Galaxy files.
    
    These files use simple HTTP downloads (not Galaxy depot chunks) and include:
    - Offline installers (.exe, .sh, .pkg, .dmg)
    - Extras/bonus content (manuals, wallpapers, soundtracks)
    - Patches (non-Galaxy patches)
    - Language packs
    
    Each file entry from get_game_details() contains:
    - manualUrl: Link to get downlink JSON with actual download URL
    - name: File description
    - type: File type (installer, extra, patch, etc.)
    - size: File size in bytes
    """
    
    def __init__(self, auth_manager: AuthManager):
        """
        Initialize extras downloader.
        
        Args:
            auth_manager: AuthManager with valid credentials
        """
        self.auth_manager = auth_manager
        self.logger = logging.getLogger("galaxy_dl.extras")
        
        # Setup session
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": constants.USER_AGENT.format(version="0.1.0")
        })
        
        # Set authorization if authenticated
        auth_header = self.auth_manager.get_auth_header()
        if auth_header:
            self.session.headers["Authorization"] = auth_header
    
    def get_downlink_info(self, manual_url: str) -> Dict[str, Any]:
        """
        Get downlink JSON from manualUrl.
        
        The manualUrl (from game details) returns a JSON with:
        - downlink: Actual CDN download URL
        - checksum: Optional XML file URL for file verification
        
        Args:
            manual_url: The manualUrl from game details file entry
            
        Returns:
            Dictionary with:
            - downlink: Direct download URL
            - checksum: Checksum XML URL (may be empty)
            
        Example:
            >>> downlink_info = downloader.get_downlink_info(file_entry['manualUrl'])
            >>> download_url = downlink_info['downlink']
            >>> checksum_url = downlink_info.get('checksum', '')
        """
        self._update_auth_header()
        
        try:
            response = self.session.get(manual_url, timeout=constants.DEFAULT_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            
            if "downlink" not in data:
                raise ValueError("Invalid downlink JSON: missing 'downlink' field")
            
            self.logger.debug(f"Got downlink info from {manual_url}")
            return {
                "downlink": data["downlink"],
                "checksum": data.get("checksum", "")
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get downlink info from {manual_url}: {e}")
            raise
    
    def get_checksum_info(self, checksum_url: str) -> Dict[str, str]:
        """
        Parse checksum XML file to get file verification info.
        
        GOG provides XML files with MD5 checksums for verification.
        Format: <file name="..." md5="..." ... />
        
        Args:
            checksum_url: URL to checksum XML file
            
        Returns:
            Dictionary with file info:
            - name: Filename
            - md5: MD5 hash
            - chunks: List of chunk info if file is split
            
        Example:
            >>> if checksum_url:
            ...     checksum_info = downloader.get_checksum_info(checksum_url)
            ...     expected_md5 = checksum_info['md5']
        """
        if not checksum_url:
            return {}
        
        try:
            response = self.session.get(checksum_url, timeout=constants.DEFAULT_TIMEOUT)
            response.raise_for_status()
            
            # Parse XML
            root = ET.fromstring(response.content)
            
            # Extract file info
            file_elem = root.find("file")
            if file_elem is None:
                self.logger.warning("No <file> element in checksum XML")
                return {}
            
            info = {
                "name": file_elem.get("name", ""),
                "md5": file_elem.get("md5", ""),
                "chunks": []
            }
            
            # Check for chunk info (for split files)
            chunks_elem = file_elem.find("chunks")
            if chunks_elem is not None:
                for chunk_elem in chunks_elem.findall("chunk"):
                    chunk_info = {
                        "id": chunk_elem.get("id", ""),
                        "from": int(chunk_elem.get("from", 0)),
                        "to": int(chunk_elem.get("to", 0)),
                        "method": chunk_elem.get("method", "md5"),
                        "hash": chunk_elem.text or ""
                    }
                    info["chunks"].append(chunk_info)
            
            self.logger.debug(f"Parsed checksum info: {info['name']}")
            return info
            
        except Exception as e:
            self.logger.warning(f"Failed to parse checksum XML from {checksum_url}: {e}")
            return {}
    
    def download_file(
        self,
        downlink_url: str,
        output_path: str,
        expected_md5: Optional[str] = None,
        chunk_size: int = 50 * 1024 * 1024,  # 50 MB chunks
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> str:
        """
        Download a file from direct URL.
        
        Args:
            downlink_url: Direct download URL from downlink JSON
            output_path: Where to save the file
            expected_md5: Optional MD5 hash for verification
            chunk_size: Download chunk size in bytes (default: 50 MB)
            progress_callback: Optional callback(downloaded_bytes, total_bytes)
            
        Returns:
            Path to downloaded file
            
        Raises:
            RuntimeError: If download fails or MD5 verification fails
            
        Example:
            >>> downloader.download_file(
            ...     downlink_url="https://...",
            ...     output_path="./downloads/installer.exe",
            ...     expected_md5="abc123..."
            ... )
        """
        self._update_auth_header()
        
        # Create output directory
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        
        self.logger.info(f"Downloading to {output_path}")
        
        try:
            # Stream download
            response = self.session.get(downlink_url, stream=True, timeout=constants.DEFAULT_TIMEOUT)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            # Initialize MD5 hasher if verification requested
            md5_hasher = hashlib.md5() if expected_md5 else None
            
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if md5_hasher:
                            md5_hasher.update(chunk)
                        
                        if progress_callback:
                            progress_callback(downloaded, total_size)
            
            # Verify MD5 if provided
            if expected_md5 and md5_hasher:
                actual_md5 = md5_hasher.hexdigest()
                if actual_md5.lower() != expected_md5.lower():
                    raise RuntimeError(
                        f"MD5 verification failed!\n"
                        f"Expected: {expected_md5}\n"
                        f"Got:      {actual_md5}"
                    )
                self.logger.info(f"MD5 verification passed: {actual_md5}")
            
            self.logger.info(f"Downloaded {downloaded:,} bytes to {output_path}")
            return output_path
            
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            # Clean up partial download
            if os.path.exists(output_path):
                os.remove(output_path)
            raise
    
    def download_from_game_details(
        self,
        file_entry: Dict[str, Any],
        output_dir: str,
        verify_checksum: bool = True,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> str:
        """
        Download a file from a game details entry.
        
        This is a convenience method that handles the complete flow:
        1. Get downlink JSON from manualUrl
        2. Get checksum info if available
        3. Download file with verification
        
        Args:
            file_entry: File entry from game details (installer, extra, etc.)
                Must have 'manualUrl' and 'name' fields
            output_dir: Directory to save file
            verify_checksum: Whether to verify MD5 checksum (default: True)
            progress_callback: Optional progress callback
            
        Returns:
            Path to downloaded file
            
        Example:
            >>> # From get_game_details() response
            >>> details = api.get_game_details(game_id)
            >>> 
            >>> # Download an installer
            >>> for lang, platforms in details.get('downloads', []):
            ...     for platform, files in platforms.items():
            ...         for file_entry in files:
            ...             path = downloader.download_from_game_details(
            ...                 file_entry,
            ...                 output_dir="./downloads/installers"
            ...             )
            >>> 
            >>> # Download extras
            >>> for extra in details.get('extras', []):
            ...     path = downloader.download_from_game_details(
            ...         extra,
            ...         output_dir="./downloads/extras"
            ...     )
        """
        if "manualUrl" not in file_entry:
            raise ValueError("file_entry must have 'manualUrl' field")
        
        # Get downlink info
        downlink_info = self.get_downlink_info(file_entry["manualUrl"])
        download_url = downlink_info["downlink"]
        checksum_url = downlink_info.get("checksum", "")
        
        # Parse filename from URL or use name from entry
        filename = file_entry.get("name", "unknown_file")
        # Try to extract actual filename from URL
        if "/" in download_url:
            url_filename = download_url.split("/")[-1].split("?")[0]
            if url_filename:
                filename = url_filename
        
        output_path = os.path.join(output_dir, filename)
        
        # Get checksum if available and verification requested
        expected_md5 = None
        if verify_checksum and checksum_url:
            checksum_info = self.get_checksum_info(checksum_url)
            expected_md5 = checksum_info.get("md5")
            if expected_md5:
                self.logger.info(f"Will verify MD5: {expected_md5}")
        
        # Download
        return self.download_file(
            download_url,
            output_path,
            expected_md5=expected_md5,
            progress_callback=progress_callback
        )
    
    def _update_auth_header(self) -> None:
        """Update authorization header with fresh token if needed."""
        auth_header = self.auth_manager.get_auth_header()
        if auth_header:
            self.session.headers["Authorization"] = auth_header
