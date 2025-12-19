# Handling Delisted Builds

## Overview

GOG sometimes delists builds from the public builds API while keeping the actual manifest files accessible on the CDN. This guide explains how to download delisted builds using data from external sources like [gogdb.org](https://www.gogdb.org).

## Understanding Build IDs vs Repository IDs

GOG uses different identifiers for builds:

### Build ID
- **User-facing identifier** shown in builds API
- Example: `"3101"`
- Shown in builds JSON as `"build_id"`
- **Not used in V1 manifest URLs**

### Repository ID (Legacy Build ID)
- **Internal identifier** used in V1 manifest URLs
- Example: `"24085618"`
- Shown in builds JSON as `"legacy_build_id"`
- Also called "Repository timestamp" on gogdb.org
- **This is what V1 URLs actually use**

### V1 URL Structure

```
https://cdn.gog.com/content-system/v1/manifests/{product_id}/{platform}/{repository_id}/repository.json
                                                                         ^^^^^^^^^^^^^^
                                                                         NOT build_id!
```

Example:
```
Product ID: 1207658924 (The Witcher Enhanced Edition)
Platform: osx
Build ID: 3101 (user-facing)
Repository ID: 24085618 (used in URL)

URL: https://cdn.gog.com/content-system/v1/manifests/1207658924/osx/24085618/repository.json
```

## When Builds Are Listed

If a build still appears in the builds API, you can use normal methods:

```python
from galaxy_dl.api import GalaxyAPI
from galaxy_dl.auth import AuthManager

auth = AuthManager(...)
api = GalaxyAPI(auth)

# Automatic - library handles legacy_build_id extraction
manifest = api.get_manifest(
    product_id="1207658924",
    build_id="3101",  # User-facing ID
    platform="osx"
)

# The manifest object has both IDs
print(f"Build ID: {manifest.build_id}")           # "3101"
print(f"Repository ID: {manifest.repository_id}") # "24085618"
```

**Builds API Response:**
```json
{
  "items": [
    {
      "build_id": "3101",
      "legacy_build_id": 24085618,
      "generation": 1,
      "link": "https://cdn.gog.com/content-system/v1/manifests/1207658924/osx/24085618/repository.json"
    }
  ]
}
```

The library automatically extracts `legacy_build_id` and uses it in the URL.

## When Builds Are Delisted

If a build is removed from builds API but files remain on CDN, use direct access methods.

### Method 1: Direct Repository ID Access

Use data from gogdb.org or archived build info:

```python
# From gogdb.org
# Product: The Witcher Enhanced Edition (1207658924)
# Platform: Mac (osx)
# Repository timestamp: 24085618

manifest_json = api.get_manifest_v1_direct(
    product_id="1207658924",
    repository_id="24085618",
    platform="osx"
)

if manifest_json:
    manifest = Manifest.from_json_v1(manifest_json, "1207658924")
    manifest.repository_id = "24085618"
```

### Method 2: Direct URL Access

Copy URL directly from gogdb.org or construct manually:

```python
# From gogdb.org build record or manual construction
url = "https://cdn.gog.com/content-system/v1/manifests/1207658924/osx/24085618/repository.json"

manifest_json = api.get_manifest_by_url(url)

if manifest_json:
    manifest = Manifest.from_json_v1(manifest_json, "1207658924")
    manifest.repository_id = "24085618"
```

### Method 3: Low-Level Access

For maximum control:

```python
# Construct URL manually
product_id = "1207658924"
platform = "osx"
repository_id = "24085618"

url = f"https://cdn.gog.com/content-system/v1/manifests/{product_id}/{platform}/{repository_id}/repository.json"

manifest_json = api.get_manifest_by_url(url)
```

## V2 Delisted Builds

V2 builds use manifest hashes instead of repository IDs. If you have the hash:

```python
# From gogdb.org or archived data
manifest_hash = "abc123def456..."

# Direct access
manifest_json = api.get_manifest_v2(manifest_hash)

if manifest_json:
    manifest = Manifest.from_json_v2(manifest_json)
```

Or with full URL:

```python
# V2 URL pattern
url = "https://cdn.gog.com/content-system/v2/meta/abc123def456..."

manifest_json = api.get_manifest_by_url(url)

if manifest_json:
    manifest = Manifest.from_json_v2(manifest_json)
```

## Using gogdb.org Data

### Finding Repository ID

1. Go to [gogdb.org](https://www.gogdb.org)
2. Search for your game
3. Navigate to "Builds" tab
4. Find the build you want
5. Look for **"Repository timestamp"** field - this is the repository_id

Example gogdb.org build record:
```
Build ID: 3101
Version: 
Generation: 1
Repository timestamp: 24085618  ← This is repository_id!
```

### Constructing V1 URL from gogdb.org

```python
def build_v1_url_from_gogdb(product_id, platform, repository_timestamp):
    """
    Construct V1 manifest URL using gogdb.org data.
    
    Args:
        product_id: Product ID from gogdb
        platform: windows, osx, or linux
        repository_timestamp: "Repository timestamp" from gogdb build record
    """
    return (
        f"https://cdn.gog.com/content-system/v1/manifests/"
        f"{product_id}/{platform}/{repository_timestamp}/repository.json"
    )

# Example usage
url = build_v1_url_from_gogdb("1207658924", "osx", "24085618")
manifest_json = api.get_manifest_by_url(url)
```

## Complete Delisted Build Download Example

```python
from galaxy_dl.api import GalaxyAPI
from galaxy_dl.auth import AuthManager
from galaxy_dl.models import Manifest
from galaxy_dl.downloader import GalaxyDownloader

# Setup
auth = AuthManager(...)
api = GalaxyAPI(auth)
downloader = GalaxyDownloader(api)

# From gogdb.org
product_id = "1207658924"
platform = "osx"
repository_id = "24085618"  # Repository timestamp from gogdb

# Option 1: Direct repository ID
manifest_json = api.get_manifest_v1_direct(product_id, repository_id, platform)

# Option 2: Direct URL
url = f"https://cdn.gog.com/content-system/v1/manifests/{product_id}/{platform}/{repository_id}/repository.json"
manifest_json = api.get_manifest_by_url(url)

# Create manifest object
if manifest_json:
    manifest = Manifest.from_json_v1(manifest_json, product_id)
    manifest.generation = 1
    manifest.repository_id = repository_id
    
    # Download (assuming V1 downloader is implemented)
    downloader.download(manifest, output_dir="./downloads")
else:
    print(f"Manifest not found - may be truly deleted or URL incorrect")
```

## Verifying Delisted Build Availability

Before attempting download, check if manifest exists:

```python
import requests

def check_v1_manifest_exists(product_id, platform, repository_id):
    """
    Check if V1 manifest is still accessible.
    
    Returns:
        tuple: (exists: bool, url: str)
    """
    url = (
        f"https://cdn.gog.com/content-system/v1/manifests/"
        f"{product_id}/{platform}/{repository_id}/repository.json"
    )
    
    try:
        response = requests.head(url, timeout=10)
        exists = response.status_code == 200
        return exists, url
    except:
        return False, url

# Usage
exists, url = check_v1_manifest_exists("1207658924", "osx", "24085618")
if exists:
    print(f"Manifest accessible: {url}")
    manifest_json = api.get_manifest_by_url(url)
else:
    print(f"Manifest not accessible: {url}")
```

## Common Scenarios

### Scenario 1: Build shown on gogdb but not in builds API

This happens when GOG delists old builds.

**Solution:** Use `get_manifest_v1_direct()` with repository timestamp from gogdb

### Scenario 2: Have build_id but not repository_id

If builds API still shows it, use normal `get_manifest()` - it extracts legacy_build_id automatically.

If delisted, you need to find repository_id from:
- gogdb.org archive
- Personal archives
- Community databases

### Scenario 3: Want to archive all builds (including future delistings)

Store both `build_id` and `legacy_build_id` from builds API:

```python
builds = api.get_product_builds(product_id, platform, generation="1")

for build in builds.get("items", []):
    archive_record = {
        "build_id": build["build_id"],
        "legacy_build_id": build["legacy_build_id"],
        "generation": build["generation"],
        "url": build["link"],
        "date": build["date_published"]
    }
    # Store archive_record for future use
```

## API Method Summary

| Method | Use Case | Required Info |
|--------|----------|---------------|
| `get_manifest()` | Listed builds | product_id, build_id |
| `get_manifest_v1_direct()` | Delisted V1 builds | product_id, repository_id, platform |
| `get_manifest_v2()` | Delisted V2 builds | manifest_hash |
| `get_manifest_by_url()` | Any delisted build | Full URL |

## Troubleshooting

### 404 Not Found
- Verify repository_id is correct (not build_id!)
- Check platform (windows/osx/linux)
- Confirm product_id
- Manifest may be truly deleted from CDN

### 401 Unauthorized
- V1 manifests are usually public, shouldn't need auth
- Check if token is valid anyway
- Try without authentication

### Empty Response
- URL may be correct but file deleted
- Check gogdb.org for alternative builds
- Verify generation (1 vs 2)

## External Resources

- **gogdb.org**: Primary source for delisted build data
- **PCGamingWiki**: Sometimes has build IDs
- **Community Archives**: Reddit, Discord communities
- **Personal Archives**: If you've run builds API queries before delisting
