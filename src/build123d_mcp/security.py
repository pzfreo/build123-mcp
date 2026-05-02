"""
Lightweight defence-in-depth for exec'd user code.

Three layers:
  1. AST inspection  — rejects dangerous imports and calls before exec runs.
  2. Restricted builtins — namespace __builtins__ has open/eval/exec removed
     and __import__ filtered to the allowlist.
  3. Subprocess execution — code runs in a forked child process that can be
     hard-killed on timeout, eliminating the daemon-thread CPU leak of the
     previous threading-based approach.

This is not a complete sandbox. Determined Python sandbox escapes
(subclass traversal, ctypes, etc.) are not blocked. The goal is to raise
the bar against realistic prompt-injection payloads: shell commands,
filesystem reads, and network calls.
"""

import ast
import pickle
from typing import Any

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

def make_restricted_builtins() -> dict[str, Any]:
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

    def _safe_import(name: str, *args: Any, **kwargs: Any) -> Any:
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
# Layer 3: Subprocess execution with hard kill on timeout
# ---------------------------------------------------------------------------

class ExecutionTimeout(Exception):
    pass


def run_occ_in_fork(func: Any, *args: Any, timeout_sec: int = 60) -> Any:
    """Run func(*args) in a forked child process and return the result.

    Prevents OCC/TBB from starting background threads in the parent, which
    would deadlock subsequent os.fork() calls in exec_in_subprocess.

    The child inherits all parent memory (COW) so args need not be pickled
    before the fork.  The return value of func(*args) is sent back via pickle.
    Re-raises any exception raised inside the child.
    """
    import os
    import select
    import signal

    r_fd, w_fd = os.pipe()
    pid = os.fork()

    if pid == 0:
        os.close(r_fd)
        import io as _io
        w_file = _io.FileIO(w_fd, mode="wb", closefd=True)
        try:
            result = func(*args)
            flag = b"\x00"
            payload = pickle.dumps(result)
        except Exception as exc:
            flag = b"\x01"
            payload = pickle.dumps(exc)
        length = len(payload).to_bytes(4, "big")
        w_file.write(flag + length + payload)
        w_file.close()
        import os as _os
        _os._exit(0)

    os.close(w_fd)

    ready, _, _ = select.select([r_fd], [], [], timeout_sec)
    if not ready:
        os.close(r_fd)
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        os.waitpid(pid, 0)
        raise RuntimeError(f"OCC operation timed out after {timeout_sec}s.")

    with open(r_fd, "rb") as r_file:
        raw = r_file.read()

    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass

    if not raw or len(raw) < 5:
        raise RuntimeError("OCC subprocess returned no data.")

    status = raw[0:1]
    result_len = int.from_bytes(raw[1:5], "big")
    result_payload = raw[5 : 5 + result_len]
    result = pickle.loads(result_payload)

    if status == b"\x01":
        raise result  # re-raise the original exception
    return result


