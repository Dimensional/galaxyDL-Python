# GOG Library API Comparison

This document explains the differences between the various GOG API endpoints for listing owned games.

## Summary - Which API Should You Use?

**For a complete library list:** Use `get_owned_games()` → `/user/data/games`
- Returns **ALL 787 games** including delisted titles
- This is what `lgogdownloader` uses for completeness

**For rich UI display:** Use `get_filtered_products()` → `/account/getFilteredProducts`
- Returns **only 498 games** but with metadata (ratings, platforms, updates)
- Good for showing users their "active" library

**For download links:** Use `get_game_details(game_id)` → `/account/gameDetails/{game_id}.json`
- Get installers, extras, DLCs, and actual download URLs
- Use game IDs from `get_owned_games()` to ensure you can access ALL games

## API Methods

### 1. `get_owned_games()` - User Data Games Endpoint ⭐ RECOMMENDED FOR COMPLETENESS

**Endpoint:** `https://embed.gog.com/user/data/games`

**Returns:** Simple list of owned game IDs

**Count:** Returns the **complete** list of all owned games, including:
- Active games
- Delisted games (no longer available for purchase but still owned)
- Hidden games
- Games that may not have current downloadable builds
- DLC and expansions counted separately
- Special editions and bundles

**Example Response:**
```json
{
  "owned": [1207658691, 1207658713, 1207658805, ...]
}
```

**Pros:**
- Simple and fast
- Returns **ALL owned games** (787 in test case)
- Includes delisted/unavailable games
- **This is what lgogdownloader uses**

**Cons:**
- No metadata (title, platforms, etc.)
- Requires additional API calls to get game details

### 2. `get_filtered_products()` / `get_all_filtered_products()` - Filtered Products Endpoint ⚠️ INCOMPLETE

**Endpoint:** `https://embed.gog.com/account/getFilteredProducts?mediaType=1&page=X`

**Returns:** Paginated list of games with rich metadata

**Count:** Returns **only 498 out of 787 games** - excludes delisted titles and some DLCs

**Important:** Even with all parameter combinations (`system`, `hiddenFlag`), this endpoint only returns 498 games, missing 289 items that appear in `/user/data/games`.

**Example Response:**
```json
{
  "totalProducts": 498,
  "totalPages": 5,
  "page": 1,
  "productsPerPage": 100,
  "products": [
    {
      "id": 2099051765,
      "title": "9 Years of Shadows",
      "slug": "9_years_of_shadows",
      "category": "Action",
      "rating": 4,
      "worksOn": {"Windows": true, "Mac": false, "Linux": false},
      "updates": 1,
      "isNew": false,
      "isHidden": false,
      "availability": {"isAvailable": true, "isAvailableInAccount": true}
    }
  ]
}
```

**Pros:** for basic info
- Filterable by search, platform, tags
- Pagination support (100 items per page)
- Good for building a UI that shows "currently available" games

**Cons:**
- **Excludes 289 games** (delisted, certain DLC, etc.)
- Returns fewer games than `get_owned_games()` (498 vs 787)
- Multiple requests needed to get all pages
- **Cannot be used for complete library access**
- The `system` parameter adds 2 more games (500 total) but the API still only returns 498 unique IDidden games, etc.)
- # 3. `get_game_details(game_id)` - Game Details Endpoint

**Endpoint:** `https://embed.gog.com/account/gameDetails/{game_id}.json`

**Returns:** Complete details for a specific game including downloads, extras, and DLCs

**Example Response:**
```json
{
  "title": "Unreal Tournament 2004 Editor's Choice Edition",
  "backgroundImage": "//images-4.gog.com/...",
  "downloads": [...],  // Installer download links per language/platform
  "extras": [...],     // Manuals, wallpapers, soundtracks, etc.
  "dlcs": [],
  "tags": [],
  "releaseTimestamp": 1227585600,
  "changelog": null,
  "forumLink": "https://embed.gog.com/forum/..."
}
```

**Pros:**
- Complete download information (installers, extras)
- Works with ALL game IDs from `get_owned_games()`
- Includes game details even for delisted titles
- Provides actual download URLs

**Cons:**
- Requires one API call per game
- Can be slow for large libraria **hybrid approach**:

