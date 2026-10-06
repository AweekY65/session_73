"""Local structured JSON diff / patch / three-way merge toolkit.

Everything runs in memory or on local files; no database, no network,
no external services.
"""

from .diff import diff
from .errors import PatchError, PathError
from .merge import Conflict, MergeResult, merge
from .patch import apply, invert, rollback

__all__ = [
    "diff", "apply", "invert", "rollback", "merge",
    "Conflict", "MergeResult", "PatchError", "PathError",
]

__version__ = "1.0.0"
