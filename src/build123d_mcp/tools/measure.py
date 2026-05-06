import json
import math


def _resolve_shape(session, object_name: str):
    if object_name:
        if object_name not in session.objects:
            raise ValueError(f"Unknown object '{object_name}'. Registered: {list(session.objects.keys())}")
        return session.objects[object_name]
    if session.current_shape is None:
        raise ValueError("No shape in session. Execute code to create geometry first.")
    return session.current_shape


def _center_of_mass(shape) -> dict:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props)
    com = props.CentreOfMass()
    return {"x": round(com.X(), 4), "y": round(com.Y(), 4), "z": round(com.Z(), 4)}


_SURFACE_NAMES = None

def _get_surface_names():
    global _SURFACE_NAMES
    if _SURFACE_NAMES is None:
        from OCP.GeomAbs import (
            GeomAbs_BSplineSurface, GeomAbs_Cone, GeomAbs_Cylinder,
            GeomAbs_Plane, GeomAbs_Sphere, GeomAbs_Torus,
        )
        _SURFACE_NAMES = {
            GeomAbs_Plane: "Plane",
            GeomAbs_Cylinder: "Cylinder",
            GeomAbs_Cone: "Cone",
            GeomAbs_Sphere: "Sphere",
            GeomAbs_Torus: "Torus",
            GeomAbs_BSplineSurface: "BSpline",
        }
    return _SURFACE_NAMES


def _face_inventory(shape) -> list:
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepGProp import BRepGProp
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Sphere, GeomAbs_Torus
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS

    surface_names = _get_surface_names()
    explorer = TopExp_Explorer(shape.wrapped, TopAbs_FACE)
    faces = []
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        adaptor = BRepAdaptor_Surface(face)
        stype = adaptor.GetType()
        type_name = surface_names.get(stype, f"Other({stype})")

        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        area = props.Mass()

        info = {"type": type_name, "area": round(area, 4)}

        if stype == GeomAbs_Cylinder:
            cyl = adaptor.Cylinder()
            info["diameter"] = round(cyl.Radius() * 2, 4)
            d = cyl.Axis().Direction()
            info["axis"] = (round(d.X(), 3), round(d.Y(), 3), round(d.Z(), 3))
        elif stype == GeomAbs_Cone:
            cone = adaptor.Cone()
            info["semi_angle_deg"] = round(math.degrees(cone.SemiAngle()), 2)
        elif stype == GeomAbs_Sphere:
            sph = adaptor.Sphere()
            info["radius"] = round(sph.Radius(), 4)
        elif stype == GeomAbs_Torus:
            t = adaptor.Torus()
            info["major_r"] = round(t.MajorRadius(), 4)
            info["minor_r"] = round(t.MinorRadius(), 4)

        faces.append(info)
        explorer.Next()

    faces.sort(key=lambda f: (f["type"], -f["area"]))
    return faces


def _inertia(shape) -> dict:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props)
    mat = props.MatrixOfInertia()
    return {
        "Ixx": round(mat.Value(1, 1), 4),
        "Iyy": round(mat.Value(2, 2), 4),
        "Izz": round(mat.Value(3, 3), 4),
        "Ixy": round(mat.Value(1, 2), 4),
        "Ixz": round(mat.Value(1, 3), 4),
        "Iyz": round(mat.Value(2, 3), 4),
    }


def _cross_sections(shape, axis: str = "Z", num_slices: int = 10) -> list:
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopTools import TopTools_HSequenceOfShape
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

    axis = axis.upper()
    bb = shape.bounding_box()

    if axis == "X":
        lo, hi = bb.min.X, bb.max.X
        pln_dir = gp_Dir(1, 0, 0)
        make_pnt = lambda pos: gp_Pnt(pos, 0, 0)
    elif axis == "Y":
        lo, hi = bb.min.Y, bb.max.Y
        pln_dir = gp_Dir(0, 1, 0)
        make_pnt = lambda pos: gp_Pnt(0, pos, 0)
    else:
        lo, hi = bb.min.Z, bb.max.Z
        pln_dir = gp_Dir(0, 0, 1)
        make_pnt = lambda pos: gp_Pnt(0, 0, pos)

    span = hi - lo
    lo_s = lo + span * 0.01
    hi_s = hi - span * 0.01
    num_slices = max(num_slices, 2)
    step = (hi_s - lo_s) / (num_slices - 1)

    results = []
    for i in range(num_slices):
        pos = lo_s + i * step
        plane = gp_Pln(make_pnt(pos), pln_dir)

        section = BRepAlgoAPI_Section(shape.wrapped, plane, False)
        section.Build()

        edges = TopTools_HSequenceOfShape()
        exp = TopExp_Explorer(section.Shape(), TopAbs_EDGE)
        while exp.More():
            edges.Append(exp.Current())
            exp.Next()

        wires = TopTools_HSequenceOfShape()
        ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(edges, 1e-7, False, wires)

        total_area = 0.0
        for j in range(1, wires.Length() + 1):
            wire = TopoDS.Wire_s(wires.Value(j))
            try:
                face_maker = BRepBuilderAPI_MakeFace(plane, wire)
                if face_maker.IsDone():
                    face = face_maker.Face()
                    props = GProp_GProps()
                    BRepGProp.SurfaceProperties_s(face, props)
                    total_area += abs(props.Mass())
            except Exception:
                pass

        results.append({"position": round(pos, 4), "area": round(total_area, 4)})

    return results


def measure(session, object_name: str = "") -> str:
    shape = _resolve_shape(session, object_name)
    bb = shape.bounding_box()
    cx = round((bb.min.X + bb.max.X) / 2, 4)
    cy = round((bb.min.Y + bb.max.Y) / 2, 4)
    cz = round((bb.min.Z + bb.max.Z) / 2, 4)
    return json.dumps({
        "volume": round(shape.volume, 4),
        "area": round(shape.area, 4),
        "topology": {
            "faces": len(shape.faces()),
            "edges": len(shape.edges()),
            "vertices": len(shape.vertices()),
        },
        "bbox": {
            "xmin": round(bb.min.X, 4), "xmax": round(bb.max.X, 4),
            "ymin": round(bb.min.Y, 4), "ymax": round(bb.max.Y, 4),
            "zmin": round(bb.min.Z, 4), "zmax": round(bb.max.Z, 4),
            "xsize": round(bb.size.X, 4),
            "ysize": round(bb.size.Y, 4),
            "zsize": round(bb.size.Z, 4),
            "center": {"x": cx, "y": cy, "z": cz},
        },
        "center_of_mass": _center_of_mass(shape),
        "inertia": _inertia(shape),
        "face_inventory": _face_inventory(shape),
    }, indent=2)


def clearance(session, object_a: str, object_b: str) -> str:
    for name in (object_a, object_b):
        if name not in session.objects:
            raise ValueError(f"Unknown object '{name}'. Registered: {list(session.objects.keys())}")
    dist = session.objects[object_a].distance_to(session.objects[object_b])
    return json.dumps({"clearance": dist}, indent=2)
