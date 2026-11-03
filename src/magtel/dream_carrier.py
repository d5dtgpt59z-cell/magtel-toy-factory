"""Sculpt the outside of a bored chassis while preserving its mechanical interfaces."""

from .mesh import Point, Triangle

# Front taper (start, amount), rear taper (start, amount), waist, lower chamfer.
_PROPORTIONS = {
    "lunar": ((0.53, 0.60), (0.55, 0.43), 0.14, 0.29),
    "racer": ((0.43, 0.67), (0.68, 0.29), 0.20, 0.34),
    "truck": ((0.60, 0.48), (0.66, 0.33), 0.08, 0.37),
}


def _ramp(value: float, start: float, end: float) -> float:
    t = min(1.0, max(0.0, (value - start) / (end - start)))
    return t * t * (3 - 2 * t)


def shape_carrier(
    faces: list[Triangle], profile: str, length: float, height: float, wheelbase: float, bore_diameter: float,
) -> list[Triangle]:
    """Shape the transverse envelope. Keep bore vertices and the mounting planes fixed."""
    if profile == "plain":
        return faces
    front, rear, waist, chamfer = _PROPORTIONS[profile]
    radius = bore_diameter / 2
    axle_x = wheelbase / 2
    mount_z = height / 2

    def sculpt(point: Point) -> Point:
        x, y, z = point
        # Outer and optional middle bore rings retain the original exits and fit.
        axle_offset = min(abs(x), abs(abs(x) - axle_x))
        if axle_offset ** 2 + (z - mount_z) ** 2 <= radius ** 2 + 1e-9:
            return point

        s, h = abs(x) / (length / 2), z / height
        start, cut = front if x >= 0 else rear
        end_taper = cut * _ramp(s, start, 1.0)
        waist_taper = waist * (1 - _ramp(s, 0.13, 0.48))
        lower_bevel = chamfer * (1 - _ramp(h, 0.0, 0.53))
        upper_bevel = 0.035 * _ramp(h, 0.76, 1.0)
        width_factor = (1 - end_taper - waist_taper) * (1 - lower_bevel - upper_bevel)
        return x, y * width_factor, z

    return [(sculpt(a), sculpt(b), sculpt(c)) for a, b, c in faces]
