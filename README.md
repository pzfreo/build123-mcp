# build123-mcp

An MCP (Model Context Protocol) server that exposes build123d CAD operations as tools, enabling AI assistants to build, inspect, and iterate on 3D geometry interactively.

## Why

When using an AI to write build123d scripts, the AI writes blind — it cannot see the geometry it produces. This server closes the feedback loop: the AI can create geometry, render views, query dimensions, and catch errors incrementally rather than writing complete scripts and hoping they are correct.

## Tools (v1)

- `execute` — run build123d Python code and return any errors
- `render_view` — render the current model from a given direction, returns an image
- `export` — export the current model as STEP or STL
- `measure` — query bounding box and face distances on the current model

## Requirements

- Python 3.10+
- build123d
- An MCP-compatible client (Claude Code, Claude Desktop, etc.)

## Status

Early development.
