"""
Build a SQLite database of your complete GOG library.

This example shows how to:
- Authenticate with GOG (using GUI if available)
- Fetch all owned product IDs (Step 1)
- Get game list from getFilteredProducts (Step 2)
- Fetch detailed game info and DLC list URLs (Step 3-4)
- Store complete game and DLC information (Step 5)

Database structure:
- products: All owned product IDs
- games: Full game details with DLC IDs list
- dlcs: Full DLC details linked to their parent games

The database can be opened with any SQLite browser tool.
"""

import sqlite3
import json
import time
import argparse
from pathlib import Path
from typing import List, Dict, Any
import requests
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
    
    # Step 1: All owned products (games + DLCs) - just IDs
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Step 2-5: Games table - details from getFilteredProducts + api.gog.com
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS games (
            game_id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            slug TEXT,
            category TEXT,
            rating REAL,
            is_new BOOLEAN,
            is_hidden BOOLEAN,
            updates INTEGER,
            works_on_json TEXT,
            availability_json TEXT,
            image TEXT,
            url TEXT,
            -- From api.gog.com/products
            game_type TEXT,
            purchase_link TEXT,
            release_date TEXT,
            is_pre_order BOOLEAN,
            is_installable BOOLEAN,
            content_system_compatibility_json TEXT,
            languages_json TEXT,
            images_json TEXT,
            links_json TEXT,
            description_json TEXT,
            downloads_json TEXT,
            changelog TEXT,
            -- DLC info
            dlc_ids_json TEXT,  -- Array of DLC product IDs
            dlc_count INTEGER DEFAULT 0,
            -- Tracking
            metadata_fetched BOOLEAN DEFAULT 0,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (game_id) REFERENCES products(product_id)
        )
    """)
    
    # Step 5: DLCs table - full details from expanded_all_products_url
    # Stores ALL DLCs (owned + unowned) with ownership flag
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dlcs (
            dlc_id INTEGER PRIMARY KEY,
            parent_game_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            slug TEXT,
            game_type TEXT,
            purchase_link TEXT,
            release_date TEXT,
            is_pre_order BOOLEAN,
            is_installable BOOLEAN,
            content_system_compatibility_json TEXT,
            languages_json TEXT,
            images_json TEXT,
            links_json TEXT,
            description_json TEXT,
            downloads_json TEXT,
            changelog TEXT,
            owned BOOLEAN DEFAULT 0,  -- Track ownership status
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (parent_game_id) REFERENCES games(game_id)
        )
    """)
    
    # Indexes for faster lookups
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_game_title ON games(title)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_game_metadata ON games(metadata_fetched)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dlc_title ON dlcs(title)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dlc_parent ON dlcs(parent_game_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_dlc_owned ON dlcs(owned)")
    
    conn.commit()
    return conn


def store_product_id(conn: sqlite3.Connection, product_id: int):
    """Store product ID in products table (Step 1)."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO products (product_id)
        VALUES (?)
    """, (product_id,))
    conn.commit()


def store_game_initial(conn: sqlite3.Connection, game_data: Dict[str, Any]):
    """Store initial game data from getFilteredProducts (Step 2)."""
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT OR REPLACE INTO games (
            game_id, title, slug, category, rating, is_new, is_hidden,
            updates, works_on_json, availability_json, image, url
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        game_data['id'],
        game_data.get('title'),
        game_data.get('slug'),
        game_data.get('category'),
        game_data.get('rating'),
        game_data.get('isNew'),
        game_data.get('isHidden'),
        game_data.get('updates'),
        json.dumps(game_data.get('worksOn', {})),
        json.dumps(game_data.get('availability', {})),
        game_data.get('image'),
        game_data.get('url')
    ))
    
    conn.commit()


def update_game_details(conn: sqlite3.Connection, game_id: int, details: Dict[str, Any]):
    """Update game with details from api.gog.com (Step 3-4)."""
    cursor = conn.cursor()
    
    # Extract DLC IDs - dlcs can be [] (no DLCs) or {"products": [...], ...} (has DLCs)
    dlcs = details.get('dlcs', [])
    if isinstance(dlcs, dict):
        dlc_ids = [dlc['id'] for dlc in dlcs.get('products', [])]
    else:
        dlc_ids = []
    
    cursor.execute("""
        UPDATE games SET
            game_type = ?,
            purchase_link = ?,
            release_date = ?,
            is_pre_order = ?,
            is_installable = ?,
            content_system_compatibility_json = ?,
            languages_json = ?,
            images_json = ?,
            links_json = ?,
            description_json = ?,
            downloads_json = ?,
            changelog = ?,
            dlc_ids_json = ?,
            dlc_count = ?,
            metadata_fetched = 1
        WHERE game_id = ?
    """, (
        details.get('game_type'),
        details.get('purchase_link'),
        details.get('release_date'),
        details.get('is_pre_order'),
        details.get('is_installable'),
        json.dumps(details.get('content_system_compatibility', {})),
        json.dumps(details.get('languages', {})),
        json.dumps(details.get('images', {})),
        json.dumps(details.get('links', {})),
        json.dumps(details.get('description', {})),
        json.dumps(details.get('downloads', {})),
        details.get('changelog'),
        json.dumps(dlc_ids),
        len(dlc_ids),
        game_id
    ))
    
    conn.commit()


