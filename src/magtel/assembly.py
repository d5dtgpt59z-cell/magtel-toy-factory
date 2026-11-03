"""Parametric placement and fit checks for a four-wheel toy car."""

import math
from dataclasses import dataclass

from .mesh import Point, Triangle, _CIRCLE_SEGMENTS, mesh
from .model import DesignError, ToySpec, _dimension, mm

_MIN_GAP = 0.1
_EPSILON = 1e-9


@dataclass(frozen=True)
class CarSpec:
    name: str = "Toy Car"
    chassis: ToySpec | None = None
    axle: ToySpec | None = None
    wheel: ToySpec | None = None
    wheelbase: float | None = None
    wheel_gap: float = 1.0
    axle_clearance: float = 0.4

    def missing(self) -> tuple[str, ...]:
        return tuple(
            label for value, label in (
                (self.chassis, "chassis"), (self.axle, "axles"),
                (self.wheel, "wheels"), (self.wheelbase, "wheelbase"),
            ) if value is None
        )

    def validate(self) -> "CarSpec":
        if (not isinstance(self.name, str) or not self.name.strip()
                or len(self.name) > 80 or not self.name.isprintable()):
            raise DesignError("Use a car name of 1 to 80 printable characters.")
        if self.wheelbase is not None:
            _dimension(self.wheelbase, "Wheelbase")
        _dimension(self.wheel_gap, "Wheel-to-chassis gap")
        _dimension(self.axle_clearance, "Chassis bore clearance")
        for label, part, kind in (
            ("chassis", self.chassis, "block"), ("axle", self.axle, "axle"), ("wheel", self.wheel, "wheel"),
        ):
            if part is not None:
                if not isinstance(part, ToySpec) or part.kind != kind:
                    raise DesignError(f"Use a {kind} part for the {label}.")
                part.validate()
        if self.chassis and self.chassis.studs:
            raise DesignError("Use a plain rectangular block for the chassis. Remove its studs first.")
        if self.wheel and self.wheel.hole is None:
            raise DesignError("Give the wheels a centered through hole for the axle.")
        self._validate_fits()
        return self

    def _validate_fits(self) -> None:
        chassis, axle, wheel = self.chassis, self.axle, self.wheel
        # Use the smallest permitted diameter for constraints already known without an axle.
        bore = (axle.diameter if axle else 0.1) + self.axle_clearance
        if axle and wheel and wheel.hole - axle.diameter < _MIN_GAP - _EPSILON:
            minimum = mm(axle.diameter + _MIN_GAP)
            raise DesignError(f"The wheels need a hole at least {minimum} mm across for these axles.")
        if self.wheelbase is not None:
            if wheel and self.wheelbase - wheel.diameter < _MIN_GAP - _EPSILON:
                minimum = mm(wheel.diameter + _MIN_GAP)
                raise DesignError(f"The front and rear wheels need a wheelbase of at least {minimum} mm.")
            if self.wheelbase - bore < _MIN_GAP - _EPSILON:
                raise DesignError("Increase the wheelbase or shrink the axle bores so the chassis holes stay separate.")
        if not chassis:
            return
        if (chassis.height - bore) / 2 < _MIN_GAP - _EPSILON:
            minimum = mm(bore + 2 * _MIN_GAP)
            raise DesignError(f"The chassis needs to be at least {minimum} mm tall to hold the axle bores.")
        if self.wheelbase is not None and (chassis.width - self.wheelbase - bore) / 2 < _MIN_GAP - _EPSILON:
            minimum = mm(self.wheelbase + bore + 2 * _MIN_GAP)
            raise DesignError(f"Use a chassis at least {minimum} mm long or bring the axles closer together.")
        if wheel and (wheel.diameter - chassis.height) / 2 < _MIN_GAP - _EPSILON:
            raise DesignError("Use taller wheels or a shorter chassis so the chassis clears the ground.")
        if axle:
            wheel_thickness = wheel.thickness if wheel else 0.1
            minimum = chassis.depth + 2 * (self.wheel_gap + wheel_thickness)
            if axle.thickness < minimum - _EPSILON:
                raise DesignError(f"Use axles at least {mm(minimum)} mm long to reach through both wheels.")

    def describe(self) -> str:
        lines = [f"{self.name} — car assembly"]
        if self.chassis:
            chassis = self.chassis
            size = f"{mm(chassis.width)} × {mm(chassis.depth)} × {mm(chassis.height)} mm"
            lines.append(f"  Chassis — {size} (length × width × height)")
        if self.axle:
            lines.append(f"  Two axles — Ø{mm(self.axle.diameter)} × {mm(self.axle.thickness)} mm long")
        if self.wheel:
            wheel = self.wheel
            lines.append(
                f"  Four wheels — Ø{mm(wheel.diameter)} × {mm(wheel.thickness)} mm thick, "
                f"Ø{mm(wheel.hole)} mm through holes"
            )
        if self.wheelbase is not None:
            lines.append(f"  Wheelbase — {mm(self.wheelbase)} mm between axle centers")
        lines.append(
            f"  Wheel-to-chassis gap — {mm(self.wheel_gap)} mm per side"
            f" · Chassis bore clearance — {mm(self.axle_clearance)} mm across"
        )
        if missing := self.missing():
            lines.append(f"  Still needed — {', '.join(missing)}")
        return "\n".join(lines)

    def _require_complete(self) -> tuple[ToySpec, ToySpec, ToySpec, float]:
        self.validate()
        if missing := self.missing():
            raise DesignError(f"Finish the car by specifying {', '.join(missing)}.")
        assert self.chassis and self.axle and self.wheel and self.wheelbase is not None
        return self.chassis, self.axle, self.wheel, self.wheelbase

    def fit_report(self) -> str:
        chassis, axle, wheel, _ = self._require_complete()
        wheel_clearance = wheel.hole - axle.diameter
        chassis_bore = axle.diameter + self.axle_clearance
        axle_overhang = (axle.thickness - chassis.depth) / 2 - self.wheel_gap - wheel.thickness
        ground_clearance = (wheel.diameter - chassis.height) / 2
        return "\n".join((
            "Nominal fit",
            f"  Wheel bore to axle — {mm(wheel_clearance)} mm across ({mm(wheel_clearance / 2)} mm per side)",
            f"  Chassis bores Ø{mm(chassis_bore)} mm — {mm(self.axle_clearance)} mm clearance across "
            f"({mm(self.axle_clearance / 2)} mm per side)",
            f"  Wheel to chassis — {mm(self.wheel_gap)} mm per side",
            f"  Axle past each wheel — {mm(max(0, axle_overhang))} mm",
            f"  Ground clearance below chassis — {mm(ground_clearance)} mm",
        ))

    def part_meshes(self) -> dict[str, list[Triangle]]:
        """Return one mesh of each type for printing as separate pieces."""
        chassis, axle, wheel, wheelbase = self._require_complete()
        return {
            "chassis": _bored_chassis(chassis.width, chassis.depth, chassis.height, wheelbase,
                                     (axle.diameter + self.axle_clearance) / 2),
            "axle": mesh(axle),
            "wheel": mesh(wheel),
        }

    def components(self) -> dict[str, list[Triangle]]:
        """Return all seven positioned solids, with the wheels resting on Z=0."""
        parts = self.part_meshes()
        assert self.chassis and self.axle and self.wheel and self.wheelbase is not None
        center_z = self.wheel.diameter / 2
        chassis_base = center_z - self.chassis.height / 2
        placed = {
            "chassis": [
                ((ax, ay, az + chassis_base), (bx, by, bz + chassis_base), (cx, cy, cz + chassis_base))
                for (ax, ay, az), (bx, by, bz), (cx, cy, cz) in parts["chassis"]
            ]
        }
        left = self.chassis.depth / 2 + self.wheel_gap
        for end, x in (("front", self.wheelbase / 2), ("rear", -self.wheelbase / 2)):
            placed[f"{end}-axle"] = _on_axle(parts["axle"], x, -self.axle.thickness / 2, center_z)
            placed[f"{end}-left-wheel"] = _on_axle(parts["wheel"], x, left, center_z)
            placed[f"{end}-right-wheel"] = _on_axle(parts["wheel"], x, -left - self.wheel.thickness, center_z)
        return placed


