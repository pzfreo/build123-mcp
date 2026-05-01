# build123d-mcp

## Running tests

Always use `uv run pytest` — it auto-installs all dependencies from `pyproject.toml` before running.

```
uv run pytest tests/
```

The target is 100% passing. There are no accepted pre-existing failures — if tests are failing, fix them.

## Running the server

```
uv run python server.py
```

Communicates over stdio (FastMCP). When configuring an MCP client, set `cwd` to the project root.

## Project structure

```
server.py          — FastMCP entry point; registers all MCP tools; holds module-level _session singleton
session.py         — Persistent state: namespace, current_shape, objects dict, snapshots
security.py        — Three-layer defence: AST check → restricted builtins → exec timeout
tools/execute.py   — Thin wrapper delegating to session.execute()
tools/render.py    — pyvista-based PNG rendering; headless (xvfb) if no DISPLAY
tools/measure.py   — Geometry queries returning JSON (bounding_box, volume, area, wall thickness, clearance)
tools/export.py    — STEP/STL export; path traversal blocked
tools/interference.py — Boolean intersection check between two named shapes
```

## Adding a new tool

1. Create `tools/<name>.py` with a function `def <name>(session, ...) -> str`.
2. Import and register in `server.py`:
   ```python
   from tools.<name> import <name> as <name>_fn

   @mcp.tool()
   def <name>(...) -> str:
       """Docstring shown to MCP clients."""
       return <name>_fn(_session, ...)
   ```

## Session model

- **Namespace persists** across `execute()` calls — imports and variables accumulate.
- **`current_shape`** is auto-detected after each execute: prefers a variable named `result`, then any new `BuildPart` or `Shape`.
- **`objects` dict** holds named shapes registered via `show(shape, name=None)`. Name defaults to `"shape"` if omitted.
- **Snapshots** save `current_shape` + `objects` only — the Python namespace is NOT restored on `restore_snapshot()`.
- **`reset()`** clears everything: namespace, shapes, objects, snapshots.

## Security model

Three layers, all must pass before user code runs:

1. **AST check** — blocks imports of anything not in the allowlist (`build123d`, `math`, `numpy`, `typing`, `collections`, `itertools`, `functools`, `copy`) and bare calls to `eval`, `exec`, `open`, etc.
2. **Restricted builtins** — exec namespace gets a filtered `__builtins__` dict; `open`, `eval`, `exec`, `compile` removed; `__import__` wrapped to enforce the same allowlist at runtime.
3. **Exec timeout** — default 30 s wall-clock via daemon thread. After timeout, the thread continues in background and the namespace may be dirty; callers should `reset()` or `restore_snapshot()`.

Known limits: memory exhaustion is not bounded; Python introspection chains can escape the sandbox.

## Gotchas

- After a timeout the namespace may be partially modified — don't trust state without a reset.
- `restore_snapshot()` restores geometry only; Python variables set after the snapshot remain in scope.
- `show()` stores shapes by reference; mutating the shape object after calling `show()` will affect the stored object.
- Clip plane in `render_view` slices at the mesh's own bounding-box midpoint, not world origin.
- Interference uses a 1 × 10⁻⁶ mm³ volume threshold to ignore floating-point noise.
