"""inspect_drawing — structured bbox/annotation report for a 2D drawing session."""
import json


def _bbox_dict(shape) -> dict | None:
    try:
        bb = shape.bounding_box()
        return {
            "min_x": round(bb.min.X, 4),
            "min_y": round(bb.min.Y, 4),
            "max_x": round(bb.max.X, 4),
            "max_y": round(bb.max.Y, 4),
            "width": round(bb.size.X, 4),
            "height": round(bb.size.Y, 4),
        }
    except Exception:
        return None


def inspect_drawing(session, objects: str = "") -> str:
    """Return a JSON report with bounding boxes and annotation metadata.

    For each named object in the session, reports its page-space bounding box,
    topology counts, and — if the object was registered via annotate() using a
    build123d_drafting DimResult or LeaderResult — the stored label string,
    measured length, and tip/elbow coordinates.

    Args:
        objects: comma-separated object names to inspect. Empty = all objects.

    Returns:
        JSON string. Top-level keys:
          objects    — dict keyed by name; each entry has bbox, faces, edges,
                       and annotation (null if not recorded via annotate()).
          drawing_bbox — bounding box enclosing all inspected objects.
          lint       — list of structural warnings (same checks as
                       build123d_drafting.lint_drawing).
    """
    if objects:
        names = [n.strip() for n in objects.split(",") if n.strip()]
        missing = [n for n in names if n not in session.objects]
        if missing:
            return json.dumps({"error": f"Unknown object(s): {', '.join(missing)}"})
    else:
        names = list(session.objects.keys())

    if not names:
        return json.dumps({"error": "No objects in session. Execute drawing code first."})

    result_objects: dict = {}
    all_min_x = all_min_y = float("inf")
    all_max_x = all_max_y = float("-inf")

    for name in names:
        shape = session.objects[name]
        bb = _bbox_dict(shape)
        if bb:
            all_min_x = min(all_min_x, bb["min_x"])
            all_min_y = min(all_min_y, bb["min_y"])
            all_max_x = max(all_max_x, bb["max_x"])
            all_max_y = max(all_max_y, bb["max_y"])

        try:
            face_count = len(shape.faces())
        except Exception:
            face_count = None
        try:
            edge_count = len(shape.edges())
        except Exception:
            edge_count = None

        result_objects[name] = {
            "bbox": bb,
            "faces": face_count,
            "edges": edge_count,
            "annotation": session.drawing_annotations.get(name),
        }

    drawing_bbox = None
    if all_min_x != float("inf"):
        drawing_bbox = {
            "min_x": round(all_min_x, 4),
            "min_y": round(all_min_y, 4),
            "max_x": round(all_max_x, 4),
            "max_y": round(all_max_y, 4),
            "width": round(all_max_x - all_min_x, 4),
            "height": round(all_max_y - all_min_y, 4),
        }

    lint = _lint(result_objects, session.drawing_annotations)

    return json.dumps(
        {"objects": result_objects, "drawing_bbox": drawing_bbox, "lint": lint},
        indent=2,
    )


def _lint(objects: dict, annotations: dict) -> list[str]:
    warnings = []
    for name, entry in objects.items():
        ann = annotations.get(name)
        if ann is None:
            continue
        label = ann.get("label_str", "")
        measured = ann.get("measured_length")
        if label and measured and measured > 1e-6:
            import re
            nums = re.findall(r"\d+\.?\d*", label.split("±")[0].split("+")[0].lstrip("ø⌀Rr"))
            if nums:
                try:
                    label_val = float(nums[0])
                    ratio = abs(label_val - measured) / measured
                    if ratio > 0.005:
                        warnings.append(
                            f"'{name}': label '{label}' value {label_val:.3f} differs from "
                            f"measured length {measured:.3f} by {ratio*100:.1f}% — possible axis swap"
                        )
                except ValueError:
                    pass

        bb = entry.get("bbox")
        tip = ann.get("tip")
        elbow = ann.get("elbow")
        text_bb = None
        # For leaders, check elbow vs text bbox (approximated from overall bbox)
        if elbow and bb:
            ex, ey = elbow
            if bb["min_x"] <= ex <= bb["max_x"] and bb["min_y"] <= ey <= bb["max_y"]:
                warnings.append(
                    f"'{name}': leader elbow ({ex:.2f}, {ey:.2f}) may be inside the label bbox"
                )

    return warnings
