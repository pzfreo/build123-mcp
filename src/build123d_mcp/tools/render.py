import math
import os
import sys

_xvfb_started = False


def _ensure_display() -> None:
    """Spawn Xvfb on Linux when no DISPLAY is set, mirroring what
    pyvista.start_xvfb() did before pyvista 0.48 removed it.

    Idempotent. No-op on macOS/Windows (which have a display) or when
    DISPLAY is already set. If the Xvfb binary is missing, leaves
    DISPLAY unset and lets the VTK render fail; the caller's SVG
    fallback then takes over.
    """
    global _xvfb_started
    if _xvfb_started or sys.platform != "linux" or os.environ.get("DISPLAY"):
        return

    import random
    import shutil
    import subprocess
    import time

    if not shutil.which("Xvfb"):
        return

    for _ in range(5):
        display_num = random.randint(100, 999)
        lock_file = f"/tmp/.X{display_num}-lock"
        if os.path.exists(lock_file):
            continue
        try:
            proc = subprocess.Popen(
                ["Xvfb", f":{display_num}", "-screen", "0", "1024x768x24", "-ac"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return

        for _ in range(30):
            time.sleep(0.1)
            if os.path.exists(lock_file):
                break

        if proc.poll() is None and os.path.exists(lock_file):
            os.environ["DISPLAY"] = f":{display_num}"
            _xvfb_started = True
            return

        try:
            proc.kill()
        except Exception:
            pass

_PALETTE = [
    "lightblue", "lightcoral", "lightgreen",
    "lightyellow", "plum", "peachpuff", "lightcyan",
]

_QUALITY = {
    "standard": {"linear_deflection": 0.001, "angular_deflection": 0.1},
    "high":     {"linear_deflection": 0.0005, "angular_deflection": 0.02},
}

_VALID_FORMATS = ("png", "svg", "dxf", "both")


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


def _color_to_rgb(name: str) -> tuple[float, float, float]:
    from matplotlib.colors import to_rgb
    return to_rgb(name)


def _camera_direction(direction: str) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Return (position_unit_vector, view_up) for the named view direction."""
    if direction == "top":
        return (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)
    if direction == "front":
        return (0.0, -1.0, 0.0), (0.0, 0.0, 1.0)
    if direction == "side":
        return (1.0, 0.0, 0.0), (0.0, 0.0, 1.0)
    return (1.0, 1.0, 1.0), (0.0, 0.0, 1.0)  # iso


def _resolve_object_labels(shapes) -> list[tuple[tuple[float, float, float], str]]:
    """Return [(position, name)] for each rendered shape with a non-default name."""
    out = []
    for name, shape, _color in shapes:
        if not name or name == "shape":
            # auto-name from bare current_shape — labelling it "shape" adds noise
            continue
        try:
            c = shape.center()
            out.append(((c.X, c.Y, c.Z), name))
        except Exception:
            try:
                bb = shape.bounding_box()
                c = bb.center
                out.append(((c.X, c.Y, c.Z), name))
            except Exception:
                pass
    return out


def _resolve_highlights(session, shapes, highlights) -> list[tuple[tuple[float, float, float], str]]:
    """Validate and resolve highlight specs to [(position, label)].

    Each highlight must be a dict with keys: object, type, index, label.
    Raises ValueError for any malformed or unresolvable entry.
    """
    if not highlights:
        return []
    rendered_names = {name for name, _, _ in shapes}
    out = []
    for h in highlights:
        if not isinstance(h, dict):
            raise ValueError(f"highlight must be a dict, got {type(h).__name__}: {h!r}")
        missing = [k for k in ("object", "type", "index", "label") if k not in h]
        if missing:
            raise ValueError(f"highlight missing required key(s) {missing}: {h!r}")
        obj_name = h["object"]
        ent_type = h["type"]
        index = h["index"]
        label = str(h["label"])

        if obj_name not in session.objects:
            raise ValueError(
                f"highlight references unknown object '{obj_name}'. "
                f"Register it first with show(shape, '{obj_name}')."
            )
        if obj_name not in rendered_names:
            raise ValueError(
                f"highlight references '{obj_name}' which is registered but not in the rendered set. "
                f"Add it to objects= or omit the highlight."
            )
        if ent_type not in ("face", "edge", "vertex"):
            raise ValueError(f"highlight type must be 'face', 'edge', or 'vertex', got '{ent_type}'")
        if not isinstance(index, int):
            raise ValueError(f"highlight index must be int, got {type(index).__name__}: {index!r}")

        shape = session.objects[obj_name]
        items = {"face": shape.faces(), "edge": shape.edges(), "vertex": shape.vertices()}[ent_type]
        n = len(items)
        if not (0 <= index < n):
            raise ValueError(
                f"highlight {ent_type} index {index} out of range for '{obj_name}' (valid: 0..{n - 1})"
            )
        entity = items[index]
        try:
            c = entity.center()
            position = (c.X, c.Y, c.Z)
        except Exception:
            try:
                position = (entity.X, entity.Y, entity.Z)
            except Exception as exc:
                raise ValueError(
                    f"could not compute position for {obj_name}.{ent_type}[{index}]: {exc}"
                )
        out.append((position, label))
    return out


def _add_label_actors(renderer, labels) -> None:
    """Add billboard text actors at each (position, text) pair.

    The renderer should be a depth-cleared overlay layer so labels at interior
    points (e.g. a solid's centroid) aren't occluded by the geometry.
    """
    if not labels:
        return
    import vtk
    for position, text in labels:
        actor = vtk.vtkBillboardTextActor3D()
        actor.SetPosition(*position)
        actor.SetInput(str(text))
        prop = actor.GetTextProperty()
        prop.SetFontSize(16)
        prop.SetColor(0.0, 0.0, 0.0)
        prop.SetBold(True)
        prop.SetBackgroundColor(1.0, 1.0, 1.0)
        prop.SetBackgroundOpacity(0.85)
        prop.SetFrame(True)
        prop.SetFrameColor(0.2, 0.2, 0.2)
        renderer.AddActor(actor)


def _do_render_png(shapes, tess, direction, clip_plane, clip_at, azimuth, elevation, labels=None) -> tuple[bytes, list[str]]:
    import tempfile
    import vtk

    _ensure_display()

    renderer = vtk.vtkRenderer()
    renderer.SetBackground(1.0, 1.0, 1.0)

    render_window = vtk.vtkRenderWindow()
    render_window.SetOffScreenRendering(1)
    render_window.SetSize(800, 600)
    render_window.AddRenderer(renderer)

    # Labels live on an overlay renderer that draws after the depth buffer is
    # cleared, so a label sitting at a solid's centroid stays readable instead
    # of being occluded by the surrounding geometry.
    label_renderer = None
    if labels:
        label_renderer = vtk.vtkRenderer()
        label_renderer.SetActiveCamera(renderer.GetActiveCamera())
        label_renderer.SetLayer(1)
        render_window.SetNumberOfLayers(2)
        render_window.AddRenderer(label_renderer)

    failed: list[str] = []
    actor_count = 0

    for i, (name, shape, obj_color) in enumerate(shapes):
        try:
            verts, tris = shape.tessellate(
                tess["linear_deflection"], tess["angular_deflection"]
            )
        except Exception as exc:
            failed.append(f"{name}: {exc}")
            continue

        points = vtk.vtkPoints()
        for v in verts:
            points.InsertNextPoint(v.X, v.Y, v.Z)

        cells = vtk.vtkCellArray()
        for tri in tris:
            cells.InsertNextCell(3)
            cells.InsertCellPoint(tri[0])
            cells.InsertCellPoint(tri[1])
            cells.InsertCellPoint(tri[2])

        poly = vtk.vtkPolyData()
        poly.SetPoints(points)
        poly.SetPolys(cells)

        if clip_plane:
            if clip_at is not None:
                origin = {"x": (clip_at, 0, 0), "y": (0, clip_at, 0), "z": (0, 0, clip_at)}[clip_plane]
            else:
                bounds = poly.GetBounds()  # xmin, xmax, ymin, ymax, zmin, zmax
                cx = (bounds[0] + bounds[1]) / 2
                cy = (bounds[2] + bounds[3]) / 2
                cz = (bounds[4] + bounds[5]) / 2
                origin = {"x": (cx, 0, 0), "y": (0, cy, 0), "z": (0, 0, cz)}[clip_plane]
            normal = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[clip_plane]

            plane = vtk.vtkPlane()
            plane.SetOrigin(*origin)
            plane.SetNormal(*normal)

            clipper = vtk.vtkClipPolyData()
            clipper.SetInputData(poly)
            clipper.SetClipFunction(plane)
            clipper.SetInsideOut(False)
            clipper.Update()
            poly = clipper.GetOutput()

        # Compute vertex normals so Phong shading works on both B-rep tessellations
        # and imported mesh shells (STL), where face orientations may be inconsistent.
        normals_filter = vtk.vtkPolyDataNormals()
        normals_filter.SetInputData(poly)
        normals_filter.ComputePointNormalsOn()
        normals_filter.ConsistencyOn()
        normals_filter.AutoOrientNormalsOn()
        normals_filter.Update()
        poly = normals_filter.GetOutput()

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputData(poly)

        actor = vtk.vtkActor()
        actor.SetMapper(mapper)

        r, g, b = _color_to_rgb(obj_color if obj_color else _PALETTE[i % len(_PALETTE)])
        prop = actor.GetProperty()
        prop.SetColor(r, g, b)
        prop.SetAmbient(0.3)
        prop.SetDiffuse(0.7)
        prop.SetSpecular(0.2)
        prop.SetInterpolationToPhong()  # smooth shading

        renderer.AddActor(actor)
        actor_count += 1

    if actor_count == 0:
        msg = "All shapes failed to tessellate: " + "; ".join(failed) if failed else "No geometry to render"
        raise RuntimeError(msg)

    if label_renderer is not None:
        _add_label_actors(label_renderer, labels)

    # Camera setup
    camera = renderer.GetActiveCamera()
    camera.SetParallelProjection(False)
    pos, up = _camera_direction(direction)
    camera.SetPosition(*pos)
    camera.SetFocalPoint(0.0, 0.0, 0.0)
    camera.SetViewUp(*up)
    renderer.ResetCamera()

    if azimuth != 0.0 or elevation != 0.0:
        camera.Azimuth(azimuth)
        camera.Elevation(elevation)
        camera.OrthogonalizeViewUp()
        renderer.ResetCameraClippingRange()

    render_window.Render()

    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(render_window)
    w2i.Update()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        png_path = os.path.join(tmpdir, "render.png")
        writer = vtk.vtkPNGWriter()
        writer.SetFileName(png_path)
        writer.SetInputConnection(w2i.GetOutputPort())
        writer.Write()

        with open(png_path, "rb") as f:
            return f.read(), failed


def _viewport_origin_for(direction: str, shapes, azimuth: float, elevation: float):
    """Compute (origin, up, look_at) for build123d's project_to_viewport.

    Distance is chosen large enough to be effectively orthographic. Azimuth/
    elevation rotate the iso baseline around the look-at point. For top/front/
    side they rotate around the cardinal axis-aligned baseline.
    """
    from build123d import Vector
    # Aggregate bounding centre across all shapes for look_at
    centres = [shape.center() for _name, shape, _c in shapes]
    centre = sum(centres, Vector(0, 0, 0)) * (1.0 / len(centres))

    # Direction vector matches the VTK camera baseline
    dx, dy, dz = {
        "top":   (0.0, 0.0, 1.0),
        "front": (0.0, -1.0, 0.0),
        "side":  (1.0, 0.0, 0.0),
    }.get(direction, (1.0, 1.0, 1.0))
    up = (0.0, 1.0, 0.0) if direction == "top" else (0.0, 0.0, 1.0)

    # Apply azimuth/elevation as rotations of the direction vector
    if azimuth != 0.0:
        a = math.radians(azimuth)
        dx, dy = dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)
    if elevation != 0.0:
        e = math.radians(elevation)
        # Rotate in the plane spanned by current direction and up
        ux, uy, uz = up
        # simple elevation: tilt the dz component
        horiz = math.sqrt(dx * dx + dy * dy)
        new_horiz = horiz * math.cos(e) - dz * math.sin(e)
        dz = horiz * math.sin(e) + dz * math.cos(e)
        if horiz > 1e-9:
            dx = dx * (new_horiz / horiz)
            dy = dy * (new_horiz / horiz)

    # Distance: 10x the largest bounding extent across all shapes (effectively orthographic)
    extents = []
    for _n, s, _c in shapes:
        bb = s.bounding_box()
        extents.extend([bb.size.X, bb.size.Y, bb.size.Z])
    distance = max(extents + [1.0]) * 10.0

    origin = (
        centre.X + dx * distance,
        centre.Y + dy * distance,
        centre.Z + dz * distance,
    )
    look_at = (centre.X, centre.Y, centre.Z)
    return origin, up, look_at


def _do_render_svg(shapes, direction, clip_plane, clip_at, azimuth, elevation) -> bytes:
    """Produce an SVG via build123d's HLR projection.

    Multi-shape: each shape gets its own colored layer (matching the PNG palette).
    Visible edges are drawn solid; hidden edges dashed and lighter.
    Clip plane is honoured by splitting each shape at the plane and projecting
    only the keep-side.
    """
    import tempfile
    from build123d import ExportSVG, Plane, Vector

    # Optionally clip each shape to the keep-side of the requested plane
    clipped_shapes = []
    if clip_plane:
        for name, shape, color in shapes:
            if clip_at is not None:
                origin = {"x": (clip_at, 0, 0), "y": (0, clip_at, 0), "z": (0, 0, clip_at)}[clip_plane]
            else:
                c = shape.center()
                origin = {"x": (c.X, 0, 0), "y": (0, c.Y, 0), "z": (0, 0, c.Z)}[clip_plane]
            normal = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[clip_plane]
            plane = Plane(origin=Vector(*origin), z_dir=Vector(*normal))
            try:
                halves = shape.split(plane, keep=None)
                # split with keep=None returns a tuple of (positive_side, negative_side);
                # invert=False in PNG path means we keep the +normal side
                kept = halves[0] if isinstance(halves, tuple) else halves
            except Exception:
                kept = shape  # fall back to unclipped if split is unsupported for the shape type
            clipped_shapes.append((name, kept, color))
    else:
        clipped_shapes = list(shapes)

    origin, up, look_at = _viewport_origin_for(direction, clipped_shapes, azimuth, elevation)

    exporter = ExportSVG(margin=5, line_weight=0.25)
    for i, (name, shape, obj_color) in enumerate(clipped_shapes):
        try:
            visible, hidden = shape.project_to_viewport(
                viewport_origin=origin, viewport_up=up, look_at=look_at,
            )
        except Exception:
            continue

        from build123d import Color
        rgb = _color_to_rgb(obj_color if obj_color else _PALETTE[i % len(_PALETTE)])
        line_color = Color(*rgb)

        layer_visible = f"{name or f'shape_{i}'}_visible"
        layer_hidden = f"{name or f'shape_{i}'}_hidden"
        exporter.add_layer(layer_visible, line_color=line_color, line_weight=0.4)
        exporter.add_layer(layer_hidden, line_color=line_color, line_weight=0.15)
        if visible:
            exporter.add_shape(visible, layer=layer_visible)
        if hidden:
            exporter.add_shape(hidden, layer=layer_hidden)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        svg_path = os.path.join(tmpdir, "render.svg")
        exporter.write(svg_path)
        with open(svg_path, "rb") as f:
            return f.read()


def _do_render_dxf(shapes, direction, clip_plane, clip_at, azimuth, elevation) -> bytes:
    """Produce a DXF via build123d's HLR projection.

    DXF is the standard 2D CAD interchange format. Use it when the LLM (or a
    downstream tool) needs the projected geometry as parseable polylines
    rather than as a raster — e.g. building a matplotlib annotation overlay
    on top of a faithful base layer instead of redrawing the shape by hand.

    Each input shape becomes two layers: <name>_visible (solid) and
    <name>_hidden (dashed). Clip-plane handling mirrors the SVG path.
    """
    import tempfile
    from build123d import ExportDXF, LineType, Plane, Vector

    clipped_shapes = []
    if clip_plane:
        for name, shape, color in shapes:
            if clip_at is not None:
                origin = {"x": (clip_at, 0, 0), "y": (0, clip_at, 0), "z": (0, 0, clip_at)}[clip_plane]
            else:
                c = shape.center()
                origin = {"x": (c.X, 0, 0), "y": (0, c.Y, 0), "z": (0, 0, c.Z)}[clip_plane]
            normal = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[clip_plane]
            plane = Plane(origin=Vector(*origin), z_dir=Vector(*normal))
            try:
                halves = shape.split(plane, keep=None)
                kept = halves[0] if isinstance(halves, tuple) else halves
            except Exception:
                kept = shape
            clipped_shapes.append((name, kept, color))
    else:
        clipped_shapes = list(shapes)

    origin, up, look_at = _viewport_origin_for(direction, clipped_shapes, azimuth, elevation)

    exporter = ExportDXF()
    for i, (name, shape, _obj_color) in enumerate(clipped_shapes):
        try:
            visible, hidden = shape.project_to_viewport(
                viewport_origin=origin, viewport_up=up, look_at=look_at,
            )
        except Exception:
            continue

        layer_visible = f"{name or f'shape_{i}'}_visible"
        layer_hidden = f"{name or f'shape_{i}'}_hidden"
        exporter.add_layer(layer_visible)
        exporter.add_layer(layer_hidden, line_type=LineType.HIDDEN)
        if visible:
            exporter.add_shape(visible, layer=layer_visible)
        if hidden:
            exporter.add_shape(hidden, layer=layer_hidden)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        dxf_path = os.path.join(tmpdir, "render.dxf")
        exporter.write(dxf_path)
        with open(dxf_path, "rb") as f:
            return f.read()


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
    format: str = "png",
    label_objects: bool = False,
    highlights: list[dict] | None = None,
) -> dict:
    """Render the active session geometry.

    Returns a dict with optional keys:
      - "png": bytes of the rasterised PNG (when format in ("png","both")
        or as automatic fallback failed)
      - "svg": bytes of the SVG document (when format in ("svg","both") or
        as automatic fallback when raster rendering failed)
      - "fallback": str, present when SVG was returned in place of a
        requested PNG because the VTK renderer failed
    """
    direction = direction.lower()
    if direction not in ("top", "front", "side", "iso"):
        raise ValueError(f"Unknown direction '{direction}'. Use: top, front, side, iso")

    quality = quality.lower()
    if quality not in _QUALITY:
        raise ValueError(f"Unknown quality '{quality}'. Use: standard, high")

    clip_plane = clip_plane.lower()
    if clip_plane and clip_plane not in ("x", "y", "z"):
        raise ValueError(f"Unknown clip_plane '{clip_plane}'. Use: x, y, z")

    format = format.lower()
    if format not in _VALID_FORMATS:
        raise ValueError(f"Unknown format '{format}'. Use: png, svg, dxf, both")

    shapes = _resolve_shapes(session, objects)
    tess = _QUALITY[quality]

    # Resolve labels up-front so validation errors surface before any rendering work.
    labels: list[tuple[tuple[float, float, float], str]] = []
    if label_objects:
        labels.extend(_resolve_object_labels(shapes))
    labels.extend(_resolve_highlights(session, shapes, highlights))

    result: dict = {}

    if (label_objects or highlights) and format in ("svg", "dxf", "both"):
        result["label_warnings"] = [
            "Labels are only rendered in PNG output; SVG/DXF output is unlabelled."
        ]

    if format in ("png", "both"):
        try:
            png_bytes, png_failed = _do_render_png(
                shapes, tess, direction, clip_plane, clip_at, azimuth, elevation,
                labels=labels,
            )
            result["png"] = png_bytes
            if png_failed:
                result["png_warnings"] = [
                    f"Skipped shapes (tessellation failed): {', '.join(png_failed)}"
                ]
        except Exception as exc:
            if format == "png":
                # Auto-fallback: produce SVG so the AI still gets a visual.
                result["svg"] = _do_render_svg(
                    shapes, direction, clip_plane, clip_at, azimuth, elevation,
                )
                result["format"] = "svg"
                result["fallback"] = (
                    f"VTK raster render failed ({type(exc).__name__}: {exc}). "
                    f"Returning SVG via build123d HLR projection. "
                    f"Common causes: no DISPLAY and no OSMesa/EGL backend on a headless host."
                )
            else:
                # 'both' was requested. Record the PNG failure and continue to SVG.
                result["png_error"] = f"{type(exc).__name__}: {exc}"

    if format in ("svg", "both") and "svg" not in result:
        result["svg"] = _do_render_svg(
            shapes, direction, clip_plane, clip_at, azimuth, elevation,
        )

    if format == "dxf":
        result["dxf"] = _do_render_dxf(
            shapes, direction, clip_plane, clip_at, azimuth, elevation,
        )

    if save_to:
        from build123d_mcp.tools._paths import safe_output_path
        # Strip a known extension so format='both' produces consistent <base>.png and <base>.svg
        base, ext = os.path.splitext(save_to)
        if ext.lower() in (".png", ".svg", ".dxf"):
            save_to = base
        if "png" in result:
            with open(safe_output_path(save_to + ".png"), "wb") as f:
                f.write(result["png"])
        if "svg" in result:
            with open(safe_output_path(save_to + ".svg"), "wb") as f:
                f.write(result["svg"])
        if "dxf" in result:
            with open(safe_output_path(save_to + ".dxf"), "wb") as f:
                f.write(result["dxf"])

    return result
