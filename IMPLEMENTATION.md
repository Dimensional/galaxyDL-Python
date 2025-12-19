# Galaxy DL Implementation Summary

## Overview

This document provides a comprehensive summary of the galaxy_dl library implementation, which was created by combining best practices from heroic-gogdl (Python) and lgogdownloader (C++).

## What Was Built

A specialized Python library focused exclusively on downloading GOG Galaxy CDN files (depot chunks and binary blobs).

## Key Components

### 1. Core Modules

#### `galaxy_dl/constants.py`
- **Purpose**: Centralized API endpoints and configuration
- **Key Updates from lgogdownloader**:
  - Updated CDN URLs (cdn.gog.com for content-system)
  - Correct manifest v2 URLs with zlib encoding
  - Secure link URL with generation parameter
  - Dependency link URLs
  - ZLIB_WINDOW_SIZE constant (15)

#### `galaxy_dl/auth.py`
- **Purpose**: OAuth2 authentication management
- **Features**:
  - Token storage in JSON file
  - Automatic token refresh
  - Session management
  - Expiry checking (with 60-second buffer)
- **Based on**: heroic-gogdl auth.py with improvements

#### `galaxy_dl/models.py`
- **Purpose**: Data structures for Galaxy depot system
- **Models**:
  - `DepotItemChunk`: Individual compressed/uncompressed chunk
  - `DepotItem`: Complete file with multiple chunks
  - `Depot`: Depot metadata with language/bitness filters
  - `Manifest`: V1 and V2 manifest structures
- **Key Features**:
  - Support for small files containers (SFC)
  - MD5 and SHA256 hash tracking
  - Offset calculation for chunks
  - Language and bitness filtering

#### `galaxy_dl/utils.py`
- **Purpose**: Utility functions for downloads
- **Key Functions**:
  - `galaxy_path()`: Convert hash to Galaxy CDN path format (ab/cd/abcdef...)
  - `get_zlib_encoded()`: Fetch and decompress zlib-encoded JSON
  - `calculate_hash()`: MD5/SHA256 file hashing
  - `verify_chunk_hash()`: Chunk integrity verification
  - `normalize_path()`: Cross-platform path handling
  - `merge_url_with_params()`: URL template processing
- **Based on**: heroic-gogdl dl_utils.py + lgogdownloader util.cpp

#### `galaxy_dl/api.py`
- **Purpose**: Galaxy API client
- **Key Methods**:
  - `get_product_builds()`: Get available builds
  - `get_manifest_v1()`: Fetch V1 manifests
  - `get_manifest_v2()`: Fetch V2 manifests (with zlib decompression)
  - `get_depot_items()`: Parse manifest into depot items
  - `get_secure_link()`: Get CDN download URLs
  - `get_dependency_link()`: Get dependency URLs
  - `_extract_urls_from_response()`: CDN URL prioritization
- **Improvements**:
  - Proper handling of zlib-compressed responses
  - CDN URL prioritization (from lgogdownloader)
  - Automatic auth token refresh
  - Secure link caching

#### `galaxy_dl/downloader.py`
- **Purpose**: Chunk-based download manager
- **Features**:
  - Multi-threaded parallel downloads
  - Chunk fetching with retry logic
  - Zlib decompression of compressed chunks
  - MD5 hash verification
  - Progress callbacks
  - Resume capability
- **Key Methods**:
  - `download_item()`: Download single depot item
  - `download_items_parallel()`: Parallel multi-item download
  - `download_manifest_items()`: Download entire manifest
- **Based on**: heroic-gogdl download managers + lgogdownloader download logic

#### `galaxy_dl/cli.py`
- **Purpose**: Command-line interface
- **Commands**:
  - `login`: Authenticate with OAuth code
  - `info`: Show product builds
  - `list-items`: List depot items in manifest
  - `download`: Download depot items
- **Features**:
  - Progress tracking
  - Error handling
  - Configurable threads
  - Continue-on-error option

### 2. Configuration Files

#### `pyproject.toml`
- Modern Python packaging configuration
- Dependencies: requests (main requirement)
- Dev dependencies: pytest, black, ruff, mypy
- CLI entry point: `galaxy-dl` command

#### `README.md`
- Comprehensive documentation
- Quick start guide
- API reference
- Architecture overview
- Credits to reference projects

#### `example.py`
- Working example script
- Demonstrates authentication flow
- Shows download process
- Progress tracking example

## Key Improvements Over Reference Implementations

### From lgogdownloader (C++)

1. **Updated API Endpoints**
   - Correct manifest v2 URL: `https://cdn.gog.com/content-system/v2/meta/{path}`
   - Proper dependency URLs
   - Updated secure link generation

2. **Zlib Compression Handling**
   - Proper detection of zlib headers (0x78XX)
   - Correct decompression with ZLIB_WINDOW_SIZE=15
   - Fallback to plain JSON if not compressed

3. **Small Files Container Support**
   - Parsing of SFC metadata
   - Tracking of files within containers
   - Offset and size management

