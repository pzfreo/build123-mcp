# Changelog

## v0.3.7

### Features

- **`last_error()` tool**: returns structured JSON for the most recent failed `execute()` call — error type, message, line number, and a 5-line code excerpt with an arrow marker at the failing line. Cleared automatically on success.
- **`validate_code()` tool**: static analysis of code before execution — catches syntax errors, blocked imports, missing build123d import, and code that produces no output (no `result` assignment or `show()` call). No execution required.
- **`shape_compare()` tool**: compares two named objects side-by-side — volume, area, topology counts, bounding-box dimensions, and center-point offset delta. Returns structured JSON.
- **`repair_hints()` tool**: takes an error message and returns a targeted hint from an 11-entry pattern library (NoneType, CadQuery syntax, face selection, interference check, missing show(), etc.). Falls back to a generic hint if nothing matches.
- **`measure(query="summary")` mode**: single call returning volume, area, topology, bounding-box dimensions, and center — covers the most common post-execute sanity check in one round trip.
- **`session_state()` namespace variables**: the response now includes a `variables` map summarising all non-shape Python variables in the session namespace (type + value/length).
- **Assembly export via `object_name='*'`**: `export()` with `object_name='*'` bundles all named objects into a single `Compound` and exports it as one STEP or STL file.
- **Dual `render_view` response**: returns both an `ImageContent` (base64 PNG for standard MCP clients) and a `TextContent("[SEND: path]")` marker (for Telegram/file-path consumers) so both client types work without configuration.

### Bug fixes

- **Issue #54 — PNG render fails for complex assemblies**: replaced `Mesher`/Lib3MF pipeline with `shape.tessellate()` + direct VTK PolyData construction. Lib3MF's `IsValid()` check was rejecting valid OCCT boolean shapes; `tessellate()` bypasses the Lib3MF layer entirely. Per-shape try/except means partial renders succeed rather than failing the whole call.
- **Transactional `execute()`**: on any error (exception, timeout, assertion) the session now rolls back `current_shape` and `objects` to their pre-exec state. Failed code can no longer silently advance session geometry.
- **STL export via `tessellate()`**: `export()` for STL now uses `shape.tessellate()` + a binary STL writer instead of `Mesher`, matching the render fix and avoiding the same Lib3MF failures.
- **CLI `--python` version**: `--help` epilog now correctly shows `3.12` instead of `3.13` (no Python 3.13 wheels for vtk/cadquery-ocp).

---

## v0.3.5

### Features

- **`session_state` tool**: returns a structured JSON snapshot of the full session — `current_shape` metrics, all named objects with geometry stats, and snapshot names. Useful for orienting at session start or after a restore.
- **`health_check` tool**: verifies PNG render (VTK), SVG render (HLR), STEP export, and STL export with a trivial shape. Returns per-capability `ok`/`error` status. Run at session start if you suspect a missing dependency.
- **`version` MCP tool**: returns the server version string from inside the session, complementing the existing `--version` CLI flag.
- **`diff_snapshot` JSON mode**: passing `format="json"` returns structured diff output (`{"a": {...}, "b": {...}}`) for programmatic consumption by agents.
- **Outcome test suite**: added 21 usage-focused outcome tests covering the full API surface (all MCP tools exercised end-to-end).
- **README badges**: added PyPI version, Python version, CI status, and MIT license badges.
- **Updated `llms.md`**: full rewrite covering all tools with inputs, outputs, and examples; updated recommended 12-step workflow.

### Bug fixes

- **`show()` now sets `current_shape`**: calling `show(shape, "name")` now also updates `current_shape`, so subsequent `measure()`/`render_view()`/`export()` calls work immediately without an explicit `result` assignment.
- **Failed `execute()` no longer mutates `current_shape`**: if code raises an exception, the previous `current_shape` is preserved. Failed code cannot silently advance session state.
- **`exec_timeout` wired through to worker**: `WorkerSession(exec_timeout=N)` now correctly passes the timeout to the child process (previously silently used the default 30 s).
- **`requires-python` capped at `<3.13`**: `vtk` and `cadquery-ocp` have no wheels for Python 3.13+; the cap now prevents confusing resolver errors.

---

## v0.3.4

### Features

- **Auto-diagnostics after `execute()`**: when `current_shape` changes on a successful run, the response now includes a compact diagnostics line (volume, bounding-box dimensions, face/edge/vertex counts). Agents no longer need a separate `measure()` call just to confirm a new shape was created.
- **Assertion / constraint support**: `AssertionError` raised inside executed code is now surfaced as `"Constraint failed: <message>"` rather than `"Error: AssertionError: ..."`. Scripts can use `assert shape.volume > X, "too small"` as explicit geometry constraints, distinct from accidental bugs.
- **`diff_snapshot` tool**: new tool comparing two named snapshots (or a snapshot vs current session state). Reports volume delta, topology changes (face/edge/vertex counts), bounding-box changes, and added/removed/changed objects — useful for confirming that a fillet, cut, or other operation changed geometry as expected.

