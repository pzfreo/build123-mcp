import json
import os

import pytest

from build123d_mcp.session import Session
from build123d_mcp.tools.execute import execute_code
from build123d_mcp.tools.export import export_file
from build123d_mcp.tools.interference import interference
from build123d_mcp.tools.measure import measure
from build123d_mcp.tools.render import render_view


@pytest.fixture
def session():
    s = Session()
    s.execute("from build123d import *")
    return s


@pytest.fixture
def fast_session():
    """Session with a 1-second exec timeout for testing timeout behaviour."""
    s = Session(exec_timeout=1)
    s.execute("from build123d import *")
    return s


# --- execute ---

def test_execute_persists_state(session):
    execute_code(session, "x = 42")
    result = execute_code(session, "print(x)")
    assert "42" in result


def test_execute_captures_stdout(session):
    result = execute_code(session, "print('hello')")
    assert "hello" in result


def test_execute_error_returns_message(session):
    result = execute_code(session, "raise ValueError('bad input')")
    assert "ValueError" in result
    assert "bad input" in result


def test_execute_creates_shape(session):
    execute_code(session, "result = Box(10, 10, 10)")
    assert session.current_shape is not None


def test_execute_detects_buildpart(session):
    execute_code(session, "with BuildPart() as p:\n    Box(10, 10, 10)")
    assert session.current_shape is not None


# --- security ---

def test_import_os_blocked(session):
    result = execute_code(session, "import os")
    assert "SecurityError" in result or "not allowed" in result.lower()


def test_import_subprocess_blocked(session):
    result = execute_code(session, "import subprocess")
    assert "not allowed" in result.lower()


def test_from_os_import_blocked(session):
    result = execute_code(session, "from os import getcwd")
    assert "not allowed" in result.lower()


def test_import_socket_blocked(session):
    result = execute_code(session, "import socket")
    assert "not allowed" in result.lower()


def test_import_pathlib_blocked(session):
    result = execute_code(session, "import pathlib")
    assert "not allowed" in result.lower()


def test_eval_call_blocked(session):
    result = execute_code(session, "eval('1+1')")
    assert "not allowed" in result.lower()


def test_exec_call_blocked(session):
    result = execute_code(session, "exec('x=1')")
    assert "not allowed" in result.lower()


def test_open_call_blocked(session):
    result = execute_code(session, "open('/etc/passwd')")
    assert "not allowed" in result.lower()


def test_open_removed_from_builtins(session):
    # open is blocked by builtins restriction even if AST check were bypassed
    assert "open" not in session.namespace.get("__builtins__", {})


def test_import_math_allowed(session):
    result = execute_code(session, "import math\nx = math.pi")
    assert "Error" not in result


def test_import_build123d_allowed(session):
    result = execute_code(session, "from build123d import *\nresult = Box(1, 1, 1)")
    assert "Error" not in result


def test_execution_timeout(fast_session):
    result = execute_code(fast_session, "while True: pass")
    assert "timeout" in result.lower() or "time limit" in result.lower()


def test_blocked_import_does_not_corrupt_shape(session):
    execute_code(session, "result = Box(10, 10, 10)")
    shape_before = session.current_shape
    execute_code(session, "import os")
    assert session.current_shape is shape_before


# --- render_view ---

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_render_view_iso_returns_png(session):
    execute_code(session, "result = Box(10, 10, 10)")
    png = render_view(session, "iso")
    assert png[:8] == PNG_MAGIC


def test_render_view_all_directions(session):
    execute_code(session, "result = Box(10, 10, 10)")
    for direction in ("top", "front", "side", "iso"):
        png = render_view(session, direction)
        assert png[:8] == PNG_MAGIC, f"direction '{direction}' did not return valid PNG"


def test_render_view_invalid_direction(session):
    execute_code(session, "result = Box(10, 10, 10)")
    with pytest.raises(ValueError, match="Unknown direction"):
        render_view(session, "diagonal")


def test_render_view_no_shape_raises(session):
    with pytest.raises(ValueError, match="No shape"):
        render_view(session, "iso")


def test_render_view_high_quality_returns_png(session):
    execute_code(session, "result = Cylinder(5, 20)")
    png = render_view(session, "iso", quality="high")
    assert png[:8] == PNG_MAGIC


def test_render_view_invalid_quality_raises(session):
    execute_code(session, "result = Box(10, 10, 10)")
    with pytest.raises(ValueError, match="Unknown quality"):
        render_view(session, "iso", quality="ultra")


