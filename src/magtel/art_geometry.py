"""Validate art-derived recipes and build exact solids with optional build123d."""

from math import hypot, isfinite
import re

from .model import DesignError

_MAX_PARTS = 24
_MAX_FEATURES_PER_PART = 24
_MAX_FEATURES = 192
_MAX_PROFILE_VERTICES = 64
_MAX_LOFT_SECTIONS = 16
_MAX_VERTICES = 4096
_MAX_MM = 10_000
_MIN_MM = 0.01
_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")
_SIZE_COUNTS = {"box": 3, "cylinder": 2, "extrude": 1, "loft": 0}


def _schema_object(properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _schema_array(items):
    return {"type": "array", "items": items}


_NUMBER = {"type": "number"}
_STRING = {"type": "string"}
_VECTOR = _schema_array(_NUMBER)
_PROFILE = _schema_array(_VECTOR)
_SECTION = _schema_object({"z": _NUMBER, "profile": _PROFILE})
_FEATURE = _schema_object({
    "operation": {"type": "string", "enum": ["add", "cut"]},
    "kind": {"type": "string", "enum": list(_SIZE_COUNTS)},
    "position": _VECTOR,
    "rotation": _VECTOR,
    "size": _VECTOR,
    "profile": _PROFILE,
    "sections": _schema_array(_SECTION),
})
_PART = _schema_object({
    "name": _STRING,
    "color": _STRING,
    "features": _schema_array(_FEATURE),
})
ART_SCHEMA = _schema_object({
    "name": _STRING,
    "assumptions": _schema_array(_STRING),
    "parts": _schema_array(_PART),
})


def _object(value, path, schema):
    if not isinstance(value, dict) or value.keys() != schema["properties"].keys():
        required = ", ".join(schema["properties"])
        raise DesignError(f"{path} must contain exactly these fields: {required}.")


def _array(value, path, minimum, maximum):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        length = str(minimum) if minimum == maximum else f"{minimum} to {maximum}"
        raise DesignError(f"{path} must be an array of {length} items.")


def _text(value, path, limit):
    if (not isinstance(value, str) or not value.strip() or len(value) > limit
            or not value.isprintable()):
        raise DesignError(f"{path} must contain 1 to {limit} printable characters.")


def _number(value, path, low, high):
    if type(value) not in (int, float) or not low <= value <= high or not isfinite(value):
        raise DesignError(f"{path} must be a finite number between {low:g} and {high:g}.")


def _vector(value, path, count, low, high):
    _array(value, path, count, count)
    for index, item in enumerate(value):
        _number(item, f"{path}[{index}]", low, high)


def _turn(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a, b, p):
    return all(min(a[axis], b[axis]) <= p[axis] <= max(a[axis], b[axis]) for axis in (0, 1))


def _segments_intersect(a, b, c, d):
    ac, ad, ca, cb = _turn(a, b, c), _turn(a, b, d), _turn(c, d, a), _turn(c, d, b)
    epsilon = 1e-9
    return (
        (ac * ad < 0 and ca * cb < 0)
        or (abs(ac) <= epsilon and _on_segment(a, b, c))
        or (abs(ad) <= epsilon and _on_segment(a, b, d))
        or (abs(ca) <= epsilon and _on_segment(c, d, a))
        or (abs(cb) <= epsilon and _on_segment(c, d, b))
    )


def _profile(points, path):
    _array(points, path, 3, _MAX_PROFILE_VERTICES)
    for index, point in enumerate(points):
        _vector(point, f"{path}[{index}]", 2, -_MAX_MM, _MAX_MM)
    if len({tuple(point) for point in points}) != len(points):
        raise DesignError(f"{path} needs unique vertices. The last point closes to the first automatically.")
    if any(max(axis) - min(axis) > _MAX_MM for axis in zip(*points)):
        raise DesignError(f"{path} exceeds the {_MAX_MM:g} mm profile span limit.")
    edges = list(zip(points, points[1:] + points[:1]))
    for index, (a, b) in enumerate(edges):
        if hypot(a[0] - b[0], a[1] - b[1]) < _MIN_MM:
            raise DesignError(f"{path} edges must be at least {_MIN_MM:g} mm long.")
        previous = points[index - 1]
        if abs(_turn(previous, a, b)) <= 1e-9 and (
            (previous[0] - a[0]) * (b[0] - a[0]) + (previous[1] - a[1]) * (b[1] - a[1]) > 0
        ):
            raise DesignError(f"{path} edges must not double back.")
        for later in range(index + 2, len(edges)):
            if index == 0 and later == len(edges) - 1:
                continue  # The closing edge shares one endpoint with the first edge.
            if _segments_intersect(a, b, *edges[later]):
                raise DesignError(f"{path} edges must not cross or touch.")
    twice_area = sum(a[0] * b[1] - a[1] * b[0] for a, b in edges)
    if abs(twice_area) < 2 * _MIN_MM ** 2:
        raise DesignError(f"{path} must enclose a nonzero area.")
    return 1 if twice_area > 0 else -1


def _loft_sections(sections, path):
    _array(sections, path, 2, _MAX_LOFT_SECTIONS)
    previous_z, previous_count, previous_winding = None, None, None
    vertices = 0
    for index, section in enumerate(sections):
        location = f"{path}[{index}]"
        _object(section, location, _SECTION)
        _number(section["z"], f"{location}.z", -_MAX_MM, _MAX_MM)
        z = section["z"]
        if previous_z is not None and z - previous_z < _MIN_MM:
            raise DesignError(f"{path} must ascend in Z with at least {_MIN_MM:g} mm between sections.")
        profile = section["profile"]
        winding = _profile(profile, f"{location}.profile")
        count = len(profile)
        if previous_count is not None and (count != previous_count or winding != previous_winding):
            raise DesignError(f"{path} profiles need matching vertex counts and winding.")
        previous_z, previous_count, previous_winding = z, count, winding
        vertices += count
    if sections[-1]["z"] - sections[0]["z"] > _MAX_MM:
        raise DesignError(f"{path} exceeds the {_MAX_MM:g} mm loft height limit.")
    return vertices


def _validate_feature(feature, path, first):
    _object(feature, path, _FEATURE)
    operation, kind = feature["operation"], feature["kind"]
    if operation not in ("add", "cut"):
        raise DesignError(f"{path}.operation must be add or cut.")
    if first and operation != "add":
        raise DesignError(f"{path} must add material before any cut.")
    if not isinstance(kind, str) or kind not in _SIZE_COUNTS:
        raise DesignError(f"{path}.kind must be box, cylinder, extrude, or loft.")
    _vector(feature["position"], f"{path}.position", 3, -_MAX_MM, _MAX_MM)
    _vector(feature["rotation"], f"{path}.rotation", 3, -360, 360)
    _vector(feature["size"], f"{path}.size", _SIZE_COUNTS[kind], _MIN_MM, _MAX_MM)
    if kind == "cylinder" and feature["size"][0] > _MAX_MM / 2:
        raise DesignError(f"{path}.size radius must not exceed {_MAX_MM / 2:g} mm.")

    vertices = 0
    if kind == "extrude":
        _profile(feature["profile"], f"{path}.profile")
        vertices = len(feature["profile"])
    else:
        _array(feature["profile"], f"{path}.profile", 0, 0)
    if kind == "loft":
        vertices = _loft_sections(feature["sections"], f"{path}.sections")
    else:
        _array(feature["sections"], f"{path}.sections", 0, 0)
    return vertices


def validate_art(data: dict) -> dict:
    """Check a JSON recipe before handing any geometry to the CAD kernel."""
    _object(data, "Recipe", ART_SCHEMA)
    _text(data["name"], "name", 100)
    _array(data["assumptions"], "assumptions", 0, 24)
    for index, note in enumerate(data["assumptions"]):
        _text(note, f"assumptions[{index}]", 400)
    _array(data["parts"], "parts", 1, _MAX_PARTS)
    names = set()
    total_features = 0
    total_vertices = 0
    for index, part in enumerate(data["parts"]):
        path = f"parts[{index}]"
        _object(part, path, _PART)
        _text(part["name"], f"{path}.name", 100)
        canonical_name = part["name"].strip().casefold()
        if canonical_name in names:
            raise DesignError(f"{path}.name must be unique.")
        names.add(canonical_name)
        if not isinstance(part["color"], str) or not _COLOR.fullmatch(part["color"]):
            raise DesignError(f"{path}.color must be a hex color such as #28C4B4.")
        _array(part["features"], f"{path}.features", 1, _MAX_FEATURES_PER_PART)
        total_features += len(part["features"])
        if total_features > _MAX_FEATURES:
            raise DesignError(f"Recipe must have at most {_MAX_FEATURES} features in total.")
        for feature_index, feature in enumerate(part["features"]):
            total_vertices += _validate_feature(feature, f"{path}.features[{feature_index}]", feature_index == 0)
            if total_vertices > _MAX_VERTICES:
                raise DesignError(f"Recipe must have at most {_MAX_VERTICES} profile vertices in total.")
    return data


def _make_wire(bd, profile, z):
    return bd.Wire.make_polygon([(x, y, z) for x, y in profile], close=True)


def _build_feature(bd, feature):
    kind, size = feature["kind"], feature["size"]
    align = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
    if kind == "box":
        shape = bd.Box(*size, align=align)
    elif kind == "cylinder":
        shape = bd.Cylinder(*size, align=align)
    elif kind == "extrude":
        face = bd.Face(_make_wire(bd, feature["profile"], 0))
        shape = bd.extrude(face, amount=size[0], dir=(0, 0, 1))
    else:
        wires = [_make_wire(bd, section["profile"], section["z"]) for section in feature["sections"]]
        shape = bd.Solid.make_loft(wires, ruled=False)
    return bd.Pos(*feature["position"]) * bd.Rot(*feature["rotation"]) * shape


def _build_part(bd, part):
    body = None
    for index, feature in enumerate(part["features"], start=1):
        try:
            shape = _build_feature(bd, feature)
            if not shape.is_valid or not shape.solids() or shape.volume <= 1e-8:
                raise DesignError("feature does not form a valid solid")
            if body is None:
                body = shape
            elif feature["operation"] == "add":
                body = body.fuse(shape)
            else:
                original_volume = body.volume
                body = body.cut(shape)
                if not body.solids():
                    raise DesignError("cut removed the entire part")
                if original_volume - body.volume <= 1e-8:
                    raise DesignError("cut does not intersect existing material")
        except DesignError as error:
            raise DesignError(f"{part['name']}, feature {index}: {error}.") from error
        except Exception as error:
            raise DesignError(f"{part['name']}, feature {index} could not be built by the CAD kernel.") from error

    solids = body.solids()
    if len(solids) != 1:
        raise DesignError(f"{part['name']} must form one connected solid, but has {len(solids)} solids.")
    solid = solids[0]
    if not solid.is_valid or solid.volume <= 1e-8:
        raise DesignError(f"{part['name']} did not form a valid solid.")
    solid.label = part["name"]
    solid.color = bd.Color(part["color"])
    return solid


def build_art(data: dict):
    """Build a named assembly from a validated recipe with no executable input."""
    validate_art(data)
    try:
        import build123d as bd
    except ImportError as error:
        raise DesignError("Art geometry requires build123d 0.13. Install the optional CAD dependencies.") from error
    parts = [_build_part(bd, part) for part in data["parts"]]
    return bd.Compound(children=parts, label=data["name"])
