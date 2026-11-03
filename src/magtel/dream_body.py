"""Faceted prototype bodies that share the same flat chassis mounting surface."""

import math
from dataclasses import dataclass

from .mesh import Point, Triangle, _quad
from .model import DesignError

BODY_PROFILES = ("plain", "lunar", "racer", "truck")


@dataclass(frozen=True)
class BodyPart:
    id: str
    name: str
    role: str
    faces: list[Triangle]


def body_parts(profile: str, length: float, width: float, top_z: float = 0) -> tuple[BodyPart, ...]:
    """Build separate solids in chassis coordinates with their contact faces at known heights."""
    if profile == "plain":
        return ()
    scale = min(width, length * 0.58)
    if profile == "lunar":
        parts = _lunar(length, width, scale)
    elif profile == "racer":
        parts = _racer(length, width, scale)
    elif profile == "truck":
        parts = _truck(length, width, scale)
    else:
        raise DesignError("Choose a supported body profile.")
    if not top_z:
        return parts
    return tuple(
        BodyPart(part.id, part.name, part.role, [tuple((x, y, z + top_z) for x, y, z in face) for face in part.faces])
        for part in parts
    )


def _ring(cx: float, length: float, rear_width: float, front_width: float, z: float,
          *, rear_trim: float = 0.13, front_trim: float = 0.15) -> list[Point]:
    """An eight-vertex section with independently chamfered tail and nose corners."""
    back, front = cx - length / 2, cx + length / 2
    rear, nose = rear_width / 2, front_width / 2
    rear_corner = rear + (nose - rear) * rear_trim
    front_corner = nose + (rear - nose) * front_trim
    return [
        (back, -rear * 0.75, z), (back + length * rear_trim, -rear_corner, z),
        (front - length * front_trim, -front_corner, z), (front, -nose * 0.65, z),
        (front, nose * 0.65, z), (front - length * front_trim, front_corner, z),
        (back + length * rear_trim, rear_corner, z), (back, rear * 0.75, z),
    ]


def _oval(cx: float, length: float, width: float, z: float) -> list[Point]:
    return [
        (cx + length / 2 * math.cos(i * math.tau / 16), width / 2 * math.sin(i * math.tau / 16), z)
        for i in range(16)
    ]


def _band(faces: list[Triangle], lower: list[Point], upper: list[Point]) -> None:
    for index in range(len(lower)):
        next_index = (index + 1) % len(lower)
        _quad(faces, lower[index], lower[next_index], upper[next_index], upper[index])


def _cap(faces: list[Triangle], ring: list[Point], *, top: bool) -> None:
    points = ring if top else ring[::-1]
    faces.extend((points[0], points[i], points[i + 1]) for i in range(1, len(points) - 1))


def _solid(*rings: list[Point]) -> list[Triangle]:
    faces: list[Triangle] = []
    _cap(faces, rings[0], top=False)
    for lower, upper in zip(rings, rings[1:]):
        _band(faces, lower, upper)
    _cap(faces, rings[-1], top=True)
    return faces


def _lunar(length: float, width: float, scale: float) -> tuple[BodyPart, ...]:
    cabin_height = 0.41 * scale
    deck_height = 0.21 * scale
    return (
        BodyPart("body-cabin", "Survey cabin", "shell", _solid(
            _ring(0.13 * length, 0.50 * length, 0.68 * width, 0.59 * width, 0),
            _ring(0.13 * length, 0.55 * length, 0.78 * width, 0.68 * width, 0.07 * scale),
            _ring(0.12 * length, 0.54 * length, 0.76 * width, 0.65 * width, 0.22 * scale),
            _ring(0.062 * length, 0.40 * length, 0.55 * width, 0.46 * width, cabin_height),
        )),
        BodyPart("body-canopy", "Panoramic canopy", "accent", _solid(
            _ring(0.06 * length, 0.32 * length, 0.49 * width, 0.37 * width, cabin_height),
            _ring(0.034 * length, 0.26 * length, 0.41 * width, 0.31 * width, cabin_height + 0.085 * scale),
            _ring(0.032 * length, 0.22 * length, 0.35 * width, 0.26 * width, cabin_height + 0.115 * scale),
        )),
        BodyPart("body-deck", "Equipment deck", "equipment", _solid(
            _ring(-0.31 * length, 0.27 * length, 0.66 * width, 0.74 * width, 0),
            _ring(-0.31 * length, 0.30 * length, 0.73 * width, 0.82 * width, 0.055 * scale),
            _ring(-0.31 * length, 0.26 * length, 0.69 * width, 0.74 * width, deck_height),
        )),
        BodyPart("body-sensor", "Survey scanner", "accent", _solid(
            _oval(-0.31 * length, 0.13 * length, 0.34 * width, deck_height),
            _oval(-0.31 * length, 0.20 * length, 0.52 * width, deck_height + 0.055 * scale),
            _oval(-0.32 * length, 0.16 * length, 0.44 * width, deck_height + 0.135 * scale),
            _oval(-0.325 * length, 0.105 * length, 0.31 * width, deck_height + 0.19 * scale),
        )),
    )


