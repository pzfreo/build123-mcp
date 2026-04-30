import os


def export_file(session, filename: str, format: str = "step") -> str:
    shape = session.current_shape
    if shape is None:
        raise ValueError("No shape in session. Execute code to create geometry first.")

    fmt = format.lower()
    if fmt not in ("step", "stl"):
        raise ValueError(f"Unknown format '{fmt}'. Use: step, stl")

    if fmt == "step" and not filename.lower().endswith((".step", ".stp")):
        filename += ".step"
    elif fmt == "stl" and not filename.lower().endswith(".stl"):
        filename += ".stl"

    if fmt == "step":
        from build123d import export_step
        export_step(shape, filename)
    else:
        from build123d import Mesher
        mesher = Mesher()
        mesher.add_shape(shape)
        mesher.write(filename)

    return f"Exported to {os.path.abspath(filename)}"
