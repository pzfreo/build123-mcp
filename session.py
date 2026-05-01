import io
from contextlib import redirect_stdout, redirect_stderr

from security import (
    EXEC_TIMEOUT_SECONDS,
    ExecutionTimeout,
    check_ast,
    exec_with_timeout,
    make_restricted_builtins,
)


class Session:
    def __init__(self, exec_timeout: int = EXEC_TIMEOUT_SECONDS):
        self.exec_timeout = exec_timeout
        self.namespace = {}
        self.current_shape = None
        self.objects = {}
        self.snapshots = {}
        self._inject_builtins()

    def _inject_builtins(self):
        self.namespace["__builtins__"] = make_restricted_builtins()
        objects = self.objects

        def show(shape, name=None):
            if name is None:
                name = "shape"
            objects[name] = shape

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

        buf = io.StringIO()
        keys_before = set(self.namespace.keys())
        try:
            with redirect_stdout(buf), redirect_stderr(buf):
                # Layer 3: timeout wraps the actual exec
                exec_with_timeout(compiled, self.namespace, self.exec_timeout)
            new_keys = set(self.namespace.keys()) - keys_before
            self._update_current_shape(new_keys)
        except ExecutionTimeout as e:
            return f"Error: ExecutionTimeout: {e}"
        except Exception as e:
            return f"Error: {type(e).__name__}: {e}"
        output = buf.getvalue()
        return output if output else "OK"

    def _update_current_shape(self, new_keys):
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

    def reset(self):
        self.namespace.clear()
        self.current_shape = None
        self.objects.clear()
        self.snapshots.clear()
        self._inject_builtins()
