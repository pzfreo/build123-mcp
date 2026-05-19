"""view_axes — analytic world→page axis mapping for a project_to_viewport call."""
import json


def view_axes(
    viewport_origin: tuple,
    viewport_up: tuple = (0.0, 1.0, 0.0),
    look_at: tuple = (0.0, 0.0, 0.0),
) -> str:
    """Return JSON {world_X, world_Y, world_Z: [page_axis, sign]}.

    Wraps build123d_drafting.view_axes. Useful BEFORE calling project_to_viewport
    so you know which world axis ends up on which page axis (and its sign) —
    catches bottom-view / side-view axis swaps before they show up in the render.
    """
    from build123d_drafting import view_axes as _va

    mapping = _va(viewport_origin, viewport_up, look_at)
    return json.dumps(
        {k: [v[0], round(v[1], 6)] for k, v in mapping.items()},
        indent=2,
    )
