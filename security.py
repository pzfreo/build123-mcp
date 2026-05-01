"""
Lightweight defence-in-depth for exec'd user code.

Three layers:
  1. AST inspection  — rejects dangerous imports and calls before exec runs.
  2. Restricted builtins — namespace __builtins__ has open/eval/exec removed
     and __import__ filtered to the allowlist.
  3. Execution timeout — a background thread enforces a wall-clock limit.

This is not a complete sandbox. Determined Python sandbox escapes
(subclass traversal, ctypes, etc.) are not blocked. The goal is to raise
the bar against realistic prompt-injection payloads: shell commands,
filesystem reads, and network calls.
"""

import ast
import threading

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EXEC_TIMEOUT_SECONDS = 30

# Modules user code may import. build123d's own internal imports are
# unaffected — they run through the real import system, not this namespace.
IMPORT_ALLOWLIST = frozenset({
    "build123d",
    "math",
    "numpy",
    "typing",
    "collections",
    "itertools",
    "functools",
    "copy",
})

# Builtins that are dangerous even without an import.
_BLOCKED_BUILTINS = frozenset({
    "eval", "exec", "compile", "open", "breakpoint", "input",
})

# Bare-name calls that are caught at the AST level (before exec runs).
_BLOCKED_CALL_NAMES = frozenset({
    "__import__", "eval", "exec", "compile", "open", "breakpoint", "input",
})


# ---------------------------------------------------------------------------
# Layer 1: AST inspection
# ---------------------------------------------------------------------------

def check_ast(code: str) -> None:
    """Raise ValueError if code contains disallowed imports or dangerous calls.

    Catches the most common injection patterns before exec() is ever called.
    Syntax errors are left for exec() to report with better messages.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _check_module(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                _check_module(node.module)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in _BLOCKED_CALL_NAMES:
                raise ValueError(
                    f"Call to '{node.func.id}' is not allowed."
                )


def _check_module(dotted_name: str) -> None:
    root = dotted_name.split(".")[0]
    if root not in IMPORT_ALLOWLIST:
        raise ValueError(
            f"Import of '{dotted_name}' is not allowed. "
            f"This blocks filesystem (os, pathlib, shutil), network (socket, urllib, "
            f"requests), and shell access (subprocess). "
            f"Permitted: {sorted(IMPORT_ALLOWLIST)}"
        )


# ---------------------------------------------------------------------------
# Layer 2: Restricted builtins
# ---------------------------------------------------------------------------

def make_restricted_builtins() -> dict:
    """Return a __builtins__ dict with dangerous functions removed.

    open / eval / exec / compile are removed outright.
    __import__ is replaced with an allowlisted version so that
    'from build123d import *' works but 'import os' is blocked at the
    namespace level even if AST inspection is somehow bypassed.
    """
    import builtins
    safe = vars(builtins).copy()

    for name in _BLOCKED_BUILTINS:
        safe.pop(name, None)

    _original_import = safe["__import__"]

    def _safe_import(name, *args, **kwargs):
        root = name.split(".")[0]
        if root not in IMPORT_ALLOWLIST:
            raise ImportError(
                f"Import of '{name}' is not allowed. "
                f"Permitted: {sorted(IMPORT_ALLOWLIST)}"
            )
        return _original_import(name, *args, **kwargs)

    safe["__import__"] = _safe_import
    return safe


# ---------------------------------------------------------------------------
# Layer 3: Execution timeout
# ---------------------------------------------------------------------------

class ExecutionTimeout(Exception):
    pass


def exec_with_timeout(compiled, namespace: dict, timeout_sec: int) -> None:
    """Run exec(compiled, namespace) and raise ExecutionTimeout if it exceeds timeout_sec.

    Uses a daemon thread so this works regardless of which thread the caller
    is in (e.g. asyncio event loop). The background thread may outlive the
    timeout — it is daemon so it will not prevent process exit, but it may
    still modify namespace after the timeout. Callers should treat the
    namespace as potentially dirty after a timeout.
    """
    exc_holder: list = [None]

    def _run() -> None:
        try:
            exec(compiled, namespace)  # noqa: S102
        except Exception as exc:
            exc_holder[0] = exc

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout_sec)

    if t.is_alive():
        raise ExecutionTimeout(f"Code exceeded the {timeout_sec}s execution time limit.")
    if exc_holder[0] is not None:
        raise exc_holder[0]
