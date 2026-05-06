import base64
import os
import tempfile

from mcp.server.fastmcp import FastMCP
from mcp.types import ImageContent, PromptMessage, TextContent

from build123d_mcp.worker import WorkerSession

mcp = FastMCP("build123d-mcp")
_session: WorkerSession
_has_library = False


@mcp.tool()
def execute(code: str) -> str:
    """Execute build123d Python code in the persistent session. Errors include automatic fix hints — read them before retrying. Use show(shape, name) to register named objects (name defaults to 'shape'); show() immediately prints volume and face count confirming the shape is non-empty. After any boolean operation (-, +, &) call measure() to confirm it succeeded (check topology.faces). named_face(shape, name) is a built-in helper: named_face(box, 'top') returns the highest-Z face, 'bottom'/'front'/'back'/'left'/'right' work similarly."""
    from build123d_mcp.tools.execute import execute_code
    return execute_code(_session, code)


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
def measure(object_name: str = "") -> str:
    """Measure a shape and return a complete geometric summary: volume (mm³), surface area (mm²), topology (face/edge/vertex counts), bounding box with per-axis size and center, volumetric center of mass, 6-component inertia tensor (Ixx/Iyy/Izz/Ixy/Ixz/Iyz), and a face-type inventory classifying every face as Plane/Cylinder/Cone/Sphere/Torus/BSpline with area and type-specific params (e.g. cylinder diameter and axis). Prefer measure over render_view for verifying geometry — numbers are unambiguous. topology is the fastest confirmation that a boolean operation succeeded: a failed cut leaves face/edge/vertex counts unchanged. object_name: named object from show() (default: current shape)."""
    return _session.measure(object_name)


@mcp.tool()
def clearance(object_a: str, object_b: str) -> str:
    """Return the minimum distance (mm) between two named shapes registered via show(). A result of 0 means the shapes are touching or overlapping — use interference() to check for overlap. object_a, object_b: names from show()."""
    return _session.clearance(object_a, object_b)


@mcp.tool()
def cross_sections(object_name: str = "", axis: str = "Z", num_slices: int = 10) -> str:
    """Compute cross-sectional areas at evenly spaced planes along an axis. Returns a list of {position, area} pairs. axis: X, Y, or Z (default Z). num_slices: number of planes (default 10, minimum 2). Useful for detecting internal voids, wall-thickness variation, or verifying that a shape's cross-section profile matches a reference. object_name: named object from show() (default: current shape)."""
    return _session.cross_sections(object_name, axis, num_slices)


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
    """Return a structured JSON snapshot of the current session: current_shape metrics, all named objects (replaces list_objects) with geometry stats, snapshot names, and a variables summary of the Python namespace (type + volume for shapes, type + length for collections, type + value for scalars). Use this to orient after a reset, restore, or multi-step build to confirm what geometry and variables are active."""
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
def shape_compare(object_a: str, object_b: str) -> str:
    """Compare two named shapes (from show()) by geometry metrics: volume delta, bbox delta, topology delta (faces/edges/vertices), and center offset. Useful when you have an intended design and a reference/test shape and want to verify they match — or to quantify how a modification changed the geometry."""
    return _session.shape_compare(object_a, object_b)


@mcp.tool()
def import_cad_file(path: str, name: str = "") -> str:
    """Import a STEP (.step/.stp) or STL (.stl) file as a named object in the session. path: absolute or relative path to the file. name: name to register the shape under (defaults to the filename stem). The shape becomes both the named object and the current_shape. Returns volume, topology, and bounding box of the imported shape. Use this to load reference geometry for comparison with show() objects via shape_compare() or measure()."""
    return _session.import_cad_file(path, name)


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
   After any cut, union, or intersection, call measure() and check topology.faces.
   A successful boolean changes face/edge/vertex counts; a failed one leaves them unchanged.
   measure().volume confirms the magnitude of the change.

4. MEASURE THE OBJECT IN QUESTION — NOT A PROXY
   When debugging, call measure() on the actual disputed object.
   Testing an isolated reconstruction and using that as proof of the full assembly is a
   common mistake — the two may differ in ways that matter.

5. NAME AND AUDIT YOUR SHAPES
   Use show(shape, "name") after creating important geometry — it also sets current_shape.
   The execute() output immediately confirms name, volume, and face count.
   Call session_state() for a full JSON view of all active shapes, objects, and snapshots.
   session_state() includes the named-object list — no separate list_objects() call needed.

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


