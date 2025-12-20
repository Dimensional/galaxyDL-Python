#!/usr/bin/env python3
import json
from pathlib import Path

# Load repository to get manifest UUID
repo_path = Path('The Witcher 2/v1/manifests/1207658930/osx/37397519/repository.json')
with open(repo_path) as f:
    data = json.load(f)

manifest_file = data['product']['depots'][0]['manifest']
manifest_uuid = manifest_file.replace('.json', '')

# Load manifest
manifest_path = Path(f'The Witcher 2/v1/manifests/1207658930/osx/37397519/{manifest_uuid}.json')
with open(manifest_path) as f:
    manifest = json.load(f)

# Get all files with offsets and sizes
files = []
for file_data in manifest['depot']['files']:
    if file_data.get('size', 0) > 0 and 'offset' in file_data:
        files.append({
            'path': file_data['path'],
            'offset': file_data['offset'],
            'size': file_data['size']
        })

# Sort by offset
files.sort(key=lambda f: f['offset'])

print(f'Total files: {len(files)}')
print(f'\nFiles around index 35-60 (where slowdown occurs):')
print(f'{"Index":<6} {"Offset":<15} {"Size (MB)":<12} {"Path"}')
print('=' * 100)

for i, f in enumerate(files[35:60], 36):
    size_mb = f['size'] / (1024 * 1024)
    print(f'{i:<6} {f["offset"]:<15,} {size_mb:<12.2f} {f["path"]}')

print(f'\nLargest files in the archive:')
files_by_size = sorted(files, key=lambda f: f['size'], reverse=True)
for i, f in enumerate(files_by_size[:20], 1):
    size_mb = f['size'] / (1024 * 1024)
    offset_rank = next(idx for idx, file in enumerate(files, 1) if file['offset'] == f['offset'])
    print(f'{i:<3}. Size: {size_mb:>8.2f} MB  (at offset rank #{offset_rank:<4})  {f["path"]}')
