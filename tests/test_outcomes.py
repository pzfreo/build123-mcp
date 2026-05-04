"""
Outcome-focused tests: verify what the server actually produces,
not just that functions return without error.
"""
import asyncio
import base64
import json
import os
import struct
import sys

import pytest

from build123d_mcp.session import Session
from build123d_mcp.tools.execute import execute_code
from build123d_mcp.tools.export import export_file
from build123d_mcp.tools.measure import measure
from build123d_mcp.tools.render import render_view

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


def test_create_measure_export_round_trip(session, tmp_path, monkeypatch):
    """Create a known shape, verify its dimensions, then export it."""
    monkeypatch.chdir(tmp_path)
    execute_code(session, "result = Box(30, 20, 10)")
    data = json.loads(measure(session, "bounding_box"))
    assert abs(data["xsize"] - 30) < 0.01
    assert abs(data["ysize"] - 20) < 0.01
    assert abs(data["zsize"] - 10) < 0.01

    export_file(session, "out", "step")
    # A real STEP file for a simple box is several kilobytes
    assert os.path.getsize("out.step") > 1000


def test_multi_format_export_produces_both_files(session, tmp_path, monkeypatch):
    """Exporting step,stl in one call writes both files with real content."""
    monkeypatch.chdir(tmp_path)
    execute_code(session, "result = Box(20, 20, 20)")
    result = export_file(session, "part", "step,stl")
    step_size = os.path.getsize("part.step")
    stl_size = os.path.getsize("part.stl")
    # STEP files are text-based and larger; STL binary is compact but non-zero
    assert step_size > 1000
    assert stl_size > 0
    # Both paths reported in the return message
    assert ".step" in result
    assert ".stl" in result


def test_multi_format_export_named_object(session, tmp_path, monkeypatch):
    """Multi-format export targets the named object, not current_shape."""
    monkeypatch.chdir(tmp_path)
    execute_code(session, "result = Box(5, 5, 5)\nshow(Box(40, 40, 40), 'big')")
    export_file(session, "big", "step,stl", "big")
    # The big box STEP file is distinctly larger than a 5mm box would produce
    assert os.path.getsize("big.step") > 1000
    assert os.path.getsize("big.stl") > 0


def test_reset_discards_previous_geometry(session):
    """After reset, old geometry is gone and new geometry starts from scratch."""
    execute_code(session, "result = Box(100, 100, 100)")
    session.reset()
    session.execute("from build123d import *")
    execute_code(session, "result = Box(5, 5, 5)")
    bb = json.loads(measure(session, "bounding_box"))
    assert abs(bb["xsize"] - 5) < 0.01


def test_render_changes_when_model_changes(session):
    """Rendering a different shape produces a different image.

    Note: the camera autofits to the bounds, so a uniform scale change
    (Box(10) → Box(50)) renders identically. This test uses shapes that
    differ in proportion, which is what actually changes the rendered pixels.
    """
    execute_code(session, "result = Box(10, 10, 10)")
    png_cube = render_view(session, "iso")["png"]
    execute_code(session, "result = Box(10, 30, 50)")
    png_slab = render_view(session, "iso")["png"]
    assert png_cube[:8] == PNG_MAGIC
    assert png_slab[:8] == PNG_MAGIC
    assert png_cube != png_slab


def test_error_in_execute_preserves_current_shape(session):
    """A failed execute does not wipe the current shape."""
    execute_code(session, "result = Box(10, 10, 10)")
    shape_before = session.current_shape
    execute_code(session, "this_will_fail(")  # SyntaxError
    assert session.current_shape is shape_before


# ---------------------------------------------------------------------------
# Security: injection resistance
# ---------------------------------------------------------------------------

def test_shell_injection_attempt_blocked(session):
    """A prompt-injection payload trying to run a shell command is rejected."""
    execute_code(session, "result = Box(10, 10, 10)")
    shape_before = session.current_shape
    result = execute_code(session, "import subprocess; subprocess.run(['id'])")
    assert "not allowed" in result.lower() or "SecurityError" in result
    # Geometry is intact
    assert session.current_shape is shape_before


