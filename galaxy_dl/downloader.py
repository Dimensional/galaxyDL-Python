"""
Unified Galaxy Downloader
Handles both V1 (range-based main.bin) and V2 (chunk-based) downloads
Based on heroic-gogdl task_executor approach with multi-threading for both versions
"""

import hashlib
import logging
import os
import zlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Callable, Dict, Tuple

import requests

from galaxy_dl import constants, utils
from galaxy_dl.api import GalaxyAPI
from galaxy_dl.models import DepotItem, DepotItemChunk


class DownloadError(Exception):
    """Exception raised when download fails."""
    pass


@dataclass
class DownloadTask:
    """Base download task."""
    task_id: str
    url: str
    output_path: str


@dataclass
class ChunkDownloadTask(DownloadTask):
    """V2 chunk download task."""
    chunk: DepotItemChunk
    chunk_index: int
    verify_hash: bool = True


@dataclass
class RangeDownloadTask(DownloadTask):
    """V1 range download task."""
    offset: int
    size: int
    chunk_index: int


class GalaxyDownloader:
    """
    Unified downloader for both V1 and V2 Galaxy manifests.
    
    V1: Downloads main.bin using HTTP range requests (multi-threaded)
    V2: Downloads individual chunks (multi-threaded)
    
    Both approaches use ThreadPoolExecutor for parallel downloads.
    """

    def __init__(self, api: GalaxyAPI, max_workers: int = 4):
        """
        Initialize the unified downloader.
        
        Args:
            api: GalaxyAPI instance for getting secure links
            max_workers: Maximum number of concurrent download threads
        """
        self.api = api
        self.max_workers = max_workers
        self.logger = logging.getLogger("galaxy_dl.downloader")
        
        # Create a session for downloads
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": constants.USER_AGENT.format(version="0.1.0")
        })

    def download_item(self, item: DepotItem, output_dir: str,
                     cdn_urls: Optional[List[str]] = None,
                     verify_hash: bool = True,
                     progress_callback: Optional[Callable[[int, int], None]] = None) -> str:
        """
        Download a depot item (auto-detects V1 vs V2).
        
        Args:
            item: DepotItem to download
            output_dir: Directory to save the file
            cdn_urls: List of CDN URLs (will fetch if not provided)
            verify_hash: Whether to verify hashes
            progress_callback: Optional callback(bytes_downloaded, total_bytes)
            
        Returns:
            Path to the downloaded file
        """
        # Detect if this is V1 blob or V2 chunk-based
        if item.is_v1_blob:
            return self._download_v1_blob(item, output_dir, cdn_urls, verify_hash, progress_callback)
        else:
            return self._download_v2_item(item, output_dir, cdn_urls, verify_hash, progress_callback)

    def _download_v1_blob(self, item: DepotItem, output_dir: str,
                         cdn_urls: Optional[List[str]],
                         verify_hash: bool,
                         progress_callback: Optional[Callable[[int, int], None]]) -> str:
        """
        Download V1 main.bin using multi-threaded range requests.
        
        Similar to heroic-gogdl's approach: split into chunks and download in parallel.
        """
        utils.ensure_directory(output_dir)
        output_path = os.path.join(output_dir, item.path)
        parent_dir = os.path.dirname(output_path)
        if parent_dir:
            utils.ensure_directory(parent_dir)
        
        total_size = item.total_size_compressed or item.total_size_uncompressed
        self.logger.info(f"Downloading V1 blob {item.path} ({total_size:,} bytes) using range requests")
        
        # Get CDN URLs if not provided
        if not cdn_urls:
            cdn_urls = self.api.get_secure_link(item.product_id)
            if not cdn_urls:
                raise DownloadError(f"Failed to get secure links for {item.product_id}")
        
        # Build main.bin URL
        url = cdn_urls[0].replace("{GALAXY_PATH}", item.v1_blob_path)
        
        # Calculate chunk size (use 10MB chunks for range requests, like V2)
        chunk_size = 10 * 1024 * 1024  # 10MB
        num_chunks = (total_size + chunk_size - 1) // chunk_size
        
        self.logger.info(f"Splitting into {num_chunks} range request chunks of ~{chunk_size:,} bytes")
        
        # Create range download tasks
        tasks = []
        for i in range(num_chunks):
            offset = i * chunk_size
            size = min(chunk_size, total_size - offset)
            
            task = RangeDownloadTask(
                task_id=f"v1_chunk_{i}",
                url=url,
                output_path=output_path,
                offset=offset,
                size=size,
                chunk_index=i
            )
            tasks.append(task)
        
        # Create output file (sparse/pre-allocated)
        with open(output_path, 'wb') as f:
            f.seek(total_size - 1)
            f.write(b'\0')
        
        # Download chunks in parallel
        downloaded_bytes = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_task = {
                executor.submit(self._download_range_chunk, task): task
                for task in tasks
            }
            
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    chunk_data = future.result()
                    
                    # Write chunk to file at correct offset
                    with open(output_path, 'r+b') as f:
                        f.seek(task.offset)
                        f.write(chunk_data)
                    
                    downloaded_bytes += len(chunk_data)
                    if progress_callback:
                        progress_callback(downloaded_bytes, total_size)
                    
                    self.logger.debug(f"Completed range chunk {task.chunk_index + 1}/{num_chunks}")
                    
                except Exception as e:
                    self.logger.error(f"Failed to download range chunk {task.chunk_index}: {e}")
                    raise DownloadError(f"V1 blob download failed: {e}")
        
        # Verify blob hash if available
        if verify_hash and item.v1_blob_md5:
            self.logger.info("Verifying V1 blob hash...")
            actual_hash = utils.calculate_hash(output_path, "md5")
            if actual_hash.lower() != item.v1_blob_md5.lower():
                self.logger.error(f"Hash mismatch! Expected: {item.v1_blob_md5}, Got: {actual_hash}")
                os.remove(output_path)
                raise DownloadError("V1 blob hash verification failed")
        
        self.logger.info(f"Successfully downloaded V1 blob to {output_path}")
        return output_path

    def _download_range_chunk(self, task: RangeDownloadTask) -> bytes:
        """Download a single range chunk with retry logic."""
        range_header = utils.get_range_header(task.offset, task.size)
        
        for attempt in range(constants.DEFAULT_RETRIES):
            try:
                response = self.session.get(
                    task.url,
                    headers={'Range': range_header},
                    timeout=constants.DEFAULT_TIMEOUT
                )
                response.raise_for_status()
                
                data = response.content
                
                if len(data) != task.size:
                    self.logger.warning(f"Size mismatch: expected {task.size}, got {len(data)}")
                    if attempt < constants.DEFAULT_RETRIES - 1:
                        continue
                
                return data
                
            except requests.RequestException as e:
                if attempt == constants.DEFAULT_RETRIES - 1:
                    raise DownloadError(f"Failed to download range chunk: {e}")
                self.logger.debug(f"Retry {attempt + 1}/{constants.DEFAULT_RETRIES}")
        
        raise DownloadError("Failed to download range chunk")

    def _download_v2_item(self, item: DepotItem, output_dir: str,
                         cdn_urls: Optional[List[str]],
                         verify_hash: bool,
                         progress_callback: Optional[Callable[[int, int], None]]) -> str:
        """
        Download V2 item using multi-threaded chunk downloads.
        
        Original V2 implementation from downloader.py.
        """
        utils.ensure_directory(output_dir)
        normalized_path = utils.normalize_path(item.path)
        output_path = os.path.join(output_dir, normalized_path)
        parent_dir = os.path.dirname(output_path)
        if parent_dir:
            utils.ensure_directory(parent_dir)
        
        self.logger.info(f"Downloading V2 item {item.path} ({len(item.chunks)} chunks)")
        
        # Get CDN URLs if not provided
        if not cdn_urls:
            cdn_urls = self.api.get_secure_link(item.product_id)
            if not cdn_urls:
                raise DownloadError(f"Failed to get secure links for {item.product_id}")
        
        # Download chunks
        total_bytes = sum(chunk.size_compressed for chunk in item.chunks)
        downloaded_bytes = 0
        
        with open(output_path, 'wb') as output_file:
            for idx, chunk in enumerate(item.chunks):
                self.logger.debug(f"Downloading chunk {idx + 1}/{len(item.chunks)}")
                
                chunk_data = self._download_v2_chunk(chunk, cdn_urls, verify_hash)
                
                # Decompress if needed
                if chunk.size_compressed != chunk.size_uncompressed:
                    try:
                        chunk_data = zlib.decompress(chunk_data, constants.ZLIB_WINDOW_SIZE)
                    except zlib.error as e:
                        raise DownloadError(f"Failed to decompress chunk {idx}: {e}")
                
                # Write to file
                output_file.write(chunk_data)
                
                downloaded_bytes += chunk.size_compressed
                if progress_callback:
                    progress_callback(downloaded_bytes, total_bytes)
        
        # Verify final file hash if available
        if item.md5 and verify_hash:
            self.logger.debug("Verifying file hash...")
            actual_hash = utils.calculate_hash(output_path, "md5")
            if actual_hash.lower() != item.md5.lower():
                self.logger.error(f"Hash mismatch! Expected: {item.md5}, Got: {actual_hash}")
                raise DownloadError("File hash verification failed")
        
        self.logger.info(f"Successfully downloaded V2 item to {output_path}")
        return output_path

    def _download_v2_chunk(self, chunk: DepotItemChunk, cdn_urls: List[str],
                          verify_hash: bool = True) -> bytes:
        """Download a single V2 chunk with retry logic."""
        chunk_path = utils.galaxy_path(chunk.md5_compressed)
        
        for cdn_url in cdn_urls:
            url = cdn_url.replace("{GALAXY_PATH}", chunk_path)
            
            try:
                chunk_data = self._fetch_chunk_data(url, chunk.size_compressed)
                
                if verify_hash and not utils.verify_chunk_hash(chunk_data, chunk.md5_compressed):
                    self.logger.warning(f"Chunk hash mismatch from {url}")
                    continue
                
                return chunk_data
                
            except requests.RequestException as e:
                self.logger.warning(f"Failed to download chunk from {url}: {e}")
                continue
        
        raise DownloadError(f"Failed to download chunk {chunk.md5_compressed} from all CDN URLs")

    def _fetch_chunk_data(self, url: str, expected_size: int,
                         retries: int = constants.DEFAULT_RETRIES) -> bytes:
        """Fetch chunk data from URL with retries."""
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=constants.DEFAULT_TIMEOUT)
                response.raise_for_status()
                
                data = response.content
                
                if len(data) != expected_size:
                    self.logger.warning(f"Size mismatch: expected {expected_size}, got {len(data)}")
                    if attempt < retries - 1:
                        continue
                
                return data
                
            except requests.RequestException as e:
                if attempt == retries - 1:
                    raise
                self.logger.debug(f"Retry {attempt + 1}/{retries} after error: {e}")
        
        raise requests.RequestException("Failed to fetch chunk data")

    def download_items_parallel(self, items: List[DepotItem], output_dir: str,
                               cdn_urls: Optional[List[str]] = None,
                               verify_hash: bool = True,
                               progress_callback: Optional[Callable[[str, int, int], None]] = None) -> Dict[str, str]:
        """
        Download multiple depot items in parallel (works for both V1 and V2).
        
        Args:
            items: List of DepotItems to download
            output_dir: Directory to save files
            cdn_urls: List of CDN URLs (will fetch if not provided)
            verify_hash: Whether to verify hashes
            progress_callback: Optional callback(item_path, bytes_downloaded, total_bytes)
            
        Returns:
            Dictionary mapping item paths to downloaded file paths
        """
        results = {}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_item = {
                executor.submit(
                    self.download_item,
                    item,
                    output_dir,
                    cdn_urls,
                    verify_hash,
                    lambda downloaded, total, path=item.path: progress_callback(path, downloaded, total) if progress_callback else None
                ): item
                for item in items
            }
            
            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    output_path = future.result()
                    results[item.path] = output_path
                    self.logger.info(f"Completed: {item.path}")
                except Exception as e:
                    self.logger.error(f"Failed to download {item.path}: {e}")
                    results[item.path] = None
        
        return results
