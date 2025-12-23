"""
Build a SQLite database of your complete GOG library.

This example shows how to:
- Authenticate with GOG (using GUI if available)
- Fetch all owned games (including delisted titles)
- Retrieve detailed information for each game
- Store everything in a SQLite database for easy querying

The database can be opened with any SQLite browser tool.
"""

import sqlite3
import json
from pathlib import Path
from galaxy_dl import GalaxyAPI, AuthManager


def authenticate_user(auth: AuthManager) -> bool:
    """
    Authenticate user with GUI fallback to code-based login.
    
    Args:
        auth: AuthManager instance
        
    Returns:
        True if authentication successful, False otherwise
    """
    if auth.is_authenticated():
        return True
    
    # Try GUI login first
    try:
        from galaxy_dl.gui_login import gui_login
        print("Opening browser for authentication...")
        code = gui_login()
        if code and auth.login_with_code(code):
            print("Authentication successful!")
            return True
        elif code is None:
            print("GUI login cancelled or failed, falling back to manual code entry.")
        else:
            print("Authentication failed with GUI code, falling back to manual entry.")
    except ImportError:
        print("GUI login not available (PySide6 not installed).")
        print("Install with: pip install galaxy-dl[gui]")
    except Exception as e:
        print(f"GUI login error: {e}")
        print("Falling back to manual code entry.")
    
    # Fallback to code-based login
    print("\nPlease get your OAuth code from:")
    print("https://auth.gog.com/auth?client_id=46899977096215655&redirect_uri=https%3A%2F%2Fembed.gog.com%2Fon_login_success%3Forigin%3Dclient&response_type=code&layout=client2")
    code = input("Enter code: ").strip()
    
    if not code:
        print("No code provided!")
        return False
    
    if auth.login_with_code(code):
        print("Authentication successful!")
        return True
    else:
        print("Authentication failed!")
        return False


def create_database(db_path: str):
    """Create the SQLite database schema."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Main games table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS games (
            game_id INTEGER PRIMARY KEY,
            title TEXT,
            background_image TEXT,
            cd_key TEXT,
            text_information TEXT,
            release_timestamp INTEGER,
            is_pre_order BOOLEAN,
            changelog TEXT,
            forum_link TEXT,
            is_base_product_missing BOOLEAN,
            missing_base_product TEXT,
            downloads_json TEXT,
            extras_json TEXT,
            dlcs_json TEXT,
            tags_json TEXT,
            messages_json TEXT,
            details_available BOOLEAN DEFAULT 1,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Index for faster lookups
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_title ON games(title)")
    
    conn.commit()
    return conn


def store_game_details(conn: sqlite3.Connection, game_id: int, details: dict, details_available: bool = True):
    """Store game details in the database."""
    cursor = conn.cursor()
    
    if not details_available:
        # Store minimal record for games without available details
        cursor.execute("""
            INSERT OR REPLACE INTO games (
                game_id, details_available, title
            ) VALUES (?, ?, ?)
        """, (
            game_id,
            False,
            f"Game {game_id} (details unavailable)"
        ))
    else:
        cursor.execute("""
            INSERT OR REPLACE INTO games (
                game_id, title, background_image, cd_key, text_information,
                release_timestamp, is_pre_order, changelog, forum_link,
                is_base_product_missing, missing_base_product,
                downloads_json, extras_json, dlcs_json, tags_json, messages_json,
                details_available
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            game_id,
            details.get('title'),
            details.get('backgroundImage'),
            details.get('cdKey'),
            details.get('textInformation'),
            details.get('releaseTimestamp'),
            details.get('isPreOrder'),
            details.get('changelog'),
            details.get('forumLink'),
            details.get('isBaseProductMissing'),
            details.get('missingBaseProduct'),
            json.dumps(details.get('downloads', [])),
            json.dumps(details.get('extras', [])),
            json.dumps(details.get('dlcs', [])),
            json.dumps(details.get('tags', [])),
            json.dumps(details.get('messages', [])),
            True
        ))
    
    conn.commit()


def main():
    # Authenticate
    auth = AuthManager()
    
    if not authenticate_user(auth):
        return
    
    # Create API client
    api = GalaxyAPI(auth)
    
    # Get ALL owned games (complete list including delisted titles)
    print("\nFetching your complete game library...")
    game_ids = api.get_owned_games()
    
    if not game_ids:
        print("No games found in your library!")
        return
    
    print(f"You own {len(game_ids)} games (including delisted titles)")
    
    # Set up database
    db_path = Path("gog_library.db")
    print(f"\nCreating database: {db_path.absolute()}")
    conn = create_database(str(db_path))
    
    # Fetch and store details for each game
    print(f"\nFetching details for {len(game_ids)} games...")
    print("This may take a while...\n")
    
    failed_games = []
    unavailable_count = 0
    
    for idx, game_id in enumerate(game_ids, 1):
        try:
            # Fetch game details
            details = api.get_game_details(game_id)
            
            # Check if details are unavailable (API returns None)
            if details is None:
                store_game_details(conn, game_id, {}, details_available=False)
                unavailable_count += 1
                print(f"[{idx}/{len(game_ids)}] Game {game_id} (details not available)")
            elif not details:  # Empty dict means error
                raise Exception("API returned empty response")
            else:
                # Store in database
                store_game_details(conn, game_id, details)
                
                # Progress update
                title = details.get('title', 'Unknown')
                print(f"[{idx}/{len(game_ids)}] {title}")
            
        except Exception as e:
            print(f"[{idx}/{len(game_ids)}] ERROR: Game ID {game_id} - {e}")
            failed_games.append((game_id, str(e)))
    
    # Close database
    conn.close()
    
    # Summary
    print(f"\n{'='*60}")
    print(f"Database created: {db_path.absolute()}")
    print(f"Total games processed: {len(game_ids)}")
    print(f"With full details: {len(game_ids) - len(failed_games) - unavailable_count}")
    print(f"Details unavailable: {unavailable_count}")
    
    if failed_games:
        print(f"Failed: {len(failed_games)}")
        print(f"\nFailed games:")
        for game_id, error in failed_games[:10]:  # Show first 10
            print(f"  - Game ID {game_id}: {error}")
        if len(failed_games) > 10:
            print(f"  ... and {len(failed_games) - 10} more")
    
    print(f"\nYou can now open '{db_path}' with any SQLite browser.")
    print("Recommended tools:")
    print("  - DB Browser for SQLite (https://sqlitebrowser.org/)")
    print("  - DBeaver (https://dbeaver.io/)")
    print("  - VS Code SQLite extension")
    print(f"\nUseful SQL queries:")
    print("  -- All games with full details:")
    print("  SELECT game_id, title FROM games WHERE details_available = 1;")
    print(f"\n  -- Games without available details:")
    print("  SELECT game_id FROM games WHERE details_available = 0;")
    print(f"\n  -- Games with extras:")
    print("  SELECT title, json_array_length(extras_json) as count")
    print("  FROM games WHERE details_available = 1 AND extras_json != '[]';")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
