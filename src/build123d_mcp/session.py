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
        self.last_error_detail: dict[str, Any] | None = None
        self._inject_builtins()

    def _inject_builtins(self) -> None:
        self.namespace["__builtins__"] = make_restricted_builtins()
        objects = self.objects

        session_ref = self

        def show(shape: Any, name: str | None = None) -> None:
            if name is None:
                name = "shape"
            objects[name] = shape
            session_ref.current_shape = shape
            try:
                vol = shape.volume
                faces = len(shape.faces())
                print(f"Registered '{name}': volume={vol:.4g} mm³, faces={faces}")
            except Exception:
                print(f"Registered '{name}'")

        self.namespace["show"] = show

    def _quick_diagnostics(self, shape) -> str:
        try:
            bb = shape.bounding_box()
            vol = shape.volume
            faces = len(shape.faces())
            edges = len(shape.edges())
            verts = len(shape.vertices())
            return (
                f"--- current_shape ---\n"
                f"volume: {vol:.4g} mm³  |  "
                f"bbox: {bb.size.X:.4g}×{bb.size.Y:.4g}×{bb.size.Z:.4g} mm  |  "
                f"{faces}f {edges}e {verts}v"
            )
        except Exception:
            return ""

    def execute(self, code: str) -> str:
        # Layer 1: AST check before anything runs
        try:
            check_ast(code)
        except ValueError as e:
            self.last_error_detail = {"type": "SecurityError", "message": str(e), "line": None, "excerpt": None}
            return f"Error: SecurityError: {e}"

        try:
            compiled = compile(code, "<mcp>", "exec")
        except SyntaxError as e:
            excerpt = self._syntax_excerpt(code, e.lineno)
            self.last_error_detail = {"type": "SyntaxError", "message": str(e), "line": e.lineno, "excerpt": excerpt}
            return f"Error: SyntaxError: {e}"

        values_before = {k: self.namespace[k] for k in self.namespace if k not in ("__builtins__", "show")}
        shape_before = self.current_shape
        objects_before = dict(self.objects)

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
            self._rollback_namespace(values_before)
            self.current_shape = shape_before
            self.objects.clear()
            self.objects.update(objects_before)
            self.last_error_detail = {"type": "ExecutionTimeout", "message": str(e), "line": None, "excerpt": None}
            return f"Error: ExecutionTimeout: {e}"
        except AssertionError as e:
            self._rollback_namespace(values_before)
            self.current_shape = shape_before
            self.objects.clear()
            self.objects.update(objects_before)
            msg = str(e) or "Constraint failed"
            self.last_error_detail = {"type": "AssertionError", "message": msg, "line": None, "excerpt": None}
            return f"Constraint failed: {e}" if str(e) else "Constraint failed"
        except Exception as e:
            exc = e
        finally:
            if _alarm_set:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, _old_handler)

        if exc is not None:
            self._rollback_namespace(values_before)
            self.current_shape = shape_before
            self.objects.clear()
            self.objects.update(objects_before)
            self.last_error_detail = self._make_error_detail(exc, code)
            return f"Error: {type(exc).__name__}: {exc}"

        self.last_error_detail = None
        new_keys = {k for k in self.namespace if k not in ("__builtins__", "show")} - values_before.keys()
        self._update_current_shape(new_keys)

        output = buf.getvalue() or "OK"
        if self.current_shape is not None and self.current_shape is not shape_before:
            diag = self._quick_diagnostics(self.current_shape)
            if diag:
                output = output.rstrip("\n") + "\n" + diag
        return output

    def _rollback_namespace(self, values_before: dict[str, Any]) -> None:
        # Delete keys that didn't exist before; restore values for keys that were overwritten.
        current = {k for k in self.namespace if k not in ("__builtins__", "show")}
        for k in current - values_before.keys():
            del self.namespace[k]
        for k, v in values_before.items():
            self.namespace[k] = v

    def _syntax_excerpt(self, code: str, lineno: int | None) -> str | None:
        if lineno is None:
            return None
        lines = code.splitlines()
        start = max(0, lineno - 3)
        end = min(len(lines), lineno + 2)
        return "\n".join(
            f"{i + 1:3d}{'→ ' if i + 1 == lineno else '  '}{lines[i]}"
            for i in range(start, end)
        )

    def _make_error_detail(self, exc: Exception, code: str) -> dict[str, Any]:
        import traceback as tb_module
        frames = tb_module.extract_tb(exc.__traceback__)
        mcp_frames = [f for f in frames if f.filename == "<mcp>"]
        lineno: int | None = mcp_frames[-1].lineno if mcp_frames else None
        excerpt: str | None = None
        if lineno is not None:
            lines = code.splitlines()
            start = max(0, lineno - 3)
            end = min(len(lines), lineno + 2)
            excerpt = "\n".join(
                f"{i + 1:3d}{'→ ' if i + 1 == lineno else '  '}{lines[i]}"
                for i in range(start, end)
            )
        return {"type": type(exc).__name__, "message": str(exc), "line": lineno, "excerpt": excerpt}

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
        self.last_error_detail = None
        self._inject_builtins()