1. **Get complete game list**: Uses `/user/data/games` (like `get_owned_games()`) to get ALL 787 game IDs
2. **Get metadata for display**: Uses `/account/getFilteredProducts` to show rich information (title, updates, ratings)
3. *✅ RECOMMENDED: Get complete library with download links
```python
from galaxy_dl import GalaxyAPI, AuthManager

auth = AuthManager()
api = GalaxyAPI(auth)

# Get ALL game IDs (complete list - 787 games)
game_ids = api.get_owned_games()

# Get details and download links for each game
for game_id in game_ids:
    details = api.get_game_details(game_id)
    print(f"{details['title']}")
    
    # Access installers
    for lang, platforms in details.get('downloads', []):
        print(f"  Language: {lang}")
        for platform, files in platforms.items():
            print(f"    {platform}: {len(files)} installer(s)")
    
    # Access extras (manuals, wallpapers, etc.)
    for extra in details.get('extras', []):
        print(f"  Extra: {extra['name']} ({extra['size']})")
```

### Get games with rich metadata (incomplete but fast):
```python
api = GalaxyAPI(auth_manager)
# WARNING: Only returns 498 games, missing 289 delisted titles
games = api.get_all_filtered_products(media_type=1)

for game in games:
    print(f"{game['title']} - Rating: {game['rating']}/5")
    print(f"  Platforms: {[p for p, avail in game['worksOn'].items() if avail]}")
```

### Search for specific games:
```python
api = GalaxyAPI(auth_manager)
witcher_games = api.get_all_filtered_products(search="Witcher")
# Note: Only searches within the 498 "available" games
```

### Filter by platform (still incomplete):
```python
api = GalaxyAPI(auth_manager)
# Returns at most 500 games, still missing 287
windows_games = api.get_all_filtered_products(system="Windows")
```

### Complete library archival example:
```python
from galaxy_dl import GalaxyAPI, AuthManager

auth = AuthManager()
api = GalaxyAPI(auth)

# Step 1: Get complete list
all_game_ids = api.get_owned_games()
print(f"You own {len(all_game_ids)} games")

# Step 2: Get details for archival
for idx, game_id in enumerate(all_game_ids, 1):
    print(f"Processing {idx}/{len(all_game_ids)}...")
    details = api.get_game_details(game_id)
    
    # Save game info
    # Download installers using manualUrl or downloaderUrl
    # Archive extras, DLCs, etc.ars to have intentional filtering that excludes certain product types, regardless of parameters used.

### Investigation Results

Testing revealed:
- **No `system` parameter**: 498 products
- **With `system=Windows/Mac/Linux/all`**: 500 products (but only 498 unique IDs collected)
- **With `hiddenFlag=1`**: 0 products (no hidden products exist)
- **All combinations tested**: Maximum 498 unique game IDs

**Conclusion**: The `getFilteredProducts` API cannot return all owned games, even with all possible parameter combination
3. **Hidden/Unavailable Games**: Games marked as `isAvailable: false` or that have been removed from your account view.

4. **Platform Filtering**: The filtered products endpoint may apply implicit platform filters.

## Which One to Use?

### Use `get_owned_games()` when:
- You need a complete list of ALL owned games
- You're archiving your library
- You need to access delisted games
- You only need game IDs for further API calls

### Use `get_filtered_products()` when:
- You want rich metadata without extra API calls
- You're building a game library UI
- You want to filter or search games
- You only care about currently downloadable games
- You want to show platform compatibility, ratings, updates

## lgogdownloader Approach

The `lgogdownloader` tool uses the user data games endpoint (similar to `get_owned_games()`) because it prioritizes completeness and the ability to download ALL owned content, including delisted games.

## Code Examples

### Get ALL games (including delisted):
```python
api = GalaxyAPI(auth_manager)
game_ids = api.get_owned_games()  # Returns 787 games
```

### Get games with metadata (filtered):
```python
api = GalaxyAPI(auth_manager)
games = api.get_all_filtered_products(media_type=1)  # Returns 498 games with metadata
```

### Search for specific games:
```python
api = GalaxyAPI(auth_manager)
witcher_games = api.get_all_filtered_products(search="Witcher")
```

### Filter by platform:
```python
api = GalaxyAPI(auth_manager)
windows_games = api.get_all_filtered_products(system="Windows")
```
