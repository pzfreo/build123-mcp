import base64
import os
import tempfile

from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, TextContent

from build123d_mcp.worker import WorkerSession

mcp = FastMCP("build123d-mcp")
_session: WorkerSession
_has_library = False


@mcp.tool()
def execute(code: str) -> str:
    """Execute build123d Python code in the persistent session. Use show(shape, name) to register named objects (name defaults to 'shape'); show() immediately prints volume and face count confirming the shape is non-empty. After any boolean operation (-, +, &) call measure(topology) or measure(volume) to confirm it succeeded before calling render_view."""
    return _session.execute(code)


@mcp.tool()
def render_view(direction: str = "iso", objects: str = "", quality: str = "standard", clip_plane: str = "", clip_at: float | None = None, azimuth: float = 0.0, elevation: float = 0.0, save_to: str = "", format: str = "png") -> list:
    """Render model. format: 'png' (raster, default), 'svg' (HLR line drawing — works without a display, no shading but precise edges), or 'both' (returns the PNG and SVG together — useful when you want shaded depth cues plus crisp edge geometry). If the raster path fails (typically headless host with no display backend) and format='png', the server falls back to SVG automatically. Renders confirm appearance, not geometry — verify boolean operations with measure() before rendering. direction: top, front, side, iso. objects: comma-separated names or name:color pairs e.g. 'u_frame:blue,roller:red' (default: all, auto-coloured). quality: standard, high. clip_plane: x, y, z to slice; clip_at: absolute world coordinate along that axis (default: each mesh's midpoint). azimuth/elevation: camera rotation in degrees applied after the direction preset. save_to: optional file path; for format='both' the PNG and SVG are written as <save_to>.png and <save_to>.svg."""
    result = _session.render_view(
        direction=direction, objects=objects, quality=quality,
        clip_plane=clip_plane, clip_at=clip_at, azimuth=azimuth,
        elevation=elevation, save_to=save_to, format=format,
    )

    contents: list = []
    for key, suffix, mime in (("png", ".png", "image/png"), ("svg", ".svg", "image/svg+xml")):
        if key in result:
            data = result[key]
            fd, path = tempfile.mkstemp(suffix=suffix, prefix="build123d_")
            os.close(fd)
            with open(path, "wb") as f:
                f.write(data)
            contents.append(ImageContent(
                type="image",
                data=base64.b64encode(data).decode(),
                mimeType=mime,
            ))
            contents.append(TextContent(type="text", text=f"[SEND: {path}]"))
    if result.get("fallback"):
        contents.append(TextContent(type="text", text=result["fallback"]))
    if result.get("png_error"):
        contents.append(TextContent(type="text", text=f"PNG render failed: {result['png_error']}"))
    if result.get("png_warnings"):
        for w in result["png_warnings"]:
            contents.append(TextContent(type="text", text=f"Warning: {w}"))
    return contents


@mcp.tool()
def measure(query: str = "bounding_box", object_name: str = "", object_name2: str = "") -> str:
    """Query geometry of a shape. Prefer measure over render_view when verifying geometry — numbers are unambiguous. query: bounding_box, volume, area, min_wall_thickness, clearance, topology, summary. summary returns bbox + volume + area + topology + center in one call — use it to orient quickly. topology (face/edge/vertex counts) is the fastest way to confirm a boolean operation succeeded: a cut that failed leaves the counts unchanged. object_name/object_name2: named objects from show() (clearance requires both)."""
    return _session.measure(query, object_name, object_name2)


@mcp.tool()
def export(filename: str, format: str = "step", object_name: str = "") -> str:
    """Export model. format: step, stl, or comma-separated list e.g. 'step,stl'. object_name: named object from show(), '*' to export all named shapes as a combined assembly (default: current shape)."""
    return _session.export_file(filename, format, object_name)


@mcp.tool()
def interference(object_a: str, object_b: str) -> str:
    """Check whether two named objects (from show()) intersect. Returns interferes (bool), volume (mm³ of overlap), and bounds of the interference region."""
    return _session.interference(object_a, object_b)


@mcp.tool()
def search_library(query: str = "") -> str:
    """Search the part library. query: keywords matched against name, description, tags, category (empty returns all). Returns name, category, description, tags, and full parameter specs including types, defaults, and descriptions."""
    if not _has_library:
        return "No part library configured. Start the server with --library PATH or set BUILD123D_PART_LIBRARY."
    return _session.search_library(query)


