import os
from pathlib import PurePosixPath, PureWindowsPath


def export_file(session, filename: str, format: str = "step") -> str:
    shape = session.current_shape
    if shape is None:
        raise ValueError("No shape in session. Execute code to create geometry first.")

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
