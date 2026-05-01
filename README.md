# build123d-mcp

An MCP (Model Context Protocol) server that exposes build123d CAD operations as tools, enabling AI assistants to build, inspect, and iterate on 3D geometry interactively.

## Why

When using an AI to write build123d scripts, the AI writes blind — it cannot see the geometry it produces. This server closes the feedback loop: the AI can create geometry, render views, query dimensions, and catch errors incrementally rather than writing complete scripts and hoping they are correct.

## Tools

- `execute` — run build123d Python code in a persistent session; use `show(name, shape)` to register named parts
- `render_view` — render one or more shapes as PNG; supports assembly compositing, high-quality tessellation, and cross-section clip planes
- `measure` — query bounding box, volume, surface area, minimum wall thickness, or clearance between two named bodies
- `export` — export as STEP, STL, or both in one call; targets a named object or the current shape
- `save_snapshot` / `restore_snapshot` — checkpoint and recover geometric state without re-running prior code
- `reset` — clear the session back to empty state

See [llms.md](llms.md) for full tool reference and usage patterns.

## Requirements

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- build123d, pyvista (installed automatically via uv)
- An MCP-compatible client (Claude Code, Claude Desktop, Cursor, etc.)

## Installation

Clone the repository:

```bash
git clone https://github.com/pzfreo/build123d-mcp
cd build123d-mcp
```

Install dependencies with uv:

```bash
uv sync
```

Or with pip:

```bash
pip install -e .
```

---

## Adding to MCP clients

The server runs over stdio — the client launches it as a subprocess. The command in all cases is:

```
uv run python server.py
```

run from the `build123d-mcp` directory.

### Claude Code

Add to your project's `.mcp.json` (or `~/.claude/mcp.json` for global use):

```json
{
  "mcpServers": {
    "build123d-mcp": {
      "command": "uv",
      "args": ["run", "python", "server.py"],
      "cwd": "/path/to/build123d-mcp"
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
      "args": ["run", "python", "server.py"],
      "cwd": "/path/to/build123d-mcp"
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
      "args": ["run", "python", "server.py"],
      "cwd": "/path/to/build123d-mcp"
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
      "args": ["run", "python", "server.py"],
      "cwd": "/path/to/build123d-mcp"
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
      "args": ["run", "python", "server.py"],
      "cwd": "/path/to/build123d-mcp"
    }
  }
}
```

---

## System prompt

For best results, paste the contents of [default_prompt.md](default_prompt.md) as a system prompt in your AI client. This tells the assistant to work incrementally, verify geometry after each step, and use the tools in the right order.

---

## Status

Active development (v0.2.0).
