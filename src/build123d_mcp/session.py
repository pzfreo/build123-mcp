import io
from contextlib import redirect_stdout, redirect_stderr
from typing import Any

from build123d_mcp.security import (
    EXEC_TIMEOUT_SECONDS,
    ExecutionTimeout,
    check_ast,
    exec_in_subprocess,
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
            compile(code, "<mcp>", "exec")
        except SyntaxError as e:
            return f"Error: SyntaxError: {e}"

        user_ns = {k: v for k, v in self.namespace.items() if k not in ("__builtins__", "show")}
        keys_before = set(user_ns.keys())

        try:
            # Layer 3: runs in a forked child process; hard-killed on timeout
            stdout, exc, new_namespace, show_calls = exec_in_subprocess(
                code, user_ns, self.exec_timeout
            )
        except ExecutionTimeout as e:
            return f"Error: ExecutionTimeout: {e}"

        if exc is not None:
            return f"Error: {type(exc).__name__}: {exc}"

        self.namespace.update(new_namespace)
        for name, shape in show_calls:
            self.objects[name] = shape

        new_keys = set(new_namespace.keys()) - keys_before
        self._update_current_shape(new_keys)

        return stdout if stdout else "OK"

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