_QUICKREF = """\
BUILD123D QUICK REFERENCE — all measurements in mm
====================================================

## Pattern 1: direct shape algebra (simplest)
from build123d import *
result = Box(20, 10, 5)
result = result - Cylinder(3, 6).move(Location((0, 0, 0)))
show(result, "part")

## Pattern 2: BuildPart context manager (required for extrude/revolve/loft/fillet)
from build123d import *
with BuildPart() as p:
    Box(20, 10, 5)
    Cylinder(3, 6, mode=Mode.SUBTRACT)   # cut hole
result = p.part
show(result, "part")

## Primitives
Box(length, width, height)              # centred at origin
Cylinder(radius, height)
Sphere(radius)
Cone(bottom_radius, top_radius, height)
Torus(major_radius, minor_radius)

## Boolean operators (direct algebra)
a + b    # union
a - b    # cut b from a
a & b    # intersection

## Boolean modes (inside BuildPart)
mode=Mode.ADD        # default — union with existing solid
mode=Mode.SUBTRACT   # cut from existing solid
mode=Mode.INTERSECT  # keep overlap only
mode=Mode.REPLACE    # replace current solid entirely

## Positioning
# Alignment (corner vs centred)
Box(10, 5, 3, align=(Align.MIN, Align.MIN, Align.MIN))        # corner at origin
Box(10, 5, 3, align=(Align.CENTER, Align.CENTER, Align.MIN))  # centred XY, bottom at Z=0

# Translate (and optionally rotate)
shape.move(Location((x, y, z)))
shape.move(Location((x, y, z), (rx_deg, ry_deg, rz_deg)))

# Place multiple instances inside BuildPart
with Locations((5, 0, 0), (-5, 0, 0)):
    Cylinder(2, 10, mode=Mode.SUBTRACT)
with GridLocations(x_spacing, y_spacing, x_count, y_count):
    Cylinder(2, 10, mode=Mode.SUBTRACT)
with PolarLocations(radius, count):
    Cylinder(2, 10, mode=Mode.SUBTRACT)

## Sketch → solid (requires BuildPart)
# Extrude
with BuildPart() as p:
    with BuildSketch() as sk:            # default plane: XY
        Circle(10)
        Rectangle(6, 6, mode=Mode.SUBTRACT)   # cutout in sketch
    extrude(amount=15)

# Revolve — profile in Plane.XZ, offset from axis
with BuildPart() as p:
    with BuildSketch(Plane.XZ) as sk:
        with Locations((12, 0)):
            Rectangle(4, 8)
    revolve(axis=Axis.Z)                 # full 360°

# Loft between two profiles
with BuildPart() as p:
    with BuildSketch(Plane.XY) as s1:
        Rectangle(10, 10)
    with BuildSketch(Plane.XY.offset(15)) as s2:
        Circle(4)
    loft()

## Selecting edges and faces
result.faces().sort_by(Axis.Z)[-1]       # highest-Z face (top)
result.faces().sort_by(Axis.Z)[0]        # lowest-Z face (bottom)
result.edges().sort_by(Axis.Z)[-4:]      # 4 edges at highest Z (for fillet)
result.edges().filter_by(Axis.Z)         # edges parallel to Z
result.faces().filter_by(GeomType.PLANE) # planar faces only

## Fillets and chamfers (inside BuildPart only)
with BuildPart() as p:
    Box(20, 10, 5)
    fillet(p.part.edges().sort_by(Axis.Z)[-4:], radius=1)

with BuildPart() as p:
    Box(20, 10, 5)
    chamfer(p.part.edges().sort_by(Axis.Z)[-4:], length=0.5)

## MCP server conventions
- Name the final shape 'result' OR call show() — both trigger current_shape auto-detection
- show(shape, "name")      registers object, prints vol + face count as immediate confirmation
- named_face(shape, "top") returns the highest-Z face; also: bottom/front/back/left/right

## Common gotchas
- After every -, +, & : call measure() and check topology.faces — a failed boolean leaves counts unchanged
- fillet/chamfer radius too large → OCC kernel exception; reduce radius or select fewer edges
- Cylinder/Sphere are centred at origin; use .move() or align= to reposition
- Locations() inside BuildPart shifts the construction origin — it does NOT move the whole part
- Pass p.part (the Shape) to show(), not p (the BuildPart context)
- revolve() needs the profile offset from the revolution axis — a profile touching the axis produces a solid, one crossing it fails
"""


