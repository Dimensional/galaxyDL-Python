"""
Library Cache Module - Fast Lookup Index

Provides lightweight JSON cache of basic game info (ID, title, slug) for fast searches.
This is a SIMPLE LOOKUP INDEX, not a comprehensive database.

NOTE: This is separate from examples/list_library.py which creates gog_library.db
      
      library_cache.json (this module):
      - Purpose: Fast game ID/slug lookups during downloads
      - Size: ~78 KB (lightweight)
      - Data: Only id, title, slug
      - Used by: CLI commands, download examples
      
      gog_library.db (examples/list_library.py):
      - Purpose: Comprehensive library archival and exploration
      - Size: ~9 MB (complete metadata)
      - Data: Full game details, DLCs, downloads, images, changelog
      - Used by: SQLite queries, library exploration
      
Similar to how lgogdownloader has cache files + config/data structures.
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional
import logging

from galaxy_dl import constants


class LibraryCache:
    """
    Manages local cache of GOG library for faster game lookups.
    
    Cache structure:
    {
        "timestamp": 1234567890,
        "games": {
            "123456": {
                "id": 123456,
                "title": "The Witcher 3",
                "slug": "the_witcher_3"
            },
            ...
        }
    }
    """
    
    def __init__(self, cache_path: Optional[str] = None):
        """
        Initialize library cache.
        
        Args:
            cache_path: Path to cache file (default: ~/.config/galaxy_dl/library_cache.json)
        """
        if cache_path:
            self.cache_path = Path(cache_path)
        else:
            config_dir = Path.home() / ".config" / "galaxy_dl"
            config_dir.mkdir(parents=True, exist_ok=True)
            self.cache_path = config_dir / "library_cache.json"
        
        self.logger = logging.getLogger("galaxy_dl.library_cache")
        self._cache_data = None
    
    def load(self) -> Dict[str, Dict]:
        """
        Load cache from disk.
        
        Returns:
            Dictionary of game_id -> game_info
        """
        if self._cache_data is not None:
            return self._cache_data.get("games", {})
        
        if not self.cache_path.exists():
            self.logger.debug("Cache file not found")
            return {}
        
        try:
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                self._cache_data = json.load(f)
            
            games = self._cache_data.get("games", {})
            timestamp = self._cache_data.get("timestamp", 0)
            age_days = (time.time() - timestamp) / 86400
            
            self.logger.info(f"Loaded {len(games)} games from cache (age: {age_days:.1f} days)")
            return games
            
        except Exception as e:
            self.logger.warning(f"Failed to load cache: {e}")
            return {}
    
    def save(self, games: Dict[str, Dict]) -> None:
        """
        Save cache to disk.
        
        Args:
            games: Dictionary of game_id -> game_info
        """
        try:
            cache_data = {
                "timestamp": int(time.time()),
                "games": games
            }
            
            # Ensure directory exists
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write atomically
            temp_path = self.cache_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            # Replace old cache
            temp_path.replace(self.cache_path)
            
            self._cache_data = cache_data
            self.logger.info(f"Saved {len(games)} games to cache")
            
        except Exception as e:
            self.logger.error(f"Failed to save cache: {e}")
    
    def update_from_api(self, api) -> Dict[str, Dict]:
        """
        Update cache by fetching fresh data from API.
        
        Args:
            api: GalaxyAPI instance
            
        Returns:
            Dictionary of game_id -> game_info
        """
        self.logger.info("Updating library cache from API...")
        
        # Get all owned game IDs
        game_ids = api.get_owned_games()
        
        if not game_ids:
            self.logger.warning("No games found in library")
            return {}
        
        self.logger.info(f"Found {len(game_ids)} games, fetching details...")
        
        games = {}
        skipped = 0
        for idx, game_id in enumerate(game_ids, 1):
            try:
                # First check if game has downloadable content
                details = api.get_game_details(game_id)
                
                # Skip DLC entries, empty responses, and games without downloads
                # DLC items return empty list [], games without content return empty dict or list
                if not details or not isinstance(details, dict) or not details.get("title"):
                    skipped += 1
                    if idx % 10 == 0:
                        self.logger.info(f"  Fetched {idx}/{len(game_ids)} games...")
                    continue
                
                # Get slug from product info (game_details doesn't include it)
                try:
                    product_info = api.get_product_info(str(game_id))
                    slug = product_info.get("slug", "") if isinstance(product_info, dict) else ""
                except Exception:
                    slug = ""
                
                games[str(game_id)] = {
                    "id": game_id,
                    "title": details.get("title", "Unknown"),
                    "slug": slug
                }
                
                # Progress indicator
                if idx % 10 == 0:
                    self.logger.info(f"  Fetched {idx}/{len(game_ids)} games...")
                
            except Exception as e:
                self.logger.debug(f"Skipping game {game_id}: {e}")
                skipped += 1
                skipped += 1
                continue
        
        if skipped > 0:
            self.logger.info(f"Skipped {skipped} entries (DLC or unavailable games)")
        
        # Save to disk
        self.save(games)
        
        return games
    
    def get_age_days(self) -> Optional[float]:
        """
        Get cache age in days.
        
        Returns:
            Age in days, or None if cache doesn't exist
        """
        # Use cached data if already loaded
        if self._cache_data is not None:
            timestamp = self._cache_data.get("timestamp", 0)
            return (time.time() - timestamp) / 86400
        
        # Otherwise read from file
        if not self.cache_path.exists():
            return None
        
        try:
            with open(self.cache_path, 'r') as f:
                data = json.load(f)
            
            timestamp = data.get("timestamp", 0)
            return (time.time() - timestamp) / 86400
            
        except Exception:
            return None
    
    def is_stale(self, max_age_days: int = 7) -> bool:
        """
        Check if cache is stale (older than max_age_days).
        
        Args:
            max_age_days: Maximum age in days before cache is considered stale
            
        Returns:
            True if cache is stale or doesn't exist
        """
        age = self.get_age_days()
        if age is None:
            return True
        return age > max_age_days
    
    def find_by_slug(self, slug: str) -> Optional[Dict]:
        """
        Find game by slug (lgogdownloader-style game name).
        
        Args:
            slug: Game slug (e.g., "the_witcher_3")
            
        Returns:
            Game info dict or None
        """
        games = self.load()
        slug_lower = slug.lower()
        
        for game in games.values():
            if game.get("slug", "").lower() == slug_lower:
                return game
        
        return None
    
    def find_by_title(self, title: str) -> Optional[Dict]:
        """
        Find game by exact title (case-insensitive).
        
        Args:
            title: Game title
            
        Returns:
            Game info dict or None
        """
        games = self.load()
        title_lower = title.lower()
        
        for game in games.values():
            if game.get("title", "").lower() == title_lower:
                return game
        
        return None
    
    def search(self, pattern: str, use_regex: bool = False, case_sensitive: bool = False) -> List[Dict]:
        """
        Search games by pattern (slug or title).
        
        Args:
            pattern: Search pattern
            use_regex: Whether to treat pattern as regex
            case_sensitive: Whether matching should be case-sensitive
            
        Returns:
            List of matching game info dicts
        """
        import re
        
        games = self.load()
        matches = []
        
        if use_regex:
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                regex = re.compile(pattern, flags)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern '{pattern}': {e}")
            
            for game in games.values():
                # Match against both slug and title
                if regex.search(game.get("slug", "")) or regex.search(game.get("title", "")):
                    matches.append(game)
        else:
            # Simple substring match
            pattern_lower = pattern.lower() if not case_sensitive else pattern
            
            for game in games.values():
                slug = game.get("slug", "")
                title = game.get("title", "")
                
                if not case_sensitive:
                    slug = slug.lower()
                    title = title.lower()
                
                if pattern_lower in slug or pattern_lower in title:
                    matches.append(game)
        
        return matches
