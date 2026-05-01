import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from session import Session
from tools.execute import execute_code
from tools.export import export_file
from tools.measure import measure
from tools.render import render_view


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
    execute_code(session, "show('a', Box(10,10,10))\nshow('b', Box(10,10,10).move(Location((20,0,0))))")
    data = json.loads(measure(session, "clearance", "a", "b"))
    assert abs(data["clearance"] - 10) < 0.1


def test_measure_clearance_missing_object2_raises(session):
    execute_code(session, "show('a', Box(10,10,10))")
    with pytest.raises(ValueError, match="object_name2"):
        measure(session, "clearance", "a")


def test_measure_clearance_unknown_object2_raises(session):
    execute_code(session, "show('a', Box(10,10,10))")
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
    session.namespace["show"]("mybox", session.current_shape)
    assert "mybox" in session.objects


def test_show_callable_from_execute(session):
    execute_code(session, "box = Box(10, 10, 10)\nshow('mybox', box)")
    assert "mybox" in session.objects


def test_reset_clears_objects(session):
    execute_code(session, "show('b', Box(5, 5, 5))")
    assert session.objects
    session.reset()
    assert not session.objects


def test_show_available_after_reset(session):
    session.reset()
    assert "show" in session.namespace


def test_render_view_multiple_objects(session):
    execute_code(session, "show('a', Box(10, 10, 10))\nshow('b', Cylinder(5, 20))")
    png = render_view(session, "iso")
    assert png[:8] == PNG_MAGIC


def test_render_view_named_subset(session):
    execute_code(session, "show('a', Box(10, 10, 10))\nshow('b', Cylinder(5, 20))")
    png = render_view(session, "iso", "a")
    assert png[:8] == PNG_MAGIC


def test_render_view_unknown_object_raises(session):
    execute_code(session, "show('a', Box(10, 10, 10))")
    with pytest.raises(ValueError, match="Unknown object"):
        render_view(session, "iso", "missing")


def test_measure_named_object(session):
    execute_code(session, "show('wide', Box(30, 10, 10))")
    data = json.loads(measure(session, "bounding_box", "wide"))
    assert abs(data["xsize"] - 30) < 0.01


def test_measure_unknown_object_raises(session):
    execute_code(session, "show('a', Box(5, 5, 5))")
    with pytest.raises(ValueError, match="Unknown object"):
        measure(session, "bounding_box", "missing")


def test_export_named_object(session, tmp_path):
    execute_code(session, "show('part', Box(10, 10, 10))")
    path = str(tmp_path / "out")
    result = export_file(session, path, "step", "part")
    assert os.path.exists(path + ".step")
    assert "Exported" in result


def test_export_unknown_object_raises(session, tmp_path):
    execute_code(session, "show('a', Box(5, 5, 5))")
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
    execute_code(session, "show('part', Box(10, 10, 10))")
    session.save_snapshot("s1")
    execute_code(session, "show('extra', Box(5, 5, 5))")
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
