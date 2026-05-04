import struct

from build123d_mcp.tools._paths import safe_output_path

_VALID_FORMATS = ("step", "stl")


def _resolve_shape(session, object_name: str):
    if object_name == "*":
        if not session.objects:
            raise ValueError("No named objects in session. Use show() to register shapes first.")
        from build123d import Compound
        return Compound(children=list(session.objects.values()))
    if object_name:
        if object_name not in session.objects:
            raise ValueError(f"Unknown object '{object_name}'. Registered: {list(session.objects.keys())}")
        return session.objects[object_name]
    if session.current_shape is None:
        raise ValueError("No shape in session. Execute code to create geometry first.")
    return session.current_shape


def _stl_write(shape, abs_path: str) -> None:
    verts, tris = shape.tessellate(0.001, 0.1)

    with open(abs_path, "wb") as f:
        f.write(b"\x00" * 80)  # header
        f.write(struct.pack("<I", len(tris)))
        for tri in tris:
            v0 = verts[tri[0]]
            v1 = verts[tri[1]]
            v2 = verts[tri[2]]
            # flat normal via cross product
            ax, ay, az = v1.X - v0.X, v1.Y - v0.Y, v1.Z - v0.Z
            bx, by, bz = v2.X - v0.X, v2.Y - v0.Y, v2.Z - v0.Z
            nx, ny, nz = ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx
            length = (nx * nx + ny * ny + nz * nz) ** 0.5
            if length > 0:
                nx, ny, nz = nx / length, ny / length, nz / length
            f.write(struct.pack("<3f", nx, ny, nz))
            for v in (v0, v1, v2):
                f.write(struct.pack("<3f", v.X, v.Y, v.Z))
            f.write(b"\x00\x00")  # attribute byte count


def _write_one(shape, abs_path: str, fmt: str) -> None:
    if fmt == "step":
        from build123d import export_step
        export_step(shape, abs_path)
    else:
        _stl_write(shape, abs_path)


def export_file(session, filename: str, format: str = "step", object_name: str = "") -> str:
    shape = _resolve_shape(session, object_name)

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
        abs_path = safe_output_path(path)
        _write_one(shape, abs_path, fmt)
        exported.append(abs_path)

    if len(exported) == 1:
        return f"Exported to {exported[0]}"
    return "Exported to:\n" + "\n".join(exported)
