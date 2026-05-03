"""Shared output-path validation for file-writing tools.

Allowed write roots:
  - the current working directory (the MCP server's `cwd`)
  - `tempfile.gettempdir()` (`$TMPDIR` on macOS, `/tmp` on most Linux)
  - `/tmp` itself when present (covers Linux installs where `gettempdir()`
    returns something else, and macOS where `/tmp` is a symlink to `/private/tmp`)

Validation runs after `os.path.realpath()`, so symlink escapes and `..`
traversal are rejected naturally rather than relying on textual checks.
"""

from __future__ import annotations

import os
import tempfile


def _allowed_roots() -> list[str]:
    roots: list[str] = [
        os.path.realpath(os.getcwd()),
        os.path.realpath(tempfile.gettempdir()),
    ]
    if os.path.isdir("/tmp"):
        slash_tmp = os.path.realpath("/tmp")
        if slash_tmp not in roots:
            roots.append(slash_tmp)
    return roots


def safe_output_path(filename: str) -> str:
    """Resolve `filename` and reject paths outside the allowed write roots.

    Returns the resolved absolute path on success. Raises ``ValueError``
    if the resolved path is not under one of the allowed roots — this
    covers absolute paths to sensitive locations, `..` traversal, and
    symlink escapes in a single check.
    """
    resolved = os.path.realpath(filename)
    for root in _allowed_roots():
        if resolved == root or resolved.startswith(root + os.sep):
            return resolved
    raise ValueError(
        f"Path '{filename}' resolves to '{resolved}', "
        f"which is outside the allowed write roots."
    )
