import json

from build123d_mcp.tools.diff import _collect

_SKIP = {"__builtins__", "show"}


def _namespace_summary(namespace: dict) -> dict:
    try:
        from build123d import Shape
    except ImportError:
        Shape = None

    result = {}
    for name, val in namespace.items():
        if name.startswith("_") or name in _SKIP:
            continue
        try:
            typ = type(val).__name__
            if Shape is not None and isinstance(val, Shape):
                try:
                    result[name] = {"type": typ, "volume": round(val.volume, 4)}
                except Exception:
                    result[name] = {"type": typ}
            elif isinstance(val, (list, tuple)):
                result[name] = {"type": typ, "length": len(val)}
            elif isinstance(val, dict):
                result[name] = {"type": "dict", "length": len(val)}
            elif isinstance(val, bool):
                result[name] = {"type": "bool", "value": val}
            elif isinstance(val, (int, float)):
                result[name] = {"type": typ, "value": val}
            elif isinstance(val, str):
                result[name] = {"type": "str", "value": val[:80]}
            elif callable(val):
                result[name] = {"type": "function"}
            else:
                result[name] = {"type": typ}
        except Exception:
            pass
    return result


def session_state(session) -> str:
    state = _collect(session.current_shape, session.objects)
    state["snapshots"] = list(session.snapshots.keys())
    state["variables"] = _namespace_summary(session.namespace)
    return json.dumps(state, indent=2)
