import json


def interference(session, object_a: str, object_b: str) -> str:
    for name in (object_a, object_b):
        if not name or name not in session.objects:
            raise ValueError(f"Unknown object '{name}'. Registered: {list(session.objects.keys())}")

    shape_a = session.objects[object_a]
    shape_b = session.objects[object_b]

    try:
        inter = shape_a & shape_b
        vol = inter.volume
    except Exception:
        return json.dumps({"interferes": False, "volume": 0.0}, indent=2)

    if vol < 1e-6:
        return json.dumps({"interferes": False, "volume": 0.0}, indent=2)

    bb = inter.bounding_box()
    return json.dumps({
        "interferes": True,
        "volume": vol,
        "bounds": {
            "xmin": bb.min.X, "xmax": bb.max.X,
            "ymin": bb.min.Y, "ymax": bb.max.Y,
            "zmin": bb.min.Z, "zmax": bb.max.Z,
        },
    }, indent=2)
