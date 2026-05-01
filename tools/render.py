import os
import tempfile

_display_initialized = False


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


def render_view(session, direction: str = "iso") -> bytes:
    shape = session.current_shape
    if shape is None:
        raise ValueError("No shape in session. Execute code to create geometry first.")

    direction = direction.lower()
    if direction not in ("top", "front", "side", "iso"):
        raise ValueError(f"Unknown direction '{direction}'. Use: top, front, side, iso")

    _init_display()
    import pyvista as pv
    from build123d import Mesher

    with tempfile.TemporaryDirectory() as tmpdir:
        stl_path = os.path.join(tmpdir, "shape.stl")
        png_path = os.path.join(tmpdir, "render.png")

        mesher = Mesher()
        mesher.add_shape(shape)
        mesher.write(stl_path)

        mesh = pv.read(stl_path)
        plotter = pv.Plotter(off_screen=True, window_size=[800, 600])
        plotter.add_mesh(
            mesh,
            color="lightblue",
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
