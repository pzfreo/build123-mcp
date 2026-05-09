"""Single source of truth for the build123d quick reference.

Each Section with a label is a fully self-contained, executable code block.
Prose-only sections (no label) are reference documentation that cannot be run.

build_quickref_text() assembles all sections into the MCP resource text.
RUNNABLE_EXAMPLES is the list used by tests/test_quickref.py.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class Section:
    text: str
    label: Optional[str] = None  # None = prose only, not tested


SECTIONS: list[Section] = [
    Section(
        "BUILD123D QUICK REFERENCE — all measurements in mm\n"
        "===================================================="
    ),

    Section(
        label="pattern1",
        text="""\
## Pattern 1: direct shape algebra (simplest)
from build123d import *
result = Box(20, 10, 5)
result = result - Cylinder(3, 6).move(Location((0, 0, 0)))
show(result, "part")""",
    ),

    Section(
        label="pattern2",
        text="""\
## Pattern 2: BuildPart context manager (required for extrude/revolve/loft/fillet)
from build123d import *
with BuildPart() as p:
    Box(20, 10, 5)
    Cylinder(3, 6, mode=Mode.SUBTRACT)   # cut hole
result = p.part
show(result, "part")""",
    ),

    Section(
        text="""\
## Primitives
Box(length, width, height)              # centred at origin
Cylinder(radius, height)
Sphere(radius)
Cone(bottom_radius, top_radius, height)
Torus(major_radius, minor_radius)""",
    ),

    Section(
        text="""\
