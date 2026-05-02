from mcp.server.fastmcp import FastMCP, Image

from build123d_mcp.session import Session
from build123d_mcp.tools.execute import execute_code
from build123d_mcp.tools.render import render_view as render_view_fn
from build123d_mcp.tools.measure import measure as measure_fn
from build123d_mcp.tools.export import export_file
from build123d_mcp.tools.interference import interference as interference_fn
from build123d_mcp.tools.list_objects import list_objects as list_objects_fn
from build123d_mcp.tools.library import (
    _LibraryIndex,
    search_library as search_library_fn,
    load_part as load_part_fn,
)

mcp = FastMCP("build123d-mcp")
_session = Session()
_library_index: _LibraryIndex | None = None


@mcp.tool()
def execute(code: str) -> str:
    """Execute build123d Python code in the persistent session. Use show(shape, name) to register named objects; name is optional and defaults to 'shape'."""
    return execute_code(_session, code)


@mcp.tool()
def render_view(direction: str = "iso", objects: str = "", quality: str = "standard", clip_plane: str = "", clip_at: float = None, azimuth: float = 0.0, elevation: float = 0.0, save_to: str = "") -> Image:
    """Render model as PNG. direction: top, front, side, iso. objects: comma-separated names or name:color pairs e.g. 'u_frame:blue,roller:red' (default: all, auto-coloured). quality: standard, high. clip_plane: x, y, z to slice; clip_at: absolute world coordinate along that axis (default: each mesh's midpoint). azimuth/elevation: camera rotation in degrees applied after the direction preset. save_to: optional file path to save the PNG (extension auto-appended if omitted)."""
    png_bytes = render_view_fn(_session, direction, objects, quality, clip_plane, clip_at, azimuth, elevation, save_to)
    return Image(data=png_bytes, format="png")


@mcp.tool()
def measure(query: str = "bounding_box", object_name: str = "", object_name2: str = "") -> str:
    """Query geometry. query: bounding_box, volume, area, min_wall_thickness, clearance, topology. topology returns face/edge/vertex counts — use it to verify a boolean cut happened. object_name/object_name2: named objects from show() (clearance requires both)."""
    return measure_fn(_session, query, object_name, object_name2)


@mcp.tool()
def export(filename: str, format: str = "step", object_name: str = "") -> str:
    """Export model. format: step, stl, or comma-separated list e.g. 'step,stl'. object_name: named object from show() (default: current shape)."""
    return export_file(_session, filename, format, object_name)


@mcp.tool()
def interference(object_a: str, object_b: str) -> str:
    """Check whether two named objects (from show()) intersect. Returns interferes (bool), volume (mm³ of overlap), and bounds of the interference region."""
    return interference_fn(_session, object_a, object_b)


@mcp.tool()
def search_library(query: str = "") -> str:
    """Search the part library. query: keywords matched against name, description, tags, category (empty returns all). Returns name, category, description, tags, and full parameter specs including types, defaults, and descriptions."""
    if _library_index is None:
        return "No part library configured. Start the server with --library PATH or set BUILD123D_PART_LIBRARY."
    return search_library_fn(_library_index, query)


@mcp.tool()
def load_part(name: str, params: str = "") -> str:
    """Load a named part from the library into the session. name: part name from search_library. params: optional JSON object of parameter overrides e.g. '{\"od\": 8.0, \"length\": 20.0}' — unspecified params use their defaults. The part is registered as a named object and becomes current_shape."""
    if _library_index is None:
        return "No part library configured. Start the server with --library PATH or set BUILD123D_PART_LIBRARY."
    return load_part_fn(_session, _library_index, name, params)


@mcp.tool()
def list_objects() -> str:
    """List all named shapes registered via show(), each with volume (mm³), face, edge, and vertex counts. Call this to audit session state without guessing what show() has been called on."""
    return list_objects_fn(_session)


@mcp.tool()
def save_snapshot(name: str) -> str:
    """Save a named checkpoint of the current geometric state (current_shape and the show() object registry).
    The Python variable namespace is NOT saved — only geometry. Call this before risky experiments so you can
    restore known-good geometry without re-running all prior execute() calls."""
    _session.save_snapshot(name)
    saved = ["current_shape"] + list(_session.snapshots[name]["objects"].keys())
    return f"Snapshot '{name}' saved. Geometry captured: {', '.join(saved) if saved else 'none'}."


@mcp.tool()
def restore_snapshot(name: str) -> str:
    """Restore geometric state from a previously saved snapshot (current_shape and the show() registry).
    The Python variable namespace is NOT restored — execute() calls made after the snapshot are still in scope,
    but current_shape and all show() objects revert to what they were at snapshot time.
    Raises an error if the snapshot name does not exist."""
    try:
        _session.restore_snapshot(name)
    except KeyError as e:
        return f"Error: {e}"
    restored = ["current_shape"] + list(_session.objects.keys())
    return f"Snapshot '{name}' restored. Active geometry: {', '.join(restored) if restored else 'none'}."


@mcp.tool()
def reset() -> str:
    """Clear the current session back to empty state, including all snapshots."""
    _session.reset()
    return "Session reset."


def main():
    import argparse
    import os
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
        "args": ["build123d-mcp", "--library", "/path/to/parts"]
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
  search_library    Search the part library by keyword (requires --library)
  load_part         Load a named part with optional parameter overrides (requires --library)
  save_snapshot     Save a named geometric checkpoint
  restore_snapshot  Restore geometry from a named checkpoint
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
    parser.add_argument(
        "--library", metavar="PATH",
        default=os.environ.get("BUILD123D_PART_LIBRARY", ""),
        help="Path to part library directory (overrides BUILD123D_PART_LIBRARY env var)",
    )
    args = parser.parse_args()

    if args.library:
        if not os.path.isdir(args.library):
            parser.error(f"Library path is not a directory: {args.library}")
        global _library_index
        _library_index = _LibraryIndex(args.library)

    mcp.run()


if __name__ == "__main__":
    main()
