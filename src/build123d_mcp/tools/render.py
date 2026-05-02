import os
import select
import signal

_display_initialized = False

_PALETTE = [
    "lightblue", "lightcoral", "lightgreen",
    "lightyellow", "plum", "peachpuff", "lightcyan",
]

_QUALITY = {
    "standard": {"linear_deflection": 0.001, "angular_deflection": 0.1},
    "high":     {"linear_deflection": 0.0005, "angular_deflection": 0.02},
}


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
    """Return list of (name, shape, color_or_None) tuples based on objects selector.

    Each entry in the comma-separated objects string may be 'name' or 'name:color'.
    """
    if objects:
        result = []
        for entry in [e.strip() for e in objects.split(",") if e.strip()]:
            if ":" in entry:
                name, color = entry.split(":", 1)
                name, color = name.strip(), color.strip()
            else:
                name, color = entry, None
            if name not in session.objects:
                raise ValueError(f"Unknown object(s): {name}")
            result.append((name, session.objects[name], color))
        return result
    if session.objects:
        return [(n, s, None) for n, s in session.objects.items()]
    if session.current_shape is not None:
        return [("shape", session.current_shape, None)]
    raise ValueError("No shape in session. Execute code to create geometry first.")


def _do_render(shapes, tess, direction, clip_plane, clip_at, azimuth, elevation) -> bytes:
    """Run pyvista rendering in the current process.  Call only from a forked child."""
    import tempfile
    import pyvista as pv
    from build123d import Mesher

    with tempfile.TemporaryDirectory() as tmpdir:
        png_path = os.path.join(tmpdir, "render.png")
        plotter = pv.Plotter(off_screen=True, window_size=[800, 600])

        for i, (name, shape, obj_color) in enumerate(shapes):
            stl_path = os.path.join(tmpdir, f"shape_{i}.stl")
            mesher = Mesher()
            mesher.add_shape(shape, **tess)  # type: ignore[arg-type]
            mesher.write(stl_path)
            mesh = pv.read(stl_path)

            if clip_plane:
                if clip_at is not None:
                    origin = {"x": [clip_at, 0, 0], "y": [0, clip_at, 0], "z": [0, 0, clip_at]}[clip_plane]
                else:
                    origin = list(mesh.center)
                mesh = mesh.clip(normal=clip_plane, origin=origin, invert=False)

            plotter.add_mesh(
                mesh,  # type: ignore[arg-type]
                color=obj_color if obj_color else _PALETTE[i % len(_PALETTE)],
                smooth_shading=True,
                ambient=0.3,
                diffuse=0.7,
                specular=0.2,
            )

        plotter.background_color = "white"  # type: ignore[assignment]

        if direction == "top":
            plotter.view_xy()  # type: ignore[call-arg]
        elif direction == "front":
            plotter.view_xz()  # type: ignore[call-arg]
        elif direction == "side":
            plotter.view_yz()  # type: ignore[call-arg]
        else:
            plotter.view_isometric()  # type: ignore[call-arg]

        if azimuth != 0.0 or elevation != 0.0:
            plotter.camera.Azimuth(azimuth)
            plotter.camera.Elevation(elevation)
            plotter.camera.OrthogonalizeViewUp()
            plotter.reset_camera_clipping_range()

        plotter.screenshot(png_path)
        plotter.close()

        with open(png_path, "rb") as f:
            return f.read()


def _render_in_fork(shapes, tess, direction, clip_plane, clip_at, azimuth, elevation) -> bytes:
    """Fork a child to run meshing + pyvista rendering.

    This isolates OCC/TBB threads from the parent process so they cannot corrupt
    the fork state of subsequent os.fork() calls in exec_in_subprocess.
    """
    r_fd, w_fd = os.pipe()
    pid = os.fork()

    if pid == 0:
        # Child: do all OCC meshing and VTK rendering here, then exit.
        os.close(r_fd)

        # Suppress VTK/pyvista noise on stderr.
        devnull_w = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull_w, 2)
        os.close(devnull_w)

        import io as _io
        w_file = _io.FileIO(w_fd, mode="wb", closefd=True)

        try:
            png_data = _do_render(shapes, tess, direction, clip_plane, clip_at, azimuth, elevation)
            flag = b"\x00"
            payload = png_data
        except Exception as exc:
            flag = b"\x01"
            payload = str(exc).encode("utf-8", errors="replace")

        length = len(payload).to_bytes(4, "big")
        w_file.write(flag + length + payload)
        w_file.close()
        import os as _os
        _os._exit(0)

    # Parent
    os.close(w_fd)

    _RENDER_TIMEOUT = 120
    ready, _, _ = select.select([r_fd], [], [], _RENDER_TIMEOUT)
    if not ready:
        os.close(r_fd)
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        os.waitpid(pid, 0)
        raise RuntimeError(f"Rendering timed out after {_RENDER_TIMEOUT}s.")

    with open(r_fd, "rb") as r_file:
        raw = r_file.read()

    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass

    if not raw or len(raw) < 5:
        raise RuntimeError("Rendering subprocess returned no data.")

    status = raw[0:1]
    result_len = int.from_bytes(raw[1:5], "big")
    payload = raw[5 : 5 + result_len]

    if status == b"\x01":
        raise RuntimeError(f"Rendering error: {payload.decode('utf-8', errors='replace')}")

    return payload


def render_view(
    session,
    direction: str = "iso",
    objects: str = "",
    quality: str = "standard",
    clip_plane: str = "",
    clip_at: float | None = None,
    azimuth: float = 0.0,
    elevation: float = 0.0,
    save_to: str = "",
) -> bytes:
    direction = direction.lower()
    if direction not in ("top", "front", "side", "iso"):
        raise ValueError(f"Unknown direction '{direction}'. Use: top, front, side, iso")

    quality = quality.lower()
    if quality not in _QUALITY:
        raise ValueError(f"Unknown quality '{quality}'. Use: standard, high")

    clip_plane = clip_plane.lower()
    if clip_plane and clip_plane not in ("x", "y", "z"):
        raise ValueError(f"Unknown clip_plane '{clip_plane}'. Use: x, y, z")

    shapes = _resolve_shapes(session, objects)
    tess = _QUALITY[quality]

    # Start xvfb (if needed) in the parent so children inherit DISPLAY.
    # Importing pyvista here is safe: it does not create VTK objects or start threads.
    _init_display()

    # All meshing + rendering runs in a fork subprocess.  This prevents OCC/TBB
    # from starting background threads in the parent, which would deadlock
    # subsequent os.fork() calls in exec_in_subprocess.
    png_bytes = _render_in_fork(shapes, tess, direction, clip_plane, clip_at, azimuth, elevation)

    if save_to:
        from pathlib import PurePosixPath, PureWindowsPath
        if os.path.isabs(save_to) or ".." in PurePosixPath(save_to).parts or ".." in PureWindowsPath(save_to).parts:
            raise ValueError("Path traversal not allowed.")
        dest = save_to if save_to.lower().endswith(".png") else save_to + ".png"
        import os as _os
        with open(_os.path.realpath(dest), "wb") as f:
            f.write(png_bytes)

    return png_bytes
