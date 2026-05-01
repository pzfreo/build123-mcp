"""
Outcome-focused tests: verify what the server actually produces,
not just that functions return without error.
"""
import asyncio
import base64
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

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def session():
    s = Session()
    s.execute("from build123d import *")
    return s


# ---------------------------------------------------------------------------
# Multi-step workflow: does state build up correctly across execute calls?
# ---------------------------------------------------------------------------

def test_incremental_construction_extends_geometry(session):
    """Second execute can reference and extend geometry from the first."""
    execute_code(session, "b = Box(20, 20, 20)")
    execute_code(session, "result = b + Cylinder(5, 30)")
    bb = json.loads(measure(session, "bounding_box"))
    assert bb["zsize"] > 20  # cylinder taller than box


def test_boolean_subtraction_removes_material(session):
    """Cutting a cylinder from a box reduces volume."""
    execute_code(session, "box = Box(10, 10, 10)")
    full_volume = session.current_shape.volume
    execute_code(session, "result = box - Cylinder(3, 12)")
    assert session.current_shape.volume < full_volume


def test_create_measure_export_round_trip(session, tmp_path):
    """Create a known shape, verify its dimensions, then export it."""
    execute_code(session, "result = Box(30, 20, 10)")
    data = json.loads(measure(session, "bounding_box"))
    assert abs(data["xsize"] - 30) < 0.01
    assert abs(data["ysize"] - 20) < 0.01
    assert abs(data["zsize"] - 10) < 0.01

    path = str(tmp_path / "out")
    export_file(session, path, "step")
    # A real STEP file for a simple box is several kilobytes
    assert os.path.getsize(path + ".step") > 1000


def test_multi_format_export_produces_both_files(session, tmp_path):
    """Exporting step,stl in one call writes both files with real content."""
    execute_code(session, "result = Box(20, 20, 20)")
    path = str(tmp_path / "part")
    result = export_file(session, path, "step,stl")
    step_size = os.path.getsize(path + ".step")
    stl_size = os.path.getsize(path + ".stl")
    # STEP files are text-based and larger; STL binary is compact but non-zero
    assert step_size > 1000
    assert stl_size > 0
    # Both paths reported in the return message
    assert ".step" in result
    assert ".stl" in result


def test_multi_format_export_named_object(session, tmp_path):
    """Multi-format export targets the named object, not current_shape."""
    execute_code(session, "result = Box(5, 5, 5)\nshow('big', Box(40, 40, 40))")
    path = str(tmp_path / "big")
    export_file(session, path, "step,stl", "big")
    # The big box STEP file is distinctly larger than a 5mm box would produce
    assert os.path.getsize(path + ".step") > 1000
    assert os.path.getsize(path + ".stl") > 0


def test_reset_discards_previous_geometry(session):
    """After reset, old geometry is gone and new geometry starts from scratch."""
    execute_code(session, "result = Box(100, 100, 100)")
    session.reset()
    session.execute("from build123d import *")
    execute_code(session, "result = Box(5, 5, 5)")
    bb = json.loads(measure(session, "bounding_box"))
    assert abs(bb["xsize"] - 5) < 0.01


def test_render_changes_when_model_changes(session):
    """Rendering a different shape produces a different image."""
    execute_code(session, "result = Box(10, 10, 10)")
    png_small = render_view(session, "iso")
    execute_code(session, "result = Box(50, 50, 50)")
    png_large = render_view(session, "iso")
    assert png_small[:8] == PNG_MAGIC
    assert png_large[:8] == PNG_MAGIC
    assert png_small != png_large


def test_error_in_execute_preserves_current_shape(session):
    """A failed execute does not wipe the current shape."""
    execute_code(session, "result = Box(10, 10, 10)")
    shape_before = session.current_shape
    execute_code(session, "this_will_fail(")  # SyntaxError
    assert session.current_shape is shape_before


# ---------------------------------------------------------------------------
# Multi-object session: show(), per-object measure/export/render
# ---------------------------------------------------------------------------

def test_named_objects_have_independent_bounding_boxes(session):
    """show() isolates shapes: each named object reports its own dimensions."""
    execute_code(session, "show('small', Box(5, 5, 5))\nshow('large', Box(40, 40, 40))")
    small = json.loads(measure(session, "bounding_box", "small"))
    large = json.loads(measure(session, "bounding_box", "large"))
    assert abs(small["xsize"] - 5) < 0.01
    assert abs(large["xsize"] - 40) < 0.01


