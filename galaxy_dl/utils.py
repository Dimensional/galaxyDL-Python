"""
Utility functions for Galaxy downloads
Based on heroic-gogdl dl_utils.py and lgogdownloader util.cpp
"""

import hashlib
import json
import os
import sys
import zlib
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, Callable

import requests

from galaxy_dl import constants


# Global symbol variables (set by setup_symbols)
SYMBOL_CHECK = '[OK]'
SYMBOL_ERROR = '[ERROR]'
SYMBOL_WARNING = '[WARNING]'
SYMBOL_INFO = '[INFO]'


def detect_unicode_support(force_ascii=False):
    """
    Detect if the terminal supports Unicode output.
    
    Args:
        force_ascii: If True, force ASCII mode regardless of terminal support
    
    Returns:
        True if Unicode is supported, False otherwise
    """
    # Check for explicit force ASCII flag
    if force_ascii:
        return False
    
    # Check for environment variable to force ASCII mode
    if os.environ.get('FORCE_ASCII', '').lower() in ('1', 'true', 'yes'):
        return False
    
    # Check if stdout encoding supports Unicode
    try:
        encoding = sys.stdout.encoding or ''
        if encoding.lower() in ('utf-8', 'utf8'):
            return True
        
        # Try to encode a Unicode character
        '✓'.encode(encoding)
        return True
    except (UnicodeEncodeError, AttributeError, LookupError):
        return False


def setup_symbols(force_ascii=False):
    """
    Set up symbol variables based on Unicode support.
    
    Args:
        force_ascii: If True, force ASCII mode
    """
    global SYMBOL_CHECK, SYMBOL_ERROR, SYMBOL_WARNING, SYMBOL_INFO
    
    use_unicode = detect_unicode_support(force_ascii)
    
    if use_unicode:
        SYMBOL_CHECK = '✓'
        SYMBOL_ERROR = '✗'
        SYMBOL_WARNING = '⚠'
        SYMBOL_INFO = 'ℹ'
    else:
        SYMBOL_CHECK = '[OK]'
        SYMBOL_ERROR = '[ERROR]'
        SYMBOL_WARNING = '[WARNING]'
        SYMBOL_INFO = '[INFO]'


def galaxy_path(manifest_hash: str) -> str:
    """
    Convert a manifest hash to Galaxy CDN path format.
    
    Galaxy uses a directory structure like: ab/cd/abcdef123...
    where the first 2 characters become the first directory,
    next 2 characters become the second directory.
    
    Args:
        manifest_hash: The manifest hash string
        
    Returns:
        Path formatted for Galaxy CDN (e.g., "ab/cd/abcdef123...")
    """
    if "/" in manifest_hash:
        # Already formatted
        return manifest_hash
    
    if len(manifest_hash) < 4:
        return manifest_hash
    
    return f"{manifest_hash[0:2]}/{manifest_hash[2:4]}/{manifest_hash}"


def get_json(session: requests.Session, url: str, timeout: int = constants.DEFAULT_TIMEOUT) -> Optional[Dict[str, Any]]:
    """
    Fetch JSON data from a URL.
    
    Args:
        session: Requests session to use
        url: URL to fetch
        timeout: Request timeout in seconds
        
    Returns:
        Parsed JSON data or None if request failed
    """
    try:
        response = session.get(url, headers={"Accept": "application/json"}, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, json.JSONDecodeError) as e:
        return None


def get_zlib_encoded(session: requests.Session, url: str, retries: int = constants.DEFAULT_RETRIES,
                     timeout: int = constants.DEFAULT_TIMEOUT) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
    """
    Fetch and decompress zlib-encoded JSON data from a URL.
    
    Many Galaxy API endpoints return zlib-compressed JSON.
    This function handles both compressed and uncompressed responses.
    
    Args:
        session: Requests session to use
        url: URL to fetch
        retries: Number of retries on failure
        timeout: Request timeout in seconds
        
    Returns:
        Tuple of (parsed JSON data, response headers) or (None, None) if failed
    """
    attempt = 0
    while attempt < retries:
        try:
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            
            # Try to decompress
            try:
                decompressed = zlib.decompress(response.content, constants.ZLIB_WINDOW_SIZE)
                data = json.loads(decompressed)
                return data, dict(response.headers)
            except zlib.error:
                # Not compressed, try as plain JSON
                try:
                    data = response.json()
                    return data, dict(response.headers)
                except json.JSONDecodeError:
                    return None, None
                    
        except requests.RequestException:
            attempt += 1
            if attempt >= retries:
                return None, None
    
    return None, None


def is_zlib_compressed(data: bytes) -> bool:
    """
    Check if data has zlib compression header.
    
    Zlib headers are: 0x78 0x01, 0x78 0x5E, 0x78 0x9C, or 0x78 0xDA
    
    Args:
        data: Byte data to check
        
    Returns:
        True if data appears to be zlib compressed
    """
    if len(data) < 2:
        return False
    
    header = (data[0] << 8) | data[1]
    zlib_headers = [0x7801, 0x785E, 0x789C, 0x78DA]
    return header in zlib_headers