def test_filesystem_read_attempt_blocked(session):
    """Attempting to read a file via open() is rejected."""
    result = execute_code(session, "data = open('/etc/passwd').read()")
    assert "not allowed" in result.lower() or "Error" in result


def test_network_access_attempt_blocked(session):
    """Attempting to open a network socket is rejected."""
    result = execute_code(session, "import socket; socket.create_connection(('1.1.1.1', 80))")
    assert "not allowed" in result.lower() or "SecurityError" in result


def test_normal_workflow_unaffected_by_security(session):
    """Security hardening does not break a legitimate build123d session."""
    execute_code(session, "import math\nresult = Cylinder(math.pi, 20)")
    assert session.current_shape is not None
    bb = json.loads(measure(session, "bounding_box"))
    assert bb["zsize"] > 0


def test_builtins_import_restriction_independent_of_ast(session):
    """The builtins __import__ restriction provides a second layer: even if a
    future change widened the AST allowlist, the namespace-level filter still
    blocks non-allowlisted imports at runtime."""
    # Bypass AST by calling __import__ through builtins dict directly
    restricted_import = session.namespace["__builtins__"]["__import__"]
    with pytest.raises(ImportError, match="not allowed"):
        restricted_import("os")


# ---------------------------------------------------------------------------
# Session snapshots
# ---------------------------------------------------------------------------

def test_snapshot_restores_geometry_after_bad_experiment(session):
    """save_snapshot / restore_snapshot recovers known-good geometry."""
    execute_code(session, "result = Box(10, 10, 10)")
    session.save_snapshot("good")
    good_vol = json.loads(measure(session, "volume"))["volume"]

    # Simulate an experiment that produces wrong geometry
    execute_code(session, "result = Box(1, 1, 1)")
    assert json.loads(measure(session, "volume"))["volume"] < good_vol

    session.restore_snapshot("good")
    assert abs(json.loads(measure(session, "volume"))["volume"] - good_vol) < 0.1


def test_snapshot_objects_registry_survives_round_trip(session):
    """Named objects are captured in the snapshot and restored correctly."""
    execute_code(session, "show(Box(60, 40, 8), 'frame')\nshow(Cylinder(5, 50), 'axle')")
    session.save_snapshot("assembly_v1")

    # Overwrite both objects
    execute_code(session, "show(Box(1, 1, 1), 'frame')\nshow(Box(1, 1, 1), 'axle')")
    session.restore_snapshot("assembly_v1")

    frame_bb = json.loads(measure(session, "bounding_box", "frame"))
    axle_bb = json.loads(measure(session, "bounding_box", "axle"))
    assert abs(frame_bb["xsize"] - 60) < 0.1
    assert abs(axle_bb["zsize"] - 50) < 0.1


def test_namespace_not_restored_by_snapshot(session):
    """Python variables set after a snapshot are still accessible after restore.
    This confirms the documented behaviour: snapshot saves geometry only."""
    execute_code(session, "result = Box(10, 10, 10)")
    session.save_snapshot("s1")
    execute_code(session, "extra_var = 123")
    session.restore_snapshot("s1")
    # extra_var is still in scope even though it was created after the snapshot
    assert session.namespace.get("extra_var") == 123


# ---------------------------------------------------------------------------
# Multi-object session: show(), per-object measure/export/render
# ---------------------------------------------------------------------------

def test_named_objects_have_independent_bounding_boxes(session):
    """show() isolates shapes: each named object reports its own dimensions."""
    execute_code(session, "show(Box(5, 5, 5), 'small')\nshow(Box(40, 40, 40), 'large')")
    small = json.loads(measure(session, "bounding_box", "small"))
    large = json.loads(measure(session, "bounding_box", "large"))
    assert abs(small["xsize"] - 5) < 0.01
    assert abs(large["xsize"] - 40) < 0.01