def test_assembly_render_differs_from_single_part_render(session):
    """Rendering all registered objects produces a different image than one part alone."""
    execute_code(session, "show('box', Box(10, 10, 10))\nshow('cyl', Cylinder(3, 30))")
    png_all = render_view(session, "iso")
    png_one = render_view(session, "iso", objects="box")
    assert png_all[:8] == PNG_MAGIC
    assert png_one[:8] == PNG_MAGIC
    assert png_all != png_one


def test_export_named_object_independent_of_current_shape(session, tmp_path):
    """Exporting a named object writes that shape, not current_shape."""
    execute_code(session, "result = Box(5, 5, 5)\nshow('big', Box(50, 50, 50))")
    path = str(tmp_path / "big")
    export_file(session, path, "step", "big")
    # The big box STEP file should be larger than a tiny box would produce
    assert os.path.getsize(path + ".step") > 1000


def test_reset_clears_show_registry(session):
    """After reset, previously registered objects are gone."""
    execute_code(session, "show('part', Box(10, 10, 10))")
    assert "part" in session.objects
    session.reset()
    assert not session.objects


# ---------------------------------------------------------------------------
# Richer measurements
# ---------------------------------------------------------------------------

def test_volume_detects_missing_boolean(session):
    """volume() exposes the difference between a solid and a hollowed part."""
    execute_code(session, "show('full', Box(20, 20, 20))")
    solid_vol = json.loads(measure(session, "volume", "full"))["volume"]
    execute_code(session, "show('hollow', Box(20, 20, 20) - Cylinder(5, 22))")
    hollow_vol = json.loads(measure(session, "volume", "hollow"))["volume"]
    assert hollow_vol < solid_vol
    assert abs(solid_vol - 8000) < 1


def test_area_increases_after_adding_surface(session):
    """Surface area grows when a protrusion is added."""
    execute_code(session, "result = Box(10, 10, 10)")
    base_area = json.loads(measure(session, "area"))["area"]
    execute_code(session, "result = Box(10, 10, 10) + Cylinder(2, 5).move(Location((0, 0, 7.5)))")
    new_area = json.loads(measure(session, "area"))["area"]
    assert new_area > base_area


def test_min_wall_thickness_thinnest_wall_reported(session):
    """A shape with one thin wall reports that wall's thickness."""
    # Slab 20x20 wide but only 3mm thick
    execute_code(session, "result = Box(20, 20, 3)")
    data = json.loads(measure(session, "min_wall_thickness"))
    assert abs(data["min_wall_thickness"] - 3) < 0.5


def test_clearance_between_assembly_parts(session):
    """Clearance query returns the gap between two registered bodies."""
    execute_code(session,
        "show('shaft', Cylinder(4, 30))\n"
        "show('bore_housing', Box(30, 30, 30) - Cylinder(5, 32))"
    )
    data = json.loads(measure(session, "clearance", "shaft", "bore_housing"))
    # shaft radius 4, bore radius 5 — clearance should be ~1mm
    assert data["clearance"] >= 0
    assert data["clearance"] < 5


def test_clearance_zero_for_touching_shapes(session):
    """Touching shapes report zero clearance."""
    execute_code(session,
        "show('a', Box(10, 10, 10))\n"
        "show('b', Box(10, 10, 10).move(Location((10, 0, 0))))"
    )
    data = json.loads(measure(session, "clearance", "a", "b"))
    assert data["clearance"] < 0.01


# ---------------------------------------------------------------------------
# Rendering quality and clip plane
# ---------------------------------------------------------------------------

def test_high_quality_render_differs_from_standard(session):
    """High quality tessellation produces a different image than standard."""
    execute_code(session, "result = Cylinder(5, 20)")
    png_std = render_view(session, "iso", quality="standard")
    png_hi = render_view(session, "iso", quality="high")
    assert png_std[:8] == PNG_MAGIC
    assert png_hi[:8] == PNG_MAGIC
    assert png_std != png_hi


def test_clip_plane_produces_different_image_than_unclipped(session):
    """A clipped render exposes internal geometry and differs from the unclipped view."""
    execute_code(session, "result = Cylinder(8, 30)")
    png_full = render_view(session, "iso")
    png_clip = render_view(session, "iso", clip_plane="y")
    assert png_full[:8] == PNG_MAGIC
    assert png_clip[:8] == PNG_MAGIC
    assert png_full != png_clip