def _child_exec_worker(code: str, ns_bytes: bytes, conn: Any) -> None:
    """Entrypoint for the forked child process.

    Deserialises the namespace, executes the user code, then sends
    (stdout, exception, result_namespace, show_calls) back over conn.
    The parent can hard-kill this process on timeout with no thread leak.
    """
    import io
    import os
    from contextlib import redirect_stdout, redirect_stderr

    # Disconnect from the parent's stdio immediately.  The MCP server
    # communicates over stdin/stdout; any write to fd 1 or fd 2 from OCC
    # internals or asyncio cleanup in the child would corrupt the wire.
    # User code output is captured via redirect_stdout(buf) below.
    _devnull_w = os.open(os.devnull, os.O_WRONLY)
    _devnull_r = os.open(os.devnull, os.O_RDONLY)
    os.dup2(_devnull_r, 0)
    os.dup2(_devnull_w, 1)
    os.dup2(_devnull_w, 2)
    os.close(_devnull_w)
    os.close(_devnull_r)

    show_calls: list[tuple[str, Any]] = []

    def show(shape: Any, name: str | None = None) -> None:
        n = name or "shape"
        show_calls.append((n, shape))
        try:
            vol = shape.volume
            faces = len(shape.faces())
            print(f"Registered '{n}': volume={vol:.4g} mm³, faces={faces}")
        except Exception:
            print(f"Registered '{n}'")

    namespace: dict[str, Any] = pickle.loads(ns_bytes)
    namespace["__builtins__"] = make_restricted_builtins()
    namespace["show"] = show

    buf = io.StringIO()
    exc: Exception | None = None
    try:
        with redirect_stdout(buf), redirect_stderr(buf):
            exec(compile(code, "<mcp>", "exec"), namespace)  # noqa: S102
    except Exception as e:
        exc = e

    # Build result namespace, serialising each value.  BuildPart objects are
    # not picklable (OCC internals), so we fall back to their .part Shape.
    safe_ns: dict[str, Any] = {}
    for k, v in namespace.items():
        if k in ("__builtins__", "show"):
            continue
        try:
            pickle.dumps(v)
            safe_ns[k] = v
        except Exception:
            try:
                part = v.part  # BuildPart → Shape
                pickle.dumps(part)
                safe_ns[k] = part
            except Exception:
                pass  # skip anything that still can't be serialised

    try:
        conn.send((buf.getvalue(), exc, safe_ns, show_calls))
    except Exception as send_err:
        try:
            conn.send((buf.getvalue(), exc or send_err, {}, []))
        except Exception:
            pass
    conn.close()
    # Skip Python teardown: inherited asyncio/OCC state in the forked child
    # would otherwise run finalizers that can corrupt the parent's stdio.
    import os as _os
    _os._exit(0)


def exec_in_subprocess(
    code: str,
    user_namespace: dict[str, Any],
    timeout_sec: int,
) -> tuple[str, Exception | None, dict[str, Any], list[tuple[str, Any]]]:
    """Execute code in a forked child process.

    Returns (stdout, exception, new_namespace, show_calls).
    On timeout the process is hard-killed and ExecutionTimeout is raised.
    Uses raw os.fork() + os.pipe() to avoid multiprocessing bootstrap
    overhead which can deadlock inside an asyncio event loop.
    """
    import os
    import select
    import signal

    ns_bytes = pickle.dumps(user_namespace)

    r_fd, w_fd = os.pipe()
    pid = os.fork()

    if pid == 0:
        # ---- child ----
        os.close(r_fd)
        import io
        w_conn = io.FileIO(w_fd, mode="wb", closefd=True)

        class _Conn:
            def send(self, obj: Any) -> None:
                data = pickle.dumps(obj)
                length = len(data).to_bytes(4, "big")
                w_conn.write(length + data)
                w_conn.flush()

            def close(self) -> None:
                w_conn.close()

        _child_exec_worker(code, ns_bytes, _Conn())
        # _child_exec_worker ends with os._exit(0)

    # ---- parent ----
    os.close(w_fd)

    def _kill_child() -> None:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        os.waitpid(pid, 0)

    # Wait up to timeout_sec for the child to finish writing
    ready, _, _ = select.select([r_fd], [], [], timeout_sec)
    if not ready:
        os.close(r_fd)
        _kill_child()
        raise ExecutionTimeout(f"Code exceeded the {timeout_sec}s execution time limit.")

    try:
        with open(r_fd, "rb") as r_file:
            raw = r_file.read()
    except OSError:
        _kill_child()
        raise ExecutionTimeout(f"Code exceeded the {timeout_sec}s execution time limit.")

    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass

    if not raw:
        raise ExecutionTimeout(f"Code exceeded the {timeout_sec}s execution time limit.")

    length = int.from_bytes(raw[:4], "big")
    return pickle.loads(raw[4 : 4 + length])
