import os
from pathlib import PurePosixPath, PureWindowsPath


def _resolve_shape(session, object_name: str):
    if object_name:
        if object_name not in session.objects:
            raise ValueError(f"Unknown object '{object_name}'. Registered: {list(session.objects.keys())}")
        return session.objects[object_name]
    if session.current_shape is None:
        raise ValueError("No shape in session. Execute code to create geometry first.")
    return session.current_shape


def export_file(session, filename: str, format: str = "step", object_name: str = "") -> str:
    shape = _resolve_shape(session, object_name)

    fmt = format.lower()
    if fmt not in ("step", "stl"):
        raise ValueError(f"Unknown format '{fmt}'. Use: step, stl")

    # Reject path traversal attempts
    if ".." in PurePosixPath(filename).parts or ".." in PureWindowsPath(filename).parts:
        raise ValueError("Path traversal not allowed.")

    if fmt == "step" and not filename.lower().endswith((".step", ".stp")):
        filename += ".step"
    elif fmt == "stl" and not filename.lower().endswith(".stl"):
        filename += ".stl"

    abs_path = os.path.realpath(filename)

    if fmt == "step":
        from build123d import export_step
        export_step(shape, abs_path)
    else:
        from build123d import Mesher
        mesher = Mesher()
        mesher.add_shape(shape)
        mesher.write(abs_path)

    return f"Exported to {abs_path}"
