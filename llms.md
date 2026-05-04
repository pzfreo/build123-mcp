# build123d-mcp — LLM Reference

build123d-mcp is an MCP server that wraps the [build123d](https://github.com/gumyr/build123d) Python CAD library. It gives you tools to build 3D geometry incrementally, render views, measure dimensions, export files, snapshot state, inspect session state, and verify dependencies.

## Key concept: persistent session

All tool calls share a single Python namespace. Variables and shapes you create with `execute` persist across subsequent calls. Use this to build geometry step by step, checking your work after each step.

### Multi-object sessions

Use `show(shape, name)` inside `execute` to register named objects. Calling `show()` also sets `current_shape`, so subsequent `measure()`/`export()`/`render_view()` calls work immediately without an explicit `result` assignment. All tools that accept `object_name` operate on a named object instead of the implicit `current_shape`. This is essential for assemblies where you need to inspect, measure, or export individual parts.

```python
frame = Box(60, 40, 8)
show(frame, "frame")

axle = Cylinder(5, 50)
show(axle, "axle")
```

---

## Tools

### `version`
Return the server version string.

**No inputs.**

**Returns:** version string, e.g. `"0.3.5"`

---

### `execute`
Run build123d Python code in the persistent session.

**Input:** `code` (string) — valid Python source

**Returns:** captured stdout/stderr, or `"OK"` if silent, or an error message on exception.

The server auto-detects the current shape. Prefer assigning your final shape to `result`, or use `show(shape, name)` for named objects:
```python
result = Box(10, 20, 30)
```
```python
with BuildPart() as bp:
    Box(10, 20, 30)
    Cylinder(radius=3, height=30, mode=Mode.SUBTRACT)
result = bp.part
```

**On error:** the previous `current_shape` is preserved; the namespace is not wiped. Failed code cannot silently advance session state.

---

### `session_state`
Return a structured JSON snapshot of the full session.

**No inputs.**

**Returns:** JSON with:
- `current_shape` — geometry metrics (volume, faces, edges, vertices, bbox) or `null`
- `objects` — dict of name → metrics for all shapes registered via `show()`
- `snapshots` — list of saved snapshot names

Use this to orient at the start of a session, after a restore, or after a multi-step build to confirm what geometry is active.

```json
{
  "current_shape": {"volume": 1000.0, "faces": 6, "edges": 12, "vertices": 8,
                    "bbox": [10.0, 10.0, 10.0]},
  "objects": {
    "frame": {"volume": 1920.0, "faces": 6, "edges": 12, "vertices": 8,
              "bbox": [60.0, 40.0, 8.0]}
  },
  "snapshots": ["before_fillet", "v2"]
}
```

---

### `health_check`
Verify that render and export dependencies are working end-to-end.

**No inputs.**

**Returns:** JSON with per-capability `ok`/`error` status:
- `render_png` — VTK raster render
- `render_svg` — build123d HLR line projection
- `export_step` — STEP file export
- `export_stl` — STL mesh export
- `ok` — `true` only if all capabilities pass

Run at session start if you suspect a missing dependency (headless display, missing VTK wheels, etc.).

---

### `render_view`
Render one or more shapes and return a file path to the rendered image.

**Inputs:**
- `direction` (string, default `"iso"`) — `top`, `front`, `side`, `iso`
- `objects` (string, default `""`) — comma-separated names from `show()` to render; empty = all registered objects, or `current_shape` if none registered. Optionally suffix a name with `:color` to override the auto-assigned colour, e.g. `"frame:blue,axle:red"`
- `quality` (string, default `"standard"`) — `standard` or `high`; high uses finer tessellation to eliminate artefacts on curved surfaces
- `clip_plane` (string, default `""`) — `x`, `y`, or `z`; clips each mesh at its bounding-box midpoint to expose internal geometry (bores, wall thickness)
- `clip_at` (float, optional) — absolute world coordinate for the clip plane instead of the midpoint
- `azimuth` / `elevation` (float, default `0.0`) — camera rotation in degrees applied after the direction preset
- `format` (string, default `"png"`) — `png`, `svg`, or `both`
- `save_to` (string, default `""`) — optional path to also write the file(s) to disk

**Returns:** `[SEND: /tmp/build123d_xxx.png]` text marker; the file is delivered directly to the client.

Each named object is rendered in a distinct colour. Call this after each significant change to verify geometry visually.

---

### `measure`
Query geometry of a shape.

**Inputs:**
- `query` (string, default `"bounding_box"`) — one of:
  - `bounding_box` — extents, sizes, and centre
  - `volume` — shape volume
  - `area` — total surface area
  - `topology` — face, edge, and vertex counts; fastest way to confirm a boolean succeeded
  - `min_wall_thickness` — shortest wall crossing via ray cast (accurate for prismatic parts)
  - `clearance` — minimum distance between two named bodies (requires `object_name` and `object_name2`)
- `object_name` (string, default `""`) — named object from `show()`; empty = `current_shape`
- `object_name2` (string, default `""`) — second named object; required for `clearance`

**Returns:** JSON

`bounding_box` example:
```json
{
  "xmin": -5.0, "xmax": 5.0,
  "ymin": -10.0, "ymax": 10.0,
  "zmin": -15.0, "zmax": 15.0,
  "xsize": 10.0, "ysize": 20.0, "zsize": 30.0,
  "center": {"x": 0.0, "y": 0.0, "z": 0.0}
}
```

`volume` example: `{"volume": 1000.0}`

`topology` example: `{"faces": 6, "edges": 12, "vertices": 8}`

`clearance` example: `{"clearance": 1.0}`

---

### `export`
Export a shape to a file.

**Inputs:**
- `filename` (string) — target path; extension auto-appended if missing
- `format` (string, default `"step"`) — `"step"`, `"stl"`, or comma-separated `"step,stl"` to write both in one call
- `object_name` (string, default `""`) — named object from `show()`; empty = `current_shape`

**Returns:** path(s) of exported file(s)

STEP preserves exact geometry for downstream CAD tools. STL is for mesh-based workflows (3D printing, slicers, GitHub preview).

---

### `interference`
Check whether two named shapes intersect.

**Inputs:**
- `object_a`, `object_b` (string) — names from `show()`

**Returns:** JSON with `interferes` (bool), `volume` (mm³ of overlap), and `bounds` of the interference region.

---

### `list_objects`
List all named shapes registered via `show()`.

**No inputs.**

**Returns:** JSON array of objects with name, volume, faces, edges, vertices.

---

### `save_snapshot`
Save a named checkpoint of the current geometric state.

**Input:** `name` (string) — snapshot label

**Returns:** confirmation listing what was captured

**What is saved:** `current_shape` and the `show()` object registry.
**What is NOT saved:** the Python variable namespace. After a restore, any intermediate Python variables created after the snapshot are still in scope — but `current_shape` and all `show()` objects revert to the snapshot state.

---

### `restore_snapshot`
Restore geometric state from a previously saved snapshot.

**Input:** `name` (string) — snapshot label

**Returns:** confirmation listing restored geometry, or an error if the name does not exist.

---

### `diff_snapshot`
Compare two snapshots by geometry metrics.

**Inputs:**
- `snapshot_a` (string) — baseline snapshot name
- `snapshot_b` (string, default `""`) — comparison snapshot; defaults to current session state
- `format` (string, default `"text"`) — `"text"` for human-readable output, `"json"` for structured

**Returns:** volume delta, topology changes, and added/removed/changed objects.

JSON format returns `{"a": {"label": ..., "current_shape": ..., "objects": ...}, "b": {...}}`.

---

### `reset`
Clear the session back to empty state, including all snapshots.

**No inputs.**

**Returns:** `"Session reset."`

---

## Recommended workflow

1. `version` — confirm server version
2. `health_check` — verify dependencies (optional; run if first session or suspect issues)
3. `reset` — start clean
4. `execute` — imports and initial geometry; use `show()` for named parts
5. `session_state` — confirm active shapes after any complex step
6. `render_view` — visually verify (try `iso` first; use `quality="high"` for curved surfaces)
7. `measure` — confirm dimensions (`bounding_box`, `volume`, `topology`, `clearance`, etc.)
8. `save_snapshot` — checkpoint before complex or risky operations
9. `execute` — add features; if something breaks, `restore_snapshot`
10. `diff_snapshot` — confirm what changed (use `format="json"` for programmatic checks)
11. Repeat 5–10 until satisfied
12. `export` — write STEP + STL in one call with `format="step,stl"`

---

## build123d quick reference

```python
from build123d import *

# Primitives
Box(length, width, height)
Cylinder(radius, height)
Sphere(radius)
Cone(bottom_radius, top_radius, height)

# Boolean operations (use mode=)
Box(5, 5, 5, mode=Mode.SUBTRACT)   # subtract from current part
Box(5, 5, 5, mode=Mode.INTERSECT)  # intersect with current part

# Location / movement
Pos(x, y, z)
Rot(x_deg, y_deg, z_deg)

# Context manager pattern (recommended)
with BuildPart() as part:
    Box(10, 10, 10)
    with Locations(Pos(0, 0, 5)):
        Cylinder(radius=3, height=10, mode=Mode.SUBTRACT)
result = part.part

# Boolean between separate shapes
combined = part_a + part_b
cut = part_a - part_b
intersection = part_a & part_b
```

All units are millimetres by default.

---

## Common mistakes

- **No shape yet:** `render_view`, `measure`, and `export` all fail if no shape exists. Always `execute` geometry first.
- **Forgetting imports:** the namespace starts empty. Include `from build123d import *` in your first `execute` call.
- **Shape not detected:** if the server doesn't pick up your shape, assign it explicitly to `result` or use `show()`.
- **Dirty session:** unexpected results often mean leftover state. Call `reset` first, or `session_state` to inspect what's active.
- **`clearance` missing second object:** `clearance` requires both `object_name` and `object_name2`.
- **Failed execute advancing state:** it doesn't — failed code preserves the previous `current_shape`.
