"""
RGOG (Reproducible GOG Archive) Format Tools

A self-contained implementation for creating and managing RGOG archives
following the RGOG Format Specification v2.0.
"""

__version__ = "2.0.0"

# Import submodules to make them available
from . import common
from . import pack
from . import list
from . import extract
from . import verify
from . import info

__all__ = [
    'common',
    'pack',
    'list',
    'extract',
    'verify',
    'info',
]
