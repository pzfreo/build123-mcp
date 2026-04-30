import json


def measure(session, query: str = "bounding_box") -> str:
    shape = session.current_shape
    if shape is None:
        raise ValueError("No shape in session. Execute code to create geometry first.")

    query = query.lower()
    if query != "bounding_box":
        raise ValueError(f"Unknown query '{query}'. Use: bounding_box")

    bb = shape.bounding_box()
    result = {
        "xmin": bb.min.X,
        "xmax": bb.max.X,
        "ymin": bb.min.Y,
        "ymax": bb.max.Y,
        "zmin": bb.min.Z,
        "zmax": bb.max.Z,
        "xsize": bb.size.X,
        "ysize": bb.size.Y,
        "zsize": bb.size.Z,
        "center": {
            "x": (bb.min.X + bb.max.X) / 2,
            "y": (bb.min.Y + bb.max.Y) / 2,
            "z": (bb.min.Z + bb.max.Z) / 2,
        },
    }
    return json.dumps(result, indent=2)
