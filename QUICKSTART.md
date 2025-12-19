# Quick Start Guide for Galaxy DL

This guide will help you get started with the galaxy_dl library quickly.

## Prerequisites

- Python 3.8 or higher
- pip package manager
- GOG account

## Installation

### 1. Install the library

From the project directory:

```bash
pip install -e .
```

Or install just the dependencies:

```bash
pip install requests
```

### 2. Set up Python path (if not installing)

If you don't want to install, add to your Python path:

```python
import sys
sys.path.insert(0, '/path/to/galaxyDL-Python')
```

## First Steps

### Step 1: Authenticate with GOG

1. **Get OAuth Code**:
   
   Open this URL in your browser:
   ```
   https://auth.gog.com/auth?client_id=46899977096215655&redirect_uri=https%3A%2F%2Fembed.gog.com%2Fon_login_success%3Forigin%3Dclient&response_type=code&layout=client2
   ```

2. **Login to GOG**

3. **Copy the code parameter** from the redirect URL. It will look like:
   ```
   https://embed.gog.com/on_login_success?origin=client&code=XXXXXXXXXXXXXX
   ```
   Copy the `XXXXXXXXXXXXXX` part.

4. **Authenticate**:

   **Option A: Using CLI**
   ```bash
   galaxy-dl login XXXXXXXXXXXXXX
   ```

   **Option B: Using Python**
   ```python
   from galaxy_dl import AuthManager
   
   auth = AuthManager()
   auth.login_with_code("XXXXXXXXXXXXXX")
   ```

Your credentials are now saved in `~/.config/galaxy_dl/auth.json` (or `%APPDATA%\galaxy_dl\auth.json` on Windows).

### Step 2: Find What to Download

You need two things:
1. **Product ID**: The GOG product identifier
2. **Manifest Hash**: The specific version/build manifest

**Get Product Builds**:

```bash
galaxy-dl info <PRODUCT_ID>
```

Or in Python:
```python
from galaxy_dl import GalaxyAPI, AuthManager

auth = AuthManager()
api = GalaxyAPI(auth)

builds = api.get_product_builds(product_id="1234567890")
for build in builds["items"]:
    print(f"Build: {build['build_id']}, Version: {build.get('version_name', 'unknown')}")
```

**List Items in a Manifest**:

```bash
galaxy-dl list-items <MANIFEST_HASH>
```

Or in Python:
```python
items = api.get_depot_items("abc123def456")
for item in items:
    print(f"{item.path}: {len(item.chunks)} chunks, {item.total_size_compressed} bytes")
```

### Step 3: Download Files

**Option A: CLI (Recommended for beginners)**

```bash
# Download all items from a manifest
galaxy-dl download <MANIFEST_HASH> -o ./my_downloads

# With more threads for faster downloads
galaxy-dl download <MANIFEST_HASH> -o ./my_downloads -t 8

# Continue even if some files fail
galaxy-dl download <MANIFEST_HASH> -o ./my_downloads --continue-on-error
```

**Option B: Python Script**

```python
from galaxy_dl import GalaxyAPI, GalaxyDownloader, AuthManager

# Initialize
auth = AuthManager()
api = GalaxyAPI(auth)
downloader = GalaxyDownloader(api, max_workers=8)

# Get items to download
manifest_hash = "abc123def456"
items = api.get_depot_items(manifest_hash)

# Download with progress tracking
for item in items:
    print(f"Downloading {item.path}...")
    
    def show_progress(downloaded, total):
        percent = (downloaded / total) * 100 if total > 0 else 0
        print(f"  {percent:.1f}% ({downloaded:,}/{total:,} bytes)", end='\r')
    
    try:
        output_path = downloader.download_item(
            item,
            output_dir="./my_downloads",
            progress_callback=show_progress
        )
        print(f"\n  ✓ Saved to: {output_path}")
    except Exception as e:
        print(f"\n  ✗ Failed: {e}")
```

## Common Tasks

### Download a Specific Product

```python
from galaxy_dl import GalaxyAPI, GalaxyDownloader, AuthManager

auth = AuthManager()
api = GalaxyAPI(auth)
downloader = GalaxyDownloader(api)

# Get latest build
product_id = "1234567890"
builds = api.get_product_builds(product_id)
latest_build = builds["items"][0]

# Extract manifest hash (structure varies by build)
manifest_hash = latest_build.get("manifest_id") or latest_build.get("generation_hash")

# Download
downloader.download_manifest_items(
    manifest_hash=manifest_hash,
    output_dir="./downloads",
    product_id=product_id
)
```

### Download with Custom Filtering

```python
from galaxy_dl.models import Manifest

# Get manifest data
manifest_data = api.get_manifest_v2("manifest_hash")
manifest = Manifest.from_json_v2(manifest_data)

# Filter depots by language
filtered_depots = manifest.get_filtered_depots(
    language="en",
    bitness="64"
)

# Download filtered items
for depot in filtered_depots:
    items = api.get_depot_items(depot.manifest)
    for item in items:
        downloader.download_item(item, "./downloads")
```

### Resume Interrupted Downloads

The library automatically handles resume by re-downloading failed chunks. Just run the same download command again.

### Verify Downloaded Files

```python
from galaxy_dl import utils

# Verify MD5 hash
actual_hash = utils.calculate_hash("downloaded_file.bin", algorithm="md5")
expected_hash = "abc123def456..."

if actual_hash.lower() == expected_hash.lower():
    print("✓ File verified!")
else:
    print("✗ Hash mismatch!")
```

## Troubleshooting

### "Not authenticated" error

Re-run the login process. Your token may have expired.

```bash
galaxy-dl login YOUR_NEW_CODE
```

### Download fails with "Failed to get secure links"

Make sure you're using the correct product ID and that you own the product on GOG.

### Hash verification fails

The file may be corrupted. Try downloading again. You can skip verification with `--no-verify` flag (not recommended).

### Slow downloads

Increase the number of worker threads:

```bash
galaxy-dl download MANIFEST -t 16
```

Or in Python:
```python
downloader = GalaxyDownloader(api, max_workers=16)
```

### Import errors

Make sure the library is installed or the path is set correctly:

```bash
pip install -e .
```

## Next Steps

- Read the [full README](README.md) for detailed documentation
- Check [IMPLEMENTATION.md](IMPLEMENTATION.md) for architecture details
- See [example.py](example.py) for a complete working example
- Explore the API in `galaxy_dl/api.py` for advanced usage

## Getting Help

- Check the logs (use `--verbose` flag for detailed output)
- Review error messages carefully
- Ensure you're using the latest version
- Check that heroic-gogdl and lgogdownloader are available as references (read-only)

## Important Notes

1. **Never edit heroic-gogdl or lgogdownloader** - they are read-only references
2. **Respect GOG's Terms of Service** - only download content you own
3. **This is unofficial** - not affiliated with or endorsed by GOG
4. **Credentials are sensitive** - keep your auth.json file secure

Happy downloading! 🚀