@mcp.tool()
def load_part(name: str, params: str = "") -> str:
    """Load a named part from the library into the session. name: part name from search_library. params: optional JSON object of parameter overrides e.g. '{\"od\": 8.0, \"length\": 20.0}' — unspecified params use their defaults. The part is registered as a named object and becomes current_shape."""
    if not _has_library:
        return "No part library configured. Start the server with --library PATH or set BUILD123D_PART_LIBRARY."
    return _session.load_part(name, params)


@mcp.tool()
def list_objects() -> str:
    """List all named shapes registered via show(), each with volume (mm³), face, edge, and vertex counts. Call this to audit session state without guessing what show() has been called on."""
    return _session.list_objects()


@mcp.tool()
def save_snapshot(name: str) -> str:
    """Save a named checkpoint of the current geometric state (current_shape and the show() object registry).
    The Python variable namespace is NOT saved — only geometry. Call this before risky experiments so you can
    restore known-good geometry without re-running all prior execute() calls."""
    return _session.save_snapshot(name)


@mcp.tool()
def restore_snapshot(name: str) -> str:
    """Restore geometric state from a previously saved snapshot (current_shape and the show() registry).
    The Python variable namespace is NOT restored — execute() calls made after the snapshot are still in scope,
    but current_shape and all show() objects revert to what they were at snapshot time.
    Raises an error if the snapshot name does not exist."""
    return _session.restore_snapshot(name)


@mcp.tool()
def diff_snapshot(snapshot_a: str, snapshot_b: str = "", format: str = "text") -> str:
    """Compare two snapshots by geometry metrics (volume, topology, bounding box). snapshot_b defaults to current session state if omitted. format: 'text' (default, human-readable) or 'json' (structured, for programmatic consumption)."""
    return _session.diff_snapshot(snapshot_a, snapshot_b, format)


@mcp.tool()
def session_state() -> str:
    """Return a structured JSON snapshot of the current session: current_shape metrics, all named objects with geometry stats, snapshot names, and a variables summary of the Python namespace (type + volume for shapes, type + length for collections, type + value for scalars). Use this to orient after a reset, restore, or multi-step build to confirm what geometry and variables are active."""
    return _session.session_state()


@mcp.tool()
def health_check() -> str:
    """Verify that render and export dependencies are working. Tests PNG render (VTK), SVG render (build123d HLR), STEP export, and STL export with a trivial shape. Returns JSON with ok/error per capability. Run at session start if you suspect a missing dependency."""
    return _session.health_check()


@mcp.tool()
def reset() -> str:
    """Clear the current session back to empty state, including all snapshots."""
    return _session.reset()


@mcp.tool()
def validate_code(code: str) -> str:
    """Check build123d code for syntax errors, blocked imports/calls, and common omissions before executing. Returns {syntax, blocked, warnings, ok}. blocked items prevent execution; warnings are advisory (e.g. no build123d import in this snippet, no result/show() call). Use this before a long generated script to catch obvious problems without burning a session execute()."""
    from build123d_mcp.tools.validate_code import validate_code as _validate_code
    return _validate_code(code)


@mcp.tool()
def shape_compare(object_a: str, object_b: str) -> str:
    """Compare two named shapes (from show()) by geometry metrics: volume delta, bbox delta, topology delta (faces/edges/vertices), and center offset. Useful when you have an intended design and a reference/test shape and want to verify they match — or to quantify how a modification changed the geometry."""
    return _session.shape_compare(object_a, object_b)


@mcp.tool()
def repair_hints(error_text: str) -> str:
    """Given an error message from execute(), return targeted fix suggestions for common build123d mistakes: wrong Location syntax, missing .part, CadQuery idioms, blocked imports, degenerate boolean results, fillet edge selection, and more. Pass the full error string from execute() or last_error()."""
    from build123d_mcp.tools.repair_hints import repair_hints as _repair_hints
    return _repair_hints(error_text)


@mcp.tool()
def last_error() -> str:
    """Return details of the last failed execute() call: exception type, message, and (for runtime and syntax errors) line number and a 5-line excerpt around the failing line. Security errors include a message but no line/excerpt. Returns {\"error\": null} if the last execute() succeeded or no execute() has failed yet. Call this immediately after an execute() error to get the exact failing line — much faster than re-reading the submitted code."""
    return _session.last_error()


@mcp.tool()
def version() -> str:
    """Return the build123d-mcp server version."""
    from importlib.metadata import version as _version
    return _version("build123d-mcp")