def _racer(length: float, width: float, scale: float) -> tuple[BodyPart, ...]:
    deck_height = 0.19 * scale
    return (
        BodyPart("body-wedge", "Aero wedge", "shell", _solid(
            _ring(0.062 * length, 0.77 * length, 0.66 * width, 0.49 * width, 0),
            _ring(0.067 * length, 0.80 * length, 0.89 * width, 0.61 * width, 0.045 * scale),
            _ring(0.041 * length, 0.74 * length, 0.81 * width, 0.52 * width, 0.085 * scale),
            _ring(-0.084 * length, 0.47 * length, 0.65 * width, 0.34 * width, deck_height),
        )),
        BodyPart("body-canopy", "Speed canopy", "accent", _solid(
            _ring(-0.067 * length, 0.32 * length, 0.43 * width, 0.28 * width, deck_height),
            _ring(-0.109 * length, 0.205 * length, 0.34 * width, 0.20 * width, deck_height + 0.12 * scale),
            _ring(-0.114 * length, 0.16 * length, 0.29 * width, 0.17 * width, deck_height + 0.15 * scale),
        )),
        BodyPart("body-wing", "Rear aerofoil", "equipment", _solid(
            _ring(-0.410 * length, 0.11 * length, 0.32 * width, 0.38 * width, 0),
            _ring(-0.423 * length, 0.061 * length, 0.29 * width, 0.31 * width, 0.19 * scale),
            _ring(-0.423 * length, 0.097 * length, 0.89 * width, 0.77 * width, 0.25 * scale),
            _ring(-0.427 * length, 0.105 * length, 0.94 * width, 0.84 * width, 0.30 * scale),
            _ring(-0.433 * length, 0.086 * length, 0.89 * width, 0.81 * width, 0.34 * scale),
        )),
    )


def _truck(length: float, width: float, scale: float) -> tuple[BodyPart, ...]:
    cab_height = 0.54 * scale
    bed_height = 0.30 * scale
    lower = _ring(-0.29 * length, 0.31 * length, 0.74 * width, 0.75 * width, 0)
    shoulder = _ring(-0.29 * length, 0.36 * length, 0.86 * width, 0.87 * width, 0.055 * scale)
    rim = _ring(-0.29 * length, 0.36 * length, 0.86 * width, 0.87 * width, bed_height)
    inside = _ring(-0.29 * length, 0.265 * length, 0.65 * width, 0.65 * width, bed_height)
    floor = _ring(-0.29 * length, 0.253 * length, 0.62 * width, 0.62 * width, 0.105 * scale)
    tray: list[Triangle] = []
    _cap(tray, lower, top=False)
    _band(tray, lower, shoulder)
    _band(tray, shoulder, rim)
    _band(tray, rim, inside)  # Annular rim joins to the inward-facing pocket walls.
    _band(tray, inside, floor)
    _cap(tray, floor, top=True)

    return (
        BodyPart("body-cab", "High-roof cab", "shell", _solid(
            _ring(0.18 * length, 0.51 * length, 0.74 * width, 0.72 * width, 0),
            _ring(0.176 * length, 0.54 * length, 0.83 * width, 0.84 * width, 0.074 * scale),
            _ring(0.176 * length, 0.54 * length, 0.83 * width, 0.82 * width, 0.255 * scale),
            _ring(0.125 * length, 0.425 * length, 0.76 * width, 0.72 * width, 0.473 * scale),
            _ring(0.116 * length, 0.391 * length, 0.69 * width, 0.65 * width, cab_height),
        )),
        BodyPart("body-visor", "Cab visor", "accent", _solid(
            _ring(0.112 * length, 0.33 * length, 0.59 * width, 0.57 * width, cab_height),
            _ring(0.128 * length, 0.376 * length, 0.65 * width, 0.68 * width, cab_height + 0.038 * scale),
            _ring(0.117 * length, 0.341 * length, 0.61 * width, 0.62 * width, cab_height + 0.075 * scale),
        )),
        BodyPart("body-cargo", "Recessed cargo bed", "equipment", tray),
    )