@mcp.resource("build123d://quickref", mime_type="text/plain",
              description="build123d API quick reference: primitives, booleans, positioning, sketch-to-3D, selectors, fillets.")
def build123d_quickref() -> str:
    """build123d API quick reference."""
    return _QUICKREF


@mcp.prompt(
    name="start-cad-session",
    description="Prime a new CAD design session with the task description and workflow reminders.",
)
def start_cad_session(description: str) -> list[PromptMessage]:
    """Start a new CAD design session.

    Args:
        description: What you want to build.
    """
    text = f"""\
Design task: {description}

Workflow:
1. Call reset(), then execute 'from build123d import *' to start clean.
2. Build incrementally — small execute() calls are easier to debug than one large block.
3. After every execute(), call measure() to verify geometry (check volume and topology.faces).
4. After every boolean (-, +, &), confirm topology.faces changed — unchanged counts mean the boolean failed.
5. Use show(shape, "name") to register important intermediate shapes; it prints vol + face count immediately.
6. Call render_view() only after measure() confirms the geometry is correct.
7. Call save_snapshot("name") before any experiment you might want to undo.
8. When complete: export("part", "step,stl").

Read the build123d://quickref resource before writing execute() code — it has accurate API syntax.
Call workflow_hints() if unsure which tool to use next.
"""
    return [PromptMessage(role="user", content=TextContent(type="text", text=text))]


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
        "command": "uv",
        "args": ["tool", "run", "--python", "3.12", "build123d-mcp", "--library", "/path/to/parts"]
      }
    }
  }

Available tools:
  execute           Run build123d Python code; errors include automatic fix hints
  render_view       Render model as PNG (direction, azimuth, elevation, clip_plane, clip_at, save_to)
  measure           Full geometric summary: volume, area, topology, bbox, center_of_mass, inertia, face_inventory
  clearance         Minimum distance between two named shapes
  cross_sections    Cross-sectional areas along X/Y/Z axis at evenly-spaced planes
  export            Export model to STEP or STL
  interference      Check intersection volume between two named shapes
  session_state     Full session JSON: current_shape, all named objects, snapshot names, variables
  health_check      Verify VTK/SVG/STEP/STL dependencies work end-to-end
  search_library    Search the part library by keyword (requires --library)
  load_part         Load a named part with optional parameter overrides (requires --library)
  save_snapshot     Save a named geometric checkpoint
  restore_snapshot  Restore geometry from a named checkpoint
  diff_snapshot     Compare two snapshots; format="json" for structured output
  last_error        Details of the last failed execute() (type, message, line, excerpt)
  shape_compare     Compare two named shapes by geometry metrics
  import_cad_file   Import a STEP or STL file as a named object for comparison
  repair_hints      Get additional fix suggestions for a given execute() error message
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
    parser.add_argument(
        "--allow-all-imports", action="store_true",
        default=os.environ.get("BUILD123D_ALLOW_ALL_IMPORTS", "").lower() in ("1", "true", "yes"),
        help="Disable the import allowlist — any Python module can be imported. "
             "Use only in trusted environments. Overrides BUILD123D_ALLOW_ALL_IMPORTS env var.",
    )
    parser.add_argument(
        "--exec-timeout", metavar="SECONDS", type=int,
        default=int(os.environ.get("BUILD123D_EXEC_TIMEOUT", "60")),
        help="Execution time limit in seconds for user code (default: 60). "
             "Overrides BUILD123D_EXEC_TIMEOUT env var.",
    )
    args = parser.parse_args()

    if args.library and not os.path.isdir(args.library):
        parser.error(f"Library path is not a directory: {args.library}")

    if args.allow_all_imports:
        import build123d_mcp.security as _sec
        _sec.ALLOW_ALL_IMPORTS = True

    global _session, _has_library
    _has_library = bool(args.library)
    _session = WorkerSession(library_path=args.library, allow_all_imports=args.allow_all_imports, exec_timeout=args.exec_timeout)

    mcp.run()


if __name__ == "__main__":
    main()