def test_render_view_clip_plane_returns_png(session):
    execute_code(session, "result = Cylinder(5, 20)")
    for plane in ("x", "y", "z"):
        png = render_view(session, "iso", clip_plane=plane)
        assert png[:8] == PNG_MAGIC, f"clip_plane '{plane}' did not return valid PNG"


def test_render_view_invalid_clip_plane_raises(session):
    execute_code(session, "result = Box(10, 10, 10)")
    with pytest.raises(ValueError, match="Unknown clip_plane"):
        render_view(session, "iso", clip_plane="w")


# --- measure ---

def test_measure_bounding_box(session):
    execute_code(session, "result = Box(10, 20, 30)")
    data = json.loads(measure(session, "bounding_box"))
    assert abs(data["xsize"] - 10) < 0.01
    assert abs(data["ysize"] - 20) < 0.01
    assert abs(data["zsize"] - 30) < 0.01


def test_measure_center_origin(session):
    execute_code(session, "result = Box(10, 10, 10)")
    data = json.loads(measure(session, "bounding_box"))
    center = data["center"]
    assert abs(center["x"]) < 0.01
    assert abs(center["y"]) < 0.01
    assert abs(center["z"]) < 0.01


def test_measure_invalid_query(session):
    execute_code(session, "result = Box(10, 10, 10)")
    with pytest.raises(ValueError, match="Unknown query"):
        measure(session, "surface_area")


def test_measure_volume(session):
    execute_code(session, "result = Box(10, 10, 10)")
    data = json.loads(measure(session, "volume"))
    assert abs(data["volume"] - 1000) < 0.1


def test_measure_area(session):
    execute_code(session, "result = Box(10, 10, 10)")
    data = json.loads(measure(session, "area"))
    assert abs(data["area"] - 600) < 0.1


def test_measure_min_wall_thickness(session):
    execute_code(session, "result = Box(20, 20, 4)")
    data = json.loads(measure(session, "min_wall_thickness"))
    assert abs(data["min_wall_thickness"] - 4) < 0.1


def test_measure_clearance(session):
    execute_code(session, "show(Box(10,10,10), 'a')\nshow(Box(10,10,10).move(Location((20,0,0))), 'b')")
    data = json.loads(measure(session, "clearance", "a", "b"))
    assert abs(data["clearance"] - 10) < 0.1


def test_measure_clearance_missing_object2_raises(session):
    execute_code(session, "show(Box(10,10,10), 'a')")
    with pytest.raises(ValueError, match="object_name2"):
        measure(session, "clearance", "a")


def test_measure_clearance_unknown_object2_raises(session):
    execute_code(session, "show(Box(10,10,10), 'a')")
    with pytest.raises(ValueError, match="Unknown object"):
        measure(session, "clearance", "a", "missing")


# --- export ---

def test_export_step(session, tmp_path):
    execute_code(session, "result = Box(10, 10, 10)")
    path = str(tmp_path / "out")
    result = export_file(session, path, "step")
    assert os.path.exists(path + ".step")
    assert os.path.getsize(path + ".step") > 0
    assert "Exported" in result


def test_export_stl(session, tmp_path):
    execute_code(session, "result = Box(10, 10, 10)")
    path = str(tmp_path / "out")
    result = export_file(session, path, "stl")
    assert os.path.exists(path + ".stl")
    assert os.path.getsize(path + ".stl") > 0


def test_export_multi_format(session, tmp_path):
    execute_code(session, "result = Box(10, 10, 10)")
    path = str(tmp_path / "out")
    result = export_file(session, path, "step,stl")
    assert os.path.exists(path + ".step")
    assert os.path.exists(path + ".stl")
    assert os.path.getsize(path + ".step") > 0
    assert os.path.getsize(path + ".stl") > 0
    assert path + ".step" in result
    assert path + ".stl" in result


def test_export_invalid_format(session):
    execute_code(session, "result = Box(10, 10, 10)")
    with pytest.raises(ValueError, match="Unknown format"):
        export_file(session, "out", "obj")


def test_export_path_traversal_rejected(session):
    execute_code(session, "result = Box(10, 10, 10)")
    with pytest.raises(ValueError, match="Path traversal"):
        export_file(session, "../../etc/passwd", "step")


# --- reset ---

def test_reset_clears_shape(session):
    execute_code(session, "result = Box(10, 10, 10)")
    assert session.current_shape is not None
    session.reset()
    assert session.current_shape is None


def test_reset_clears_namespace(session):
    execute_code(session, "x = 99")
    session.reset()
    assert "x" not in session.namespace
    assert "show" in session.namespace