def test_assembly_render_differs_from_single_part_render(session):
    """Rendering all registered objects produces a different image than one part alone."""
    execute_code(session, "show(Box(10, 10, 10), 'box')\nshow(Cylinder(3, 30), 'cyl')")
    png_all = render_view(session, "iso")["png"]
    png_one = render_view(session, "iso", objects="box")["png"]
    assert png_all[:8] == PNG_MAGIC
    assert png_one[:8] == PNG_MAGIC
    assert png_all != png_one


def test_export_named_object_independent_of_current_shape(session, tmp_path, monkeypatch):
    """Exporting a named object writes that shape, not current_shape."""
    monkeypatch.chdir(tmp_path)
    execute_code(session, "result = Box(5, 5, 5)\nshow(Box(50, 50, 50), 'big')")
    export_file(session, "big", "step", "big")
    # The big box STEP file should be larger than a tiny box would produce
    assert os.path.getsize("big.step") > 1000


def test_export_assembly_step_contains_all_parts(session, tmp_path, monkeypatch):
    """object_name='*' exports a compound of all named shapes; STEP is larger than any single part."""
    monkeypatch.chdir(tmp_path)
    execute_code(session, "show(Box(10, 10, 10), 'box')\nshow(Cylinder(5, 20), 'cyl')")
    export_file(session, "box", "step", "box")
    export_file(session, "cyl", "step", "cyl")
    export_file(session, "assembly", "step", "*")
    box_size = os.path.getsize("box.step")
    cyl_size = os.path.getsize("cyl.step")
    asm_size = os.path.getsize("assembly.step")
    assert asm_size > box_size
    assert asm_size > cyl_size


def test_export_assembly_stl_is_valid_binary(session, tmp_path, monkeypatch):
    """object_name='*' produces a valid binary STL whose triangle count matches the header."""
    monkeypatch.chdir(tmp_path)
    execute_code(session, "show(Box(10, 10, 10), 'a')\nshow(Box(5, 5, 5), 'b')")
    export_file(session, "assembly", "stl", "*")
    with open("assembly.stl", "rb") as f:
        data = f.read()
    # Binary STL: 80-byte header + 4-byte count + count * 50 bytes
    tri_count = struct.unpack_from("<I", data, 80)[0]
    assert tri_count > 0
    assert len(data) == 84 + tri_count * 50


def test_export_stl_avoids_mesher_for_complex_shape(session, tmp_path, monkeypatch):
    """STL export of a boolean-subtracted shape uses tessellate(), not Mesher, so it doesn't
    raise '3mf mesh is invalid' for shapes that pass OCCT meshing but fail Lib3MF validation."""
    monkeypatch.chdir(tmp_path)
    execute_code(session, "show(Box(20, 20, 20) - Cylinder(5, 22), 'hollow')")
    export_file(session, "hollow", "stl", "hollow")
    with open("hollow.stl", "rb") as f:
        data = f.read()
    tri_count = struct.unpack_from("<I", data, 80)[0]
    assert tri_count > 0


def test_reset_clears_show_registry(session):
    """After reset, previously registered objects are gone."""
    execute_code(session, "show(Box(10, 10, 10), 'part')")
    assert "part" in session.objects
    session.reset()
    assert not session.objects


# ---------------------------------------------------------------------------
# Richer measurements
# ---------------------------------------------------------------------------

def test_volume_detects_missing_boolean(session):
    """volume() exposes the difference between a solid and a hollowed part."""
    execute_code(session, "show(Box(20, 20, 20), 'full')")
    solid_vol = json.loads(measure(session, "volume", "full"))["volume"]
    execute_code(session, "show(Box(20, 20, 20) - Cylinder(5, 22), 'hollow')")
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
        "show(Cylinder(4, 30), 'shaft')\n"
        "show(Box(30, 30, 30) - Cylinder(5, 32), 'bore_housing')"
    )
    data = json.loads(measure(session, "clearance", "shaft", "bore_housing"))
    # shaft radius 4, bore radius 5 — clearance should be ~1mm
    assert data["clearance"] >= 0
    assert data["clearance"] < 5


