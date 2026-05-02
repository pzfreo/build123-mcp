import io
import signal
from contextlib import redirect_stdout, redirect_stderr
from typing import Any

from build123d_mcp.security import (
    EXEC_TIMEOUT_SECONDS,
    ExecutionTimeout,
    check_ast,
    make_restricted_builtins,
)


class Session:
    def __init__(self, exec_timeout: int = EXEC_TIMEOUT_SECONDS):
        self.exec_timeout = exec_timeout
        self.namespace: dict[str, Any] = {}
        self.current_shape: Any = None
        self.objects: dict[str, Any] = {}
        self.snapshots: dict[str, Any] = {}
        self._inject_builtins()

    def _inject_builtins(self) -> None:
        self.namespace["__builtins__"] = make_restricted_builtins()
        objects = self.objects

        def show(shape: Any, name: str | None = None) -> None:
            if name is None:
                name = "shape"
            objects[name] = shape
            try:
                vol = shape.volume
                faces = len(shape.faces())
                print(f"Registered '{name}': volume={vol:.4g} mm³, faces={faces}")
            except Exception:
                print(f"Registered '{name}'")

        self.namespace["show"] = show

    def execute(self, code: str) -> str:
        # Layer 1: AST check before anything runs
        try:
            check_ast(code)
        except ValueError as e:
            return f"Error: SecurityError: {e}"

        try:
            compiled = compile(code, "<mcp>", "exec")
        except SyntaxError as e:
            return f"Error: SyntaxError: {e}"

        keys_before = {k for k in self.namespace if k not in ("__builtins__", "show")}

        buf = io.StringIO()
        exc: Exception | None = None

        # Layer 3: SIGALRM timeout (Unix main-thread only; silently skipped otherwise).
        # Fire 2s before the parent's conn.poll() deadline so the worker always
        # returns a response before the parent kills it.
        _alarm_set = False
        _old_handler: Any = None
        try:
            def _timeout_handler(signum: int, frame: Any) -> None:
                raise ExecutionTimeout(
                    f"Code exceeded the {self.exec_timeout}s execution time limit."
                )
            _old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(max(1, self.exec_timeout - 2))
            _alarm_set = True
        except (OSError, ValueError, AttributeError):
            pass  # Windows (no SIGALRM) or non-main thread; no timeout protection

        try:
            with redirect_stdout(buf), redirect_stderr(buf):
                exec(compiled, self.namespace)  # noqa: S102
        except ExecutionTimeout as e:
            return f"Error: ExecutionTimeout: {e}"
        except Exception as e:
            exc = e
        finally:
            if _alarm_set:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, _old_handler)

        new_keys = {k for k in self.namespace if k not in ("__builtins__", "show")} - keys_before
        self._update_current_shape(new_keys)

        if exc is not None:
            return f"Error: {type(exc).__name__}: {exc}"

        return buf.getvalue() or "OK"

    def _update_current_shape(self, new_keys: set[str]) -> None:
        try:
            from build123d import Shape, BuildPart
        except ImportError:
            return

        ns = self.namespace

        # Always prefer explicit 'result', even if it pre-existed
        if "result" in ns and isinstance(ns["result"], Shape):
            self.current_shape = ns["result"]
            return

        # Scan newly created variables for BuildPart or Shape
        for key in new_keys:
            if key.startswith("_"):
                continue
            obj = ns.get(key)
            if isinstance(obj, BuildPart):
                try:
                    self.current_shape = obj.part
                    return
                except Exception:
                    pass
            elif isinstance(obj, Shape):
                self.current_shape = obj
                return

    def save_snapshot(self, name: str) -> None:
        self.snapshots[name] = {
            "current_shape": self.current_shape,
            "objects": dict(self.objects),
        }

    def restore_snapshot(self, name: str) -> None:
        if name not in self.snapshots:
            raise KeyError(f"No snapshot named '{name}'. Available: {list(self.snapshots.keys())}")
        snap = self.snapshots[name]
        self.current_shape = snap["current_shape"]
        self.objects.clear()
        self.objects.update(snap["objects"])

    def reset(self) -> None:
        self.namespace.clear()
        self.current_shape = None
        self.objects.clear()
        self.snapshots.clear()
        self._inject_builtins()
