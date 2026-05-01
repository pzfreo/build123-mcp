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
def measure(query: str = "bounding_box", object_name: str = "") -> str:
    """Query geometry. query: bounding_box. object_name: named object from show() (default: current shape)."""
    return measure_fn(_session, query, object_name)


@mcp.tool()
def export(filename: str, format: str = "step", object_name: str = "") -> str:
    """Export model. format: step, stl. object_name: named object from show() (default: current shape)."""
    return export_file(_session, filename, format, object_name)


@mcp.tool()
def reset() -> str:
    """Clear the current session back to empty state."""
    _session.reset()
    return "Session reset."


def main():
    mcp.run()


if __name__ == "__main__":
    main()
