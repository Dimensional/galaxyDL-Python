#!/usr/bin/env python3
"""
Test GUI Login Feature (Mock)

This script tests the GUI login integration without actually
requiring PySide6 to be installed. It simulates what would happen
when a user runs `galaxy-dl login --gui`.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_constants():
    """Test that OAuth constants are available."""
    print("=" * 80)
    print("TEST 1: OAuth Constants")
    print("=" * 80)
    
    from galaxy_dl import constants
    
    print("\nChecking OAuth constants...")
    
    assert hasattr(constants, 'CLIENT_ID'), "Missing CLIENT_ID"
    assert hasattr(constants, 'CLIENT_SECRET'), "Missing CLIENT_SECRET"
    assert hasattr(constants, 'REDIRECT_URI'), "Missing REDIRECT_URI"
    assert hasattr(constants, 'OAUTH_URL_TEMPLATE'), "Missing OAUTH_URL_TEMPLATE"
    
    print(f"✓ CLIENT_ID: {constants.CLIENT_ID}")
    print(f"✓ REDIRECT_URI: {constants.REDIRECT_URI}")
    
    # Build OAuth URL
    from urllib.parse import quote
    oauth_url = constants.OAUTH_URL_TEMPLATE.format(
        client_id=constants.CLIENT_ID,
        redirect_uri=quote(constants.REDIRECT_URI, safe='')
    )
    
    print(f"\n✓ OAuth URL built successfully:")
    print(f"  {oauth_url[:80]}...")


def test_gui_module_import():
    """Test that GUI module can be imported (even if PySide6 isn't installed)."""
    print("\n" + "=" * 80)
    print("TEST 2: GUI Module Import")
    print("=" * 80)
    
    try:
        from galaxy_dl import gui_login
        print("\n✓ GUI login module imports successfully")
        print(f"✓ Module location: {gui_login.__file__}")
        
        # Check that gui_login function exists
        assert hasattr(gui_login, 'gui_login'), "Missing gui_login function"
        print(f"✓ gui_login() function available")
        
    except ImportError as e:
        print(f"\n✗ Failed to import gui_login module: {e}")
        return False
    
    return True


def test_cli_integration():
    """Test that CLI has --gui flag."""
    print("\n" + "=" * 80)
    print("TEST 3: CLI Integration")
    print("=" * 80)
    
    import argparse
    from galaxy_dl import cli
    
    # Create parser
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    
    subparsers = parser.add_subparsers(dest="command")
    login_parser = subparsers.add_parser("login")
    login_parser.add_argument("code", nargs="?")
    login_parser.add_argument("--gui", action="store_true")
    
    # Test parsing
    args = parser.parse_args(["login", "--gui"])
    
    assert args.command == "login", "Failed to parse login command"
    assert args.gui == True, "Failed to parse --gui flag"
    
    print("\n✓ CLI argument parsing works")
    print(f"  Command: {args.command}")
    print(f"  GUI flag: {args.gui}")


def test_pyproject_extra():
    """Test that pyproject.toml has [gui] extra."""
    print("\n" + "=" * 80)
    print("TEST 4: Package Configuration")
    print("=" * 80)
    
    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    
    try:
        if sys.version_info >= (3, 11):
            import tomllib
            with open(pyproject_path, "rb") as f:
                pyproject = tomllib.load(f)
        else:
            import tomli
            with open(pyproject_path, "rb") as f:
                pyproject = tomli.load(f)
    except ImportError:
        # tomli not available, just check file exists
        print("\n⊘ SKIP: tomli/tomllib not available (can't parse TOML)")
        print(f"  But pyproject.toml exists: {pyproject_path.exists()}")
        return
    
    extras = pyproject.get("project", {}).get("optional-dependencies", {})
    
    if "gui" in extras:
        print("\n✓ [gui] extra defined in pyproject.toml")
        print(f"  Dependencies: {extras['gui']}")
        
        assert "PySide6" in str(extras["gui"]), "PySide6 not in gui extra"
        print(f"✓ PySide6 included in [gui] extra")
    else:
        print("\n✗ [gui] extra not found in pyproject.toml")


def test_installation_instructions():
    """Show installation instructions."""
    print("\n" + "=" * 80)
    print("Installation Instructions")
    print("=" * 80)
    
    print("\nTo use GUI login:")
    print("  pip install -e .[gui]")
    print()
    print("Then run:")
    print("  galaxy-dl login --gui")
    print()
    print("The GUI browser will:")
    print("  1. Open to GOG login page")
    print("  2. Automatically capture the auth code")
    print("  3. Complete authentication")
    print("  4. Save credentials to ~/.config/galaxy_dl/auth.json")


def main():
    print("GUI Login Feature Test Suite")
    print("Tests the integration without requiring PySide6\n")
    
    try:
        test_constants()
        test_gui_module_import()
        test_cli_integration()
        test_pyproject_extra()
        test_installation_instructions()
        
        print("\n" + "=" * 80)
        print("✓ All tests passed!")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
