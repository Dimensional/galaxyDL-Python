"""
Complete game download workflow.

This example shows the full process:
1. Browse library
2. Select a game
3. Choose a build
4. Download files
"""

import os
from galaxy_dl import GalaxyAPI, GalaxyDownloader, AuthManager


def main():
    # Authenticate
    auth = AuthManager()
    
    if not auth.is_authenticated():
        print("Not authenticated. Please run list_library.py first.")
        return
    
    api = GalaxyAPI(auth)
    
    # Step 1: Browse library
    print("=== Your Game Library ===\n")
    game_ids = api.get_owned_games()
    
    # Show first 20 games
    games = api.get_owned_games_with_details(limit=20)
    for idx, game in enumerate(games, 1):
        print(f"{idx}. {game.get('title', 'Unknown')}")
    
    print(f"\n... and {len(game_ids) - 20} more")
    
    # Step 2: Select game
    try:
        choice = int(input(f"\nSelect game (1-{min(20, len(games))}): "))
        if choice < 1 or choice > len(games):
            print("Invalid choice!")
            return
    except ValueError:
        print("Invalid input!")
        return
    
    selected_game = games[choice - 1]
    product_id = str(selected_game['id'])
    
    print(f"\nSelected: {selected_game['title']}")
    
    # Step 3: Select platform
    platform = input("Platform (windows/osx/linux) [windows]: ").strip() or "windows"
    
    # Step 4: Get builds
    print(f"\nFetching builds for {platform}...")
    builds_data = api.get_all_product_builds(product_id, platform)
    
    if not builds_data or "items" not in builds_data:
        print("No builds found!")
        return
    
    builds = builds_data["items"]
    print(f"\nFound {len(builds)} builds:")
    
    for idx, build in enumerate(builds[:10], 1):  # Show first 10
        build_id = build.get("build_id", "unknown")
        generation = build.get("generation", "?")
        version = build.get("version_name", "")
        print(f"{idx}. Build {build_id} (Gen {generation}){f' - {version}' if version else ''}")
    
    # Step 5: Select build
    try:
        choice = int(input(f"\nSelect build (1-{min(10, len(builds))}): "))
        if choice < 1 or choice > min(10, len(builds)):
            print("Invalid choice!")
            return
    except ValueError:
        print("Invalid input!")
        return
    
    selected_build = builds[choice - 1]
    
    # Step 6: Get manifest
    print(f"\nFetching manifest for build {selected_build.get('build_id')}...")
    manifest = api.get_manifest_from_build(product_id, selected_build, platform)
    
    if not manifest:
        print("Failed to get manifest!")
        return
    
    print(f"\nManifest loaded!")
    print(f"Generation: {manifest.generation}")
    print(f"Depots: {len(manifest.depots)}")
    
    # Step 7: Download
    output_dir = input(f"\nOutput directory [./downloads/{product_id}]: ").strip()
    if not output_dir:
        output_dir = f"./downloads/{product_id}"
    
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"\n=== Download Configuration ===")
    print(f"Product: {selected_game['title']}")
    print(f"Build: {selected_build.get('build_id')}")
    print(f"Generation: {manifest.generation}")
    print(f"Output: {output_dir}")
    
    confirm = input("\nProceed with download? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Download cancelled.")
        return
    
    # Initialize downloader
    downloader = GalaxyDownloader(api, max_workers=8)
    
    # For this example, we'll just show how to download
    # In a real implementation, you'd iterate through depot items
    print("\n=== Download Started ===")
    print("NOTE: This is a simplified example.")
    print("For full implementation, you need to:")
    print("1. Parse depot items from manifest")
    print("2. Filter by language/bitness if needed")
    print("3. Download each item with progress tracking")
    print(f"\nManifest data available in manifest object")
    print(f"Use downloader.download_item() for each file")
    
    # Show depot info
    for idx, depot in enumerate(manifest.depots, 1):
        print(f"\nDepot {idx}:")
        print(f"  Languages: {', '.join(depot.languages)}")
        print(f"  Size: {depot.size:,} bytes")


if __name__ == "__main__":
    main()