---

## v0.3.3

### Bug fixes

- Fix `render_view` crashing with `AttributeError: module 'pyvista' has no attribute 'start_xvfb'` under `uvx build123d-mcp` (#43). pyvista 0.48 removed the helper that the server relied on for headless Linux rendering. Replaced pyvista with direct VTK calls (already pulled in transitively via cadquery-ocp/cadquery-vtk, no install bloat); `_ensure_display()` spawns Xvfb on Linux when needed, mirroring what pyvista's helper used to do.
- Fix `export` and `render_view(save_to=...)` rejecting `/tmp/` paths as path-traversal (#44). Writes are now allowed under the cwd, `tempfile.gettempdir()`, and `/tmp`. Validation runs against the resolved real path, so symlink escapes (e.g. `/tmp/foo` → `/etc/passwd`) are now caught — the previous textual `..` check missed them.

### Features

- Add `format` parameter to `render_view`: `"png"` (default), `"svg"`, or `"both"`. SVG uses build123d's HLR projection — works without a display backend at all. When `format="png"` is requested but the VTK pipeline fails (no DISPLAY, no OSMesa/EGL), the call automatically falls back to SVG so the AI still gets a visual.

### CI

- Add cross-platform matrix: Ubuntu, macOS, and Windows. Linux gets xvfb, Windows gets Mesa3D for offscreen rendering (via `pyvista/setup-headless-display-action`, CI-tooling only — no pyvista runtime dep). Pin Python to 3.12 in CI because vtk 9.3 has no cp313 wheel.

---

## v0.3.2

### Packaging

- Cap `requires-python` at `<3.14` so `uvx build123d-mcp` selects a compatible interpreter instead of trying to build `cadquery-ocp` from source on Python versions where it has no wheels.

---

## v0.3.1

### Features

- Add `--version` flag to the CLI (`uvx build123d-mcp --version`).

### CI

- Fix TestPyPI publish failures: dev builds now use a unique `.devNNN` version suffix, and the patch version is auto-bumped in `pyproject.toml` after each release.

---

## v0.3.0

### Security

- Block subclass-traversal sandbox escapes at AST level: dunder attribute access (`__class__`, `__bases__`, `__subclasses__`, etc.) is now rejected by the AST check, and `getattr`/`vars`/`dir`/`hasattr` are removed from both the AST-level blocklist and the restricted builtins. Closes the most common prompt-injection escape paths without affecting normal build123d usage (operator overloading uses bytecode ops, not explicit dunder access).
- Add AST check to `load_part` for consistency with `execute` — library part code now goes through the same security validation as user-submitted code.

### Architecture

- Replace fork-per-call worker with a persistent subprocess. The worker process now stays alive across calls; the session (namespace, shapes, snapshots) persists in the worker. On timeout the worker is killed and restarted with a fresh session. This eliminates per-call fork overhead and makes timeout behaviour deterministic.
- Use `spawn` context `Pipe()` instead of the default `multiprocessing.Pipe()` for cross-platform reliability.

### Bug fixes

- Fix worker crash paths that returned `str` where `bytes` were expected, causing cascading errors after a crash.
- Fix library name collision when two parts in different subdirectories share the same filename.
- Fix `save_snapshot` / `restore_snapshot` incorrectly listing `current_shape` in the captured geometry when it was `None`.

### Performance

- Reduce `_needs_rescan` syscall overhead with a directory mtime fast path — the library index skips a full directory walk when the mtime is unchanged.

---

## v0.2.0

### Features

- Add part library: `search_library` and `load_part` tools for parametric part reuse.
- Add topology queries to `measure` (`face_count`, `edge_count`, `vertex_count`, `shell_count`, `solid_count`, `compound_count`).
- Add arbitrary camera angles to `render_view` (`azimuth`, `elevation` parameters).
- Add positional clip plane to `render_view` (`clip_at` parameter to specify cut position rather than always bisecting at the mesh centre).

### Fixes

- Update docs for `src` layout, `uvx` invocation, and corrected `show()` argument order.

---

## v0.1.0

Initial release.

- MCP server with `execute`, `render_view`, `export_file`, `measure`, `interference`, `save_snapshot`, `restore_snapshot`, `reset`, `list_objects` tools.
- Persistent session: namespace, `current_shape`, and named objects survive across `execute()` calls.
- Three-layer security model: AST inspection, restricted builtins, execution timeout.
- Multi-object support via `show(shape, name)`.
- Security fixes: path traversal in `export_file`, temp-file race in `render_view`.