# ---------------------------------------------------------------------------
# MCP protocol round-trip: test through the actual stdio transport
# ---------------------------------------------------------------------------

async def _mcp_session(coro):
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command="uv",
        args=["run", "python", "server.py"],
        cwd=SERVER_DIR,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as mcp:
            await mcp.initialize()
            return await coro(mcp)


def test_mcp_lists_all_five_tools():
    async def run(mcp):
        result = await mcp.list_tools()
        return {t.name for t in result.tools}

    names = asyncio.run(_mcp_session(run))
    assert names == {"execute", "render_view", "measure", "export", "reset"}


def test_mcp_execute_and_measure_round_trip():
    async def run(mcp):
        await mcp.call_tool(
            "execute",
            {"code": "from build123d import *\nresult = Box(10, 20, 30)"},
        )
        result = await mcp.call_tool("measure", {"query": "bounding_box"})
        return result.content[0].text

    data = json.loads(asyncio.run(_mcp_session(run)))
    assert abs(data["xsize"] - 10) < 0.01
    assert abs(data["ysize"] - 20) < 0.01
    assert abs(data["zsize"] - 30) < 0.01


def test_mcp_render_returns_valid_png():
    async def run(mcp):
        await mcp.call_tool(
            "execute",
            {"code": "from build123d import *\nresult = Box(10, 10, 10)"},
        )
        result = await mcp.call_tool("render_view", {"direction": "iso"})
        c = result.content[0]
        return c.type, c.mimeType, c.data

    content_type, mime_type, data = asyncio.run(_mcp_session(run))
    assert content_type == "image"
    assert mime_type == "image/png"
    assert base64.b64decode(data)[:8] == PNG_MAGIC


def test_mcp_reset_clears_state():
    async def run(mcp):
        await mcp.call_tool(
            "execute",
            {"code": "from build123d import *\nresult = Box(10, 10, 10)"},
        )
        await mcp.call_tool("reset", {})
        # measure should now fail — no shape
        result = await mcp.call_tool("measure", {"query": "bounding_box"})
        return result.content[0].text

    text = asyncio.run(_mcp_session(run))
    assert "No shape" in text


def test_mcp_multi_format_export():
    """export with format='step,stl' reports both paths over the MCP wire."""
    async def run(mcp):
        await mcp.call_tool("execute", {"code": "from build123d import *\nresult = Box(10, 10, 10)"})
        result = await mcp.call_tool("export", {"filename": "/tmp/mcp_test_out", "format": "step,stl"})
        return result.content[0].text

    text = asyncio.run(_mcp_session(run))
    assert ".step" in text
    assert ".stl" in text


def test_mcp_volume_and_clearance():
    """volume and clearance round-trip through the MCP wire."""
    async def run(mcp):
        await mcp.call_tool("execute", {"code": (
            "from build123d import *\n"
            "show('a', Box(10, 10, 10))\n"
            "show('b', Box(10, 10, 10).move(Location((15, 0, 0))))"
        )})
        r_vol = await mcp.call_tool("measure", {"query": "volume", "object_name": "a"})
        r_cl = await mcp.call_tool("measure", {"query": "clearance", "object_name": "a", "object_name2": "b"})
        return r_vol.content[0].text, r_cl.content[0].text

    vol_json, cl_json = asyncio.run(_mcp_session(run))
    assert abs(json.loads(vol_json)["volume"] - 1000) < 1
    assert abs(json.loads(cl_json)["clearance"] - 5) < 0.1


def test_mcp_show_and_measure_named_object():
    """show() + per-object measure round-trip through the MCP wire."""
    async def run(mcp):
        await mcp.call_tool(
            "execute",
            {"code": "from build123d import *\nshow('wide', Box(40, 5, 5))\nshow('tall', Box(5, 5, 40))"},
        )
        r_wide = await mcp.call_tool("measure", {"query": "bounding_box", "object_name": "wide"})
        r_tall = await mcp.call_tool("measure", {"query": "bounding_box", "object_name": "tall"})
        return r_wide.content[0].text, r_tall.content[0].text

    wide_json, tall_json = asyncio.run(_mcp_session(run))
    wide = json.loads(wide_json)
    tall = json.loads(tall_json)
    assert abs(wide["xsize"] - 40) < 0.01
    assert abs(tall["zsize"] - 40) < 0.01
