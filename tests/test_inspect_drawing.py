"""Tests for inspect_drawing tool and annotate() session helper."""
import json
import pytest

from build123d_mcp.session import Session


@pytest.fixture
def session():
    return Session()


# ---------------------------------------------------------------------------
# annotate() helper
# ---------------------------------------------------------------------------

class TestAnnotate:
    def test_annotate_registers_shape(self, session):
        session.execute("""
from build123d import *
from build123d import Draft
from build123d_drafting import dim_linear
draft = Draft(font_size=2.5, decimal_precision=1)
w = dim_linear((-10, 0, 0), (10, 0, 0), "above", 8, draft, label="20")
annotate(w, "width")
""")
        assert "width" in session.objects

    def test_annotate_stores_metadata(self, session):
        session.execute("""
from build123d import *
from build123d import Draft
from build123d_drafting import dim_linear
draft = Draft(font_size=2.5, decimal_precision=1)
w = dim_linear((-10, 0, 0), (10, 0, 0), "above", 8, draft, label="20")
annotate(w, "width")
""")
        ann = session.drawing_annotations.get("width")
        assert ann is not None
        assert ann["label_str"] == "20"
        assert abs(ann["measured_length"] - 20.0) < 0.01

    def test_annotate_leader_stores_tip_elbow(self, session):
        session.execute("""
from build123d import *
from build123d import Draft
from build123d_drafting import leader
draft = Draft(font_size=2.5, decimal_precision=1)
lea = leader((5, 5, 0), (20, 12, 0), "Ra 1.6", draft)
annotate(lea, "ra_mark")
""")
        ann = session.drawing_annotations.get("ra_mark")
        assert ann is not None
        assert ann["label_str"] == "Ra 1.6"
        assert "tip" in ann
        assert "elbow" in ann

    def test_annotate_clears_on_reset(self, session):
        session.execute("""
from build123d import *
from build123d import Draft
from build123d_drafting import dim_linear
draft = Draft(font_size=2.5, decimal_precision=1)
w = dim_linear((-10, 0, 0), (10, 0, 0), "above", 8, draft, label="20")
annotate(w, "width")
""")
        session.reset()
        assert session.drawing_annotations == {}

    def test_annotate_rolled_back_on_error(self, session):
        session.execute("""
from build123d import *
from build123d import Draft
from build123d_drafting import dim_linear
draft = Draft(font_size=2.5, decimal_precision=1)
w = dim_linear((-10, 0, 0), (10, 0, 0), "above", 8, draft, label="20")
annotate(w, "width")
""")
        # Now execute bad code that should roll back
        session.execute("raise ValueError('intentional error')")
        # annotation from first execute must still be there (only the bad exec rolls back)
        assert "width" in session.drawing_annotations


# ---------------------------------------------------------------------------
# inspect_drawing tool
# ---------------------------------------------------------------------------

