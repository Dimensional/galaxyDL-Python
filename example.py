"""
Example usage of galaxy_dl library

This script demonstrates how to:
1. Authenticate with GOG
2. Get product builds
3. Download depot files from Galaxy CDN
"""

import logging
import sys
from pathlib import Path

from galaxy_dl import GalaxyAPI, AuthManager, GalaxyDownloader


def setup_logging():
    """Configure logging for the example."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def main():
    """Main example function."""
    setup_logging()
    logger = logging.getLogger("example")
    
    # Initialize authentication
    logger.info("Initializing authentication...")
    auth_config_path = Path.home() / ".config" / "galaxy_dl" / "auth.json"
    auth = AuthManager(config_path=str(auth_config_path))
    
    # Check if already authenticated
    if not auth.is_authenticated():
        logger.error("Not authenticated!")
        logger.info("Please authenticate first:")
        logger.info("1. Go to https://auth.gog.com/auth?client_id=46899977096215655&redirect_uri=https%3A%2F%2Fembed.gog.com%2Fon_login_success%3Forigin%3Dclient&response_type=code&layout=client2")
        logger.info("2. Login and copy the 'code' parameter from the redirect URL")
        logger.info("3. Run: python -c \"from galaxy_dl import AuthManager; auth = AuthManager(); auth.login_with_code('YOUR_CODE_HERE')\"")
        return 1
    
    logger.info("Authenticated successfully!")
    
    # Initialize API
    api = GalaxyAPI(auth)
    
    # Example: Get builds for a product
    # Replace with actual product ID
    product_id = "1234567890"
    
    logger.info(f"Getting builds for product {product_id}...")
    builds = api.get_product_builds(product_id)
    
    if not builds or "items" not in builds:
        logger.error("Failed to get builds or no builds available")
        return 1
    
    # Get the latest build
    latest_build = builds["items"][0] if builds["items"] else None
    if not latest_build:
        logger.error("No builds found")
        return 1
    
    build_id = latest_build.get("build_id")
    logger.info(f"Latest build ID: {build_id}")
    
    # Get manifest from build
    if "link" in latest_build:
        manifest_url = latest_build["link"]
        logger.info(f"Manifest URL: {manifest_url}")
        
        # Extract manifest hash from URL or use API
        # This is simplified - in practice you'd parse the build response
        manifest_hash = latest_build.get("manifest_id", "")
        
        if manifest_hash:
            # Get depot items
            logger.info("Getting depot items...")
            depot_items = api.get_depot_items(manifest_hash)
            
            logger.info(f"Found {len(depot_items)} depot items")
            
            # Download first item as example
            if depot_items:
                downloader = GalaxyDownloader(api)
                output_dir = "./downloads"
                
                first_item = depot_items[0]
                logger.info(f"Downloading: {first_item.path}")
                
                def progress(downloaded, total):
                    percent = (downloaded / total) * 100 if total > 0 else 0
                    logger.info(f"Progress: {percent:.1f}% ({downloaded}/{total} bytes)")
                
                try:
                    output_path = downloader.download_item(
                        first_item,
                        output_dir,
                        progress_callback=progress
                    )
                    logger.info(f"Downloaded to: {output_path}")
                except Exception as e:
                    logger.error(f"Download failed: {e}")
                    return 1
    
    logger.info("Example completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())

