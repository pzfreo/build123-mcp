import json


def last_error(session) -> str:
    if session.last_error_detail is None:
        return json.dumps({"error": None}, indent=2)
    return json.dumps(session.last_error_detail, indent=2)