def calculate_hash(file_path: str, algorithm: str = "md5", 
                  chunk_size: int = constants.CHUNK_READ_SIZE,
                  progress_callback: Optional[Callable[[int], None]] = None) -> str:
    """
    Calculate hash of a file.
    
    Args:
        file_path: Path to the file
        algorithm: Hash algorithm ("md5" or "sha256")
        chunk_size: Size of chunks to read
        progress_callback: Optional callback function called with bytes read
        
    Returns:
        Hex digest of the hash
    """
    if algorithm == "md5":
        hasher = hashlib.md5()
    elif algorithm == "sha256":
        hasher = hashlib.sha256()
    else:
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")
    
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
            if progress_callback:
                progress_callback(len(chunk))
    
    return hasher.hexdigest()


def verify_chunk_hash(data: bytes, expected_md5: str) -> bool:
    """
    Verify MD5 hash of chunk data.
    
    Args:
        data: Chunk data bytes
        expected_md5: Expected MD5 hash
        
    Returns:
        True if hash matches
    """
    hasher = hashlib.md5()
    hasher.update(data)
    actual_md5 = hasher.hexdigest()
    return actual_md5.lower() == expected_md5.lower()


def get_readable_size(size_bytes: int) -> Tuple[float, str]:
    """
    Convert bytes to human-readable size.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Tuple of (size value, unit string)
    """
    power = 1024
    n = 0
    labels = {0: "B", 1: "KB", 2: "MB", 3: "GB", 4: "TB"}
    
    size = float(size_bytes)
    while size > power and n < 4:
        size /= power
        n += 1
    
    return round(size, 2), labels[n]


def format_size(size_bytes: int) -> str:
    """
    Format bytes as human-readable string.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted string (e.g., "1.5 GB")
    """
    size, unit = get_readable_size(size_bytes)
    return f"{size} {unit}"


def ensure_directory(path: str) -> None:
    """
    Ensure directory exists, creating it if necessary.
    
    Args:
        path: Directory path to create
    """
    Path(path).mkdir(parents=True, exist_ok=True)


def get_case_insensitive_path(path: str) -> str:
    """
    Get case-insensitive path on case-sensitive filesystems.
    
    On Windows, paths are already case-insensitive.
    On Linux/Mac, this tries to find the correct case for existing paths.
    
    Args:
        path: Path to resolve
        
    Returns:
        Resolved path with correct case
    """
    if os.name == "nt" or os.path.exists(path):
        # Windows or path exists exactly as specified
        return path
    
    # Find existing root directory
    root = path
    while not os.path.exists(root) and root != os.path.dirname(root):
        root = os.path.dirname(root)
    
    if not os.path.exists(root):
        return path
    
    # Traverse remaining path components
    remaining = os.path.relpath(path, root)
    if remaining == ".":
        return root
    
    components = remaining.split(os.sep)
    current = root
    
    for component in components:
        if not os.path.exists(current):
            current = os.path.join(current, component)
            continue
        
        # Try to find case-insensitive match
        found = False
        try:
            for item in os.listdir(current):
                if item.lower() == component.lower():
                    current = os.path.join(current, item)
                    found = True
                    break
        except (OSError, PermissionError):
            pass
        
        if not found:
            current = os.path.join(current, component)
    
    return current


def get_range_header(offset: int, size: int) -> str:
    """
    Create HTTP Range header value.
    
    Args:
        offset: Start offset in bytes
        size: Number of bytes to request
        
    Returns:
        Range header value (e.g., "bytes=0-1023")
    """
    to_value = offset + size - 1
    return f"bytes={offset}-{to_value}"


def normalize_path(path: str) -> str:
    """
    Normalize path separators to OS native format.
    
    Galaxy uses backslashes in paths, but we need forward slashes on Unix.
    
    Args:
        path: Path to normalize
        
    Returns:
        Normalized path
    """
    # Replace backslashes with forward slashes
    normalized = path.replace("\\", "/")
    # Convert to OS native separator
    normalized = normalized.replace("/", os.sep)
    # Remove leading separator
    normalized = normalized.lstrip(os.sep)
    return normalized


def merge_url_with_params(url_template: str, parameters: Dict[str, str]) -> str:
    """
    Merge URL template with parameters.
    
    Replaces {key} placeholders in URL template with values from parameters dict.
    
    Args:
        url_template: URL template with {key} placeholders
        parameters: Dictionary of parameter values
        
    Returns:
        URL with placeholders replaced
    """
    url = url_template
    for key, value in parameters.items():
        placeholder = "{" + key + "}"
        url = url.replace(placeholder, str(value))
    return url

