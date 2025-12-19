"""
Authentication Manager for GOG Galaxy API
Based on heroic-gogdl auth.py with improvements from lgogdownloader
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, Optional

import requests

from galaxy_dl import constants

# OAuth2 credentials for GOG Galaxy
CLIENT_ID = "46899977096215655"
CLIENT_SECRET = "9d85c43b1482497dbbce61f6e4aa173a433796eeae2ca8c5f6129f2dc4de46d9"
REDIRECT_URI = "https://embed.gog.com/on_login_success?origin=client"


class AuthManager:
    """
    Manages GOG Galaxy OAuth2 authentication and token refresh.
    
    Stores credentials in a JSON file and automatically refreshes tokens when expired.
    """

    def __init__(self, config_path: Optional[str] = None, client_id: str = CLIENT_ID,
                 client_secret: str = CLIENT_SECRET):
        """
        Initialize the authentication manager.
        
        Args:
            config_path: Path to store credentials JSON file. If None, uses default location.
            client_id: OAuth2 client ID for GOG Galaxy
            client_secret: OAuth2 client secret for GOG Galaxy
        """
        self.logger = logging.getLogger("galaxy_dl.auth")
        self.client_id = client_id
        self.client_secret = client_secret
        
        # Set config path
        if config_path is None:
            config_dir = Path.home() / ".config" / "galaxy_dl"
            config_dir.mkdir(parents=True, exist_ok=True)
            self.config_path = config_dir / "auth.json"
        else:
            self.config_path = Path(config_path)
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.credentials: Dict = {}
        self._load_credentials()
        
        # Setup session
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": constants.USER_AGENT.format(version="0.1.0")
        })

    def _load_credentials(self) -> None:
        """Load credentials from the config file if it exists."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    self.credentials = json.load(f)
                self.logger.debug(f"Loaded credentials from {self.config_path}")
            except (json.JSONDecodeError, IOError) as e:
                self.logger.error(f"Failed to load credentials: {e}")
                self.credentials = {}

    def _save_credentials(self) -> None:
        """Save credentials to the config file."""
        try:
            with open(self.config_path, "w") as f:
                json.dump(self.credentials, f, indent=2)
            self.logger.debug(f"Saved credentials to {self.config_path}")
        except IOError as e:
            self.logger.error(f"Failed to save credentials: {e}")

    def is_authenticated(self) -> bool:
        """Check if user is authenticated and has valid credentials."""
        if not self.credentials:
            return False
        
        # Check if access token exists
        if "access_token" not in self.credentials:
            return False
        
        # Check if token is expired
        if self.is_token_expired():
            # Try to refresh
            return self.refresh_token()
        
        return True

    def is_token_expired(self) -> bool:
        """
        Check if the current access token is expired.
        
        Returns:
            True if token is expired or about to expire (within 60 seconds)
        """
        if "expires_in" not in self.credentials or "login_time" not in self.credentials:
            return True
        
        expiry_time = self.credentials["login_time"] + self.credentials["expires_in"]
        # Consider token expired 60 seconds before actual expiry
        return time.time() >= (expiry_time - 60)

    def login_with_code(self, code: str) -> bool:
        """
        Authenticate using an OAuth2 authorization code.
        
        Args:
            code: The authorization code obtained from GOG OAuth flow
            
        Returns:
            True if authentication successful, False otherwise
        """
        url = f"{constants.GOG_AUTH}/token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI
        }
        
        try:
            response = self.session.get(url, params=params, timeout=constants.DEFAULT_TIMEOUT)
            response.raise_for_status()
            
            token_data = response.json()
            token_data["login_time"] = int(time.time())
            self.credentials = token_data
            self._save_credentials()
            
            self.logger.info("Successfully authenticated with authorization code")
            return True
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to authenticate with code: {e}")
            return False

    def refresh_token(self, without_new_session: bool = False) -> bool:
        """
        Refresh the access token using the refresh token.
        
        Args:
            without_new_session: If True, request token refresh without creating new session
            
        Returns:
            True if refresh successful, False otherwise
        """
        if "refresh_token" not in self.credentials:
            self.logger.error("No refresh token available")
            return False
        
        url = f"{constants.GOG_AUTH}/token"
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.credentials["refresh_token"]
        }
        
        if without_new_session:
            params["without_new_session"] = "1"
        
        try:
            response = self.session.get(url, params=params, timeout=constants.DEFAULT_TIMEOUT)
            response.raise_for_status()
            
            token_data = response.json()
            token_data["login_time"] = int(time.time())
            self.credentials = token_data
            self._save_credentials()
            
            self.logger.info("Successfully refreshed access token")
            return True
            
        except requests.RequestException as e:
            self.logger.error(f"Failed to refresh token: {e}")
            return False

    def get_access_token(self) -> Optional[str]:
        """
        Get a valid access token, refreshing if necessary.
        
        Returns:
            Access token string, or None if not authenticated
        """
        if not self.is_authenticated():
            return None
        
        return self.credentials.get("access_token")

    def get_auth_header(self) -> Optional[str]:
        """
        Get the Authorization header value.
        
        Returns:
            Bearer token string for Authorization header, or None if not authenticated
        """
        access_token = self.get_access_token()
        if access_token:
            return f"Bearer {access_token}"
        return None

    def logout(self) -> None:
        """Clear stored credentials and logout."""
        self.credentials = {}
        if self.config_path.exists():
            self.config_path.unlink()
        self.logger.info("Logged out and cleared credentials")