def _on_axle(faces: list[Triangle], x: float, y: float, z: float) -> list[Triangle]:
    def point(p: Point) -> Point:
        return x + p[0], y + p[2], z - p[1]

    return [(point(a), point(b), point(c)) for a, b, c in faces]


def _ray_to_rect(
    dx: float, dz: float, center: float, start: float, end: float, half_height: float,
) -> tuple[float, float]:
    x = end if dx > 0 else start
    z = half_height if dz > 0 else -half_height
    to_x = (x - center) / dx if dx else math.inf
    to_z = z / dz if dz else math.inf
    if to_x < to_z:
        return x, dz * to_x
    return center + dx * to_z, z


def _bored_chassis(length: float, width: float, height: float, wheelbase: float, radius: float) -> list[Triangle]:
    """Triangulate one bored half, then mirror it across its open center seam."""
    center, end, half_height = wheelbase / 2, length / 2, height / 2
    step = math.tau / _CIRCLE_SEGMENTS
    rays = [(math.cos(index * step), math.sin(index * step)) for index in range(_CIRCLE_SEGMENTS)]
    faces = _bored_chassis_section(
        width, half_height, radius, center, 0.0, end, rays, open_start=True,
    )

    def mirror(p: Point) -> Point:
        return -p[0], p[1], p[2]

    return faces + [(mirror(a), mirror(c), mirror(b)) for a, b, c in faces]


