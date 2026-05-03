# Changelog

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
