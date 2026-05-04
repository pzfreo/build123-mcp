import json
import os
import sys

import pytest

from build123d_mcp.session import Session
from build123d_mcp.tools.execute import execute_code
from build123d_mcp.tools.export import export_file
from build123d_mcp.tools.interference import interference
from build123d_mcp.tools.measure import measure
from build123d_mcp.tools.diff import diff_snapshot
from build123d_mcp.tools.health_check import health_check
from build123d_mcp.tools.list_objects import list_objects
from build123d_mcp.tools.render import render_view
from build123d_mcp.tools.session_state import session_state

# A path guaranteed to resolve outside any allowed write root (cwd, tempdir, /tmp)
# on each platform. /etc/passwd on POSIX; on Windows we use the system hosts file,
# which is always present and lives under C:\Windows so realpath stays under C:\Windows.
_OUTSIDE_ROOT_PATH = (
    r"C:\Windows\System32\drivers\etc\hosts"
    if sys.platform == "win32"
    else "/etc/passwd"
)


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


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Session.execute uses SIGALRM for timeout, which is POSIX-only; in-process timeout protection is not available on Windows (the WorkerSession parent-side timeout still works in production).",
)
def test_execution_timeout(fast_session):
    result = execute_code(fast_session, "while True: pass")
    assert "timeout" in result.lower() or "time limit" in result.lower()


def test_worker_execution_timeout():
    """The production timeout path (WorkerSession's parent-side multiprocessing
    poll) works on every platform, including Windows where the in-process
    SIGALRM guard is a no-op. A `while True: pass` must return a timeout error,
    not hang the test."""
    from build123d_mcp.worker import WorkerSession
    ws = WorkerSession(exec_timeout=2)
    try:
        result = ws.execute("while True: pass")
        assert "timeout" in result.lower() or "time limit" in result.lower()
    finally:
        ws._kill_worker()


def test_blocked_import_does_not_corrupt_shape(session):
    execute_code(session, "result = Box(10, 10, 10)")
    shape_before = session.current_shape
    execute_code(session, "import os")
    assert session.current_shape is shape_before


def test_runtime_error_does_not_update_current_shape(session):
    execute_code(session, "result = Box(10, 10, 10)")
    shape_before = session.current_shape
    execute_code(session, "bad = Box(5, 5, 5); raise ValueError('oops')")
    assert session.current_shape is shape_before


def test_show_sets_current_shape(session):
    execute_code(session, "show(Box(10, 10, 10), 'part')")
    assert session.current_shape is not None
    assert session.objects.get("part") is session.current_shape


# --- render_view ---

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_render_view_iso_returns_png(session):
    execute_code(session, "result = Box(10, 10, 10)")
    out = render_view(session, "iso")
    assert "png" in out and out["png"][:8] == PNG_MAGIC


def test_render_view_all_directions(session):
    execute_code(session, "result = Box(10, 10, 10)")
    for direction in ("top", "front", "side", "iso"):
        out = render_view(session, direction)
        assert out["png"][:8] == PNG_MAGIC, f"direction '{direction}' did not return valid PNG"


def test_render_view_invalid_direction(session):
    execute_code(session, "result = Box(10, 10, 10)")
    with pytest.raises(ValueError, match="Unknown direction"):
        render_view(session, "diagonal")


def test_render_view_no_shape_raises(session):
    with pytest.raises(ValueError, match="No shape"):
        render_view(session, "iso")


def test_render_view_high_quality_returns_png(session):
    execute_code(session, "result = Cylinder(5, 20)")
    out = render_view(session, "iso", quality="high")
    assert out["png"][:8] == PNG_MAGIC


def test_render_view_invalid_quality_raises(session):
    execute_code(session, "result = Box(10, 10, 10)")
    with pytest.raises(ValueError, match="Unknown quality"):
        render_view(session, "iso", quality="ultra")


