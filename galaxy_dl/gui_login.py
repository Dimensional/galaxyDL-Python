"""
GUI Login Module for GOG Galaxy OAuth

Provides a Qt6-based browser window for easier OAuth authentication.
Automatically captures the authorization code from the redirect URL.

Requires: pip install galaxy-dl[gui]
"""

import logging
import sys
from typing import Optional
from urllib.parse import urlparse, parse_qs


def gui_login() -> Optional[str]:
    """
    Open GUI browser for GOG OAuth login and capture authorization code.
    
    Returns:
        Authorization code string, or None if login failed/cancelled
        
    Raises:
        ImportError: If PySide6 is not installed
    """
    try:
        from PySide6.QtCore import QUrl, Slot
        from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebEngineCore import QWebEnginePage
    except ImportError:
        raise ImportError(
            "PySide6 is required for GUI login.\n"
            "Install with: pip install galaxy-dl[gui]"
        )
    
    from galaxy_dl import constants
    
    logger = logging.getLogger("galaxy_dl.gui_login")
    
    class LoginBrowser(QMainWindow):
        """Browser window for GOG OAuth login."""
        
        def __init__(self):
            super().__init__()
            self.auth_code: Optional[str] = None
            
            # Setup window
            self.setWindowTitle("GOG Galaxy Login")
            self.setMinimumSize(800, 600)
            
            # Setup web view
            self.browser = QWebEngineView()
            self.setCentralWidget(self.browser)
            
            # Connect URL changed signal
            self.browser.urlChanged.connect(self.on_url_changed)
            
            # Load GOG OAuth URL
            oauth_url = constants.OAUTH_URL_TEMPLATE.format(
                client_id=constants.CLIENT_ID,
                redirect_uri=constants.REDIRECT_URI
            )
            logger.info(f"Loading OAuth URL: {oauth_url}")
            self.browser.setUrl(QUrl(oauth_url))
        
        @Slot(QUrl)
        def on_url_changed(self, url: QUrl):
            """Handle URL changes to detect OAuth redirect."""
            url_str = url.toString()
            logger.debug(f"URL changed: {url_str}")
            
            # Check if this is the success redirect
            if url_str.startswith(constants.REDIRECT_URI):
                logger.info("OAuth redirect detected")
                
                # Parse URL to extract code
                parsed = urlparse(url_str)
                params = parse_qs(parsed.query)
                
                if 'code' in params:
                    self.auth_code = params['code'][0]
                    logger.info(f"Authorization code captured: {self.auth_code[:10]}...")
                    
                    # Show success message
                    QMessageBox.information(
                        self,
                        "Login Successful",
                        "Authorization code captured successfully!\n\nYou can close this window."
                    )
                    
                    # Close the browser
                    self.close()
                else:
                    logger.warning("Redirect URL missing 'code' parameter")
                    QMessageBox.warning(
                        self,
                        "Login Error",
                        "Failed to capture authorization code from redirect URL."
                    )
    
    # Create Qt application if not already running
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    # Create and show login browser
    browser = LoginBrowser()
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
        print("\nYou can now use this code with:")
        print(f"  galaxy-dl login {code}")
    else:
        print("\n✗ Login cancelled or failed")


if __name__ == "__main__":
    main()
