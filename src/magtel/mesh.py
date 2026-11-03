"""Triangulate supported parts and write binary STL files in millimeters."""

from __future__ import annotations

import math
import struct
from collections.abc import Sequence
from pathlib import Path

from .model import ToySpec

Point = tuple[float, float, float]
Triangle = tuple[Point, Point, Point]
XY = tuple[float, float]

_CIRCLE_SEGMENTS = 96
_STUD_ANGLE_STEP = math.tau / 64
_STL_FACET = struct.Struct("<12fH")


def _quad(faces: list[Triangle], a: Point, b: Point, c: Point, d: Point) -> None:
    faces.extend(((a, b, c), (a, c, d)))


def _round_part(diameter: float, thickness: float, hole: float | None) -> list[Triangle]:
    radius = diameter / 2
    angles = (math.tau * index / _CIRCLE_SEGMENTS for index in range(_CIRCLE_SEGMENTS))
    directions = [(math.cos(angle), math.sin(angle)) for angle in angles]
    outside = [(x * radius, y * radius) for x, y in directions]
    inside = [(x * hole / 2, y * hole / 2) for x, y in directions] if hole else []
    faces: list[Triangle] = []
    for i, outside_start in enumerate(outside):
        j = (i + 1) % _CIRCLE_SEGMENTS
        outside_end = outside[j]
        a, b = (*outside_start, 0.0), (*outside_end, 0.0)
        d, c = (*outside_start, thickness), (*outside_end, thickness)
        _quad(faces, a, b, c, d)
        if inside:
            e, f = (*inside[i], 0.0), (*inside[j], 0.0)
            h, g = (*inside[i], thickness), (*inside[j], thickness)
            _quad(faces, f, e, h, g)  # Bore wall faces inward.
            _quad(faces, d, c, g, h)
            _quad(faces, b, a, e, f)
        else:
            faces.extend((((0.0, 0.0, thickness), d, c), ((0.0, 0.0, 0.0), b, a)))
    return faces


def _plain_block(width: float, depth: float, height: float) -> list[Triangle]:
    corners = [
        (-width / 2, -depth / 2),
        (width / 2, -depth / 2),
        (width / 2, depth / 2),
        (-width / 2, depth / 2),
    ]
    bottom = [(*xy, 0.0) for xy in corners]
    top = [(*xy, height) for xy in corners]
    faces: list[Triangle] = []
    _quad(faces, *reversed(bottom))
    _quad(faces, *top)
    for i in range(4):
        j = (i + 1) % 4
        _quad(faces, bottom[i], bottom[j], top[j], top[i])
    return faces


def _side_fractions(half_angle: float) -> list[float]:
    """Space edge points so rays from the cell center are nearly even in angle."""
    subdivisions = math.ceil(half_angle / _STUD_ANGLE_STEP)
    slope = math.tan(half_angle)
    interior = [
        (1 + math.tan(half_angle * i / subdivisions) / slope) / 2
        for i in range(1 - subdivisions, subdivisions)
    ]
    return [0.0, *interior, 1.0]


def _grid_samples(length: float, count: int, fractions: list[float]) -> list[list[float]]:
    boundaries = [length * (i / count - 0.5) for i in range(count + 1)]
    return [
        [start, *(start + (end - start) * ratio for ratio in fractions[1:-1]), end]
        for start, end in zip(boundaries, boundaries[1:])
    ]


def _stud_ring(x: list[float], y: list[float], radius: float) -> tuple[list[XY], list[XY]]:
    cx, cy = (x[0] + x[-1]) / 2, (y[0] + y[-1]) / 2
    perimeter = (
        [(v, y[0]) for v in x[:-1]]
        + [(x[-1], v) for v in y[:-1]]
        + [(v, y[-1]) for v in x[:0:-1]]
        + [(x[0], v) for v in y[:0:-1]]
    )
    circle: list[XY] = []
    for px, py in perimeter:
        dx, dy = px - cx, py - cy
        scale = radius / math.hypot(dx, dy)
        circle.append((cx + dx * scale, cy + dy * scale))
    return perimeter, circle


