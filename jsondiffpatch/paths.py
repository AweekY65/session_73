"""JSON Pointer (RFC 6901) path helpers.

Paths are strings like ``/a/b/0``. The empty string ``""`` addresses the
root document. ``~0`` and ``~1`` escape ``~`` and ``/`` inside object keys.
"""

from .errors import PathError


def escape(token):
    return str(token).replace("~", "~0").replace("/", "~1")


def unescape(token):
    if "~" in token:
        # Reject invalid escape sequences such as "~2" or a trailing "~".
        i = 0
        while i < len(token):
            if token[i] == "~":
                if i + 1 >= len(token) or token[i + 1] not in "01":
                    raise PathError("invalid escape in path token: %r" % token)
                i += 2
            else:
                i += 1
        token = token.replace("~1", "/").replace("~0", "~")
    return token


def parse_pointer(path):
    """Parse a JSON Pointer string into a list of tokens."""
    if not isinstance(path, str):
        raise PathError("path must be a string, got %r" % type(path).__name__)
    if path == "":
        return []
    if not path.startswith("/"):
        raise PathError("path must be empty or start with '/': %r" % path)
    return [unescape(tok) for tok in path.split("/")[1:]]


def format_pointer(tokens):
    """Format a token list as a JSON Pointer string."""
    if not tokens:
        return ""
    return "/" + "/".join(escape(tok) for tok in tokens)
