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


def test_export_invalid_format(session):
    execute_code(session, "result = Box(10, 10, 10)")
    with pytest.raises(ValueError, match="Unknown format"):
        export_file(session, "out", "obj")


# --- reset ---

def test_reset_clears_shape(session):
    execute_code(session, "result = Box(10, 10, 10)")
    assert session.current_shape is not None
    session.reset()
    assert session.current_shape is None


def test_reset_clears_namespace(session):
    execute_code(session, "x = 99")
    session.reset()
    assert len(session.namespace) == 0