## Boolean operators (direct algebra)
a + b    # union
a - b    # cut b from a
a & b    # intersection""",
    ),

    Section(
        text="""\
## Boolean modes (inside BuildPart)
mode=Mode.ADD        # default — union with existing solid
mode=Mode.SUBTRACT   # cut from existing solid
mode=Mode.INTERSECT  # keep overlap only
mode=Mode.REPLACE    # replace current solid entirely""",
    ),

    Section(
        label="align",
        text="""\
## Positioning
# Alignment — corner vs centred
from build123d import *
corner = Box(10, 5, 3, align=(Align.MIN, Align.MIN, Align.MIN))        # corner at origin
result = Box(10, 5, 3, align=(Align.CENTER, Align.CENTER, Align.MIN))  # centred XY, bottom at Z=0""",
    ),

    Section(
        label="translate",
        text="""\
# Translate (and optionally rotate)
from build123d import *
shape = Box(10, 5, 3)
result = shape.move(Location((5, 0, 0)))
rotated = shape.move(Location((5, 0, 0), (0, 0, 45)))""",
    ),

    Section(
        label="locations",
        text="""\
# Place multiple instances inside BuildPart
from build123d import *
with BuildPart() as p:
    Box(30, 30, 8)
    with Locations((10, 0, 0), (-10, 0, 0)):
        Cylinder(2, 10, mode=Mode.SUBTRACT)
result = p.part

from build123d import *
with BuildPart() as p:
    Box(40, 40, 8)
    with GridLocations(12, 12, 3, 3):
        Cylinder(2, 10, mode=Mode.SUBTRACT)
result = p.part

from build123d import *
with BuildPart() as p:
    Box(40, 40, 8)
    with PolarLocations(12, 6):
        Cylinder(2, 10, mode=Mode.SUBTRACT)
result = p.part""",
    ),

    Section(
        label="extrude",
        text="""\
## Sketch → solid (requires BuildPart)
# Extrude
from build123d import *
with BuildPart() as p:
    with BuildSketch() as sk:            # default plane: XY
        Circle(10)
        Rectangle(6, 6, mode=Mode.SUBTRACT)   # cutout in sketch
    extrude(amount=15)
result = p.part""",
    ),

    Section(
        label="revolve",
        text="""\
# Revolve — profile in Plane.XZ, offset from axis
from build123d import *
with BuildPart() as p:
    with BuildSketch(Plane.XZ) as sk:
        with Locations((12, 0)):
            Rectangle(4, 8)
    revolve(axis=Axis.Z)                 # full 360°
result = p.part""",
    ),

    Section(
        label="loft",
        text="""\
# Loft between two profiles
from build123d import *
with BuildPart() as p:
    with BuildSketch(Plane.XY) as s1:
        Rectangle(10, 10)
    with BuildSketch(Plane.XY.offset(15)) as s2:
        Circle(4)
    loft()
result = p.part""",
    ),

    Section(
        label="selectors",
        text="""\
## Selecting edges and faces
from build123d import *
result = Box(20, 10, 5)
top_face    = result.faces().sort_by(Axis.Z)[-1]        # highest-Z face
bottom_face = result.faces().sort_by(Axis.Z)[0]         # lowest-Z face
top_edges   = result.edges().sort_by(Axis.Z)[-4:]       # 4 edges at highest Z (for fillet)
z_edges     = result.edges().filter_by(Axis.Z)          # edges parallel to Z
flat_faces  = result.faces().filter_by(GeomType.PLANE)  # planar faces only""",
    ),

    Section(
        label="fillet_chamfer",
        text="""\
## Fillets and chamfers (inside BuildPart only)
from build123d import *
with BuildPart() as p:
    Box(20, 10, 5)
    fillet(p.part.edges().sort_by(Axis.Z)[-4:], radius=1)
result = p.part

from build123d import *
with BuildPart() as p:
    Box(20, 10, 5)
    chamfer(p.part.edges().sort_by(Axis.Z)[-4:], length=0.5)
result = p.part""",
    ),

    Section(
        label="joints_rigid",
        text="""\
## Joints — assembly relationships
# Joints express how parts CONNECT, not just where they happen to sit. Move the
# parent, the child follows. Reach for joints when building assemblies — they
# scale better than raw .move() because the relationship survives changes.
from build123d import *
plate = Box(20, 20, 5)
RigidJoint("mount", to_part=plate, joint_location=Location((0, 0, 2.5)))

pin = Box(2, 2, 10)
RigidJoint("base", to_part=pin, joint_location=Location((0, 0, -5)))

# Snap pin's "base" joint to plate's "mount" joint. pin is now positioned
# so its joint coincides with the plate's. Move plate later → pin follows.
plate.joints["mount"].connect_to(pin.joints["base"])
show(plate, "plate")
show(pin, "pin")""",
    ),

    Section(
        text="""\
## Joint types
RigidJoint(label, to_part, joint_location)              # fixed (no DOF)
RevoluteJoint(label, to_part, axis, angular_range)      # hinge (1 rotation)
LinearJoint(label, to_part, axis, linear_range)         # slider (1 translation)
CylindricalJoint(label, to_part, axis, ...)             # rotate + translate same axis
BallJoint(label, to_part, joint_location, angular_range) # 3 rotations, 0 translations

# For movable joints, pass position/angle to connect_to() to set the configuration:
#   plate.joints["hinge"].connect_to(arm.joints["pivot"], angle=45)
#   rail.joints["slot"].connect_to(carriage.joints["slide"], position=10)""",
    ),

    Section(
        text="""\
## MCP server conventions
- Name the final shape 'result' OR call show() — both trigger current_shape auto-detection
- show(shape, "name")      registers object, prints vol + face count as immediate confirmation
- named_face(shape, "top") returns the highest-Z face; also: bottom/front/back/left/right""",
    ),

    Section(
        text="""\
## Common gotchas
- After every -, +, & : call measure() and check topology.faces — a failed boolean leaves counts unchanged
- fillet/chamfer radius too large → OCC kernel exception; reduce radius or select fewer edges
- Cylinder/Sphere are centred at origin; use .move() or align= to reposition
- Locations() inside BuildPart shifts the construction origin — it does NOT move the whole part
- Pass p.part (the Shape) to show(), not p (the BuildPart context)
- revolve() needs the profile offset from the revolution axis — a profile touching the axis produces a solid, one crossing it fails""",
    ),
]


def build_quickref_text() -> str:
    return "\n\n".join(s.text for s in SECTIONS)


RUNNABLE_EXAMPLES: list[tuple[str, str]] = [
    (s.label, s.text) for s in SECTIONS if s.label is not None
]