def store_dlc(conn: sqlite3.Connection, dlc_data: Dict[str, Any], parent_game_id: int, owned: bool = False):
    """Store DLC details from expanded_all_products_url (Step 5)."""
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT OR REPLACE INTO dlcs (
            dlc_id, parent_game_id, title, slug, game_type, purchase_link,
            release_date, is_pre_order, is_installable,
            content_system_compatibility_json, languages_json, images_json,
            links_json, description_json, downloads_json, changelog, owned
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        dlc_data['id'],
        parent_game_id,
        dlc_data.get('title'),
        dlc_data.get('slug'),
        dlc_data.get('game_type'),
        dlc_data.get('purchase_link'),
        dlc_data.get('release_date'),
        dlc_data.get('is_pre_order'),
        dlc_data.get('is_installable'),
        json.dumps(dlc_data.get('content_system_compatibility', {})),
        json.dumps(dlc_data.get('languages', {})),
        json.dumps(dlc_data.get('images', {})),
        json.dumps(dlc_data.get('links', {})),
        json.dumps(dlc_data.get('description', {})),
        json.dumps(dlc_data.get('downloads', {})),
        dlc_data.get('changelog'),
        owned
    ))
    
    conn.commit()


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Build a SQLite database of your GOG library',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  %(prog)s                          # Normal run, skip already-processed games
  %(prog)s --force                  # Force revalidate all games
  %(prog)s --game-id 1744178250     # Update only Alien: Isolation
  %(prog)s --game-id 123 456 789    # Update multiple specific games
  %(prog)s --game-id 123 --force    # Force update specific game
        """
    )
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Force revalidation of all games (ignore metadata_fetched flag)'
    )
    parser.add_argument(
        '--game-id', '-g',
        type=int,
        nargs='+',
        metavar='ID',
        help='Update only specific game(s) by ID (space-separated)'
    )
    args = parser.parse_args()
    
    # Authenticate
    auth = AuthManager()
    
    if not authenticate_user(auth):
        return
    
    # Create API client
    api = GalaxyAPI(auth)
    
    # Set up database
    db_path = Path("gog_library.db")
    print(f"Creating database: {db_path.absolute()}\n")
    conn = create_database(str(db_path))
    
    # STEP 1: Get ALL owned product IDs (games + DLCs)
    print("STEP 1: Fetching all owned product IDs...")
    product_ids = api.get_owned_games()
    
    if not product_ids:
        print("No products found in your library!")
        return
    
    print(f"Found {len(product_ids)} owned products")
    
    # Detect new products since last run
    cursor = conn.cursor()
    cursor.execute("SELECT product_id FROM products")
    existing_products = set(row[0] for row in cursor.fetchall())
    new_products = set(product_ids) - existing_products
    
    if new_products:
        print(f"\n🆕 Detected {len(new_products)} new product(s) since last run!")
        
        # Check if any are DLCs we already know about (just need to mark owned)
        cursor.execute("SELECT dlc_id FROM dlcs WHERE owned = 0")
        unowned_dlcs = set(row[0] for row in cursor.fetchall())
        new_dlc_purchases = new_products & unowned_dlcs
        
        if new_dlc_purchases:
            print(f"  → {len(new_dlc_purchases)} are DLC(s) you just purchased!")
            placeholders = ','.join('?' * len(new_dlc_purchases))
            cursor.execute(f"UPDATE dlcs SET owned = 1 WHERE dlc_id IN ({placeholders})", 
                          list(new_dlc_purchases))
            conn.commit()
            
            # Show which DLCs were updated
            for dlc_id in new_dlc_purchases:
                cursor.execute(
                    "SELECT d.title, g.title FROM dlcs d JOIN games g ON d.parent_game_id = g.game_id WHERE d.dlc_id = ?",
                    (dlc_id,)
                )
                result = cursor.fetchone()
                if result:
                    print(f"    ✓ {result[0]} (for {result[1]})")
        
        # Check if any are existing games (shouldn't happen, but handle it)
        cursor.execute("SELECT game_id FROM games")
        existing_games = set(row[0] for row in cursor.fetchall())
        existing_game_repurchase = new_products & existing_games
        
        if existing_game_repurchase:
            print(f"  → {len(existing_game_repurchase)} are game(s) already in database (no action needed)")
        
        # What's left are truly new games or unknown DLCs
        truly_new = new_products - new_dlc_purchases - existing_game_repurchase
        if truly_new:
            print(f"  → {len(truly_new)} are new game(s) or unknown DLC(s)")
            print(f"    (will be processed during game metadata fetch)")
    else:
        print("No new products detected since last run.")
    
    print("\nStoring product IDs in database...")
    for product_id in product_ids:
        store_product_id(conn, product_id)
    print(f"✓ Stored {len(product_ids)} product IDs\n")
    
    # STEP 2: Get games list from getFilteredProducts (paginated)
    print("\nSTEP 2: Fetching games from getFilteredProducts...")
    games = api.get_all_filtered_products(media_type=1)
    
    if not games:
        print("No games found!")
        return
    
    print(f"Found {len(games)} games")
    
    # Identify which games are new (not in games table yet)
    cursor = conn.cursor()
    cursor.execute("SELECT game_id FROM games")
    existing_game_ids = set(row[0] for row in cursor.fetchall())
    
    # Store initial data for ALL games from getFilteredProducts
    print("Storing/updating game list...")
    for game in games:
        store_game_initial(conn, game)
    print(f"✓ Stored {len(games)} games\n")
    
    # Determine which games need metadata fetching
    if args.game_id:
        # Filter to specific games if requested
        game_id_set = set(args.game_id)
        games_to_process = [g for g in games if g['id'] in game_id_set]
        if not games_to_process:
            print(f"Error: None of the specified game IDs found in library")
            return
        print(f"Processing {len(games_to_process)} requested game(s)")
    elif args.force:
        # Force mode: process all games
        games_to_process = games
        print(f"Force mode: Processing all {len(games_to_process)} games")
    else:
        # Normal mode: only process new games or games without metadata
        new_game_ids = set(g['id'] for g in games) - existing_game_ids
        
        if new_game_ids:
            print(f"\n📦 Detected {len(new_game_ids)} new game(s) to catalog")
        
        # Also process games that failed before (metadata_fetched = 0)
        cursor.execute("SELECT game_id FROM games WHERE metadata_fetched = 0")
        incomplete_game_ids = set(row[0] for row in cursor.fetchall())
        
        games_to_process_ids = new_game_ids | incomplete_game_ids
        games_to_process = [g for g in games if g['id'] in games_to_process_ids]
        
        if incomplete_game_ids - new_game_ids:
            print(f"🔄 Retrying {len(incomplete_game_ids - new_game_ids)} previously failed game(s)")
        
        if not games_to_process:
            print("✓ All games already have metadata. Use --force to re-fetch.")
    
    # STEP 3-5: Fetch detailed info and DLCs for each game
    if not games_to_process:
        print("\nNo games to process for metadata.")
    else:
        print(f"\nSTEP 3-5: Fetching detailed info and DLCs for {len(games_to_process)} game(s)...")
        print("This will take a while...\n")
    
    # Convert product IDs to a set for fast ownership lookup
    owned_product_ids = set(product_ids)
    
    total_dlcs = 0
    total_unowned_dlcs = 0
    failed_games = []
    
    for idx, game in enumerate(games_to_process, 1):
        game_id = game['id']
        title = game.get('title', 'Unknown')
        
        try:
            # STEP 3: Fetch game details from api.gog.com
            url = f"https://api.gog.com/products/{game_id}?expand=downloads,description,changelog"
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            game_details = response.json()
            
            # Update game with additional details
            update_game_details(conn, game_id, game_details)
            
            # Check if game has DLCs - dlcs can be [] or {"products": [...], ...}
            dlc_info = game_details.get('dlcs', [])
            expanded_url = None
            if isinstance(dlc_info, dict):
                expanded_url = dlc_info.get('expanded_all_products_url')
            
            if expanded_url:
                # STEP 4: Fetch all DLCs using the expanded_all_products_url
                dlc_count = len(dlc_info.get('products', []))
                print(f"[{idx}/{len(games_to_process)}] {title}")
                print(f"  Fetching {dlc_count} DLCs...")
                
                time.sleep(0.5)  # Rate limiting
                dlc_response = requests.get(expanded_url, timeout=30)
                dlc_response.raise_for_status()
                dlcs_data = dlc_response.json()
                
                # STEP 5: Store ALL DLCs with ownership flag
                for dlc in dlcs_data:
                    dlc_id = dlc['id']
                    owned = dlc_id in owned_product_ids
                    store_dlc(conn, dlc, game_id, owned=owned)
                    if owned:
                        print(f"    ✓ {dlc.get('title')} (owned)")
                        total_dlcs += 1
                    else:
                        print(f"    - {dlc.get('title')}")
                        total_unowned_dlcs += 1
                
            else:
                print(f"[{idx}/{len(games_to_process)}] {title} (no DLCs)")
            
            # Rate limiting
            time.sleep(0.5)
            
        except Exception as e:
            print(f"[{idx}/{len(games_to_process)}] ERROR: {title} - {e}")
            failed_games.append((game_id, title, str(e)))
    
    # Close database
    conn.close()
    
    # Summary
    print(f"\n{'='*60}")
    print(f"Database: {db_path.absolute()}")
    if args.force:
        print(f"Mode: Force revalidation")
    if args.game_id:
        print(f"Mode: Filtered to {len(args.game_id)} game ID(s)")
    if new_products:
        print(f"\nNew products this run: {len(new_products)}")
        if new_dlc_purchases:
            print(f"  - DLC purchases auto-updated: {len(new_dlc_purchases)}")
        if truly_new:
            print(f"  - New games/unknown DLCs: {len(truly_new)}")
    print(f"\nTotal products owned: {len(product_ids)}")
    print(f"Games: {len(games)}")
    print(f"DLCs owned: {total_dlcs}")
    if total_unowned_dlcs > 0:
        print(f"DLCs cataloged (not owned): {total_unowned_dlcs}")
        print(f"Total DLCs in database: {total_dlcs + total_unowned_dlcs}")
    
    if failed_games:
        print(f"Failed: {len(failed_games)}")
        print(f"\nFailed games:")
        for game_id, title, error in failed_games[:10]:
            print(f"  - {title} (ID: {game_id}): {error}")
        if len(failed_games) > 10:
            print(f"  ... and {len(failed_games) - 10} more")
    
    print(f"\nYou can now open '{db_path}' with any SQLite browser.")
    print("Recommended tools:")
    print("  - DB Browser for SQLite (https://sqlitebrowser.org/)")
    print("  - DBeaver (https://dbeaver.io/)")
    print("  - VS Code SQLite extension")
    
    print(f"\nUseful SQL queries:")
    print("  -- All games with owned DLC count:")
    print("  SELECT g.game_id, g.title, COUNT(d.dlc_id) as owned_dlcs")
    print("  FROM games g LEFT JOIN dlcs d ON g.game_id = d.parent_game_id AND d.owned = 1")
    print("  GROUP BY g.game_id ORDER BY g.title;")
    print(f"\n  -- All owned DLCs with their parent game:")
    print("  SELECT d.title as dlc_title, g.title as game_title")
    print("  FROM dlcs d JOIN games g ON d.parent_game_id = g.game_id")
    print("  WHERE d.owned = 1;")
    print(f"\n  -- Games with most DLCs (owned vs total):")
    print("  SELECT g.title,")
    print("    SUM(CASE WHEN d.owned = 1 THEN 1 ELSE 0 END) as owned,")
    print("    COUNT(d.dlc_id) as total")
    print("  FROM games g LEFT JOIN dlcs d ON g.game_id = d.parent_game_id")
    print("  GROUP BY g.game_id ORDER BY total DESC LIMIT 10;")
    print(f"\n  -- New DLC purchases (in products but owned=0):")
    print("  UPDATE dlcs SET owned = 1")
    print("  WHERE dlc_id IN (SELECT product_id FROM products)")
    print("  AND owned = 0;")
    print(f"\n  -- DLCs you don't own yet:")
    print("  SELECT d.title, g.title as game_title, d.purchase_link")
    print("  FROM dlcs d JOIN games g ON d.parent_game_id = g.game_id")
    print("  WHERE d.owned = 0;")
    print(f"\n  -- Detect new DLC purchases (update owned flag):")
    print("  SELECT d.title, g.title as game FROM dlcs d")
    print("  JOIN games g ON d.parent_game_id = g.game_id")
    print("  WHERE d.owned = 0 AND d.dlc_id IN (SELECT product_id FROM products);")
    print(f"\n  -- Products not in games or DLCs tables (likely delisted):")
    print("  SELECT product_id FROM products")
    print("  WHERE product_id NOT IN (SELECT game_id FROM games)")
    print("  AND product_id NOT IN (SELECT dlc_id FROM dlcs);")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
