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
                     progress_callback: Optional[Callable[[int, int], None]] = None,
                     raw_mode: bool = False,
                     sfc_data: Optional[bytes] = None) -> str:
        """
        Download a depot item (auto-detects V1 vs V2).
        
        For V1 items:
        - If item has v1_offset/v1_size: Extract individual file using range request
        - If item is just the blob: Download whole main.bin
        
        For V2 items:
        - If item is in SFC: Extract from provided sfc_data
        - If raw_mode=True: Save compressed chunks without decompression
        - If raw_mode=False: Download, decompress, and assemble into final file
        
        Args:
            item: DepotItem to download
            output_dir: Directory to save the file
            cdn_urls: List of CDN URLs (will fetch if not provided)
            verify_hash: Whether to verify hashes
            progress_callback: Optional callback(bytes_downloaded, total_bytes)
            raw_mode: For V2 only - save raw compressed chunks without assembly
            sfc_data: Decompressed small files container data (for items in SFC)
            
        Returns:
            Path to the downloaded file (or chunks directory for V2 raw mode)
        """
        # Handle items that are inside a small files container
        if item.is_in_sfc:
            if sfc_data is None:
                raise DownloadError(f"Item {item.path} is in SFC but no SFC data provided")
            return self._extract_from_sfc(item, output_dir, sfc_data)
        
        # Detect if this is V1 blob or V2 chunk-based
        if item.is_v1_blob:
            # Check if this is a file extraction or whole blob download
            if item.v1_offset > 0 or (item.v1_size > 0 and item.v1_size < item.total_size_uncompressed):
                # This is an individual file extraction
                return self._download_v1_file(item, output_dir, cdn_urls, verify_hash, progress_callback)
            else:
                # This is a whole blob download
                return self._download_v1_blob(item, output_dir, cdn_urls, verify_hash, progress_callback)
        else:
            return self._download_v2_item(item, output_dir, cdn_urls, verify_hash, progress_callback, raw_mode)

    def _download_v1_blob(self, item: DepotItem, output_dir: str,
                         cdn_urls: Optional[List[str]],
                         verify_hash: bool,
                         progress_callback: Optional[Callable[[int, int], None]]) -> str:
        """
        Download V1 main.bin blob - calls _download_v1_range() for full file.
        """
        utils.ensure_directory(output_dir)
        output_path = os.path.join(output_dir, item.path)
        parent_dir = os.path.dirname(output_path)
        if parent_dir:
            utils.ensure_directory(parent_dir)
        
        # Get CDN URLs if not provided
        if not cdn_urls:
            cdn_urls = self.api.get_secure_link(item.product_id)
            if not cdn_urls:
                raise DownloadError(f"Failed to get secure links for {item.product_id}")
        
        # Build URL
        url = cdn_urls[0].replace("{GALAXY_PATH}", item.v1_blob_path)
        total_size = item.total_size_compressed or item.total_size_uncompressed
        
        self.logger.info(f"Downloading V1 blob {item.path} ({total_size:,} bytes)")
        
        # Download using range requests (offset=0, size=total)
        self._download_v1_range(url, 0, total_size, output_path, progress_callback)
        
        # Verify hash
        if verify_hash and item.v1_blob_md5:
            actual_hash = utils.calculate_hash(output_path, "md5")
            if actual_hash.lower() != item.v1_blob_md5.lower():
                self.logger.error(f"Hash mismatch! Expected: {item.v1_blob_md5}, Got: {actual_hash}")
                os.remove(output_path)
                raise DownloadError("V1 blob hash verification failed")
        
        self.logger.info(f"Successfully downloaded V1 blob to {output_path}")
        return output_path

    def _download_v1_range(self, url: str, offset: int, size: int, output_path: str,
                          progress_callback: Optional[Callable[[int, int], None]] = None) -> None:
        """
        Raw V1 range download - handles all HTTP logic for range requests.
        
        Downloads a range (offset→offset+size) using multi-threaded chunks.
        Both blob and file extraction use this method with different parameters.
        """
        # Calculate chunk size (10MB chunks for parallel downloads)
        chunk_size = 10 * 1024 * 1024  # 10MB
        num_chunks = (size + chunk_size - 1) // chunk_size
        
        self.logger.debug(f"Range download: offset={offset}, size={size:,}, chunks={num_chunks}")
        
        # Create range download tasks
        tasks = []
        for i in range(num_chunks):
            chunk_offset = offset + (i * chunk_size)
            chunk_size_actual = min(chunk_size, size - (i * chunk_size))
            
            task = RangeDownloadTask(
                task_id=f"range_chunk_{i}",
                url=url,
                output_path=output_path,
                offset=chunk_offset,
                size=chunk_size_actual,
                chunk_index=i
            )
            tasks.append(task)
        
        # Create output file (sparse/pre-allocated) if downloading from start
        if offset == 0:
            with open(output_path, 'wb') as f:
                f.seek(size - 1)
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
                    with open(output_path, 'r+b' if offset == 0 else 'wb') as f:
                        f.seek(task.offset)
                        f.write(chunk_data)
                    
                    downloaded_bytes += len(chunk_data)
                    if progress_callback:
                        progress_callback(downloaded_bytes, size)
                    
                    self.logger.debug(f"Completed range chunk {task.chunk_index + 1}/{num_chunks}")
                    
                except Exception as e:
                    self.logger.error(f"Failed to download range chunk {task.chunk_index}: {e}")
                    raise DownloadError(f"Range download failed: {e}")

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

    def _download_v1_file(self, item: DepotItem, output_dir: str,
                         cdn_urls: Optional[List[str]],
                         verify_hash: bool,
                         progress_callback: Optional[Callable[[int, int], None]]) -> str:
        """
        Download individual V1 file - calls _download_v1_range() for specific offset/size.
        
        Extracts a single file from main.bin using range requests.
        """
        utils.ensure_directory(output_dir)
        normalized_path = utils.normalize_path(item.path)
        output_path = os.path.join(output_dir, normalized_path)
        parent_dir = os.path.dirname(output_path)
        if parent_dir:
            utils.ensure_directory(parent_dir)
        
        self.logger.info(f"Extracting V1 file {item.path} (offset: {item.v1_offset}, size: {item.v1_size})")
        
        # Get CDN URLs if not provided
        if not cdn_urls:
            cdn_urls = self.api.get_secure_link(item.product_id)
            if not cdn_urls:
                raise DownloadError(f"Failed to get secure links for {item.product_id}")
        
        # Build main.bin URL
        url = cdn_urls[0].replace("{GALAXY_PATH}", item.v1_blob_path)
        
        # Download using range request for this specific file
        self._download_v1_range(url, item.v1_offset, item.v1_size, output_path, progress_callback)
        
        # Verify hash
        if verify_hash and item.md5:
            actual_hash = utils.calculate_hash(output_path, "md5")
            if actual_hash.lower() != item.md5.lower():
                self.logger.error(f"Hash mismatch! Expected: {item.md5}, Got: {actual_hash}")
                os.remove(output_path)
                raise DownloadError(f"Hash verification failed for {item.path}")
        
        self.logger.info(f"Successfully extracted V1 file to {output_path}")
        return output_path

    def _download_v2_item(self, item: DepotItem, output_dir: str,
                         cdn_urls: Optional[List[str]],
                         verify_hash: bool,
                         progress_callback: Optional[Callable[[int, int], None]],
                         raw_mode: bool = False) -> str:
        """
        Download V2 item using multi-threaded chunk downloads.
        
        Now uses parallel chunk downloads like V1 for better performance.
        
        Args:
            item: DepotItem to download
            output_dir: Output directory
            cdn_urls: CDN URLs
            verify_hash: Whether to verify hashes
            progress_callback: Progress callback
            raw_mode: If True, save compressed chunks as-is without decompression/assembly
            
        Returns:
            Path to output file (final file or chunk directory)
        """
        utils.ensure_directory(output_dir)
        normalized_path = utils.normalize_path(item.path)
        output_path = os.path.join(output_dir, normalized_path)
        parent_dir = os.path.dirname(output_path)
        if parent_dir:
            utils.ensure_directory(parent_dir)
        
        self.logger.info(f"Downloading V2 item {item.path} ({len(item.chunks)} chunks, raw_mode={raw_mode})")
        
        # Get CDN URLs if not provided
        if not cdn_urls:
            cdn_urls = self.api.get_secure_link(item.product_id)
            if not cdn_urls:
                raise DownloadError(f"Failed to get secure links for {item.product_id}")
        
        if raw_mode:
            # Raw mode: Save compressed chunks as separate files
            return self._download_v2_item_raw(item, output_dir, cdn_urls, verify_hash, progress_callback)
        
        # Normal mode: Download, decompress, and assemble
        # Download chunks in parallel
        total_bytes = sum(chunk.size_compressed for chunk in item.chunks)
        downloaded_bytes = 0
        chunk_results: List[Optional[bytes]] = [None] * len(item.chunks)  # Preserve order
        
        # Create chunk download tasks
        tasks = []
        for idx, chunk in enumerate(item.chunks):
            task = ChunkDownloadTask(
                task_id=f"v2_chunk_{idx}",
                url="",  # Will be set in download method
                output_path=output_path,
                chunk=chunk,
                chunk_index=idx,
                verify_hash=verify_hash
            )
            tasks.append(task)
        
        # Download chunks in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_task = {
                executor.submit(self._download_and_decompress_chunk, task, cdn_urls): task
                for task in tasks
            }
            
            for future in as_completed(future_to_task):
                task = future_to_task[future]
                try:
                    decompressed_data = future.result()
                    chunk_results[task.chunk_index] = decompressed_data
                    
                    downloaded_bytes += task.chunk.size_compressed
                    if progress_callback:
                        progress_callback(downloaded_bytes, total_bytes)
                    
                    self.logger.debug(f"Completed chunk {task.chunk_index + 1}/{len(item.chunks)}")
                    
                except Exception as e:
                    self.logger.error(f"Failed to download chunk {task.chunk_index}: {e}")
                    raise DownloadError(f"V2 item download failed: {e}")
        
        # Write all chunks to file in order
        with open(output_path, 'wb') as output_file:
            for chunk_data in chunk_results:
                if chunk_data is None:
                    raise DownloadError("Missing chunk data - download incomplete")
                output_file.write(chunk_data)
        
        # Verify final file hash if available
        if item.md5 and verify_hash:
            self.logger.debug("Verifying file hash...")
            actual_hash = utils.calculate_hash(output_path, "md5")
            if actual_hash.lower() != item.md5.lower():
                self.logger.error(f"Hash mismatch! Expected: {item.md5}, Got: {actual_hash}")
                os.remove(output_path)
                raise DownloadError("File hash verification failed")
        
        self.logger.info(f"Successfully downloaded V2 item to {output_path}")
        return output_path
    
    def _download_v2_item_raw(self, item: DepotItem, output_dir: str,
                             cdn_urls: List[str],
                             verify_hash: bool,
                             progress_callback: Optional[Callable[[int, int], None]]) -> str:
        """
        Download V2 item in raw mode - save compressed chunks without decompression.
        
        Chunks are saved as separate files in a directory named after the item.
        This allows frontends to process chunks later or implement custom decompression.
        
        Returns:
            Path to directory containing raw chunks
        """
        # Create directory for chunks
        normalized_path = utils.normalize_path(item.path)
        chunks_dir = os.path.join(output_dir, f"{normalized_path}.chunks")
        utils.ensure_directory(chunks_dir)
        
        self.logger.info(f"Downloading V2 raw chunks for {item.path} to {chunks_dir}")
        
        total_bytes = sum(chunk.size_compressed for chunk in item.chunks)
        downloaded_bytes = 0
        
        # Download chunks in parallel and save as separate files
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for idx, chunk in enumerate(item.chunks):
                chunk_path = os.path.join(chunks_dir, f"chunk_{idx:04d}.dat")
                future = executor.submit(self._download_v2_chunk_to_file, chunk, cdn_urls, chunk_path, verify_hash)
                futures.append((future, chunk.size_compressed))
            
            for future, chunk_size in futures:
                try:
                    future.result()
                    downloaded_bytes += chunk_size
                    if progress_callback:
                        progress_callback(downloaded_bytes, total_bytes)
                except Exception as e:
                    self.logger.error(f"Failed to download raw chunk: {e}")
                    raise DownloadError(f"Raw chunk download failed: {e}")
        
        # Save metadata about the chunks for later assembly
        metadata = {
            "path": item.path,
            "md5": item.md5,
            "sha256": item.sha256,
            "total_size_compressed": item.total_size_compressed,
            "total_size_uncompressed": item.total_size_uncompressed,
            "chunks": [
                {
                    "index": idx,
                    "md5_compressed": chunk.md5_compressed,
                    "md5_uncompressed": chunk.md5_uncompressed,
                    "size_compressed": chunk.size_compressed,
                    "size_uncompressed": chunk.size_uncompressed
                }
                for idx, chunk in enumerate(item.chunks)
            ]
        }
        
        import json
        metadata_path = os.path.join(chunks_dir, "chunks.json")
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        self.logger.info(f"Successfully downloaded {len(item.chunks)} raw chunks to {chunks_dir}")
        return chunks_dir
    
    def _download_v2_chunk_to_file(self, chunk: DepotItemChunk, cdn_urls: List[str],
                                   output_path: str, verify_hash: bool) -> None:
        """Download a single V2 chunk and save it to a file (compressed)."""
        chunk_data = self._download_v2_chunk(chunk, cdn_urls, verify_hash)
        with open(output_path, 'wb') as f:
            f.write(chunk_data)
    
    def assemble_v2_chunks(self, chunks_dir: str, output_path: str,
                          verify_hash: bool = True) -> str:
        """
        Assemble raw V2 chunks into final file.
        
        This processes chunks that were downloaded in raw mode, decompressing
        and assembling them into the final game file.
        
        Args:
            chunks_dir: Directory containing raw chunks (from raw mode download)
            output_path: Path for final assembled file
            verify_hash: Whether to verify final file hash
            
        Returns:
            Path to assembled file
        """
        import json
        
        # Load metadata
        metadata_path = os.path.join(chunks_dir, "chunks.json")
        if not os.path.exists(metadata_path):
            raise DownloadError(f"Chunks metadata not found: {metadata_path}")
        
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        self.logger.info(f"Assembling {len(metadata['chunks'])} chunks into {output_path}")
        
        # Ensure output directory exists
        parent_dir = os.path.dirname(output_path)
        if parent_dir:
            utils.ensure_directory(parent_dir)
        
        # Process and assemble chunks in order
        with open(output_path, 'wb') as output_file:
            for chunk_meta in metadata['chunks']:
                chunk_path = os.path.join(chunks_dir, f"chunk_{chunk_meta['index']:04d}.dat")
                
                if not os.path.exists(chunk_path):
                    raise DownloadError(f"Missing chunk file: {chunk_path}")
                
                # Read compressed chunk
                with open(chunk_path, 'rb') as f:
                    compressed_data = f.read()
                
                # Decompress if needed
                if chunk_meta['size_compressed'] != chunk_meta['size_uncompressed']:
                    try:
                        decompressed_data = zlib.decompress(compressed_data, constants.ZLIB_WINDOW_SIZE)
                    except zlib.error as e:
                        raise DownloadError(f"Failed to decompress chunk {chunk_meta['index']}: {e}")
                else:
                    decompressed_data = compressed_data
                
                output_file.write(decompressed_data)
        
        # Verify hash
        if verify_hash and metadata.get('md5'):
            self.logger.debug("Verifying assembled file hash...")
            actual_hash = utils.calculate_hash(output_path, "md5")
            if actual_hash.lower() != metadata['md5'].lower():
                self.logger.error(f"Hash mismatch! Expected: {metadata['md5']}, Got: {actual_hash}")
                os.remove(output_path)
                raise DownloadError("Assembled file hash verification failed")
        
        self.logger.info(f"Successfully assembled file to {output_path}")
        return output_path
    
    def _download_and_decompress_chunk(self, task: ChunkDownloadTask, cdn_urls: List[str]) -> bytes:
        """Download and decompress a single V2 chunk."""
        # Download chunk
        chunk_data = self._download_v2_chunk(task.chunk, cdn_urls, task.verify_hash)
        
        # Decompress if needed
        if task.chunk.size_compressed != task.chunk.size_uncompressed:
            try:
                chunk_data = zlib.decompress(chunk_data, constants.ZLIB_WINDOW_SIZE)
            except zlib.error as e:
                raise DownloadError(f"Failed to decompress chunk {task.chunk_index}: {e}")
        
        return chunk_data

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

    def download_v1_files(self, manifest, output_dir: str,
                         cdn_urls: Optional[List[str]] = None,
                         verify_hash: bool = True,
                         progress_callback: Optional[Callable[[str, int, int], None]] = None) -> Dict[str, str]:
        """
        Download all files from a V1 manifest using range requests.
        
        This extracts individual files from main.bin instead of downloading the whole blob.
        
        Args:
            manifest: V1 Manifest with items containing offset/size info
            output_dir: Directory to save files
            cdn_urls: List of CDN URLs (will fetch if not provided)
            verify_hash: Whether to verify MD5 hashes
            progress_callback: Optional callback(item_path, bytes_downloaded, total_bytes)
            
        Returns:
            Dictionary mapping file paths to downloaded file paths
        """
        if manifest.generation != 1:
            raise ValueError("This method only works with V1 manifests")
        
        if not manifest.items:
            self.logger.warning("No items found in V1 manifest")
            return {}
        
        self.logger.info(f"Downloading {len(manifest.items)} files from V1 manifest")
        
        results = {}
        for item in manifest.items:
            try:
                output_path = self._download_v1_file(
                    item, output_dir, cdn_urls, verify_hash,
                    lambda downloaded, total, path=item.path: progress_callback(path, downloaded, total) if progress_callback else None
                )
                results[item.path] = output_path
            except Exception as e:
                self.logger.error(f"Failed to download {item.path}: {e}")
                results[item.path] = None
        
        return results

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
    # ========== Archival Methods (Raw JSON Downloads) ==========
    
    def download_raw_depot(self, build_id: str, output_path: str) -> None:
        """
        Download depot metadata JSON in original compressed format (V2).
        
        Args:
            build_id: Build ID (the hash from build['link'])
            output_path: Where to save the file
        """
        url = self.api.get_depot_url(build_id)
        self.api.download_raw(url, output_path)
    
    def download_raw_repository(self, game_id: str, platform: str, timestamp: str, output_path: str) -> None:
        """
        Download repository metadata JSON in original format (V1).
        
        Args:
            game_id: Game ID
            platform: Platform (windows, osx, linux)
            timestamp: Repository timestamp (from meta)
            output_path: Where to save the file
        """
        url = self.api.get_repository_url(game_id, platform, timestamp)
        self.api.download_raw(url, output_path)
    
    def download_raw_manifest(self, manifest_id: str, output_path: str, generation: int = 2, 
                              game_id: Optional[str] = None, platform: Optional[str] = None, timestamp: Optional[str] = None) -> None:
        """
        Download manifest JSON in original format (may be compressed or plain).
        
        Args:
            manifest_id: Manifest hash from depot/repository
            output_path: Where to save the file
            generation: 1 for V1, 2 for V2
            game_id: Required for V1 manifests
            platform: Required for V1 manifests
            timestamp: Required for V1 manifests
        """
        url = self.api.get_manifest_url(manifest_id, game_id, platform, timestamp, generation)
        self.api.download_raw(url, output_path)
    
    def download_raw_chunk(self, compressed_md5: str, output_path: str, product_id: str = None) -> None:
        """
        Download V2 chunk in compressed format using secure links.
        
        V2 chunks require authenticated secure links for download.
        
        Args:
            compressed_md5: The compressedMd5 hash from manifest
            output_path: Where to save the file
            product_id: Product ID for secure link generation (required)
        """
        if not product_id:
            raise ValueError("product_id is required for V2 chunk downloads")
        
        # V2 chunks use the path pattern: /{hash[:2]}/{hash[2:4]}/{hash}
        chunk_subpath = f"/{compressed_md5[:2]}/{compressed_md5[2:4]}/{compressed_md5}"
        
        # Get secure link for the product (root path "/")
        # This returns URL templates with {path} parameter set to /content-system/v2/store/{product_id}
        endpoints = self.api.get_secure_link(product_id, "/", generation=2, return_full_response=True)
        
        if not endpoints:
            raise ValueError(f"Failed to get secure link for product {product_id}")
        
        # Use the first endpoint (usually fastly)
        endpoint = endpoints[0]
        
        # Append the chunk subpath to the path parameter
        params = endpoint["parameters"].copy()
        params["path"] = params.get("path", "") + chunk_subpath
        
        # Merge URL template with parameters
        url = self.api._merge_url_with_params(endpoint["url_format"], params)
        
        # Download the chunk
        self.api.download_raw(url, output_path)
    
    def _extract_from_sfc(self, item: DepotItem, output_dir: str, sfc_data: bytes) -> str:
        """
        Extract a file from small files container data.
        
        Args:
            item: DepotItem with is_in_sfc=True
            output_dir: Directory to save extracted file
            sfc_data: Decompressed small files container data
            
        Returns:
            Path to extracted file
        """
        utils.ensure_directory(output_dir)
        output_path = os.path.join(output_dir, item.path)
        parent_dir = os.path.dirname(output_path)
        if parent_dir:
            utils.ensure_directory(parent_dir)
        
        self.logger.info(f"Extracting {item.path} from SFC (offset={item.sfc_offset}, size={item.sfc_size})")
        
        # Validate offset and size
        if item.sfc_offset + item.sfc_size > len(sfc_data):
            raise DownloadError(
                f"SFC extraction out of bounds: offset={item.sfc_offset}, "
                f"size={item.sfc_size}, sfc_len={len(sfc_data)}"
            )
        
        # Extract file data from SFC
        file_data = sfc_data[item.sfc_offset:item.sfc_offset + item.sfc_size]
        
        # Write to file
        with open(output_path, 'wb') as f:
            f.write(file_data)
        
        self.logger.info(f"Successfully extracted {item.path} ({item.sfc_size} bytes)")
        return output_path
    
    def download_depot_items(self, items: List[DepotItem], output_dir: str,
                            cdn_urls: Optional[List[str]] = None,
                            verify_hash: bool = True,
                            progress_callback: Optional[Callable[[str, int, int], None]] = None,
                            delete_sfc_after_extraction: bool = True) -> Dict[str, str]:
        """
        Download all items from a depot, handling small files containers automatically.
        
        This method:
        1. Downloads and decompresses SFC items first
        2. Extracts files that reference the SFC
        3. Downloads regular items
        4. Optionally deletes SFC files after extraction
        
        Args:
            items: List of DepotItem objects
            output_dir: Directory to save files
            cdn_urls: CDN URLs (will fetch if not provided)
            verify_hash: Whether to verify hashes
            progress_callback: Optional callback(item_path, bytes_downloaded, total_bytes)
            delete_sfc_after_extraction: Whether to delete SFC files after extracting items
            
        Returns:
            Dictionary mapping item paths to downloaded file paths
        """
        results = {}
        sfc_containers = {}  # {product_id: (item, decompressed_data)}
        sfc_items = []  # Items to extract from SFC
        regular_items = []  # Regular items to download
        
        # Categorize items
        for item in items:
            if item.is_small_files_container:
                sfc_containers[item.product_id] = (item, None)
            elif item.is_in_sfc:
                sfc_items.append(item)
            else:
                regular_items.append(item)
        
        # Download and decompress SFC containers
        for product_id, (sfc_item, _) in sfc_containers.items():
            self.logger.info(f"Downloading small files container for product {product_id}")
            
            # Download SFC
            sfc_path = self.download_item(
                sfc_item, output_dir, cdn_urls, verify_hash,
                lambda downloaded, total: progress_callback(sfc_item.path, downloaded, total) if progress_callback else None
            )
            results[sfc_item.path] = sfc_path
            
            # Read and decompress SFC data
            with open(sfc_path, 'rb') as f:
                sfc_data = f.read()
            
            sfc_containers[product_id] = (sfc_item, sfc_data)
            self.logger.info(f"Loaded SFC for product {product_id} ({len(sfc_data)} bytes)")
        
        # Extract files from SFC
        for item in sfc_items:
            sfc_item, sfc_data = sfc_containers.get(item.product_id, (None, None))
            if sfc_data is None:
                self.logger.warning(f"Skipping {item.path} - no SFC data for product {item.product_id}")
                continue
            
            try:
                output_path = self._extract_from_sfc(item, output_dir, sfc_data)
                results[item.path] = output_path
                self.logger.info(f"Extracted: {item.path}")
            except Exception as e:
                self.logger.error(f"Failed to extract {item.path}: {e}")
                results[item.path] = None
        
        # Delete SFC files if requested
        if delete_sfc_after_extraction:
            for sfc_item, _ in sfc_containers.values():
                sfc_path = results.get(sfc_item.path)
                if sfc_path and os.path.exists(sfc_path):
                    os.remove(sfc_path)
                    self.logger.info(f"Deleted SFC: {sfc_path}")
                    del results[sfc_item.path]
        
        # Download regular items
        for item in regular_items:
            try:
                output_path = self.download_item(
                    item, output_dir, cdn_urls, verify_hash,
                    lambda downloaded, total: progress_callback(item.path, downloaded, total) if progress_callback else None
                )
                results[item.path] = output_path
                self.logger.info(f"Downloaded: {item.path}")
            except Exception as e:
                self.logger.error(f"Failed to download {item.path}: {e}")
                results[item.path] = None
        
        return results
    
    def download_main_bin(self, game_id: str, platform: str, timestamp: str, output_path: str,
                          num_workers: int = 4) -> None:
        """
        Download V1 main.bin file using authenticated secure links with parallel downloads.
        
        V1 main.bin files contain all game files as a binary blob and require
        authenticated secure links to download. Uses parallel byte-range requests
        for improved performance.
        
        Args:
            game_id: Product ID
            platform: Platform (e.g., 'windows', 'osx', 'linux')
            timestamp: Build timestamp from repository
            output_path: Where to save main.bin
            num_workers: Number of parallel download threads (default: 4)
        """
        self.api.download_main_bin(game_id, platform, timestamp, output_path, num_workers=num_workers)