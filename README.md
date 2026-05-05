# build123d-mcp

[![PyPI version](https://img.shields.io/pypi/v/build123d-mcp)](https://pypi.org/project/build123d-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/build123d-mcp)](https://pypi.org/project/build123d-mcp/)
[![CI](https://github.com/pzfreo/build123d-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/pzfreo/build123d-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An MCP (Model Context Protocol) server that exposes build123d CAD operations as tools, enabling AI assistants to build, inspect, and iterate on 3D geometry interactively.

## Why

When using an AI to write build123d scripts, the AI writes blind — it cannot see the geometry it produces. This server closes the feedback loop: the AI can create geometry, render views, query dimensions, and catch errors incrementally rather than writing complete scripts and hoping they are correct.

## Tools

- `execute` — run build123d Python code in a persistent session; use `show(shape, name)` to register named parts
- `render_view` — render one or more shapes as PNG or SVG; supports assembly compositing, high-quality tessellation, and cross-section clip planes
- `measure` — query bounding box, volume, surface area, topology, minimum wall thickness, or clearance between two named bodies
- `export` — export as STEP, STL, or both in one call; targets a named object or the current shape
- `session_state` — full JSON snapshot of active shapes, named objects, and snapshot names
- `health_check` — verify VTK/SVG/STEP/STL dependencies work end-to-end before starting work
- `save_snapshot` / `restore_snapshot` / `diff_snapshot` — checkpoint, recover, and compare geometric state
- `interference` — check intersection volume between two named shapes
- `list_objects` — list all named shapes with geometry stats
- `version` — return the server version
- `reset` — clear the session back to empty state

See [llms.md](llms.md) for full tool reference and usage patterns.

## Requirements

- [uv](https://github.com/astral-sh/uv)
- An MCP-compatible client (Claude Code, Claude Desktop, Cursor, etc.)

All Python dependencies (build123d, vtk, etc.) are installed automatically by uv.

## Installation

No clone needed. Install directly from PyPI:

```bash
pip install build123d-mcp
```

Or just use `uv tool run` — it fetches and runs the package in one step with no prior install required (see below).

---

## Adding to MCP clients

The server runs over stdio — the client launches it as a subprocess using `uv tool run build123d-mcp`.

> **Note on Python version.** All examples below pass `--python 3.12`. VTK and cadquery-ocp do not yet ship wheels for Python 3.13+, so pinning to 3.12 is required. uv will auto-download a managed Python 3.12 if you don't already have one.

### Claude Code

Add to your project's `.mcp.json` (or `~/.claude/mcp.json` for global use):

```json
{
  "mcpServers": {
    "build123d-mcp": {
      "command": "uv",
      "args": ["tool", "run", "--python", "3.12", "build123d-mcp"]
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
      "command": "uv",
      "args": ["tool", "run", "--python", "3.12", "build123d-mcp"]
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
      "command": "uv",
      "args": ["tool", "run", "--python", "3.12", "build123d-mcp"]
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
      "command": "uv",
      "args": ["tool", "run", "--python", "3.12", "build123d-mcp"]
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
      "command": "uv",
      "args": ["tool", "run", "--python", "3.12", "build123d-mcp"]
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
