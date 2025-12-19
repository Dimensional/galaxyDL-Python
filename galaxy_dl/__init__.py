"""
Galaxy DL - A specialized Python library for downloading GOG Galaxy files

This library provides a Python interface for downloading GOG Galaxy depot files,
including chunks and binary blobs from the Galaxy CDN.

Supports both V1 (main.bin blobs with range requests) and V2 (~10MB chunks).
"""

__version__ = "0.1.0"
__author__ = "galaxyDL-Python Contributors"
__license__ = "MIT"

from galaxy_dl.api import GalaxyAPI
from galaxy_dl.auth import AuthManager
from galaxy_dl.downloader import GalaxyDownloader
from galaxy_dl.models import DepotItem, DepotItemChunk, Manifest

__all__ = [
    "GalaxyAPI",
    "AuthManager",
    "GalaxyDownloader",
    "DepotItem",
    "DepotItemChunk",
    "Manifest",
]