class TestInspectDrawing:
    def _run(self, session, objects=""):
        from build123d_mcp.tools.inspect_drawing import inspect_drawing
        return json.loads(inspect_drawing(session, objects))

    def test_empty_session_returns_error(self, session):
        result = self._run(session)
        assert "error" in result

    def test_unknown_object_returns_error(self, session):
        session.execute("from build123d import *; show(Box(10,10,10), 'box')")
        result = self._run(session, "nonexistent")
        assert "error" in result

    def test_reports_bbox_for_plain_shape(self, session):
        session.execute("""
from build123d import *
plate = Box(40, 20, 5) - Cylinder(3, 5).move(Location((10, 0, 0)))
visible, _ = plate.project_to_viewport((0, 0, 100), (0, 1, 0), (0, 0, 0))
show(Compound(children=list(visible)), "part_view")
""")
        result = self._run(session)
        assert "part_view" in result["objects"]
        bb = result["objects"]["part_view"]["bbox"]
        assert bb is not None
        assert "min_x" in bb and "max_x" in bb

    def test_annotation_included_for_annotated_dim(self, session):
        session.execute("""
from build123d import *
from build123d import Draft
from build123d_drafting import dim_linear
draft = Draft(font_size=2.5, decimal_precision=1)
w = dim_linear((-10, 0, 0), (10, 0, 0), "above", 8, draft, label="20")
annotate(w, "width")
""")
        result = self._run(session)
        ann = result["objects"]["width"]["annotation"]
        assert ann is not None
        assert ann["label_str"] == "20"
        assert abs(ann["measured_length"] - 20.0) < 0.01

    def test_annotation_null_for_plain_show(self, session):
        session.execute("""
from build123d import *
show(Box(10, 10, 10), "box")
""")
        result = self._run(session)
        assert result["objects"]["box"]["annotation"] is None

    def test_drawing_bbox_covers_all_objects(self, session):
        session.execute("""
from build123d import *
from build123d import Draft
from build123d_drafting import dim_linear
draft = Draft(font_size=2.5, decimal_precision=1)
w = dim_linear((-20, -10, 0), (20, -10, 0), "below", 8, draft, label="40")
h = dim_linear((20, -10, 0), (20, 10, 0), "right", 8, draft, label="20")
annotate(w, "width")
annotate(h, "height")
""")
        result = self._run(session)
        db = result["drawing_bbox"]
        assert db is not None
        assert db["min_x"] < 0 and db["max_x"] > 0

    def test_objects_filter_works(self, session):
        session.execute("""
from build123d import *
from build123d import Draft
from build123d_drafting import dim_linear
draft = Draft(font_size=2.5, decimal_precision=1)
w = dim_linear((-10, 0, 0), (10, 0, 0), "above", 8, draft, label="20")
h = dim_linear((0, -10, 0), (0, 10, 0), "right", 8, draft, label="20")
annotate(w, "width")
annotate(h, "height")
""")
        result = self._run(session, "width")
        assert "width" in result["objects"]
        assert "height" not in result["objects"]

    def test_lint_flags_label_divergence(self, session):
        session.execute("""
from build123d import *
from build123d import Draft
from build123d_drafting import dim_linear
draft = Draft(font_size=2.5, decimal_precision=1)
# Label says 35 but segment is 20 mm — should be flagged
w = dim_linear((-10, 0, 0), (10, 0, 0), "above", 8, draft, label="35")
annotate(w, "wrong_dim")
""")
        result = self._run(session)
        assert len(result["lint"]) > 0
        assert any("35" in w or "differs" in w for w in result["lint"])

    def test_lint_clean_for_correct_label(self, session):
        session.execute("""
from build123d import *
from build123d import Draft
from build123d_drafting import dim_linear
draft = Draft(font_size=2.5, decimal_precision=1)
w = dim_linear((-10, 0, 0), (10, 0, 0), "above", 8, draft, label="20")
annotate(w, "width")
""")
        result = self._run(session)
        assert result["lint"] == []


# ---------------------------------------------------------------------------
# Regression: inspect_drawing must work through WorkerSession (issue #105).
# The bare-Session tests above can't catch a routing bug because the in-process
# Session has .objects/.drawing_annotations directly; the production server
# uses WorkerSession, a parent-side IPC proxy whose state lives in a subprocess.
# ---------------------------------------------------------------------------

class TestInspectDrawingViaWorker:
    def test_inspect_drawing_through_worker(self):
        from build123d_mcp.worker import WorkerSession

        ws = WorkerSession(exec_timeout=30)
        try:
            ws.execute("""
from build123d import *
from build123d import Draft
from build123d_drafting import dim_linear
draft = Draft(font_size=2.5, decimal_precision=1)
w = dim_linear((-10, 0, 0), (10, 0, 0), "above", 8, draft, label="20")
annotate(w, "width")
""")
            payload = json.loads(ws.inspect_drawing())
            assert "error" not in payload, payload
            assert "width" in payload["objects"]
            ann = payload["objects"]["width"]["annotation"]
            assert ann is not None
            assert ann["label_str"] == "20"
        finally:
            ws._kill_worker()
