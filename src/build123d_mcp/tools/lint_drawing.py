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


def _lint_annotations(annotations: dict, objects: dict | None = None) -> list[dict]:
    """Run label-vs-measured and leader checks against an annotations dict.

    Args:
        annotations: mapping of name → annotation metadata dict.
        objects: optional session.objects for leader elbow bbox check (unavailable
            in SVG mode — the geometry isn't loaded).
    """
    violations: list[dict] = []

    for name, ann in annotations.items():
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
        if elbow and objects is not None and name in objects:
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


def _lint_session(session) -> list[dict]:
    """Run structural lint on session-registered annotations."""
    return _lint_annotations(session.drawing_annotations, objects=session.objects)


_SVG_NS = "{http://www.w3.org/2000/svg}"


def _lint_svg(svg_path: str) -> list[dict]:
    """Layer-level checks on an SVG file, plus sidecar annotation checks.

    Catches:
    - text elements on a group with fill='none' or no fill attribute, which
      renders glyphs as outlines rather than filled shapes.
    - label-vs-measured divergence from the .dims.json sidecar (written by
      save_drawing_annotations()) — same axis-swap check as session mode.
    """
    import os, json as _json
    violations: list[dict] = []
    try:
        tree = ET.parse(svg_path)
    except (FileNotFoundError, ET.ParseError) as e:
        return [{"severity": "error", "check": "svg_parse",
                 "object": svg_path, "message": str(e)}]

    root = tree.getroot()

    def walk(elem, inherited_fill):
        fill = elem.get("fill", inherited_fill)
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

    # Sidecar annotation checks (label-vs-measured, leader-strikethrough).
    sidecar = os.path.splitext(svg_path)[0] + ".dims.json"
    if os.path.isfile(sidecar):
        try:
            with open(sidecar) as f:
                annotations = _json.load(f)
            violations.extend(_lint_annotations(annotations, objects=None))
        except Exception as exc:
            violations.append({
                "severity": "warning",
                "check": "sidecar_read",
                "object": sidecar,
                "message": f"Could not read sidecar: {exc}",
            })

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