def test_render_view_clip_plane_returns_png(session):
    execute_code(session, "result = Cylinder(5, 20)")
    for plane in ("x", "y", "z"):
        out = render_view(session, "iso", clip_plane=plane)
        assert out["png"][:8] == PNG_MAGIC, f"clip_plane '{plane}' did not return valid PNG"


def test_render_view_invalid_clip_plane_raises(session):
    execute_code(session, "result = Box(10, 10, 10)")
    with pytest.raises(ValueError, match="Unknown clip_plane"):
        render_view(session, "iso", clip_plane="w")


def test_render_view_svg_format(session):
    execute_code(session, "result = Box(10, 10, 10)")
    out = render_view(session, "iso", format="svg")
    assert "svg" in out and "png" not in out
    assert b"<svg" in out["svg"]


def test_render_view_both_format(session):
    execute_code(session, "result = Box(10, 10, 10)")
    out = render_view(session, "iso", format="both")
    assert out["png"][:8] == PNG_MAGIC
    assert b"<svg" in out["svg"]


def test_render_view_invalid_format_raises(session):
    execute_code(session, "result = Box(10, 10, 10)")
    with pytest.raises(ValueError, match="Unknown format"):
        render_view(session, "iso", format="jpeg")


def test_render_view_fallback_to_svg_when_vtk_fails(session, monkeypatch):
    execute_code(session, "result = Box(10, 10, 10)")
    from build123d_mcp.tools import render as render_mod

    def boom(*_a, **_kw):
        raise RuntimeError("simulated GL failure")

    monkeypatch.setattr(render_mod, "_do_render_png", boom)
    out = render_view(session, "iso", format="png")
    assert "png" not in out
    assert b"<svg" in out["svg"]
    assert "fallback" in out and "simulated GL failure" in out["fallback"]