4. **CDN URL Prioritization**
   - Priority-based CDN selection
   - URL template parameter merging
   - Support for multiple CDN endpoints

5. **Path Handling**
   - Galaxy path format (ab/cd/abcdef...)
   - Cross-platform path normalization
   - Case-insensitive path resolution

### From heroic-gogdl (Python)

1. **Clean Python Architecture**
   - Object-oriented design
   - Type hints for IDE support
   - Proper exception handling

2. **Session Management**
   - Reusable HTTP sessions
   - Connection pooling
   - Automatic retry logic

3. **Data Models**
   - Dataclass-based models
   - JSON serialization/deserialization
   - Filtering and validation

### Original Enhancements

1. **Comprehensive Logging**
   - Structured logging throughout
   - Debug and info levels
   - Error tracking

2. **Progress Callbacks**
   - Byte-level progress tracking
   - Percentage calculation
   - User-defined callbacks

3. **Parallel Downloads**
   - ThreadPoolExecutor-based
   - Configurable worker count
   - Error isolation

4. **CLI Tool**
   - Easy command-line access
   - Multiple commands
   - Progress visualization

## How It Works

### Download Flow

1. **Authentication**
   ```
   User → OAuth Code → AuthManager → Access Token
   ```

2. **Getting Builds**
   ```
   Product ID → API.get_product_builds() → Build List
   ```

3. **Getting Manifest**
   ```
   Manifest Hash → API.get_manifest_v2() → Depot Items
   ```

4. **Downloading Items**
   ```
   Depot Item → API.get_secure_link() → CDN URLs
   → Downloader.download_item() → Fetch Chunks
   → Decompress → Verify → Assemble → File
   ```

### Chunk Download Process

```
1. Get CDN URLs from secure link
2. For each chunk:
   a. Build chunk path from MD5 hash (ab/cd/abcdef...)
   b. Try each CDN URL until success
   c. Fetch compressed chunk data
   d. Verify MD5 hash
   e. Decompress with zlib if needed
   f. Write to output file at correct offset
3. Verify final file hash
```

## API Endpoint Reference

| Endpoint | Purpose | Generation |
|----------|---------|------------|
| `/products/{id}/os/{platform}/builds` | Get builds | 1 & 2 |
| `/content-system/v2/meta/{path}` | Get v2 manifest | 2 |
| `/content-system/v1/manifests/...` | Get v1 manifest | 1 |
| `/products/{id}/secure_link` | Get download URLs | 1 & 2 |
| `/dependencies/repository` | Get dependencies | 2 |
| `/open_link` | Get dependency URLs | 2 |

## Usage Examples

### Basic Download
```python
from galaxy_dl import GalaxyAPI, AuthManager, GalaxyDownloader

auth = AuthManager()
api = GalaxyAPI(auth)
downloader = GalaxyDownloader(api)

items = api.get_depot_items("manifest_hash")
for item in items:
    downloader.download_item(item, "./output")
```

### CLI Usage
```bash
# Authenticate
galaxy-dl login YOUR_OAUTH_CODE

# Get product info
galaxy-dl info 1234567890

# List items
galaxy-dl list-items abc123def456

# Download
galaxy-dl download abc123def456 -o ./downloads -t 8
```

## File Structure

```
galaxy_dl/
├── __init__.py          # Package exports
├── api.py               # Galaxy API client (340 lines)
├── auth.py              # Authentication (211 lines)
├── cli.py               # Command-line interface (315 lines)
├── constants.py         # Endpoints and config (68 lines)
├── downloader.py        # Download manager (289 lines)
├── models.py            # Data models (320 lines)
└── utils.py             # Utilities (290 lines)
```

## Dependencies

**Required**:
- `requests` >= 2.31.0

**Optional (dev)**:
- pytest, pytest-cov (testing)
- black (formatting)
- ruff (linting)
- mypy (type checking)

## Testing Recommendations

1. **Unit Tests**
   - Test each model's JSON parsing
   - Test utility functions (hash, path, compression)
   - Mock API responses

2. **Integration Tests**
   - Test authentication flow
   - Test API endpoints
   - Test download flow

3. **End-to-End Tests**
   - Full download workflow
   - Error handling
   - Resume capability

## Future Enhancements

1. **V1 Manifest Support**
   - Full parsing of V1 manifests
   - V1 download flow

2. **Patch Support**
   - xdelta3 patching
   - Differential updates

3. **Caching**
   - Manifest caching
   - Chunk deduplication

4. **Advanced Features**
   - Bandwidth limiting
   - Mirror selection
   - Integrity checking

## Conclusion

The galaxy_dl library successfully combines the best aspects of both reference implementations:
- Modern Python architecture from heroic-gogdl
- Correct API usage and robust error handling from lgogdownloader
- Additional features like CLI, parallel downloads, and comprehensive logging

It provides a focused, maintainable solution for downloading GOG Galaxy CDN files.

