"""Error types for jsondiffpatch."""


class PatchError(Exception):
    """Raised when a patch is malformed or cannot be applied.

    Covers: nonexistent paths, type mismatches while resolving a path,
    unknown/illegal operations and ``old`` value mismatches.
    """


class PathError(PatchError):
    """Raised when a JSON Pointer path is syntactically invalid."""
