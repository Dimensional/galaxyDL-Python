"""
GUI Login Module for GOG Galaxy OAuth

Provides a Qt6-based browser window for easier OAuth authentication.
Automatically captures the authorization code from the redirect URL.

This module ONLY contains PySide6-specific GUI code. The core authentication
logic is in galaxy_dl.auth.AuthManager.

Requires: pip install galaxy-dl[gui]
"""

import logging
import sys
from typing import Optional

from galaxy_dl.auth import AuthManager


def gui_login(auth_manager: Optional[AuthManager] = None) -> Optional[str]:
    """
    Open GUI browser for GOG OAuth login and capture authorization code.
    
    Args:
        auth_manager: Optional AuthManager instance to use. If None, creates a new one.
    
    Returns:
        Authorization code string, or None if login failed/cancelled
        
    Raises:
        ImportError: If PySide6 is not installed
    """
    try:
        from PySide6.QtCore import QUrl, Slot
        from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except ImportError:
        raise ImportError(
            "PySide6 is required for GUI login.\n"
            "Install with: pip install galaxy-dl[gui]"
        )
    
    # Create auth manager if not provided
    if auth_manager is None:
        auth_manager = AuthManager()
    
    logger = logging.getLogger("galaxy_dl.gui_login")
    
    class LoginBrowser(QMainWindow):
        """Browser window for GOG OAuth login."""
        
        def __init__(self, auth_manager: AuthManager):
            super().__init__()
            self.auth_manager = auth_manager
            self.auth_code: Optional[str] = None
            
            # Setup window
            self.setWindowTitle("GOG Galaxy Login")
            self.setMinimumSize(800, 600)
            
            # Setup web view
            self.browser = QWebEngineView()
            self.setCentralWidget(self.browser)
            
            # Connect URL changed signal
            self.browser.urlChanged.connect(self.on_url_changed)
            
            # Load OAuth URL from auth manager
            oauth_url = self.auth_manager.get_oauth_url()
            logger.info(f"Loading OAuth URL: {oauth_url}")
            self.browser.setUrl(QUrl(oauth_url))
        
        @Slot(QUrl)
        def on_url_changed(self, url: QUrl):
            """Handle URL changes to detect OAuth redirect."""
            url_str = url.toString()
            logger.debug(f"URL changed: {url_str}")
            
            # Use auth manager to extract code
            code = self.auth_manager.extract_code_from_url(url_str)
            
            if code:
                self.auth_code = code
                logger.info(f"Authorization code captured: {code[:10]}...")
                
                # Show success message
                QMessageBox.information(
                    self,
                    "Login Successful",
                    "Authorization code captured successfully!\n\nYou can close this window."
                )
                
                # Close the browser
                self.close()
    
    # Create Qt application if not already running
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    # Create and show login browser
    browser = LoginBrowser(auth_manager)
    browser.show()
    
    # Run event loop
    app.exec()
    
    # Return captured auth code
    return browser.auth_code


def main():
    """Test GUI login standalone."""
    logging.basicConfig(level=logging.INFO)
    
    print("Opening GUI browser for GOG login...")
    print("Please sign in and authorize the application.")
    print()
    
    code = gui_login()
    
    if code:
        print(f"\n✓ Success! Authorization code: {code}")
        print("\nYou can now use this code with AuthManager.login_with_code():")
        print(f"  auth_manager.login_with_code('{code}')")
