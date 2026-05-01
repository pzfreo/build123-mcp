# build123-mcp — LLM Reference

build123-mcp is an MCP server that wraps the [build123d](https://github.com/gumyr/build123d) Python CAD library. It gives you seven tools to build 3D geometry incrementally, render views, measure dimensions, export files, snapshot state, and reset.

## Key concept: persistent session

All tool calls share a single Python namespace. Variables and shapes you create with `execute` persist across subsequent calls. Use this to build geometry step by step, checking your work after each step.

### Multi-object sessions

Use `show(name, shape)` inside `execute` to register named objects. All tools that accept `object_name` operate on a named object instead of the implicit `current_shape`. This is essential for assemblies where you need to inspect, measure, or export individual parts.

```python
frame = Box(60, 40, 8)
show("frame", frame)

axle = Cylinder(5, 50)
show("axle", axle)
```

---

## Tools

### `execute`
Run build123d Python code in the persistent session.

**Input:** `code` (string) — valid Python source

**Returns:** captured stdout/stderr, or `"OK"` if silent, or an error message on exception.

The server auto-detects the current shape. Prefer assigning your final shape to `result`, or use `show(name, shape)` for named objects:
```python
result = Box(10, 20, 30)
```
```python
with BuildPart() as bp:
    Box(10, 20, 30)
    Cylinder(radius=3, height=30, mode=Mode.SUBTRACT)
result = bp.part
```

**On error:** the previous shape is preserved; the namespace is not wiped.

---

### `render_view`
Render one or more shapes and return a PNG image.

**Inputs:**
- `direction` (string, default `"iso"`) — `top`, `front`, `side`, `iso`
- `objects` (string, default `""`) — comma-separated names from `show()` to render; empty = all registered objects, or `current_shape` if none registered
- `quality` (string, default `"standard"`) — `standard` or `high`; high uses finer tessellation to eliminate artefacts on curved surfaces
- `clip_plane` (string, default `""`) — `x`, `y`, or `z`; clips each mesh at its bounding-box midpoint to expose internal geometry (bores, wall thickness)

**Returns:** PNG image

Each named object is rendered in a distinct colour. Call this after each significant change to verify geometry visually.

---

### `measure`
Query geometry of a shape.

**Inputs:**
- `query` (string, default `"bounding_box"`) — one of:
  - `bounding_box` — extents, sizes, and centre
  - `volume` — shape volume
  - `area` — total surface area
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

### `save_snapshot`
Save a named checkpoint of the current geometric state.

**Input:** `name` (string) — snapshot label

**Returns:** confirmation listing what was captured

**What is saved:** `current_shape` and the `show()` object registry.
**What is NOT saved:** the Python variable namespace. After a restore, any intermediate Python variables (e.g. `box`, `cyl`) created after the snapshot are still in scope — but `current_shape` and all `show()` objects revert to the snapshot state.

Call this before risky experiments so you can restore known-good geometry without re-running all prior `execute()` calls.

---

### `restore_snapshot`
Restore geometric state from a previously saved snapshot.

**Input:** `name` (string) — snapshot label

**Returns:** confirmation listing restored geometry, or an error if the name does not exist.

**What is restored:** `current_shape` and the `show()` object registry.
**What is NOT restored:** the Python variable namespace remains as-is. If you need variables to match the snapshot, re-run the relevant `execute()` calls after restoring.

---

### `reset`
Clear the session back to empty state, including all snapshots.

**No inputs.**

**Returns:** `"Session reset."`

Call this before starting a new model to ensure a clean slate.

---

## Recommended workflow

1. `reset` — start clean
2. `execute` — imports and initial geometry; use `show()` for named parts
3. `render_view` — visually verify (try `iso` first; use `quality="high"` for curved surfaces)
4. `measure` — confirm dimensions (`bounding_box`, `volume`, `clearance`, etc.)
5. `save_snapshot` — checkpoint before complex or risky operations
6. `execute` — add features; if something breaks, `restore_snapshot`
7. Repeat 3–6 until satisfied
8. `export` — write STEP + STL in one call with `format="step,stl"`

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
- **Dirty session:** unexpected results often mean leftover state. Call `reset` first.
- **`clearance` missing second object:** `clearance` requires both `object_name` and `object_name2`.
- **Snapshot restores geometry only:** after `restore_snapshot`, Python variables are not rewound. Re-run `execute()` calls if variables need to match the snapshot.
