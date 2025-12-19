"""
List your GOG library with game details.

This example shows how to:
- Authenticate with GOG
- List all owned games
- Get details for each game
"""

from galaxy_dl import GalaxyAPI, AuthManager


def main():
    # Authenticate
    auth = AuthManager()
    
    if not auth.is_authenticated():
        print("Not authenticated. Please get your OAuth code from:")
        print("https://auth.gog.com/auth?client_id=46899977096215655&redirect_uri=https%3A%2F%2Fembed.gog.com%2Fon_login_success%3Forigin%3Dclient&response_type=code&layout=client2")
        code = input("Enter code: ")
        if not auth.login_with_code(code):
            print("Authentication failed!")
            return
    
    # Create API client
    api = GalaxyAPI(auth)
    
    # Get owned games
    print("\nFetching your game library...")
    game_ids = api.get_owned_games()
    print(f"You own {len(game_ids)} games\n")
    
    # Ask how many to display
    try:
        limit = int(input(f"How many games to display? (1-{len(game_ids)}): "))
        limit = min(max(1, limit), len(game_ids))
    except ValueError:
        limit = 10
    
    # Get details for games
    print(f"\nFetching details for first {limit} games...\n")
    games = api.get_owned_games_with_details(limit=limit)
    
    # Display games
    for idx, game in enumerate(games, 1):
        print(f"{idx}. {game.get('title', 'Unknown Title')}")
        print(f"   ID: {game['id']}")
        print(f"   Downloads: {len(game.get('downloads', []))} language(s)")
        print(f"   Extras: {len(game.get('extras', []))} item(s)")
        
        # Show platform availability
        platforms = set()
        for lang_data in game.get('downloads', []):
            if len(lang_data) >= 2:
                platforms.update(lang_data[1].keys())
        if platforms:
            print(f"   Platforms: {', '.join(platforms)}")
        print()


if __name__ == "__main__":
    main()
