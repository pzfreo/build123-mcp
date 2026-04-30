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
    """Execute build123d Python code in the persistent session."""
    return execute_code(_session, code)


@mcp.tool()
def render_view(direction: str = "iso") -> Image:
    """Render the current model as PNG. Direction: top, front, side, iso."""
    png_bytes = render_view_fn(_session, direction)
    return Image(data=png_bytes, format="png")


@mcp.tool()
def measure(query: str = "bounding_box") -> str:
    """Query geometry of the current model. Query: bounding_box."""
    return measure_fn(_session, query)


@mcp.tool()
def export(filename: str, format: str = "step") -> str:
    """Export the current model. Format: step, stl."""
    return export_file(_session, filename, format)


@mcp.tool()
def reset() -> str:
    """Clear the current session back to empty state."""
    _session.reset()
    return "Session reset."


def main():
    mcp.run()


if __name__ == "__main__":
    main()
