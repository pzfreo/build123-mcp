import json

from build123d_mcp.tools.diff import _collect


def session_state(session) -> str:
    state = _collect(session.current_shape, session.objects)
    state["snapshots"] = list(session.snapshots.keys())
    return json.dumps(state, indent=2)
