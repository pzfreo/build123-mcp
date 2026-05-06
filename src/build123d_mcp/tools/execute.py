import re

from build123d_mcp.tools.repair_hints import _HINTS


def execute_code(session, code: str) -> str:
    result = session.execute(code)
    if result.startswith("Error:") or result.startswith("Constraint failed"):
        matched = [hint for patterns, hint in _HINTS
                   if any(re.search(p, result) for p in patterns)]
        if matched:
            result += "\n\nHint: " + ("\n      ".join(matched))
    return result
