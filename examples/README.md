# Examples

Practical examples for using galaxy-dl.

## Getting Started

1. **Authentication Required**: Run `list_library.py` first to authenticate
2. **Each example** demonstrates specific functionality
3. **All examples** include helpful prompts and error handling

## Examples

### [list_library.py](list_library.py)
**Browse your GOG library**

Shows how to:
- Authenticate with GOG
- List all owned games
- Get detailed information for each game
- Display available platforms and extras

```bash
python examples/list_library.py
```

---

### [build_selection.py](build_selection.py)
**Interactive build selector**

Shows how to:
- List all available builds for a game
- Display V1 vs V2 generation info
- Let user select from builds list
- Get manifest efficiently using `get_manifest_from_build()`

```bash
python examples/build_selection.py
```

---

### [delisted_builds.py](delisted_builds.py)
**Access delisted builds using gogdb.org**

Shows how to:
- Use repository_id from gogdb.org for V1 builds
- Use manifest links for V2 builds
- Access builds without querying builds API
- Handle delisted/removed builds

```bash
python examples/delisted_builds.py
```

**Note:** Get build information from [gogdb.org](https://www.gogdb.org/) for delisted builds.

---

### [download_game.py](download_game.py)
**Complete download workflow**

Shows the full process:
1. Browse your game library
2. Select a game
3. Choose platform
4. Select build
5. Get manifest
6. Download files

```bash
python examples/download_game.py
```

---

## Common Patterns

### Authenticating

```python
from galaxy_dl import AuthManager

auth = AuthManager()

if not auth.is_authenticated():
    # Get code from GOG OAuth URL
    code = input("Enter OAuth code: ")
    auth.login_with_code(code)
```

### Listing Games

```python
from galaxy_dl import GalaxyAPI

api = GalaxyAPI(auth)
game_ids = api.get_owned_games()
games = api.get_owned_games_with_details(limit=10)
```

### Getting Builds

```python
# Get ALL builds (recommended)
builds = api.get_all_product_builds(product_id, "windows")

# User selects from list
selected_build = builds["items"][0]

# Get manifest efficiently
manifest = api.get_manifest_from_build(product_id, selected_build)
```

### Downloading

```python
from galaxy_dl import GalaxyDownloader

downloader = GalaxyDownloader(api, max_workers=8)

# Download with progress
def progress(downloaded, total):
    print(f"Progress: {downloaded}/{total}")

path = downloader.download_item(
    item,
    output_dir="./downloads",
    progress_callback=progress
)
```

---

## Tips

1. **Use `get_all_product_builds()`** - Queries both generation endpoints to get all builds
2. **Use `get_manifest_from_build()`** - More efficient when user selects from list
3. **Use `get_manifest_direct()`** - For delisted builds with gogdb.org data
4. **Check gogdb.org** - For repository IDs and historical build data
5. **Multi-threading** - Both V1 and V2 downloads use parallel workers

---

## See Also

- [API Reference](../API_REFERENCE.md) - Complete API documentation
- [README](../README.md) - Library overview
- [GENERATION_DETECTION.md](../GENERATION_DETECTION.md) - Understanding V1 vs V2
- [DELISTED_BUILDS.md](../DELISTED_BUILDS.md) - Accessing delisted builds