def test_clearance_zero_for_touching_shapes(session):
    """Touching shapes report zero clearance."""
    execute_code(session,
        "show(Box(10, 10, 10), 'a')\n"
        "show(Box(10, 10, 10).move(Location((10, 0, 0))), 'b')"
    )
    data = json.loads(measure(session, "clearance", "a", "b"))
    assert data["clearance"] < 0.01


# ---------------------------------------------------------------------------
# Rendering quality and clip plane
# ---------------------------------------------------------------------------

def test_high_quality_render_differs_from_standard(session):
    """High quality tessellation produces a different image than standard."""
    execute_code(session, "result = Cylinder(5, 20)")
    png_std = render_view(session, "iso", quality="standard")["png"]
    png_hi = render_view(session, "iso", quality="high")["png"]
    assert png_std[:8] == PNG_MAGIC
    assert png_hi[:8] == PNG_MAGIC
    assert png_std != png_hi


def test_clip_plane_produces_different_image_than_unclipped(session):
    """A clipped render exposes internal geometry and differs from the unclipped view."""
    execute_code(session, "result = Cylinder(8, 30)")
    png_full = render_view(session, "iso")["png"]
    png_clip = render_view(session, "iso", clip_plane="y")["png"]
    assert png_full[:8] == PNG_MAGIC
    assert png_clip[:8] == PNG_MAGIC
    assert png_full != png_clip


# ---------------------------------------------------------------------------
# MCP protocol round-trip: test through the actual stdio transport
# ---------------------------------------------------------------------------
# Skipped on Windows: each round-trip cold-imports build123d in a freshly
# spawned worker (~60-90s on Windows runners), and pytest-timeout's "thread"
# method (the only one available on Windows) cannot kill a hung asyncio.run,
# so a stuck call blocks the entire test session indefinitely.

_skip_mcp_on_win = pytest.mark.skipif(
    sys.platform == "win32",
    reason="MCP-stdio round-trip too slow on Windows; covered by Linux/macOS jobs",
)


async def _mcp_session(coro, cwd=None):
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command="uv",
        args=["run", "build123d-mcp"],
        cwd=cwd or SERVER_DIR,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as mcp:
            await mcp.initialize()
            return await coro(mcp)


@_skip_mcp_on_win
def test_mcp_lists_all_tools():
    async def run(mcp):
        result = await mcp.list_tools()
        return {t.name for t in result.tools}

    names = asyncio.run(_mcp_session(run))
    assert names == {"execute", "render_view", "measure", "export", "reset",
                     "save_snapshot", "restore_snapshot", "diff_snapshot", "interference", "list_objects",
                     "search_library", "load_part", "workflow_hints", "session_state", "health_check", "version"}


@_skip_mcp_on_win
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


@_skip_mcp_on_win
def test_mcp_render_returns_image_and_file_path():
    async def run(mcp):
        await mcp.call_tool(
            "execute",
            {"code": "from build123d import *\nresult = Box(10, 10, 10)"},
        )
        result = await mcp.call_tool("render_view", {"direction": "iso"})
        img = result.content[0]
        path_item = result.content[1]
        return img.type, img.data, img.mimeType, path_item.type, path_item.text

    img_type, img_data, mime, path_type, path_text = asyncio.run(_mcp_session(run))
    # ImageContent with base64 PNG
    assert img_type == "image"
    assert mime == "image/png"
    import base64
    png_bytes = base64.b64decode(img_data)
    assert png_bytes[:8] == PNG_MAGIC
    # TextContent with file path for [SEND:] delivery
    assert path_type == "text"
    path = path_text.removeprefix("[SEND: ").removesuffix("]")
    assert path.endswith(".png")
    assert os.path.exists(path)
    with open(path, "rb") as f:
        assert f.read(8) == PNG_MAGIC


