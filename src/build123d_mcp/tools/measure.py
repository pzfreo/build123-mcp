import json


def _resolve_shape(session, object_name: str):
    if object_name:
        if object_name not in session.objects:
            raise ValueError(f"Unknown object '{object_name}'. Registered: {list(session.objects.keys())}")
        return session.objects[object_name]
    if session.current_shape is None:
        raise ValueError("No shape in session. Execute code to create geometry first.")
    return session.current_shape


def _min_wall_thickness(shape) -> float:
    """Ray-cast from each face center inward; return shortest wall crossing."""
    from build123d import Axis
    min_t = float("inf")
    for face in shape.faces():
        center = face.center_location.position
        normal = face.normal_at()
        inward = Axis(center, normal * -1)
        try:
            hits = shape.find_intersection_points(inward)
        except Exception:
            continue
        for pt, _ in hits:
            dist = (pt - center).length
            if dist > 1e-3:
                min_t = min(min_t, dist)
                break
    return min_t


def measure(session, query: str = "bounding_box", object_name: str = "", object_name2: str = "") -> str:
    query = query.lower()

    if query == "clearance":
        s1 = _resolve_shape(session, object_name)
        if not object_name2:
            raise ValueError("clearance requires object_name2.")
        if object_name2 not in session.objects:
            raise ValueError(f"Unknown object '{object_name2}'. Registered: {list(session.objects.keys())}")
        s2 = session.objects[object_name2]
        return json.dumps({"clearance": s1.distance_to(s2)}, indent=2)

    shape = _resolve_shape(session, object_name)

    if query == "bounding_box":
        bb = shape.bounding_box()
        result = {
            "xmin": bb.min.X, "xmax": bb.max.X,
            "ymin": bb.min.Y, "ymax": bb.max.Y,
            "zmin": bb.min.Z, "zmax": bb.max.Z,
            "xsize": bb.size.X, "ysize": bb.size.Y, "zsize": bb.size.Z,
            "center": {
                "x": (bb.min.X + bb.max.X) / 2,
                "y": (bb.min.Y + bb.max.Y) / 2,
                "z": (bb.min.Z + bb.max.Z) / 2,
            },
        }
        return json.dumps(result, indent=2)

    if query == "volume":
        return json.dumps({"volume": shape.volume}, indent=2)

    if query == "area":
        return json.dumps({"area": shape.area}, indent=2)

    if query == "min_wall_thickness":
        t = _min_wall_thickness(shape)
        return json.dumps({"min_wall_thickness": t}, indent=2)

    raise ValueError(f"Unknown query '{query}'. Use: bounding_box, volume, area, min_wall_thickness, clearance")
