"""Verify raw manifest files are properly saved as zlib-compressed."""
import zlib
import json
from pathlib import Path

# Test root manifest
root_file = Path("witcher2_patches/meta/patches/67cf3e9356b831e8738b482ed3a8dabf")
print("Root Manifest:")
print(f"  File: {root_file}")
print(f"  Size: {root_file.stat().st_size} bytes")

data = root_file.read_bytes()
print(f"  First 20 bytes: {data[:20].hex()}")

# Decompress
decompressed = zlib.decompress(data, 15)
print(f"  Decompressed size: {len(decompressed)} bytes")

# Parse JSON
manifest = json.loads(decompressed)
print(f"  Algorithm: {manifest.get('algorithm')}")
print(f"  Depots: {len(manifest.get('depots', []))}")
print(f"  Client ID: {manifest.get('clientId')[:20]}...")
print("  ✓ Valid zlib-compressed JSON")

# Test depot manifest
depot_file = Path("witcher2_patches/meta/patches/8a5a6f3f57ef5b21a855b4a0f0e3523f")
print("\nDepot Manifest:")
print(f"  File: {depot_file}")
print(f"  Size: {depot_file.stat().st_size} bytes")

data = depot_file.read_bytes()
print(f"  First 20 bytes: {data[:20].hex()}")

# Decompress
decompressed = zlib.decompress(data, 15)
print(f"  Decompressed size: {len(decompressed)} bytes")

# Parse JSON
manifest = json.loads(decompressed)
items = manifest.get('depot', {}).get('items', [])
print(f"  Items: {len(items)}")
if items:
    print(f"  First item chunks: {len(items[0].get('chunks', []))}")
print("  ✓ Valid zlib-compressed JSON")

print("\n✓ All manifests properly saved as zlib-compressed files")
