# Quick Start: Using Patches

This guide shows you how to use the patch framework for incremental game updates.

## Installation

Basic (download patches only):
```bash
pip install -e .
```

With patch application support:
```bash
pip install -e .[patch]
```

## Scenario 1: Check If Patches Available

```python
from galaxy_dl import GalaxyAPI, AuthManager

# Initialize
auth = AuthManager()
api = GalaxyAPI(auth)

# Get builds
builds = api.get_all_product_builds("1207658924", "windows")
old_build = builds[1]  # Build you have
new_build = builds[0]  # Build you want

# Check patch availability
patch_info = api.get_patch_info(
    "1207658924",
    old_build["buildId"],
    new_build["buildId"]
)

if patch_info and not patch_info.get('error'):
    print("✓ Patch available!")
    print(f"  From: {old_build['buildId']}")
    print(f"  To: {new_build['buildId']}")
else:
    print("✗ No patch - will need full download")
```

## Scenario 2: Download Patches

```python
from galaxy_dl import GalaxyAPI, AuthManager, Manifest, Patch

# Initialize
auth = AuthManager()
api = GalaxyAPI(auth)

# Get manifests
old_manifest = api.get_manifest_direct("1207658924", old_build["link"])
new_manifest = api.get_manifest_direct("1207658924", new_build["link"])

# Get patch
patch = Patch.get(
    api_client=api,
    manifest=new_manifest,
    old_manifest=old_manifest,
    language="en",
    dlc_product_ids=[]  # Add DLC IDs if needed
)

if not patch:
    print("No patch available")
    exit(1)

# Compare manifests
diff = Manifest.compare(new_manifest, old_manifest, patch)

print(f"Update requires:")
print(f"  {len(diff.new)} new files (full download)")
print(f"  {len(diff.changed)} changed files (full download)")
print(f"  {len(diff.patched)} files with patches")

# Get secure links for patches
links = api.get_secure_link(
    "1207658924",
    path="/",
    root_path="/patches/store"
)

# Download patches
import os
os.makedirs("patches", exist_ok=True)

for file_patch in diff.patched:
    delta_path = f"patches/{file_patch.target_path}.delta"
    print(f"Downloading patch: {delta_path}")
    
    # Download chunks (similar to regular file download)
    # Implementation depends on your download logic
    # Save chunks to delta_path
```

## Scenario 3: Apply Patches (with pyxdelta)

```python
import pyxdelta
import hashlib
import json

# Load patch metadata (saved during download)
with open("patch_manifest.json") as f:
    patch_data = json.load(f)

for patch_file in patch_data["patches"]:
    if patch_file["applied"]:
        print(f"✓ Already applied: {patch_file['target']}")
        continue
    
    source = f"game/{patch_file['source']}"
    delta = f"patches/{patch_file['delta_file']}"
    output = f"game/{patch_file['target']}.new"
    
    # Verify source file
    with open(source, "rb") as f:
        source_md5 = hashlib.md5(f.read()).hexdigest()
    
    if source_md5 != patch_file["md5_source"]:
        print(f"✗ Source MD5 mismatch: {patch_file['source']}")
        continue
    
    # Apply patch
    print(f"Applying patch: {patch_file['target']}")
    pyxdelta.patch(source, delta, output)
    
    # Verify output
    with open(output, "rb") as f:
        output_md5 = hashlib.md5(f.read()).hexdigest()
    
    if output_md5 == patch_file["md5_target"]:
        print(f"✓ Patch verified: {patch_file['target']}")
        
        # Replace old file
        import os
        os.replace(output, source)
        
        # Mark as applied
        patch_file["applied"] = True
    else:
        print(f"✗ Patch verification failed: {patch_file['target']}")

# Save updated metadata
with open("patch_manifest.json", "w") as f:
    json.dump(patch_data, f, indent=2)
```

## Scenario 4: Fallback to Full Download

```python
# If patch fails or not available, download full files
for item in diff.new + diff.changed:
    print(f"Full download: {item.path}")
    # Use GalaxyDownloader or manual chunk download
```

## Workflow Summary

1. **Check for patches** - Query GOG API
2. **Download patches** - Get .delta files
3. **Save metadata** - Track what was downloaded
4. **Apply patches** - Use pyxdelta or xdelta3
5. **Verify results** - Check MD5 hashes
6. **Fallback** - Full download if needed

## Tips

- Always verify MD5 before and after patching
- Keep .delta files until verified
- Store patch metadata for resume capability
- Test patch application on non-critical files first
- Have fallback to full download ready

## Error Handling

```python
try:
    patch = Patch.get(api, new_manifest, old_manifest, "en", [])
    if patch:
        # Use patches
        diff = Manifest.compare(new_manifest, old_manifest, patch)
    else:
        # No patch - full download
        diff = Manifest.compare(new_manifest, old_manifest, None)
except Exception as e:
    print(f"Patch query failed: {e}")
    # Fallback to full download
    diff = Manifest.compare(new_manifest, old_manifest, None)
```

## See Also

- `docs/PATCHES.md` - Complete patch documentation
- `docs/PATCH_IMPLEMENTATION.md` - Implementation details
- `examples/test_patch_framework.py` - Test script
