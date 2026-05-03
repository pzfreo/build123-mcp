"""Persistent worker subprocess and parent-side proxy for build123d-mcp sessions.

Architecture:
  WorkerSession (parent)  ←── multiprocessing.Pipe ──→  worker_main (child)
                                                             └─ Session + tools

The worker process owns the Session and calls all tool functions directly —
no forking, no namespace serialization per call. OCC/TBB threads are confined
to the worker; the parent process never touches OCC at all.

Timeout is managed at the WorkerSession level: if conn.poll() expires the
parent kills the worker with SIGKILL and restarts it (fresh session).
Within the worker, Session.execute() also applies a SIGALRM guard so that
a hanging execute() call returns an error rather than blocking indefinitely.
"""

import multiprocessing
from typing import Any

_WORKER_READY_TIMEOUT = 60  # seconds to wait for worker import + ready signal


def worker_main(conn: Any, library_path: str = "") -> None:
    """Entry point run in the worker subprocess.

    Loops receiving requests until the parent closes the connection.
    """
    from build123d_mcp.session import Session

    session = Session()
    library_index = None
    if library_path:
        from build123d_mcp.tools.library import _LibraryIndex
        library_index = _LibraryIndex(library_path)

    conn.send({"ready": True})

    while True:
        try:
            request = conn.recv()
        except EOFError:
            break

        op = request["op"]
        args = request.get("args", {})

        try:
            result = _dispatch(session, op, args, library_index)
            conn.send({"ok": True, "result": result})
        except Exception as exc:
            conn.send({"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def _dispatch(session: Any, op: str, args: dict, library_index: Any) -> Any:
    if op == "execute":
        return session.execute(args["code"])

    if op == "render_view":
        from build123d_mcp.tools.render import render_view
        return render_view(session, **args)

    if op == "export_file":
        from build123d_mcp.tools.export import export_file
        return export_file(session, **args)

    if op == "interference":
        from build123d_mcp.tools.interference import interference
        return interference(session, **args)

    if op == "measure":
        from build123d_mcp.tools.measure import measure
        return measure(session, **args)

    if op == "list_objects":
        from build123d_mcp.tools.list_objects import list_objects
        return list_objects(session)

    if op == "save_snapshot":
        name = args["name"]
        session.save_snapshot(name)
        saved = (["current_shape"] if session.current_shape is not None else []) + list(session.snapshots[name]["objects"].keys())
        return f"Snapshot '{name}' saved. Geometry captured: {', '.join(saved) if saved else 'none'}."

    if op == "restore_snapshot":
        name = args["name"]
        try:
            session.restore_snapshot(name)
        except KeyError as e:
            return f"Error: {e}"
        restored = (["current_shape"] if session.current_shape is not None else []) + list(session.objects.keys())
        return f"Snapshot '{name}' restored. Active geometry: {', '.join(restored) if restored else 'none'}."

    if op == "reset":
        session.reset()
        return "Session reset."

    if op == "search_library":
        if library_index is None:
            return "No part library configured."
        from build123d_mcp.tools.library import search_library
        return search_library(library_index, args.get("query", ""))

    if op == "load_part":
        if library_index is None:
            return "No part library configured."
        from build123d_mcp.tools.library import load_part
        return load_part(session, library_index, args["name"], args.get("params", ""))

    if op == "diff_snapshot":
        from build123d_mcp.tools.diff import diff_snapshot
        return diff_snapshot(session, args["snapshot_a"], args.get("snapshot_b", ""))

    raise ValueError(f"Unknown operation: '{op}'")


class WorkerSession:
    """Parent-side proxy to the persistent worker subprocess.

    Exposes the same interface as Session so server.py can use either.
    """

    _RENDER_TIMEOUT = 120
    _EXPORT_TIMEOUT = 60
    _INTERFERENCE_TIMEOUT = 30
    _SHORT_TIMEOUT = 10

    def __init__(self, exec_timeout: int = 30, library_path: str = "") -> None:
        self._exec_timeout = exec_timeout
        self._library_path = library_path
        self._conn: Any = None
        self._proc: Any = None
        self._start_worker()

    def _start_worker(self) -> None:
        ctx = multiprocessing.get_context("spawn")
        parent_conn, child_conn = ctx.Pipe()
        self._proc = ctx.Process(
            target=worker_main,
            args=(child_conn, self._library_path),
            daemon=True,
        )
        self._proc.start()
        child_conn.close()
        self._conn = parent_conn

        if not self._conn.poll(_WORKER_READY_TIMEOUT):
            self._proc.kill()
            self._proc.join(5)
            raise RuntimeError("Worker process failed to start within timeout.")
        self._conn.recv()  # consume the ready signal

    def _kill_worker(self) -> None:
        try:
            self._proc.kill()
            self._proc.join(5)
        except Exception:
            pass

    def _call(self, op: str, args: dict, timeout: int) -> Any:
        if not self._proc.is_alive():
            self._start_worker()
            raise RuntimeError("Worker crashed; session restarted. Re-run your setup code.")

        self._conn.send({"op": op, "args": args})

        if not self._conn.poll(timeout):
            self._kill_worker()
            self._start_worker()
            from build123d_mcp.security import ExecutionTimeout
            if op == "execute":
                raise ExecutionTimeout(
                    f"Code exceeded the {timeout}s execution time limit."
                )
            raise RuntimeError(f"Operation '{op}' timed out after {timeout}s.")

        try:
            response = self._conn.recv()
        except EOFError:
            self._start_worker()
            raise RuntimeError("Worker process crashed unexpectedly; session restarted.")

        if response["ok"]:
            return response["result"]
        raise RuntimeError(response["error"])

    # --- Session-compatible interface ---

    def execute(self, code: str) -> str:
        from build123d_mcp.security import ExecutionTimeout
        try:
            return self._call("execute", {"code": code}, self._exec_timeout)
        except (RuntimeError, ExecutionTimeout) as e:
            return f"Error: {e}"

    def render_view(
        self,
        direction: str = "iso",
        objects: str = "",
        quality: str = "standard",
        clip_plane: str = "",
        clip_at: float | None = None,
        azimuth: float = 0.0,
        elevation: float = 0.0,
        save_to: str = "",
        format: str = "png",
    ) -> dict:
        return self._call(
            "render_view",
            {
                "direction": direction,
                "objects": objects,
                "quality": quality,
                "clip_plane": clip_plane,
                "clip_at": clip_at,
                "azimuth": azimuth,
                "elevation": elevation,
                "save_to": save_to,
                "format": format,
            },
            self._RENDER_TIMEOUT,
        )

    def export_file(self, filename: str, format: str = "step", object_name: str = "") -> str:
        return self._call(
            "export_file",
            {"filename": filename, "format": format, "object_name": object_name},
            self._EXPORT_TIMEOUT,
        )

    def interference(self, object_a: str, object_b: str) -> str:
        return self._call(
            "interference",
            {"object_a": object_a, "object_b": object_b},
            self._INTERFERENCE_TIMEOUT,
        )

    def measure(self, query: str = "bounding_box", object_name: str = "", object_name2: str = "") -> str:
        return self._call(
            "measure",
            {"query": query, "object_name": object_name, "object_name2": object_name2},
            self._SHORT_TIMEOUT,
        )

    def list_objects(self) -> str:
        return self._call("list_objects", {}, self._SHORT_TIMEOUT)

    def save_snapshot(self, name: str) -> str:
        return self._call("save_snapshot", {"name": name}, self._SHORT_TIMEOUT)

    def restore_snapshot(self, name: str) -> str:
        return self._call("restore_snapshot", {"name": name}, self._SHORT_TIMEOUT)

    def reset(self) -> str:
        if not self._proc.is_alive():
            self._start_worker()
            return "Session reset."
        return self._call("reset", {}, self._SHORT_TIMEOUT)

    def diff_snapshot(self, snapshot_a: str, snapshot_b: str = "") -> str:
        return self._call("diff_snapshot", {"snapshot_a": snapshot_a, "snapshot_b": snapshot_b}, self._SHORT_TIMEOUT)

    def search_library(self, query: str = "") -> str:
        return self._call("search_library", {"query": query}, self._SHORT_TIMEOUT)

    def load_part(self, name: str, params: str = "") -> str:
        return self._call("load_part", {"name": name, "params": params}, self._SHORT_TIMEOUT)
