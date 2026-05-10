# Changelog

## v0.3.15

### Improvements

- **`execute()` output gains shape deltas and silent-failure warnings** (#81): the diagnostic appended after every `execute()` now shows volume/topology deltas relative to the previous shape (e.g. `volume: 437.2 (-62.8, -12.6%) mm³  |  ... 7f (+1) 15e (+3) 10v (+2)`) and flags two silent failure modes the LLM otherwise sailed past unnoticed — boolean no-ops (cuts that didn't intersect, leaving topology bit-identical) and degenerate results (volume collapsed to ≈ 0). No new MCP tool, no LLM behaviour change required; warnings arrive in the response text the LLM already reads.

### Release process

- **Auto-publish to MCP registry on release** (#82): a new `publish-mcp-registry` job in `publish.yml` mirrors the PyPI publish path. On every `gh release create vX.Y.Z`, after PyPI succeeds, the job authenticates via GitHub OIDC (no stored secret), rewrites `server.json`'s version fields from the release tag, and pushes to `registry.modelcontextprotocol.io`. From this release onward the registry stays in sync with PyPI automatically.

---

## v0.3.14

This release is "more build123d native" — every change closes a gap where the server was a generic Python sandbox rather than a build123d-aware tool. Five merged PRs:

### Features

- **`render_view` labels** (#73): two new optional parameters. `label_objects=True` labels each named object from `show()` at its centroid in the PNG. `highlights=[{"object", "type", "index", "label"}, ...]` labels specific faces, edges, or vertices by index — useful for confirming "edge 5 is the one I want to fillet" before committing to an operation. Labels render on a depth-cleared overlay layer so they stay legible even at a solid's interior centroid. SVG output is unlabelled (a `label_warnings` entry surfaces this).
- **`build123d://selectors` MCP resource** (#76): a task-indexed selector cookbook, separate from `quickref`'s API-shaped reference. 15 runnable examples covering the drill-down idiom (parent → child topology), cardinal selection, geom-type filters, parallel/perpendicular orientation, numeric properties, `Select.LAST` in builder context, fillet detection (`is_circular_convex`/`is_circular_concave`), and more — plus an operator translation card (`>`, `<`, `|`, `>>`, `<<`, `@`) and a pitfalls section.
- **Compound-aware STEP export** (#77): single-object exports carry `object_name` as the body label; `*` exports produce a `Compound` labelled `assembly` with each child labelled by its `show()` name. Downstream CAD tools (FreeCAD, Fusion) now see structured assemblies with named bodies instead of "Body 1, Body 2, …".

### Documentation (LLM behaviour-shaping)

- **Joints guidance** (#75): `quickref` gains a runnable `RigidJoint` example plus a reference card listing all joint types (`RigidJoint`, `RevoluteJoint`, `LinearJoint`, `CylindricalJoint`, `BallJoint`). `workflow_hints()`, `start-cad-session`, and `llms.md` all nudge toward joints for assemblies with mechanical relationships, instead of raw `.move()`/`Location()`. Docs-only — no new MCP tool — keeps LLM-generated code idiomatic and portable outside the MCP.
- **Five more native idioms in `quickref`** (#78): pattern-placement utilities (`GridLocations`, `PolarLocations`, `Locations` with task-indexed naming), the `@` and `%` operators on edges for chaining curves without coordinate duplication, the broader operations set (`sweep`, `loft`, `mirror`, `offset`, `thicken`), and `Mode.PRIVATE` for helper geometry that doesn't join the part. The two top-level patterns are renamed using build123d's own terminology — algebra mode and builder mode. Each example was verified end-to-end before being added to the `Section` dataclass.

### Release process

- **build123d version is now explicit** (#79): `pyproject.toml` soft-pins build123d as `>=0.10,<0.11` (build123d is pre-1.0, so minor bumps may break the API). The `build123d://quickref` and `build123d://selectors` resources prepend a runtime banner showing the actually-installed version via `importlib.metadata.version`, so the docs are self-describing about their compatibility window — if a user overrides the pin, the banner reflects what they really have.

---

## v0.3.13

### Features

- **`build123d://quickref` MCP resource**: exposes a plain-text quick reference for the build123d API so LLM clients can read accurate syntax before calling `execute()`. Every runnable example is tested automatically to ensure the quickref stays accurate as the codebase evolves.
- **`start-cad-session` prompt**: primes a design session with the task description plus step-by-step workflow reminders.
- **`build123d://session` MCP resource**: read-only JSON resource exposing live session state — `current_shape` diagnostics, named objects, snapshots, and user-defined variables. Clients can read session state without spending a tool-call round-trip on `session_state()`.
- **`build123d://bd_warehouse` MCP resource**: introspects the installed `bd_warehouse` package and returns a plain-text catalogue of all available parametric components (bearings, fasteners, flanges, gears, OpenBuilds parts, pipes, sprockets, threads). Each entry shows the class name, description, constructor signature, and for size-standardised classes the available types and sizes.
- **`render_view` labels**: two new optional parameters. `label_objects=True` labels each named object from `show()` at its centroid in the PNG. `highlights=[{"object", "type", "index", "label"}, ...]` labels specific faces, edges, or vertices by index — useful for confirming "edge 5 is the one I want to fillet" before committing to an operation. Labels render on a depth-cleared overlay layer so they stay legible even when sitting at a solid's interior centroid. SVG output is unlabelled (a `label_warnings` entry surfaces this).

### Improvements

- **Default exec timeout raised to 120 s** (was 60 s) — allows more complex boolean operations to complete inside the MCP without needing to fall back to a plain Python script.
- **`dir()` restored** — available again as a builtin inside `execute()`. Dunder attribute access remains blocked at the AST level, so the sandbox is unaffected.
- **`inspect` allowlisted** — `import inspect` now works inside `execute()`. `inspect.signature()`, `inspect.getdoc()`, and `inspect.getmembers()` enable API discovery without trial-and-error round trips.
- **STL render quality improved** — `vtkPolyDataNormals` (with `ConsistencyOn` and `AutoOrientNormalsOn`) is now applied before the VTK mapper. Imported STL shells shade correctly instead of rendering with incorrect face orientation.
- **`import_cad_file` docstring clarified** — documents that `render_view` works after import, that STL imports produce a shell (volume = 0), and that rendering by object name avoids Z-fighting when the original built shape is also in session.
- **Timeout error improved** — when `execute()` times out the error message now explains that all session state has been lost (worker restarted) and recommends the probe-in-MCP / build-in-script / import-and-verify workflow.
- **`bd_warehouse` resource expanded** — new preamble documents the correct size string format (`"M6-1"` not `"M6-1.0"`), a probe pattern (`ClassName.sizes("type")`), and working code examples for `CounterSinkHole`, `TapHole`, `ClearanceHole`, and `CounterBoreHole`.
- **`workflow_hints()` expanded** — new items cover bd_warehouse fastener probing, the complex-build workflow (probe → script → import → verify), import→render pattern, and Z-fighting guidance.
- **README expanded** — "Recommended workflow" and "bd_warehouse fasteners" sections added.

### Release process

- **`.dev0` version convention**: between releases, `pyproject.toml` carries a `.dev0` suffix (e.g. `0.3.14.dev0`) so it self-documents that the working version has not yet been published. The publish workflow strips the suffix on real release and TestPyPI builds replace `.dev0` with `.dev<run_number>`. Anyone — human or AI — reading `pyproject.toml` can immediately tell which version is published vs in development.
- **`CLAUDE.md` documents release process**: only `gh release create vX.Y.Z` cuts a release; never edit `pyproject.toml` or push tags manually.

---

## v0.3.12

### Features

- **`measure()` unified response**: returns a single comprehensive JSON — volume, area, topology (face/edge/vertex counts), bounding box with center, volumetric center of mass, 6-component inertia tensor (Ixx/Iyy/Izz/Ixy/Ixz/Iyz), and face-type inventory classifying every face as Plane/Cylinder/Cone/Sphere/Torus/BSpline with type-specific params (cylinder diameter/axis, cone semi-angle, sphere radius, torus radii). Replaces the old query-dispatch API.
- **`clearance(object_a, object_b)` tool**: returns the minimum distance (mm) between two named shapes.
- **`cross_sections(object_name, axis, num_slices)` tool**: cross-sectional area at evenly spaced planes along X/Y/Z — useful for detecting internal voids, wall-thickness variation, and verifying profile against a reference.
- **`import_cad_file(path, name)` tool**: loads a STEP (.step/.stp) or STL (.stl) file as a named object in the session. Supports multi-body STEP files. Use with `shape_compare()` to verify a procedural build against a reference.
- **`named_face(shape, name)` session built-in**: returns a face by semantic name (`top`, `bottom`, `front`, `back`, `left`, `right`) based on axis sorting. Available in every `execute()` call without import.
- **OCP sub-module imports in user code**: geometric OCP modules (`OCP.gp`, `OCP.BRepGProp`, `OCP.TopExp`, `OCP.BRepAlgoAPI`, etc.) are now allowed via an explicit allowlist. File I/O modules (`OCP.STEPControl`, `OCP.IGESControl`, `OCP.OSD`) remain blocked.
- **`execute()` inline repair hints**: on error, matched hints from the repair library are appended directly to the error response — no separate `repair_hints()` call needed.

### Removed

- **`fingerprint` tool**: data is now part of the `measure()` response; `cross_sections` is a separate tool.
- **`list_objects` tool**: `session_state()` is a strict superset.
- **`validate_code` tool**: `execute()` already returns syntax and security errors inline; the standalone pre-check added friction without benefit.

---

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