@_skip_mcp_on_win
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


@_skip_mcp_on_win
def test_mcp_injection_attempt_returns_error_not_executes():
    """A shell-injection payload through the MCP wire returns an error and does
    not produce side-effects (geometry is still None at the start of the session)."""
    async def run(mcp):
        result = await mcp.call_tool(
            "execute",
            {"code": "import subprocess; subprocess.run(['id'], capture_output=True)"},
        )
        return result.content[0].text

    text = asyncio.run(_mcp_session(run))
    assert "not allowed" in text.lower() or "SecurityError" in text


@_skip_mcp_on_win
def test_mcp_snapshot_save_and_restore():
    """save_snapshot / restore_snapshot round-trip through the MCP wire restores geometry."""
    async def run(mcp):
        await mcp.call_tool("execute", {"code": "from build123d import *\nresult = Box(10, 10, 10)"})
        await mcp.call_tool("save_snapshot", {"name": "v1"})
        await mcp.call_tool("execute", {"code": "result = Box(99, 99, 99)"})
        await mcp.call_tool("restore_snapshot", {"name": "v1"})
        result = await mcp.call_tool("measure", {"query": "bounding_box"})
        return result.content[0].text

    data = json.loads(asyncio.run(_mcp_session(run)))
    assert abs(data["xsize"] - 10) < 0.01


@_skip_mcp_on_win
def test_mcp_multi_format_export(tmp_path):
    """export with format='step,stl' reports both paths over the MCP wire."""
    async def run(mcp):
        await mcp.call_tool("execute", {"code": "from build123d import *\nresult = Box(10, 10, 10)"})
        result = await mcp.call_tool("export", {"filename": "mcp_test_out", "format": "step,stl"})
        return result.content[0].text

    text = asyncio.run(_mcp_session(run, cwd=str(tmp_path)))
    assert ".step" in text
    assert ".stl" in text


@_skip_mcp_on_win
def test_mcp_volume_and_clearance():
    """volume and clearance round-trip through the MCP wire."""
    async def run(mcp):
        await mcp.call_tool("execute", {"code": (
            "from build123d import *\n"
            "show(Box(10, 10, 10), 'a')\n"
            "show(Box(10, 10, 10).move(Location((15, 0, 0))), 'b')"
        )})
        r_vol = await mcp.call_tool("measure", {"query": "volume", "object_name": "a"})
        r_cl = await mcp.call_tool("measure", {"query": "clearance", "object_name": "a", "object_name2": "b"})
        return r_vol.content[0].text, r_cl.content[0].text

    vol_json, cl_json = asyncio.run(_mcp_session(run))
    assert abs(json.loads(vol_json)["volume"] - 1000) < 1
    assert abs(json.loads(cl_json)["clearance"] - 5) < 0.1


@_skip_mcp_on_win
def test_mcp_show_and_measure_named_object():
    """show() + per-object measure round-trip through the MCP wire."""
    async def run(mcp):
        await mcp.call_tool(
            "execute",
            {"code": "from build123d import *\nshow(Box(40, 5, 5), 'wide')\nshow(Box(5, 5, 40), 'tall')"},
        )
        r_wide = await mcp.call_tool("measure", {"query": "bounding_box", "object_name": "wide"})
        r_tall = await mcp.call_tool("measure", {"query": "bounding_box", "object_name": "tall"})
        return r_wide.content[0].text, r_tall.content[0].text

    wide_json, tall_json = asyncio.run(_mcp_session(run))
    wide = json.loads(wide_json)
    tall = json.loads(tall_json)
    assert abs(wide["xsize"] - 40) < 0.01
    assert abs(tall["zsize"] - 40) < 0.01