@mcp.tool()
def workflow_hints() -> str:
    """Return guidance on how to use these tools effectively. Call this at the start of a session or whenever unsure which tool to reach for."""
    return """\
BUILD123D-MCP WORKFLOW GUIDE

1. ORIENT FIRST
   At the start of a session, call session_state() to see what geometry, objects, and
   snapshots are already active. Call health_check() if you suspect a missing dependency
   (VTK, display, STEP export). Call version() to confirm the server version.

2. MEASURE BEFORE YOU LOOK
   After building or modifying geometry, verify with measure() before calling render_view.
   Numbers are unambiguous; renders can look correct even when the geometry is wrong.
   Recommended order: execute → measure → render_view (if you need to see it).

3. VERIFY BOOLEAN OPERATIONS WITH TOPOLOGY
   After any cut, union, or intersection, call measure(topology) on the result.
   A successful boolean changes face/edge/vertex counts; a failed one leaves them unchanged.
   measure(volume) confirms the magnitude of the change.

4. MEASURE THE OBJECT IN QUESTION — NOT A PROXY
   When debugging, call measure() on the actual disputed object.
   Testing an isolated reconstruction and using that as proof of the full assembly is a
   common mistake — the two may differ in ways that matter.

5. NAME AND AUDIT YOUR SHAPES
   Use show(shape, "name") after creating important geometry — it also sets current_shape.
   The execute() output immediately confirms name, volume, and face count.
   Call session_state() for a full JSON view of all active shapes, objects, and snapshots.

6. CHECKPOINT BEFORE EXPERIMENTS
   Call save_snapshot("name") before any operation you might want to undo.
   Snapshots are instant. restore_snapshot("name") reverts geometry without re-running code.
   Use diff_snapshot("name") to see what changed; pass format="json" for structured output.

7. CROSS-SECTIONS FOR INTERNAL GEOMETRY
   render_view with clip_plane + clip_at reveals interior features.
   Use clip_at to position the cut at a specific world coordinate, not just the midpoint.
   Combine with measure(topology) on the unclipped shape to confirm what you see.

8. PART LIBRARY
   search_library("keyword") returns full parameter specs.
   Call load_part("name", '{"param": value}') immediately — no second lookup needed.
   Unspecified parameters use the defaults shown in search results.
"""


def main():
    import argparse
    import os
    from importlib.metadata import version
    parser = argparse.ArgumentParser(
        prog="build123d-mcp",
        description="MCP server for interactive 3D CAD via build123d. Communicates over stdio.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
MCP client configuration example:
  {
    "mcpServers": {
      "build123d": {
        "command": "uvx",
        "args": ["--python", "3.12", "build123d-mcp", "--library", "/path/to/parts"]
      }
    }
  }

Available tools:
  execute           Run build123d Python code in the persistent session
  render_view       Render model as PNG (direction, azimuth, elevation, clip_plane, clip_at, save_to)
  measure           Query geometry: bounding_box, volume, area, topology, min_wall_thickness, clearance
  export            Export model to STEP or STL
  interference      Check intersection volume between two named shapes
  list_objects      List all named shapes with volume, faces, edges, vertices
  session_state     Full session JSON: current_shape, all objects, snapshot names
  health_check      Verify VTK/SVG/STEP/STL dependencies work end-to-end
  search_library    Search the part library by keyword (requires --library)
  load_part         Load a named part with optional parameter overrides (requires --library)
  save_snapshot     Save a named geometric checkpoint
  restore_snapshot  Restore geometry from a named checkpoint
  diff_snapshot     Compare two snapshots; format="json" for structured output
  last_error        Details of the last failed execute() (type, message, line, excerpt)
  validate_code     Check code for syntax/security errors before executing
  shape_compare     Compare two named shapes by geometry metrics
  repair_hints      Get fix suggestions for a given execute() error message
  version           Return the server version string
  workflow_hints    Return guidance on using these tools effectively
  reset             Clear the session (namespace, shapes, snapshots)

Part library file format (Python, any .py file under --library path):
  PART_INFO = {
      "description": "Short description",
      "tags": ["tag1", "tag2"],
      "parameters": {
          "width": {"type": "float", "default": 10.0, "description": "width mm"},
      }
  }
  from build123d import *
  def make(width=10.0):
      return Box(width, width, width)
""",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('build123d-mcp')}")
    parser.add_argument(
        "--library", metavar="PATH",
        default=os.environ.get("BUILD123D_PART_LIBRARY", ""),
        help="Path to part library directory (overrides BUILD123D_PART_LIBRARY env var)",
    )
    args = parser.parse_args()

    if args.library and not os.path.isdir(args.library):
        parser.error(f"Library path is not a directory: {args.library}")

    global _session, _has_library
    _has_library = bool(args.library)
    _session = WorkerSession(library_path=args.library)

    mcp.run()


if __name__ == "__main__":
    main()
