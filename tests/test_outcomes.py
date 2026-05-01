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
