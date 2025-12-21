"""
Constants for Galaxy API endpoints and configuration
Based on lgogdownloader globalconstants.h and heroic-gogdl constants.py
"""

# API Endpoints (updated from lgogdownloader)
GOG_CDN = "https://gog-cdn-fastly.gog.com"
GOG_CDN_ALT = "https://cdn.gog.com"  # Primary CDN for content-system
GOG_CONTENT_SYSTEM = "https://content-system.gog.com"
GOG_EMBED = "https://embed.gog.com"
GOG_AUTH = "https://auth.gog.com"
GOG_API = "https://api.gog.com"
GOG_CLOUDSTORAGE = "https://cloudstorage.gog.com"
GOG_REMOTE_CONFIG = "https://remote-config.gog.com"

# User Library URLs (GOG Embed API)
USER_GAMES_URL = f"{GOG_EMBED}/user/data/games"
GAME_DETAILS_URL = f"{GOG_EMBED}/account/gameDetails/{{game_id}}.json"

# Content System URLs
DEPENDENCIES_URL = "https://content-system.gog.com/dependencies/repository?generation=2"
DEPENDENCIES_V1_URL = "https://content-system.gog.com/redists/repository"

# Manifest URLs
MANIFEST_V2_URL = "https://cdn.gog.com/content-system/v2/meta/{path}"
MANIFEST_V2_DEPENDENCIES_URL = "https://cdn.gog.com/content-system/v2/dependencies/meta/{path}"
# V1 URL uses repository_id (legacy_build_id from builds API, aka repository timestamp)
MANIFEST_V1_URL = "https://cdn.gog.com/content-system/v1/manifests/{product_id}/{platform}/{repository_id}/{manifest_id}.json"
# Common V1 pattern - repository.json is the standard manifest name
MANIFEST_V1_REPOSITORY_URL = "https://cdn.gog.com/content-system/v1/manifests/{product_id}/{platform}/{repository_id}/repository.json"

# Patch URLs
PATCH_V2_URL = "https://cdn.gog.com/content-system/v2/patches/meta/{path}"
PATCH_V2_STORE_URL = "https://cdn.gog.com/content-system/v2/patches/store/{path}"
# Query patch availability between two builds
PATCHES_QUERY_URL = "https://content-system.gog.com/products/{product_id}/patches?_version=4&from_build_id={from_build_id}&to_build_id={to_build_id}"

# Secure Link URLs
SECURE_LINK_URL = "https://content-system.gog.com/products/{product_id}/secure_link?generation={generation}&path={path}&_version=2"
DEPENDENCY_LINK_URL = "https://content-system.gog.com/open_link?generation=2&_version=2&path=/dependencies/store/{path}"
# Builds API quirky behavior:
# - generation=1 or missing: Returns ONLY V1 builds (may miss some that appear in gen=2)
# - generation=2: Returns BOTH V1 and V2 builds (may miss some that appear in gen=1)
# - Some builds only appear in one endpoint or the other - must query BOTH to get all builds
BUILDS_URL = "https://content-system.gog.com/products/{product_id}/os/{platform}/builds?generation={generation}"

# Default values
DEFAULT_TIMEOUT = 10
DEFAULT_RETRIES = 3
ZLIB_WINDOW_SIZE = 15  # From lgogdownloader

# Chunk download size (16KB)
CHUNK_READ_SIZE = 16 * 1024

# Platform constants (matching lgogdownloader)
PLATFORM_WINDOWS = "windows"
PLATFORM_MAC = "osx"
PLATFORM_LINUX = "linux"

PLATFORMS = [PLATFORM_WINDOWS, PLATFORM_MAC, PLATFORM_LINUX]

# Generation constants
GENERATION_1 = "1"
GENERATION_2 = "2"

# Language codes (subset from lgogdownloader - common ones)
LANGUAGE_CODES = {
    "en": "English",
    "de": "German",
    "fr": "French",
    "pl": "Polish",
    "ru": "Russian",
    "cn": "Chinese",
    "es": "Spanish",
    "it": "Italian",
    "jp": "Japanese",
    "pt": "Portuguese",
    "ko": "Korean",
    "nl": "Dutch",
    "pt_br": "Brazilian Portuguese",
}

# User agent
USER_AGENT = "galaxy-dl/{version} (Python)"

# OAuth2 credentials and URLs
CLIENT_ID = "46899977096215655"
CLIENT_SECRET = "9d85c43b1482497dbbce61f6e4aa173a433796eeae2ca8c5f6129f2dc4de46d9"
REDIRECT_URI = "https://embed.gog.com/on_login_success?origin=client"

# OAuth URL for browser-based login
OAUTH_URL_TEMPLATE = (
    "https://auth.gog.com/auth?"
    "client_id={client_id}&"
    "redirect_uri={redirect_uri}&"
    "response_type=code&"
    "layout=client2"
)

