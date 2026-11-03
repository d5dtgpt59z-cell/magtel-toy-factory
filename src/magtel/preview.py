"""Export a part or car assembly as a self-contained browser preview."""

import json
import re
from html import escape
from importlib.resources import files
from pathlib import Path

from .assembly import CarSpec
from .mesh import Point, Triangle, mesh
from .model import ToySpec
from .project import write_output

_COLORS = {
    "block": (0.94, 0.53, 0.19),
    "chassis": (0.94, 0.53, 0.19),
    "axle": (0.69, 0.76, 0.79),
    "wheel": (0.32, 0.60, 0.83),
}
_PLACEHOLDER = re.compile(r"%%(?:TITLE|DATA)%%")


def _part(name: str, kind: str, triangles: list[Triangle], explode: Point) -> dict[str, object]:
    return {
        "name": name,
        "color": _COLORS[kind],
        "vertices": [round(coord, 6) for triangle in triangles for point in triangle for coord in point],
        "explode": explode,
    }


def car_preview_data(car: CarSpec) -> dict:
    """Describe the assembled car and its axle pivots for a 3D preview."""
    components = car.components()
    assert car.wheel and car.chassis and car.axle
    assert car.wheel.diameter and car.chassis.depth and car.chassis.height
    assert car.axle.thickness and car.axle.diameter and car.wheelbase and car.wheel.hole

    # The wheels slide off the axle ends along the same axis they use when
    # mounted. Lift the chassis clear of the axles so both bores are exposed.
    margin = car.wheel.diameter * 0.1
    wheel_inside = car.chassis.depth / 2 + car.wheel_gap
    wheel_travel = max(car.wheel.diameter / 2, car.axle.thickness / 2 - wheel_inside + margin)
    chassis_lift = (car.chassis.height + car.axle.diameter) / 2 + car.wheel.diameter / 4

    wheel_radius = car.wheel.diameter / 2
    bore_radius = car.wheel.hole / 2
    wall = wheel_radius - bore_radius
    axle_radius = car.axle.diameter / 2
    # Radial index marks are preview accents on the end faces, not export geometry.
    marks = {
        "wheel": (max(wheel_radius * .64, bore_radius + wall * .14),
                  wheel_radius - wall * .14, min(wheel_radius * .065, wall * .25)),
        "axle": (axle_radius * .12, axle_radius * .83, axle_radius * .17),
    }
    parts = []
    for key, triangles in components.items():
        kind = key.split("-")[-1]
        if kind == "wheel":
            explode = (0, wheel_travel if "-left-" in key else -wheel_travel, 0)
        elif kind == "chassis":
            explode = (0, 0, chassis_lift)
        else:
            explode = (0, 0, 0)
        part = _part(key.replace("-", " ").title(), kind, triangles, explode)
        part.update(key=key, kind=kind)
        if kind in marks:
            part.update(axle=key.split("-")[0], mark=marks[kind])
        parts.append(part)
    return {
        "title": car.name,
        "description": car.describe(),
        "parts": parts,
        "assembly": True,
        "axle_pivots": {
            "front": (car.wheelbase / 2, wheel_radius),
            "rear": (-car.wheelbase / 2, wheel_radius),
        },
    }


def export_preview(spec: CarSpec | ToySpec, path: Path, *, force: bool = False) -> None:
    """Write a standalone HTML viewer for the current geometry."""
    if isinstance(spec, CarSpec):
        data = car_preview_data(spec)
    else:
        data = {
            "title": spec.name,
            "description": spec.describe(),
            "parts": [_part(spec.name, spec.kind, mesh(spec), (0, 0, 0))],
            "assembly": False,
        }
    write_preview_data(data, path, force=force)


def write_preview_data(data: dict, path: Path, *, force: bool = False) -> None:
    """Render geometry already converted to the standalone viewer's data format."""
    # Script data uses raw-text parsing even with type="application/json".
    # Escaping the opening angle bracket prevents premature tag termination.
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    values = {
        "%%TITLE%%": escape(data["title"]),
        "%%DATA%%": payload.replace("<", "\\u003c"),
    }
    template = files("magtel").joinpath("viewer.html").read_text(encoding="utf-8")
    contents = _PLACEHOLDER.sub(lambda match: values[match[0]], template)
    write_output(path, lambda temp: temp.write_text(contents, encoding="utf-8"), force=force)
