# build123-mcp — LLM Reference

build123-mcp is an MCP server that wraps the [build123d](https://github.com/gumyr/build123d) Python CAD library. It gives you five tools to build 3D geometry incrementally, render views, measure dimensions, export files, and reset state.

## Key concept: persistent session

All tool calls share a single Python namespace. Variables and shapes you create with `execute` persist across subsequent calls. Use this to build geometry step by step, checking your work after each step.

---

## Tools

### `execute`
Run build123d Python code in the persistent session.

**Input:** `code` (string) — valid Python source

**Returns:** captured stdout/stderr, or `"OK"` if silent, or an error message on exception.

The server auto-detects the current shape. Prefer assigning your final shape to a variable named `result`:
```python
result = Box(10, 20, 30)
```
Or use the context manager pattern:
```python
with BuildPart() as bp:
    Box(10, 20, 30)
    Cylinder(radius=3, height=30, mode=Mode.SUBTRACT)
result = bp.part
```

**On error:** the previous shape is preserved; the namespace is not wiped.

---

### `render_view`
Render the current model and return a PNG image.

**Input:** `direction` (string, default `"iso"`) — one of `top`, `front`, `side`, `iso`

**Returns:** PNG image

Call this after each significant change to verify geometry visually. Use all four directions when spatial orientation matters.

---

### `measure`
Query geometry of the current model.

**Input:** `query` (string, default `"bounding_box"`)

**Returns:** JSON with bounding box extents and centre:
```json
{
  "xmin": -5.0, "xmax": 5.0,
  "ymin": -10.0, "ymax": 10.0,
  "zmin": -15.0, "zmax": 15.0,
  "xsize": 10.0, "ysize": 20.0, "zsize": 30.0,
  "center": {"x": 0.0, "y": 0.0, "z": 0.0}
}
```

Use this to verify dimensions are correct before exporting.

---

### `export`
Export the current model to a file.

**Inputs:**
- `filename` (string) — target path; extension auto-appended if missing
- `format` (string, default `"step"`) — `"step"` or `"stl"`

**Returns:** `"Exported to /path/to/file.step"`

STEP is preferred for most CAD uses (preserves exact geometry). STL is for mesh-based workflows (3D printing, etc.).

---

### `reset`
Clear the session back to empty state.

**No inputs.**

**Returns:** `"Session reset."`

Call this before starting a new model to ensure a clean slate.

---

## Recommended workflow

1. `reset` — start clean
2. `execute` — create initial geometry
3. `render_view` — visually verify
4. `measure` — confirm dimensions
5. `execute` — refine/add features
6. Repeat 3–5 until satisfied
7. `export` — write the file

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
Pos(x, y, z)           # translate
Rot(x_deg, y_deg, z_deg)   # rotate

# Context manager pattern (recommended)
with BuildPart() as part:
    Box(10, 10, 10)
    with Locations(Pos(0, 0, 5)):
        Cylinder(radius=3, height=10, mode=Mode.SUBTRACT)
result = part.part

# Compound / boolean between separate shapes
combined = part_a + part_b   # union
cut = part_a - part_b        # difference
intersection = part_a & part_b
```

All units are millimetres by default.

---

## Common mistakes

- **No shape yet:** `render_view`, `measure`, and `export` all fail if no shape exists. Always `execute` geometry first.
- **Forgetting imports:** the namespace starts empty. Include `from build123d import *` in your first `execute` call.
- **Shape not detected:** if the server doesn't pick up your shape, assign it explicitly to `result`.
- **Dirty session:** unexpected results often mean leftover state from a previous run. Call `reset` first.
