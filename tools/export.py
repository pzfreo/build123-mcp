import os
from pathlib import PurePosixPath, PureWindowsPath

_VALID_FORMATS = ("step", "stl")


def _resolve_shape(session, object_name: str):
    if object_name:
        if object_name not in session.objects:
            raise ValueError(f"Unknown object '{object_name}'. Registered: {list(session.objects.keys())}")
        return session.objects[object_name]
    if session.current_shape is None:
        raise ValueError("No shape in session. Execute code to create geometry first.")
    return session.current_shape


def _write_one(shape, abs_path: str, fmt: str) -> None:
    if fmt == "step":
        from build123d import export_step
        export_step(shape, abs_path)
    else:
        from build123d import Mesher
        mesher = Mesher()
        mesher.add_shape(shape)
        mesher.write(abs_path)


def export_file(session, filename: str, format: str = "step", object_name: str = "") -> str:
    shape = _resolve_shape(session, object_name)

    # Reject path traversal attempts
    if ".." in PurePosixPath(filename).parts or ".." in PureWindowsPath(filename).parts:
        raise ValueError("Path traversal not allowed.")

    formats = [f.strip().lower() for f in format.split(",") if f.strip()]
    if not formats:
        raise ValueError("No format specified.")
    unknown = [f for f in formats if f not in _VALID_FORMATS]
    if unknown:
        raise ValueError(f"Unknown format(s) '{', '.join(unknown)}'. Use: step, stl")

    exported = []
    for fmt in formats:
        path = filename
        if fmt == "step" and not path.lower().endswith((".step", ".stp")):
            path += ".step"
        elif fmt == "stl" and not path.lower().endswith(".stl"):
            path += ".stl"
        abs_path = os.path.realpath(path)
        _write_one(shape, abs_path, fmt)
        exported.append(abs_path)

    if len(exported) == 1:
        return f"Exported to {exported[0]}"
    return "Exported to:\n" + "\n".join(exported)
