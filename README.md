# build123d-mcp

An MCP (Model Context Protocol) server that exposes build123d CAD operations as tools, enabling AI assistants to build, inspect, and iterate on 3D geometry interactively.

## Why

When using an AI to write build123d scripts, the AI writes blind — it cannot see the geometry it produces. This server closes the feedback loop: the AI can create geometry, render views, query dimensions, and catch errors incrementally rather than writing complete scripts and hoping they are correct.

## Tools

- `execute` — run build123d Python code in a persistent session; use `show(shape, name)` to register named parts
- `render_view` — render one or more shapes as PNG; supports assembly compositing, high-quality tessellation, and cross-section clip planes
- `measure` — query bounding box, volume, surface area, minimum wall thickness, or clearance between two named bodies
- `export` — export as STEP, STL, or both in one call; targets a named object or the current shape
- `save_snapshot` / `restore_snapshot` — checkpoint and recover geometric state without re-running prior code
- `reset` — clear the session back to empty state

See [llms.md](llms.md) for full tool reference and usage patterns.

## Requirements

- [uv](https://github.com/astral-sh/uv)
- An MCP-compatible client (Claude Code, Claude Desktop, Cursor, etc.)

All Python dependencies (build123d, pyvista, etc.) are installed automatically by uv.

## Installation

No clone needed. Install directly from PyPI:

```bash
pip install build123d-mcp
```

Or just use `uvx` — it fetches and runs the package in one step with no prior install required (see below).

---

## Adding to MCP clients

The server runs over stdio — the client launches it as a subprocess using `uvx build123d-mcp`.

> **Note on Python version.** All examples below pass `--python 3.13` to `uvx`. The `cadquery-ocp` dependency does not yet ship wheels for Python 3.14+, so on machines where the default Python is 3.14 (recent macOS Homebrew, for example) `uvx build123d-mcp` will fail to resolve. Pinning to 3.13 makes the bare command work everywhere; uv will auto-download a managed Python 3.13 if you don't already have one.

### Claude Code

Add to your project's `.mcp.json` (or `~/.claude/mcp.json` for global use):

```json
{
  "mcpServers": {
    "build123d-mcp": {
      "command": "uvx",
      "args": ["--python", "3.13", "build123d-mcp"]
    }
  }
}
```

Restart Claude Code after editing. The tools appear automatically once connected.

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "build123d-mcp": {
      "command": "uvx",
      "args": ["--python", "3.13", "build123d-mcp"]
    }
  }
}
```

Restart Claude Desktop after saving.

### Cursor

Open **Settings → MCP** and add a new server entry, or edit `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "build123d-mcp": {
      "command": "uvx",
      "args": ["--python", "3.13", "build123d-mcp"]
    }
  }
}
```

### VS Code (GitHub Copilot / Continue)

For **Continue** extension, add to `.continue/config.json`:

```json
{
  "mcpServers": [
    {
      "name": "build123d-mcp",
      "command": "uvx",
      "args": ["--python", "3.13", "build123d-mcp"]
    }
  ]
}
```

For **GitHub Copilot** with MCP support, add to `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "build123d-mcp": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--python", "3.13", "build123d-mcp"]
    }
  }
}
```

---

## System prompt

For best results, paste the contents of [default_prompt.md](default_prompt.md) as a system prompt in your AI client. This tells the assistant to work incrementally, verify geometry after each step, and use the tools in the right order.

---

## Status

Active development (v0.1.0).
