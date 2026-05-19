"""lint_drawing — standalone structural checks on a 2D drawing.

Two modes:

  1. Session mode: scans session.objects + session.drawing_annotations and runs
     the same checks inspect_drawing reports inline (label-vs-measured-length
     divergence, leader elbow inside the label bbox).

  2. SVG mode: scans an SVG file on disk for layer-level pathologies that only
     show up at export time — most importantly text on a layer with no fill
     (renders as illegible thick outlines).

The structured violation list is JSON so the LLM can iterate on a drawing
without rendering it.
"""
import json
import re
import xml.etree.ElementTree as ET


def _lint_session(session) -> list[dict]:
    """Run structural lint on session-registered annotations.

    Mirrors the inline checks in inspect_drawing but returns structured dicts
    instead of strings so callers can filter/sort programmatically.
    """
    violations: list[dict] = []
    objects = session.objects
    annotations = session.drawing_annotations

    for name in objects:
        ann = annotations.get(name)
        if ann is None:
            continue

        label = ann.get("label_str", "")
        measured = ann.get("measured_length")
        if label and measured and measured > 1e-6:
            nums = re.findall(
                r"\d+\.?\d*",
                label.split("±")[0].split("+")[0].lstrip("ø⌀Rr"),
            )
            if nums:
                try:
                    label_val = float(nums[0])
                    ratio = abs(label_val - measured) / measured
                    if ratio > 0.005:
                        violations.append({
                            "severity": "error",
                            "check": "label_vs_measured",
                            "object": name,
                            "message": (
                                f"label '{label}' value {label_val:.3f} differs from "
                                f"measured length {measured:.3f} by {ratio*100:.1f}% "
                                f"— possible axis swap"
                            ),
                        })
                except ValueError:
                    pass

        elbow = ann.get("elbow")
        if elbow:
            try:
                bb = objects[name].bounding_box()
                if (bb.min.X <= elbow[0] <= bb.max.X
                        and bb.min.Y <= elbow[1] <= bb.max.Y):
                    violations.append({
                        "severity": "warning",
                        "check": "leader_elbow_in_label",
                        "object": name,
                        "message": (
                            f"leader elbow ({elbow[0]:.2f}, {elbow[1]:.2f}) "
                            f"may be inside the label bbox"
                        ),
                    })
            except Exception:
                pass

    return violations


_SVG_NS = "{http://www.w3.org/2000/svg}"


def _lint_svg(svg_path: str) -> list[dict]:
    """Layer-level checks on an SVG file.

    Catches:
    - text elements on a group with fill='none' or no fill attribute, which
      renders glyphs as outlines rather than filled shapes (the single most
      common SVG drafting bug).
    """
    violations: list[dict] = []
    try:
        tree = ET.parse(svg_path)
    except (FileNotFoundError, ET.ParseError) as e:
        return [{"severity": "error", "check": "svg_parse",
                 "object": svg_path, "message": str(e)}]

    root = tree.getroot()

    def walk(elem, inherited_fill):
        fill = elem.get("fill", inherited_fill)
        # Also check style="fill:..."
        style = elem.get("style", "")
        m = re.search(r"fill:\s*([^;]+)", style)
        if m:
            fill = m.group(1).strip()

        tag = elem.tag.replace(_SVG_NS, "")
        if tag == "text":
            if fill in (None, "none", ""):
                layer_id = elem.get("id") or "?"
                violations.append({
                    "severity": "error",
                    "check": "text_no_fill",
                    "object": layer_id,
                    "message": (
                        f"<text> element id='{layer_id}' has fill='{fill}'; "
                        f"glyphs will render as thick outlines, not filled. "
                        f"Set fill_color on the SVG layer when exporting."
                    ),
                })

        for child in elem:
            walk(child, fill)

    walk(root, None)
    return violations


def lint_drawing(session, svg_path: str = "") -> str:
    """Run structural drawing checks; return JSON with a `violations` list.

    Args:
        svg_path: if given, lint the SVG file at this path (mode 2). Otherwise
            lint the live session (mode 1).

    Returns:
        JSON: {"violations": [{severity, check, object, message}, ...]}
    """
    if svg_path:
        violations = _lint_svg(svg_path)
    else:
        violations = _lint_session(session)
    return json.dumps({"violations": violations}, indent=2)