def _studded_block(
    width: float, depth: float, height: float, grid: tuple[int, int],
    stud_diameter: float, stud_height: float,
) -> list[Triangle]:
    columns, rows = grid
    cell_width, cell_depth = width / columns, depth / rows
    x_grid = _grid_samples(width, columns, _side_fractions(math.atan2(cell_width, cell_depth)))
    y_grid = _grid_samples(depth, rows, _side_fractions(math.atan2(cell_depth, cell_width)))
    stud_top = height + stud_height
    faces: list[Triangle] = []
    for x in x_grid:
        for y in y_grid:
            perimeter, circle = _stud_ring(x, y, stud_diameter / 2)
            center = ((x[0] + x[-1]) / 2, (y[0] + y[-1]) / 2, stud_top)
            for i, start in enumerate(perimeter):
                j = (i + 1) % len(perimeter)
                end = perimeter[j]
                a, b = (*start, height), (*end, height)
                c, d = (*circle[i], height), (*circle[j], height)
                e, f = (*circle[i], stud_top), (*circle[j], stud_top)
                _quad(faces, a, b, d, c)  # Block top, with a hole for this stud.
                _quad(faces, c, d, f, e)
                faces.append((center, e, f))
                if _is_outside_edge(start, end, width / 2, depth / 2):
                    g, h = (*start, 0.0), (*end, 0.0)
                    _quad(faces, g, h, b, a)
                    faces.append(((0.0, 0.0, 0.0), h, g))
    return faces


def _is_outside_edge(start: XY, end: XY, half_width: float, half_depth: float) -> bool:
    return (start[0] == end[0] and abs(start[0]) == half_width) or (
        start[1] == end[1] and abs(start[1]) == half_depth
    )


def mesh(spec: ToySpec) -> list[Triangle]:
    """Return consistently outward-wound triangles. The base sits on z=0."""
    spec.validate()
    if spec.kind in {"wheel", "axle"}:
        assert spec.diameter is not None and spec.thickness is not None
        return _round_part(spec.diameter, spec.thickness, spec.hole)
    assert spec.width is not None and spec.depth is not None and spec.height is not None
    if spec.studs:
        assert spec.stud_diameter is not None and spec.stud_height is not None
        return _studded_block(
            spec.width, spec.depth, spec.height, spec.studs, spec.stud_diameter, spec.stud_height,
        )
    return _plain_block(spec.width, spec.depth, spec.height)


def _normal(triangle: Triangle) -> Point:
    a, b, c = triangle
    ax, ay, az = (b[i] - a[i] for i in range(3))
    bx, by, bz = (c[i] - a[i] for i in range(3))
    x, y, z = ay * bz - az * by, az * bx - ax * bz, ax * by - ay * bx
    magnitude = math.hypot(x, y, z)
    return x / magnitude, y / magnitude, z / magnitude


def write_stl(spec: ToySpec, destination: Path) -> None:
    """Write a binary STL mesh. STL coordinates use millimeters by convention."""
    write_mesh_stl(mesh(spec), destination)


def write_mesh_stl(faces: Sequence[Triangle], destination: Path) -> None:
    destination.write_bytes(stl_bytes(faces))


def stl_bytes(faces: Sequence[Triangle]) -> bytes:
    """Encode triangles as binary STL using millimeter coordinates."""
    header = b"MAGTEL Toy Factory | coordinates in millimeters".ljust(80, b"\0")
    payload = bytearray(header)
    payload.extend(struct.pack("<I", len(faces)))
    for face in faces:
        a, b, c = face
        payload.extend(_STL_FACET.pack(*_normal(face), *a, *b, *c, 0))
    return bytes(payload)