def test_render_view_save_to_both_writes_two_files(session, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    execute_code(session, "result = Box(10, 10, 10)")
    render_view(session, "iso", save_to="multi", format="both")
    assert (tmp_path / "multi.png").exists()
    assert (tmp_path / "multi.svg").exists()


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

def test_export_step(session, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    execute_code(session, "result = Box(10, 10, 10)")
    result = export_file(session, "out", "step")
    assert os.path.exists("out.step")
    assert os.path.getsize("out.step") > 0
    assert "Exported" in result


def test_export_stl(session, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    execute_code(session, "result = Box(10, 10, 10)")
    result = export_file(session, "out", "stl")
    assert os.path.exists("out.stl")
    assert os.path.getsize("out.stl") > 0


def test_export_multi_format(session, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    execute_code(session, "result = Box(10, 10, 10)")
    result = export_file(session, "out", "step,stl")
    assert os.path.exists("out.step")
    assert os.path.exists("out.stl")
    assert os.path.getsize("out.step") > 0
    assert os.path.getsize("out.stl") > 0
    assert ".step" in result
    assert ".stl" in result


def test_export_invalid_format(session):
    execute_code(session, "result = Box(10, 10, 10)")
    with pytest.raises(ValueError, match="Unknown format"):
        export_file(session, "out", "obj")


def test_export_path_traversal_rejected(session):
    execute_code(session, "result = Box(10, 10, 10)")
    with pytest.raises(ValueError, match="outside the allowed write roots"):
        export_file(session, "../../etc/passwd", "step")


def test_export_outside_roots_rejected(session):
    execute_code(session, "result = Box(10, 10, 10)")
    with pytest.raises(ValueError, match="outside the allowed write roots"):
        export_file(session, _OUTSIDE_ROOT_PATH, "step")


def test_export_to_tmp_allowed(session, tmp_path):
    execute_code(session, "result = Box(10, 10, 10)")
    target = tmp_path / "exported.step"
    result = export_file(session, str(target), "step")
    assert os.path.exists(target)
    assert str(target) in result


@pytest.mark.skipif(sys.platform == "win32", reason="/tmp does not exist on Windows; tempfile.gettempdir() coverage in test_export_to_tmp_allowed already runs there")
def test_export_to_slash_tmp_allowed(session):
    execute_code(session, "result = Box(10, 10, 10)")
    import tempfile as _tempfile
    with _tempfile.NamedTemporaryFile(
        prefix="build123d_mcp_test_", suffix=".step", dir="/tmp", delete=False
    ) as f:
        target = f.name
    try:
        export_file(session, target, "step")
        assert os.path.exists(target)
    finally:
        if os.path.exists(target):
            os.unlink(target)


def test_export_symlink_escape_rejected(session, tmp_path):
    execute_code(session, "result = Box(10, 10, 10)")
    link = tmp_path / "escape.step"
    os.symlink("/etc/passwd", link)
    try:
        with pytest.raises(ValueError, match="outside the allowed write roots"):
            export_file(session, str(link), "step")
    finally:
        if link.is_symlink():
            link.unlink()


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
    out = render_view(session, "iso")
    assert out["png"][:8] == PNG_MAGIC


def test_render_view_named_subset(session):
    execute_code(session, "show(Box(10, 10, 10), 'a')\nshow(Cylinder(5, 20), 'b')")
    out = render_view(session, "iso", "a")
    assert out["png"][:8] == PNG_MAGIC


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


def test_export_named_object(session, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    execute_code(session, "show(Box(10, 10, 10), 'part')")
    result = export_file(session, "out", "step", "part")
    assert os.path.exists("out.step")
    assert "Exported" in result


def test_export_unknown_object_raises(session):
    execute_code(session, "show(Box(5, 5, 5), 'a')")
    with pytest.raises(ValueError, match="Unknown object"):
        export_file(session, "out", "step", "missing")


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


def test_dispatch_save_snapshot_no_shape_omits_current_shape():
    from build123d_mcp.session import Session
    from build123d_mcp.worker import _dispatch
    s = Session()
    msg = _dispatch(s, "save_snapshot", {"name": "empty"}, None)
    assert "current_shape" not in msg
    assert "none" in msg.lower()


def test_dispatch_restore_snapshot_no_shape_omits_current_shape():
    from build123d_mcp.session import Session
    from build123d_mcp.worker import _dispatch
    s = Session()
    _dispatch(s, "save_snapshot", {"name": "empty"}, None)
    msg = _dispatch(s, "restore_snapshot", {"name": "empty"}, None)
    assert "current_shape" not in msg
    assert "none" in msg.lower()


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
    out = render_view(session, "iso", "a:blue,b:red")
    assert out["png"][:8] == PNG_MAGIC


def test_render_view_mixed_color_and_palette(session):
    execute_code(session, "show(Box(10, 10, 10), 'a')\nshow(Cylinder(5, 20), 'b')")
    out = render_view(session, "iso", "a:green,b")
    assert out["png"][:8] == PNG_MAGIC


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
    out = render_view(session, "iso", azimuth=45.0)
    assert out["png"][:8] == PNG_MAGIC


def test_render_view_elevation_returns_png(session):
    execute_code(session, "result = Box(10, 10, 10)")
    out = render_view(session, "iso", elevation=30.0)
    assert out["png"][:8] == PNG_MAGIC


def test_render_view_azimuth_and_elevation_returns_png(session):
    execute_code(session, "result = Cylinder(5, 20)")
    out = render_view(session, "front", azimuth=20.0, elevation=15.0)
    assert out["png"][:8] == PNG_MAGIC


# --- render_view clip_at (new) ---

def test_render_view_clip_at_returns_png(session):
    execute_code(session, "result = Cylinder(5, 20)")
    out = render_view(session, "iso", clip_plane="z", clip_at=5.0)
    assert out["png"][:8] == PNG_MAGIC


def test_render_view_clip_at_negative_returns_png(session):
    execute_code(session, "result = Box(20, 20, 20)")
    out = render_view(session, "iso", clip_plane="x", clip_at=-3.0)
    assert out["png"][:8] == PNG_MAGIC


# --- render_view save_to (new) ---

def test_render_view_save_to_writes_png(session, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    execute_code(session, "result = Box(10, 10, 10)")
    out = render_view(session, "iso", save_to="out")
    assert out["png"][:8] == PNG_MAGIC
    assert os.path.exists("out.png")
    assert os.path.getsize("out.png") > 0


def test_render_view_save_to_with_extension(session, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    execute_code(session, "result = Box(10, 10, 10)")
    render_view(session, "iso", save_to="out.png")
    assert os.path.exists("out.png")


def test_render_view_save_to_path_traversal_rejected(session):
    execute_code(session, "result = Box(10, 10, 10)")
    with pytest.raises(ValueError, match="outside the allowed write roots"):
        render_view(session, "iso", save_to="../../etc/passwd")


def test_render_view_save_to_outside_roots_rejected(session):
    execute_code(session, "result = Box(10, 10, 10)")
    with pytest.raises(ValueError, match="outside the allowed write roots"):
        render_view(session, "iso", save_to=_OUTSIDE_ROOT_PATH)


def test_render_view_save_to_tmp_allowed(session, tmp_path):
    execute_code(session, "result = Box(10, 10, 10)")
    target = tmp_path / "render.png"
    render_view(session, "iso", save_to=str(target))
    assert os.path.exists(target)


# --- show() feedback (new) ---

def test_show_prints_volume_and_faces(session):
    output = execute_code(session, "show(Box(10, 10, 10), 'cube')")
    assert "cube" in output
    assert "volume" in output.lower() or "mm" in output


def test_show_prints_feedback_without_name(session):
    output = execute_code(session, "show(Box(5, 5, 5))")
    assert "Registered" in output


# --- list_objects (new) ---

def test_list_objects_empty(session):
    result = list_objects(session)
    assert "No named objects" in result


def test_list_objects_returns_all_shapes(session):
    execute_code(session, "show(Box(10, 10, 10), 'a')\nshow(Cylinder(5, 20), 'b')")
    data = json.loads(list_objects(session))
    names = [item["name"] for item in data]
    assert "a" in names
    assert "b" in names


def test_list_objects_includes_geometry(session):
    execute_code(session, "show(Box(10, 10, 10), 'cube')")
    data = json.loads(list_objects(session))
    cube = next(item for item in data if item["name"] == "cube")
    assert abs(cube["volume"] - 1000) < 0.1
    assert cube["faces"] == 6
    assert cube["edges"] == 12
    assert cube["vertices"] == 8


# --- auto-diagnostics after execute ---

def test_execute_auto_diagnostics_on_new_shape(session):
    result = execute_code(session, "result = Box(10, 10, 10)")
    assert "current_shape" in result
    assert "volume" in result
    assert "mm³" in result


def test_execute_auto_diagnostics_includes_topology(session):
    result = execute_code(session, "result = Box(10, 10, 10)")
    assert "6f" in result


def test_execute_auto_diagnostics_not_shown_without_shape(session):
    result = execute_code(session, "x = 42")
    assert "current_shape" not in result


def test_execute_auto_diagnostics_not_shown_on_error(session):
    result = execute_code(session, "result = Box(10, 10, 10)\nraise ValueError('oops')")
    assert "Error" in result
    assert "current_shape" not in result


def test_execute_auto_diagnostics_not_repeated_when_shape_unchanged(session):
    execute_code(session, "result = Box(10, 10, 10)")
    result = execute_code(session, "x = 99")
    assert "current_shape" not in result


# --- assertion / constraint support ---

def test_assert_passing_does_not_error(session):
    result = execute_code(session, "result = Box(10, 10, 10)\nassert result.volume > 500")
    assert "Error" not in result
    assert "Constraint" not in result


def test_assert_failing_returns_constraint_failed(session):
    result = execute_code(session, "result = Box(10, 10, 10)\nassert result.volume > 9999, 'volume too small'")
    assert result.startswith("Constraint failed")
    assert "volume too small" in result


def test_assert_failing_with_no_message(session):
    result = execute_code(session, "assert False")
    assert "Constraint failed" in result


def test_assert_failure_does_not_update_current_shape(session):
    execute_code(session, "result = Box(10, 10, 10)")
    shape_before = session.current_shape
    execute_code(session, "result = Box(5, 5, 5)\nassert False")
    assert session.current_shape is shape_before


# --- diff_snapshot ---

def test_diff_snapshot_vs_current(session):
    execute_code(session, "result = Box(10, 10, 10)")
    session.save_snapshot("v1")
    execute_code(session, "result = Box(10, 10, 5)")
    result = diff_snapshot(session, "v1")
    assert "v1" in result
    assert "current" in result
    assert "volume" in result


def test_diff_snapshot_shows_volume_delta(session):
    execute_code(session, "result = Box(10, 10, 10)")
    session.save_snapshot("before")
    execute_code(session, "result = Box(10, 10, 5)")
    result = diff_snapshot(session, "before")
    assert "Δ" in result
    assert "-500" in result or "500" in result


def test_diff_snapshot_two_named_snapshots(session):
    execute_code(session, "result = Box(10, 10, 10)")
    session.save_snapshot("v1")
    execute_code(session, "result = Box(10, 10, 20)")
    session.save_snapshot("v2")
    result = diff_snapshot(session, "v1", "v2")
    assert "v1" in result
    assert "v2" in result


def test_diff_snapshot_shows_added_object(session):
    execute_code(session, "result = Box(10, 10, 10)")
    session.save_snapshot("before")
    execute_code(session, "show(Cylinder(5, 20), 'pin')")
    result = diff_snapshot(session, "before")
    assert "+ pin" in result or "pin (added)" in result


def test_diff_snapshot_shows_removed_object(session):
    execute_code(session, "show(Box(10, 10, 10), 'bracket')")
    session.save_snapshot("with_bracket")
    session.objects.clear()
    result = diff_snapshot(session, "with_bracket")
    assert "bracket" in result
    assert "removed" in result


def test_diff_snapshot_unknown_snapshot_a(session):
    result = diff_snapshot(session, "no_such")
    assert "Error" in result


def test_diff_snapshot_unchanged_object_marked(session):
    execute_code(session, "show(Box(10, 10, 10), 'base')")
    session.save_snapshot("s1")
    session.save_snapshot("s2")
    result = diff_snapshot(session, "s1", "s2")
    assert "unchanged" in result or "= base" in result


# --- session_state ---

def test_session_state_empty(session):
    data = json.loads(session_state(session))
    assert data["current_shape"] is None
    assert data["objects"] == {}
    assert data["snapshots"] == []


def test_session_state_with_shape_and_objects(session):
    execute_code(session, "result = Box(10, 10, 10)")
    execute_code(session, "show(Cylinder(5, 20), 'pin')")
    session.save_snapshot("v1")
    data = json.loads(session_state(session))
    assert data["current_shape"]["volume"] > 0
    assert "pin" in data["objects"]
    assert "v1" in data["snapshots"]


# --- diff_snapshot JSON mode ---

def test_diff_snapshot_json_format(session):
    execute_code(session, "result = Box(10, 10, 10)")
    session.save_snapshot("s1")
    execute_code(session, "result = Box(20, 20, 20)")
    data = json.loads(diff_snapshot(session, "s1", format="json"))
    assert data["a"]["label"] == "s1"
    assert data["b"]["label"] == "current"
    assert data["b"]["current_shape"]["volume"] > data["a"]["current_shape"]["volume"]


# --- health_check ---

def test_health_check_returns_json(session):
    data = json.loads(health_check(session))
    assert "ok" in data
    assert "export_step" in data
    assert "export_stl" in data
    assert "render_svg" in data
    assert data["export_step"]["ok"] is True
    assert data["export_stl"]["ok"] is True
    assert data["render_svg"]["ok"] is True