# --- multi-object / show() ---

def test_show_registers_object(session):
    execute_code(session, "box = Box(10, 10, 10)")
    session.namespace["show"](session.current_shape, "mybox")
    assert "mybox" in session.objects


def test_show_callable_from_execute(session):
    execute_code(session, "box = Box(10, 10, 10)\nshow(box, 'mybox')")
    assert "mybox" in session.objects


def test_reset_clears_objects(session):
    execute_code(session, "show(Box(5, 5, 5), 'b')")
    assert session.objects
    session.reset()
    assert not session.objects


def test_show_available_after_reset(session):
    session.reset()
    assert "show" in session.namespace


def test_render_view_multiple_objects(session):
    execute_code(session, "show(Box(10, 10, 10), 'a')\nshow(Cylinder(5, 20), 'b')")
    png = render_view(session, "iso")
    assert png[:8] == PNG_MAGIC


def test_render_view_named_subset(session):
    execute_code(session, "show(Box(10, 10, 10), 'a')\nshow(Cylinder(5, 20), 'b')")
    png = render_view(session, "iso", "a")
    assert png[:8] == PNG_MAGIC


def test_render_view_unknown_object_raises(session):
    execute_code(session, "show(Box(10, 10, 10), 'a')")
    with pytest.raises(ValueError, match="Unknown object"):
        render_view(session, "iso", "missing")


def test_measure_named_object(session):
    execute_code(session, "show(Box(30, 10, 10), 'wide')")
    data = json.loads(measure(session, "bounding_box", "wide"))
    assert abs(data["xsize"] - 30) < 0.01


def test_measure_unknown_object_raises(session):
    execute_code(session, "show(Box(5, 5, 5), 'a')")
    with pytest.raises(ValueError, match="Unknown object"):
        measure(session, "bounding_box", "missing")


def test_export_named_object(session, tmp_path):
    execute_code(session, "show(Box(10, 10, 10), 'part')")
    path = str(tmp_path / "out")
    result = export_file(session, path, "step", "part")
    assert os.path.exists(path + ".step")
    assert "Exported" in result


def test_export_unknown_object_raises(session, tmp_path):
    execute_code(session, "show(Box(5, 5, 5), 'a')")
    with pytest.raises(ValueError, match="Unknown object"):
        export_file(session, str(tmp_path / "out"), "step", "missing")


# --- snapshots ---

def test_save_and_restore_snapshot(session):
    execute_code(session, "result = Box(10, 10, 10)")
    shape_before = session.current_shape
    session.save_snapshot("v1")
    execute_code(session, "result = Box(99, 99, 99)")
    assert session.current_shape is not shape_before
    session.restore_snapshot("v1")
    assert session.current_shape is shape_before


def test_snapshot_captures_objects_registry(session):
    execute_code(session, "show(Box(10, 10, 10), 'part')")
    session.save_snapshot("s1")
    execute_code(session, "show(Box(5, 5, 5), 'extra')")
    assert "extra" in session.objects
    session.restore_snapshot("s1")
    assert "extra" not in session.objects
    assert "part" in session.objects


def test_restore_unknown_snapshot_raises(session):
    with pytest.raises(KeyError, match="no_such"):
        session.restore_snapshot("no_such")


def test_reset_clears_snapshots(session):
    execute_code(session, "result = Box(10, 10, 10)")
    session.save_snapshot("v1")
    session.reset()
    assert not session.snapshots


def test_namespace_preserved_after_restore(session):
    execute_code(session, "x = 42")
    session.save_snapshot("s1")
    execute_code(session, "x = 99")
    session.restore_snapshot("s1")
    # namespace is NOT restored — x stays at 99
    assert session.namespace.get("x") == 99


# --- show() API: shape first, optional name second (issue #11) ---

def test_show_with_explicit_name(session):
    execute_code(session, "box = Box(10, 10, 10)")
    session.namespace["show"](session.current_shape, "mybox")
    assert "mybox" in session.objects


def test_show_with_explicit_name_from_execute(session):
    execute_code(session, "box = Box(10, 10, 10)\nshow(box, 'mybox')")
    assert "mybox" in session.objects


def test_show_without_name_defaults_to_shape(session):
    execute_code(session, "box = Box(10, 10, 10)\nshow(box)")
    assert "shape" in session.objects


# --- render_view per-object color (issue #12) ---

def test_render_view_per_object_color(session):
    execute_code(session, "show(Box(10, 10, 10), 'a')\nshow(Cylinder(5, 20), 'b')")
    png = render_view(session, "iso", "a:blue,b:red")
    assert png[:8] == PNG_MAGIC


