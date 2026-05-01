import os
import tempfile

_display_initialized = False

_PALETTE = [
    "lightblue", "lightcoral", "lightgreen",
    "lightyellow", "plum", "peachpuff", "lightcyan",
]


def _init_display():
    global _display_initialized
    if not _display_initialized:
        if not os.environ.get("DISPLAY"):
            import warnings
            import pyvista as pv
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pv.start_xvfb()
        _display_initialized = True


def _resolve_shapes(session, objects: str):
    """Return list of (name, shape) tuples based on objects selector."""
    if objects:
        names = [n.strip() for n in objects.split(",") if n.strip()]
        missing = [n for n in names if n not in session.objects]
        if missing:
            raise ValueError(f"Unknown object(s): {', '.join(missing)}")
        return [(n, session.objects[n]) for n in names]
    if session.objects:
        return list(session.objects.items())
    if session.current_shape is not None:
        return [("shape", session.current_shape)]
    raise ValueError("No shape in session. Execute code to create geometry first.")


def render_view(session, direction: str = "iso", objects: str = "") -> bytes:
    direction = direction.lower()
    if direction not in ("top", "front", "side", "iso"):
        raise ValueError(f"Unknown direction '{direction}'. Use: top, front, side, iso")

    shapes = _resolve_shapes(session, objects)

    _init_display()
    import pyvista as pv
    from build123d import Mesher

    with tempfile.TemporaryDirectory() as tmpdir:
        png_path = os.path.join(tmpdir, "render.png")
        plotter = pv.Plotter(off_screen=True, window_size=[800, 600])

        for i, (name, shape) in enumerate(shapes):
            stl_path = os.path.join(tmpdir, f"shape_{i}.stl")
            mesher = Mesher()
            mesher.add_shape(shape)
            mesher.write(stl_path)
            mesh = pv.read(stl_path)
            plotter.add_mesh(
                mesh,
                color=_PALETTE[i % len(_PALETTE)],
                smooth_shading=True,
                ambient=0.3,
                diffuse=0.7,
                specular=0.2,
            )

        plotter.background_color = "white"

        if direction == "top":
            plotter.view_xy()
        elif direction == "front":
            plotter.view_xz()
        elif direction == "side":
            plotter.view_yz()
        else:
            plotter.view_isometric()

        plotter.screenshot(png_path)
        plotter.close()

        with open(png_path, "rb") as f:
            return f.read()
