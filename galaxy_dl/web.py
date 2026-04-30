"""
GOG Web Downloader

Simple downloader for non-Galaxy files (offline installers, extras, patches, language packs).
These files are regular HTTP downloads, not depot-based Galaxy CDN content.

Designed for complete GOG archival alongside the main galaxy_dl library.
"""

import os
import hashlib
import logging
import time
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional, Callable
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from galaxy_dl import constants
from galaxy_dl.auth import AuthManager
from galaxy_dl import utils


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
    
    def __init__(self, auth_manager: AuthManager, max_workers: int = 8):
        """
        Initialize extras downloader.
        
        Args:
            auth_manager: AuthManager with valid credentials
            max_workers: Maximum number of concurrent download threads (default: 8)
        """
        self.auth_manager = auth_manager
        self.max_workers = max_workers
        self.logger = logging.getLogger("galaxy_dl.extras")
        
        # Setup session
        self.session = requests.Session()
        self.session.auth = lambda r: r  # Prevent .netrc credentials from being injected
        self.session.headers.update({
            "User-Agent": constants.USER_AGENT.format(version="0.1.0")
        })
        
        # Set authorization if authenticated
        auth_header = self.auth_manager.get_auth_header()
        if auth_header:
            self.session.headers["Authorization"] = auth_header
    
    def get_downlink_info(self, manual_url: str) -> Dict[str, Any]:
        """
        Get download info from manualUrl.
        
        NOTE: GOG API changed - manualUrl now directly serves the file
        (with embedded auth token), not JSON with download info.
        
        Args:
            manual_url: The manualUrl from game details file entry
            
        Returns:
            Dictionary with:
            - downlink: Direct download URL (the resolved manualUrl)
            - checksum: Checksum XML URL (download URL + '.xml')
            
        Example:
            >>> downlink_info = downloader.get_downlink_info(file_entry['manualUrl'])
            >>> download_url = downlink_info['downlink']
            >>> checksum_url = downlink_info.get('checksum', '')
        """
        self._update_auth_header()
        
        # Convert relative URLs to absolute
        if manual_url.startswith('/'):
            manual_url = f"{constants.GOG_EMBED}{manual_url}"
        
        try:
            # Make HEAD request to get final URL (handle redirects)
            # This avoids downloading the entire file just to get the URL
            response = self.session.head(manual_url, timeout=constants.DEFAULT_TIMEOUT, allow_redirects=True)
            response.raise_for_status()
            
            # The final URL after redirects is the actual download URL
            download_url = response.url
            
            # Checksum XML is typically at download_url + '.xml'
            checksum_url = f"{download_url}.xml"
            
            self.logger.debug(f"Got download URL from {manual_url}")
            
            # Check if checksum XML exists
            has_checksum = False
            try:
                checksum_resp = self.session.head(checksum_url, timeout=5)
                has_checksum = checksum_resp.status_code == 200
            except Exception:
                pass
            
            if has_checksum:
                self.logger.info(f"✓ GOG provides checksum XML for this file")
            else:
                self.logger.info(f"✗ No checksum XML available from GOG")
                checksum_url = ""
            
            return {
                "downlink": download_url,
                "checksum": checksum_url
            }
            
        except Exception as e:
            self.logger.error(f"Failed to get download info from {manual_url}: {e}")
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
            
            # Parse XML - the <file> element is the root
            root = ET.fromstring(response.content)
            
            # Verify the root is a <file> element
            if root.tag != "file":
                self.logger.warning(f"Unexpected XML root element: {root.tag}")
                return {}
            
            info = {
                "name": root.get("name", ""),
                "md5": root.get("md5", ""),
                "total_size": int(root.get("total_size", 0)),
                "chunks": []
            }
            
            # Extract chunk info (GOG uses <chunk> children directly under <file>)
            for chunk_elem in root.findall("chunk"):
                chunk_info = {
                    "id": chunk_elem.get("id", ""),
                    "from": int(chunk_elem.get("from", 0)),
                    "to": int(chunk_elem.get("to", 0)),
                    "method": chunk_elem.get("method", "md5"),
                    "hash": chunk_elem.text.strip() if chunk_elem.text else ""
                }
                info["chunks"].append(chunk_info)
            
            self.logger.debug(f"Parsed checksum info: {info['name']}")
            return info
            
        except Exception as e:
            self.logger.warning(f"Failed to parse checksum XML from {checksum_url}: {e}")
            return {}
    
    def save_checksum_xml(self, checksum_info: Dict[str, Any], xml_path: str) -> None:
        """
        Save checksum info to XML file.
        
        Creates a GOG-compatible checksum XML file for verification.
        Format matches GOG's XML structure.
        
        Args:
            checksum_info: Dict with 'name', 'md5', 'total_size', 'chunks'
            xml_path: Path to save XML file
        """
        if not checksum_info:
            return
        
        # Create XML structure
        file_elem = ET.Element("file")
        file_elem.set("name", checksum_info.get("name", ""))
        file_elem.set("md5", checksum_info.get("md5", ""))
        file_elem.set("chunks", str(len(checksum_info.get("chunks", []))))
        file_elem.set("total_size", str(checksum_info.get("total_size", 0)))
        file_elem.set("available", "1")
        file_elem.set("notavailablemsg", "")
        file_elem.set("timestamp", checksum_info.get("timestamp", ""))
        
        # Add chunks
        for chunk in checksum_info.get("chunks", []):
            chunk_elem = ET.SubElement(file_elem, "chunk")
            chunk_elem.set("id", str(chunk.get("id", "")))
            chunk_elem.set("from", str(chunk.get("from", 0)))
            chunk_elem.set("to", str(chunk.get("to", 0)))
            chunk_elem.set("method", chunk.get("method", "md5"))
            chunk_elem.text = chunk.get("hash", "")
        
        # Write to file
        tree = ET.ElementTree(file_elem)
        ET.indent(tree, space="    ")
        tree.write(xml_path, encoding="utf-8", xml_declaration=True)
        self.logger.debug(f"Saved checksum XML to {xml_path}")
    
    def _supports_range_requests(self, url: str) -> bool:
        """Check if server supports HTTP range requests."""
        try:
            response = self.session.head(url, timeout=constants.DEFAULT_TIMEOUT)
            accept_ranges = response.headers.get('Accept-Ranges', '')
            return accept_ranges.lower() == 'bytes'
        except Exception as e:
            self.logger.debug(f"Range support check failed: {e}")
            return False
    
    def _download_range_chunk(self, url: str, offset: int, size: int) -> bytes:
        """Download a single range chunk."""
        range_header = utils.get_range_header(offset, size)
        
        for attempt in range(constants.DEFAULT_RETRIES):
            try:
                response = self.session.get(
                    url,
                    headers={'Range': range_header},
                    timeout=constants.DEFAULT_TIMEOUT
                )
                response.raise_for_status()
                
                data = response.content
                
                if len(data) != size:
                    self.logger.warning(f"Range chunk size mismatch: expected {size}, got {len(data)}")
                    if attempt < constants.DEFAULT_RETRIES - 1:
                        continue
                
                return data
                
            except requests.RequestException as e:
                if attempt == constants.DEFAULT_RETRIES - 1:
                    raise RuntimeError(f"Failed to download range chunk: {e}")
                self.logger.debug(f"Retry {attempt + 1}/{constants.DEFAULT_RETRIES}")
        
        raise RuntimeError("Failed to download range chunk")
    
    def download_file(
        self,
        downlink_url: str,
        output_path: str,
        checksum_info: Optional[Dict[str, Any]] = None,
        download_chunk_size: int = 10 * 1024 * 1024,  # 10 MB download buffer (matches verification chunk size)
        progress_callback: Optional[Callable[[int, int], None]] = None,
        use_parallel: bool = True  # Enable parallel downloads for large files
    ) -> str:
        """
        Download a file with chunk-by-chunk verification.
        
        GOG uses 10 MiB (10485760 bytes) chunks for verification. This method
        verifies each chunk during download for early failure detection.
        
        For large files (>50 MB), automatically uses parallel range-based downloads
        if the server supports it, dramatically improving speed.
        
        Args:
            downlink_url: Direct download URL
            output_path: Where to save the file
            checksum_info: Checksum info dict from get_checksum_info() or None
            download_chunk_size: HTTP download buffer size (default: 10 MB)
            progress_callback: Optional callback(downloaded_bytes, total_bytes)
            use_parallel: Enable parallel range downloads for large files (default: True)
            
        Returns:
            Path to downloaded file
            
        Raises:
            RuntimeError: If download or verification fails
        """
        self._update_auth_header()
        
        # GOG's chunk size for verification (10 MiB)
        VERIFICATION_CHUNK_SIZE = 10 * 1024 * 1024  # 10485760 bytes
        PARALLEL_THRESHOLD = 50 * 1024 * 1024  # 50 MB - use parallel for files larger than this
        
        # Create output directory
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        
        self.logger.info(f"Downloading to {output_path}")
        
        try:
            # Get file size first
            response = self.session.head(downlink_url, timeout=constants.DEFAULT_TIMEOUT, allow_redirects=True)
            response.raise_for_status()
            total_size = int(response.headers.get('content-length', 0))
            
            # Decide whether to use parallel downloads
            supports_ranges = use_parallel and total_size > PARALLEL_THRESHOLD and self._supports_range_requests(downlink_url)
            
            if supports_ranges:
                self.logger.info(f"Using parallel download ({self.max_workers} workers) for {total_size:,} bytes")
                return self._download_file_parallel(
                    downlink_url, output_path, total_size, checksum_info, progress_callback
                )
            
            # Fall back to sequential streaming download
            self.logger.info(f"Using sequential download for {total_size:,} bytes")
            response = self.session.get(downlink_url, stream=True, timeout=constants.DEFAULT_TIMEOUT)
            response.raise_for_status()
            downloaded = 0
            
            # Initialize hashers
            file_md5 = hashlib.md5()  # Overall file MD5
            chunk_md5 = hashlib.md5()  # Current verification chunk MD5
            chunk_start = 0
            chunk_index = 0
            chunks_verified = []
            
            # Get expected chunks if available
            expected_chunks = checksum_info.get("chunks", []) if checksum_info else []
            expected_file_md5 = checksum_info.get("md5") if checksum_info else None
            
            with open(output_path, 'wb') as f:
                for data in response.iter_content(chunk_size=download_chunk_size):
                    if not data:
                        continue
                    
                    f.write(data)
                    downloaded += len(data)
                    file_md5.update(data)
                    chunk_md5.update(data)
                    
                    # Check if we've completed a 10 MiB verification chunk
                    bytes_in_chunk = downloaded - chunk_start
                    if bytes_in_chunk >= VERIFICATION_CHUNK_SIZE or downloaded >= total_size:
                        chunk_hash = chunk_md5.hexdigest()
                        chunk_to = downloaded - 1
                        
                        # Verify against expected chunk if available
                        if chunk_index < len(expected_chunks):
                            expected_chunk = expected_chunks[chunk_index]
                            expected_hash = expected_chunk.get("hash", "")
                            
                            if expected_hash and chunk_hash.lower() != expected_hash.lower():
                                raise RuntimeError(
                                    f"Chunk {chunk_index} verification failed!\n"
                                    f"  Range: {chunk_start}-{chunk_to}\n"
                                    f"  Expected: {expected_hash}\n"
                                    f"  Got:      {chunk_hash}"
                                )
                            self.logger.debug(f"Chunk {chunk_index} verified: {chunk_hash}")
                        
                        # Store chunk info for XML generation
                        chunks_verified.append({
                            "id": str(chunk_index),
                            "from": chunk_start,
                            "to": chunk_to,
                            "method": "md5",
                            "hash": chunk_hash
                        })
                        
                        # Reset for next chunk
                        chunk_md5 = hashlib.md5()
                        chunk_start = downloaded
                        chunk_index += 1
                    
                    if progress_callback:
                        progress_callback(downloaded, total_size)
            
            # Verify overall file MD5
            actual_file_md5 = file_md5.hexdigest()
            if expected_file_md5:
                if actual_file_md5.lower() != expected_file_md5.lower():
                    raise RuntimeError(
                        f"File MD5 verification failed!\n"
                        f"Expected: {expected_file_md5}\n"
                        f"Got:      {actual_file_md5}"
                    )
                self.logger.info(f"File MD5 verified: {actual_file_md5}")
            else:
                self.logger.info(f"Generated file MD5: {actual_file_md5}")
            
            # Save or generate checksum XML
            xml_path = output_path + ".xml"
            if checksum_info:
                # Save GOG-provided checksums
                self.save_checksum_xml(checksum_info, xml_path)
                self.logger.info(f"Saved GOG checksum XML to {xml_path}")
            else:
                # Generate our own checksum XML
                generated_info = {
                    "name": os.path.basename(output_path),
                    "md5": actual_file_md5,
                    "total_size": downloaded,
                    "chunks": chunks_verified,
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                self.save_checksum_xml(generated_info, xml_path)
                self.logger.info(f"Generated checksum XML: {xml_path}")
            
            self.logger.info(f"Downloaded {downloaded:,} bytes to {output_path}")
            return output_path
            
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            # Clean up partial download
            if os.path.exists(output_path):
                os.remove(output_path)
            raise
    
    def _download_file_parallel(
        self,
        downlink_url: str,
        output_path: str,
        total_size: int,
        checksum_info: Optional[Dict[str, Any]],
        progress_callback: Optional[Callable[[int, int], None]]
    ) -> str:
        """Parallel range-based download for large files."""
        VERIFICATION_CHUNK_SIZE = 10 * 1024 * 1024  # 10 MiB
        
        # Calculate chunk ranges
        chunk_size = VERIFICATION_CHUNK_SIZE
        num_chunks = (total_size + chunk_size - 1) // chunk_size
        
        self.logger.info(f"Downloading {num_chunks} chunks in parallel...")
        
        # Create output file (sparse/pre-allocated)
        with open(output_path, 'wb') as f:
            f.seek(total_size - 1)
            f.write(b'\0')
        
        # Download chunks in parallel
        downloaded_bytes = 0
        downloaded_lock = []  # Will hold [current_bytes]
        downloaded_lock.append(0)
        import threading
        lock = threading.Lock()
        
        chunks_verified = []
        file_md5_data = [b''] * num_chunks  # Store data in order for final MD5
        
        def download_chunk_task(chunk_index: int):
            """Download a single chunk."""
            chunk_offset = chunk_index * chunk_size
            chunk_size_actual = min(chunk_size, total_size - chunk_offset)
            
            # Download the chunk
            chunk_data = self._download_range_chunk(downlink_url, chunk_offset, chunk_size_actual)
            
            # Compute chunk MD5
            chunk_hash = hashlib.md5(chunk_data).hexdigest()
            
            # Verify against expected chunk if available
            expected_chunks = checksum_info.get("chunks", []) if checksum_info else []
            if chunk_index < len(expected_chunks):
                expected_hash = expected_chunks[chunk_index].get("hash", "")
                if expected_hash and chunk_hash.lower() != expected_hash.lower():
                    raise RuntimeError(
                        f"Chunk {chunk_index} verification failed!\n"
                        f"  Expected: {expected_hash}\n"
                        f"  Got:      {chunk_hash}"
                    )
            
            # Write chunk to file at correct offset
            with open(output_path, 'r+b') as f:
                f.seek(chunk_offset)
                f.write(chunk_data)
            
            # Store for XML generation
            with lock:
                chunks_verified.append({
                    "id": str(chunk_index),
                    "from": chunk_offset,
                    "to": chunk_offset + chunk_size_actual - 1,
                    "method": "md5",
                    "hash": chunk_hash
                })
                file_md5_data[chunk_index] = chunk_data
                downloaded_lock[0] += len(chunk_data)
                
                if progress_callback:
                    progress_callback(downloaded_lock[0], total_size)
            
            self.logger.debug(f"Chunk {chunk_index + 1}/{num_chunks} complete: {chunk_hash}")
        
        # Download all chunks in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(download_chunk_task, i) for i in range(num_chunks)]
            
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    self.logger.error(f"Chunk download failed: {e}")
                    raise
        
        # Calculate overall file MD5
        file_md5 = hashlib.md5()
        for chunk_data in file_md5_data:
            file_md5.update(chunk_data)
        actual_file_md5 = file_md5.hexdigest()
        
        # Verify overall MD5
        expected_file_md5 = checksum_info.get("md5") if checksum_info else None
        if expected_file_md5:
            if actual_file_md5.lower() != expected_file_md5.lower():
                raise RuntimeError(
                    f"File MD5 verification failed!\n"
                    f"Expected: {expected_file_md5}\n"
                    f"Got:      {actual_file_md5}"
                )
            self.logger.info(f"File MD5 verified: {actual_file_md5}")
        else:
            self.logger.info(f"Generated file MD5: {actual_file_md5}")
        
        # Sort chunks by id for XML
        chunks_verified.sort(key=lambda x: int(x["id"]))
        
        # Save or generate checksum XML
        xml_path = output_path + ".xml"
        if checksum_info:
            self.save_checksum_xml(checksum_info, xml_path)
            self.logger.info(f"Saved GOG checksum XML to {xml_path}")
        else:
            generated_info = {
                "name": os.path.basename(output_path),
                "md5": actual_file_md5,
                "total_size": total_size,
                "chunks": chunks_verified,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self.save_checksum_xml(generated_info, xml_path)
            self.logger.info(f"Generated checksum XML: {xml_path}")
        
        self.logger.info(f"Downloaded {total_size:,} bytes to {output_path}")
        return output_path
    
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
        
        # Get checksum info if available
        checksum_info = None
        if checksum_url:
            self.logger.info(f"✓ GOG provides checksum XML - downloading and verifying")
            checksum_info = self.get_checksum_info(checksum_url)
            if checksum_info.get("md5"):
                self.logger.info(f"  Expected MD5: {checksum_info['md5']}")
                self.logger.info(f"  Chunks: {len(checksum_info.get('chunks', []))}")
            else:
                self.logger.warning(f"  Checksum XML exists but no MD5 found")
                checksum_info = None  # Don't use incomplete checksum info
        else:
            self.logger.info(f"✗ No checksum XML from GOG - will generate our own")
        
        # Download with chunk verification and XML saving
        return self.download_file(
            download_url,
            output_path,
            checksum_info=checksum_info if verify_checksum else None,
            progress_callback=progress_callback
        )
    
    def _update_auth_header(self) -> None:
        """Update authorization header with fresh token if needed."""
        auth_header = self.auth_manager.get_auth_header()
        if auth_header:
            self.session.headers["Authorization"] = auth_header
