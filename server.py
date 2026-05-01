from mcp.server.fastmcp import FastMCP, Image

from session import Session
from tools.execute import execute_code
from tools.render import render_view as render_view_fn
from tools.measure import measure as measure_fn
from tools.export import export_file

mcp = FastMCP("build123-mcp")
_session = Session()


@mcp.tool()
def execute(code: str) -> str:
    """Execute build123d Python code in the persistent session. Use show(name, shape) to register named objects."""
    return execute_code(_session, code)


@mcp.tool()
def render_view(direction: str = "iso", objects: str = "", quality: str = "standard", clip_plane: str = "") -> Image:
    """Render model as PNG. direction: top, front, side, iso. objects: comma-separated names (default: all). quality: standard, high. clip_plane: x, y, or z to slice at midpoint."""
    png_bytes = render_view_fn(_session, direction, objects, quality, clip_plane)
    return Image(data=png_bytes, format="png")


@mcp.tool()
def measure(query: str = "bounding_box", object_name: str = "", object_name2: str = "") -> str:
    """Query geometry. query: bounding_box, volume, area, min_wall_thickness, clearance. object_name/object_name2: named objects from show() (clearance requires both)."""
    return measure_fn(_session, query, object_name, object_name2)


@mcp.tool()
def export(filename: str, format: str = "step", object_name: str = "") -> str:
    """Export model. format: step, stl, or comma-separated list e.g. 'step,stl'. object_name: named object from show() (default: current shape)."""
    return export_file(_session, filename, format, object_name)


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
    mcp.run()


if __name__ == "__main__":
    main()
