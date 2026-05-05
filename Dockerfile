FROM python:3.12-slim

# Runtime deps for headless VTK rendering on Linux
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    libgl1 \
    libglu1-mesa \
    libx11-6 \
    libxrender1 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Use system Python; install script into PATH
ENV UV_PYTHON_PREFERENCE=only-system \
    UV_TOOL_BIN_DIR=/usr/local/bin

RUN uv tool install build123d-mcp

ENTRYPOINT ["build123d-mcp"]
