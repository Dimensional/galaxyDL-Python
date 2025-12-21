"""
Manifest diff utilities for comparing game builds
"""

from dataclasses import dataclass, field
from typing import List

from galaxy_dl.models import DepotItem, FilePatchDiff


@dataclass
class ManifestDiff:
    """
    Represents the difference between two manifests.
    
    Attributes:
        new: Files that don't exist in old manifest
        changed: Files that changed (need full download)
        patched: Files that can be updated via patches (FilePatchDiff objects)
        deleted: Files that exist in old but not new manifest
    """
    new: List[DepotItem] = field(default_factory=list)
    changed: List[DepotItem] = field(default_factory=list)
    patched: List[FilePatchDiff] = field(default_factory=list)
    deleted: List[DepotItem] = field(default_factory=list)

    def __str__(self) -> str:
        """Human-readable summary of diff."""
        parts = []
        if self.new:
            parts.append(f"{len(self.new)} new")
        if self.changed:
            parts.append(f"{len(self.changed)} changed")
        if self.patched:
            parts.append(f"{len(self.patched)} patched")
        if self.deleted:
            parts.append(f"{len(self.deleted)} deleted")
        
        return "ManifestDiff: " + ", ".join(parts) if parts else "ManifestDiff: no changes"