def test_render_view_mixed_color_and_palette(session):
    execute_code(session, "show(Box(10, 10, 10), 'a')\nshow(Cylinder(5, 20), 'b')")
    png = render_view(session, "iso", "a:green,b")
    assert png[:8] == PNG_MAGIC


# --- interference check (issue #13) ---

def test_interference_overlapping(session):
    execute_code(session, "show(Box(10, 10, 10), 'a')\nshow(Box(10, 10, 10).move(Location((5, 0, 0))), 'b')")
    data = json.loads(interference(session, "a", "b"))
    assert data["interferes"] is True
    assert data["volume"] > 0


def test_interference_non_overlapping(session):
    execute_code(session, "show(Box(10, 10, 10), 'a')\nshow(Box(10, 10, 10).move(Location((20, 0, 0))), 'b')")
    data = json.loads(interference(session, "a", "b"))
    assert data["interferes"] is False
    assert data["volume"] == 0.0


def test_interference_returns_bounds(session):
    execute_code(session, "show(Box(10, 10, 10), 'a')\nshow(Box(10, 10, 10).move(Location((5, 0, 0))), 'b')")
    data = json.loads(interference(session, "a", "b"))
    assert "bounds" in data
    bounds = data["bounds"]
    for key in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax"):
        assert key in bounds


def test_interference_unknown_object_raises(session):
    execute_code(session, "show(Box(10, 10, 10), 'a')")
    with pytest.raises(ValueError, match="Unknown object"):
        interference(session, "a", "missing")


# --- measure topology (new) ---

def test_measure_topology_box(session):
    execute_code(session, "result = Box(10, 10, 10)")
    data = json.loads(measure(session, "topology"))
    assert data["faces"] == 6
    assert data["edges"] == 12
    assert data["vertices"] == 8


def test_measure_topology_increases_after_boolean_cut(session):
    # A box with a cylindrical hole punched through has more than 6 faces
    execute_code(session, "result = Box(20, 20, 20) - Cylinder(3, 30)")
    data = json.loads(measure(session, "topology"))
    assert data["faces"] > 6


def test_measure_topology_named_object(session):
    execute_code(session, "show(Box(10, 10, 10), 'cube')")
    data = json.loads(measure(session, "topology", "cube"))
    assert data["faces"] == 6


# --- render_view azimuth/elevation (new) ---

def test_render_view_azimuth_returns_png(session):
    execute_code(session, "result = Box(10, 10, 10)")
    png = render_view(session, "iso", azimuth=45.0)
    assert png[:8] == PNG_MAGIC


def test_render_view_elevation_returns_png(session):
    execute_code(session, "result = Box(10, 10, 10)")
    png = render_view(session, "iso", elevation=30.0)
    assert png[:8] == PNG_MAGIC


def test_render_view_azimuth_and_elevation_returns_png(session):
    execute_code(session, "result = Cylinder(5, 20)")
    png = render_view(session, "front", azimuth=20.0, elevation=15.0)
    assert png[:8] == PNG_MAGIC


# --- render_view clip_at (new) ---

def test_render_view_clip_at_returns_png(session):
    execute_code(session, "result = Cylinder(5, 20)")
    png = render_view(session, "iso", clip_plane="z", clip_at=5.0)
    assert png[:8] == PNG_MAGIC


def test_render_view_clip_at_negative_returns_png(session):
    execute_code(session, "result = Box(20, 20, 20)")
    png = render_view(session, "iso", clip_plane="x", clip_at=-3.0)
    assert png[:8] == PNG_MAGIC


# --- render_view save_to (new) ---

def test_render_view_save_to_writes_png(session, tmp_path):
    execute_code(session, "result = Box(10, 10, 10)")
    dest = str(tmp_path / "out")
    png = render_view(session, "iso", save_to=dest)
    assert png[:8] == PNG_MAGIC
    assert os.path.exists(dest + ".png")
    assert os.path.getsize(dest + ".png") > 0


def test_render_view_save_to_with_extension(session, tmp_path):
    execute_code(session, "result = Box(10, 10, 10)")
    dest = str(tmp_path / "out.png")
    render_view(session, "iso", save_to=dest)
    assert os.path.exists(dest)


def test_render_view_save_to_path_traversal_rejected(session):
    execute_code(session, "result = Box(10, 10, 10)")
    with pytest.raises(ValueError, match="Path traversal"):
        render_view(session, "iso", save_to="../../tmp/evil")
