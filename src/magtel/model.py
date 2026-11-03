"""The editable, millimeter-based parameters for each supported part."""

from dataclasses import dataclass
from math import isfinite


class DesignError(ValueError):
    """A design or request needs correction before we can use it."""


@dataclass(frozen=True)
class ToySpec:
    kind: str
    name: str
    width: float | None = None
    depth: float | None = None
    height: float | None = None
    diameter: float | None = None
    thickness: float | None = None
    hole: float | None = None
    studs: tuple[int, int] | None = None
    stud_diameter: float | None = None
    stud_height: float | None = None

    @classmethod
    def default(cls, kind: str) -> "ToySpec":
        if kind == "wheel":
            return cls(kind, "Wheel", diameter=40, thickness=10, hole=6)
        if kind == "axle":
            return cls(kind, "Axle", diameter=5.8, thickness=24)
        if kind == "block":
            return cls(kind, "Block", width=40, depth=20, height=10)
        raise DesignError("Choose a wheel, axle, or block.")

    def validate(self) -> "ToySpec":
        if self.kind not in ("wheel", "axle", "block"):
            raise DesignError("Choose a wheel, axle, or block.")
        if (not isinstance(self.name, str) or not self.name.strip()
                or len(self.name) > 80 or not self.name.isprintable()):
            raise DesignError("Use a part name of 1 to 80 printable characters.")

        if self.kind == "block":
            self._validate_block()
        else:
            self._validate_round_part()
        return self

    def _validate_round_part(self) -> None:
        if any(value is not None for value in (
            self.width, self.depth, self.height, self.studs,
            self.stud_diameter, self.stud_height,
        )):
            raise DesignError("Width, depth, height, and studs belong to blocks.")
        diameter = _dimension(self.diameter, f"{self.kind.capitalize()} diameter")
        _dimension(self.thickness, "Wheel thickness" if self.kind == "wheel" else "Axle length")
        if self.hole is not None:
            if self.kind != "wheel":
                raise DesignError("Axles are solid. Only wheels can have a hole.")
            hole = _dimension(self.hole, "Hole diameter")
            if (diameter - hole) / 2 < 0.1 - 1e-9:
                raise DesignError("Make the hole at least 0.2 mm smaller than the wheel diameter.")

    def _validate_block(self) -> None:
        if any(value is not None for value in (self.diameter, self.thickness, self.hole)):
            raise DesignError("Use width, depth, and height for a block. Blocks do not have holes.")
        width = _dimension(self.width, "Block width")
        depth = _dimension(self.depth, "Block depth")
        _dimension(self.height, "Block height")
        if self.studs is None:
            if self.stud_diameter is not None or self.stud_height is not None:
                raise DesignError("Add a stud grid before setting stud dimensions.")
            return
        if (not isinstance(self.studs, tuple) or len(self.studs) != 2
                or any(type(count) is not int or not 1 <= count <= 20 for count in self.studs)):
            raise DesignError("Use 1 to 20 columns and rows for the stud grid.")
        columns, rows = self.studs
        if columns * rows > 100:
            raise DesignError("Use at most 100 studs per block.")
        diameter = _dimension(self.stud_diameter, "Stud diameter")
        _dimension(self.stud_height, "Stud height")
        if (min(width / columns, depth / rows) - diameter) / 2 < 0.1 - 1e-9:
            raise DesignError("Use fewer studs, a smaller stud diameter, or a larger block so the studs fit.")

    def describe(self) -> str:
        if self.kind == "block":
            geometry = f"{mm(self.width)} × {mm(self.depth)} × {mm(self.height)} mm (width × depth × height)"
            if self.studs:
                columns, rows = self.studs
                geometry += (f", {columns} × {rows} studs"
                             f" (Ø{mm(self.stud_diameter)} × {mm(self.stud_height)} mm)")
        elif self.kind == "axle":
            geometry = f"Ø{mm(self.diameter)} × {mm(self.thickness)} mm long"
        else:
            hole = f"Ø{mm(self.hole)} mm through hole" if self.hole is not None else "solid center"
            geometry = f"Ø{mm(self.diameter)} × {mm(self.thickness)} mm thick, {hole}"
        label = self.name if self.name.casefold() == self.kind else f"{self.name} ({self.kind})"
        return f"{label} — {geometry}"


def _dimension(value: float | None, label: str) -> float:
    if type(value) not in (int, float) or not 0.1 <= value <= 1000 or not isfinite(value):
        raise DesignError(f"{label} must be between 0.1 and 1000 mm.")
    return value


def mm(value: float) -> str:
    """Display millimeters without floating-point artifacts from unit conversion."""
    return format(value, ".12g")