def _bored_chassis_section(
    width: float, half_height: float, radius: float, center: float, start: float, end: float,
    rays: list[tuple[float, float]], *, open_start: bool = False, open_end: bool = False,
) -> list[Triangle]:
    """Triangulate a rectangular cross-section with one bore and optional open X ends."""
    step = math.tau / len(rays)
    inner = [(center + dx * radius, dz * radius) for dx, dz in rays]
    outer = [_ray_to_rect(dx, dz, center, start, end, half_height) for dx, dz in rays]
    corners_between: list[list[tuple[float, tuple[float, float]]]] = [[] for _ in rays]
    for corner in ((start, -half_height), (end, -half_height), (end, half_height), (start, half_height)):
        sector = (math.atan2(corner[1], corner[0] - center) % math.tau) / step
        nearest = round(sector) % len(rays)
        # A separate sample here could collapse onto the corner in a binary STL.
        if math.dist(corner, outer[nearest]) < 0.00025:
            outer[nearest] = corner
        else:
            index = min(int(sector), len(rays) - 1)
            corners_between[index].append((sector, corner))

    def near(xz: tuple[float, float]) -> Point:
        return xz[0], -width / 2, xz[1] + half_height

    def far(p: Point) -> Point:
        return p[0], width / 2, p[2]

    faces: list[Triangle] = []
    for index, outer_start in enumerate(outer):
        end_index = (index + 1) % len(rays)
        boundary = [outer_start, *(corner for _, corner in sorted(corners_between[index])), outer[end_index]]
        inside = near(inner[index])
        next_inside = near(inner[end_index])
        for start_xz, end_xz in zip(boundary, boundary[1:]):
            a, b = near(start_xz), near(end_xz)
            faces.extend(((inside, a, b), (far(inside), far(b), far(a))))
            if open_start and a[0] == b[0] == start:
                continue
            if open_end and a[0] == b[0] == end:
                continue
            faces.extend(((b, a, far(a)), (b, far(a), far(b))))
        last = near(boundary[-1])
        faces.extend(((inside, last, next_inside), (far(inside), far(next_inside), far(last))))
        faces.extend(((inside, next_inside, far(next_inside)), (inside, far(next_inside), far(inside))))

    return faces
