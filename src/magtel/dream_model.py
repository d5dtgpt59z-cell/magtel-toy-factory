"""Local concept recipes and validated modular vehicles for Dream Mode."""

import math
import re
from dataclasses import dataclass

from .assembly import CarSpec, _bored_chassis_section, _on_axle
from .language import _dimension as _parse_measure
from .language import _measurement
from .mesh import Triangle, _CIRCLE_SEGMENTS, _quad
from .model import DesignError, ToySpec, _dimension, mm

FORMAT = "magtel-dream"
VERSION = 1

_FIELDS = (
    "length", "width", "height", "wheel_diameter", "wheel_thickness",
    "wheel_bore", "axle_diameter", "axle_length", "wheelbase", "wheel_gap", "axle_clearance",
)
_PARTS = ("chassis", "axle", "wheel")
_PROFILES = {
    "ribbed": ("Off-Road", "#a5b453", "#333a32"),
    "beveled": ("Racing", "#f24853", "#303b55"),
    "balloon": ("Monster Truck", "#fb9a35", "#463241"),
    "crowned": ("Lunar Explorer", "#8cacf8", "#323e60"),
    "stepped": ("Cartoon Vehicle", "#ed84c2", "#754d99"),
}
_RECIPE_COLORS = {
    "Lunar Rover": ("#b7ef58", "#384067"),
    "Pocket Racer": ("#fdaf42", "#343b42"),
    "Rescue Truck": ("#c390f4", "#3f3248"),
    "Workshop Buggy": ("#ff693c", "#303b55"),
}
_COLORS = {
    "lime green": "#b7ef58", "lime": "#b7ef58", "green": "#5de399",
    "pink": "#ff80a5", "orange": "#ff703c", "red": "#ee495e", "yellow": "#ffd459",
    "blue": "#5f9ffc", "teal": "#53e5d3", "purple": "#ae8af3",
    "black": "#34364a", "white": "#eef0f7",
}
_RECIPES = {
    "Lunar Rover": (3, 127, 43, 19, 35, 12, 90, "crowned"),
    "Pocket Racer": (2, 86, 33, 9, 25, 8, 62, "beveled"),
    "Rescue Truck": (2, 112, 47, 25, 44, 14, 73, "ribbed"),
    "Workshop Buggy": (2, 95, 38, 14, 36, 10, 66, "straight"),
}
_STYLE_RULES = (
    ("Lunar Rover", r"\b(?:moon|lunar|mars|space|rover)\b"),
    ("Rescue Truck", r"\b(?:rescue|truck|heavy[ -]duty|monster)\b"),
    ("Pocket Racer", r"\b(?:race|racer|racing|speed|pocket[ -]sized|low[ -]profile)\b"),
)
_COUNT_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_WHEEL_COUNT = re.compile(
    rf"\b({'|'.join(_COUNT_WORDS)}|\d+)[\s\-‑]+wheel(?:s|ed|er)?\b"
)
_VEHICLE = re.compile(r"\b(?:car|rover|buggy|truck|vehicle|racer|kart)\b")
_CONCEPT_ONLY = {
    "powered motion": r"\b(?:battery|electric|motor(?:ized|ised)?|remote[ -]control)\b",
    "flight": r"\b(?:fl(?:y|ies|ying)|wings?|rockets?|jet engines?)\b",
    "lighting": r"\b(?:leds?|lights?|lighting)\b",
    "movable accessories": r"\b(?:arms?|claws?|cranes?|suspension|steering)\b",
    "obstacle climbing": r"\bclimb(?:s|ing)?\b",
}
_FEASIBILITY = (
    "The workshop generates editable rolling vehicles from local recipes. "
    "Appearance and custom features outside those recipes remain concept notes.",
    "Nominal slip fits need prototype testing and separate wheel retainers. "
    "Materials, print settings, durability and age suitability require separate checks.",
)
_MEASURE = _measurement()
_LEADING_MEASURE = rf"(?<![\w.+/\-]){_MEASURE}"
_MEASURES = {
    "length": (
        rf"\b(?:chassis |body )?length\s*(?:of |is |[:=])?\s*{_MEASURE}",
        rf"{_LEADING_MEASURE}\s+long\b",
    ),
    "width": (rf"\b(?:chassis|body) width\s*(?:of |is |[:=])?\s*{_MEASURE}",),
    "height": (rf"\b(?:chassis|body) height\s*(?:of |is |[:=])?\s*{_MEASURE}",),
    "wheel_diameter": (
        rf"\bwheel diameter\s*(?:of |is |[:=])?\s*{_MEASURE}",
        rf"{_LEADING_MEASURE}[\s\-‑]+(?:diameter\s+)?wheels?\b",
    ),
    "wheel_thickness": (rf"\bwheel thickness\s*(?:of |is |[:=])?\s*{_MEASURE}",),
    "wheelbase": (rf"\bwheelbase\s*(?:of |is |[:=])?\s*{_MEASURE}",),
}


def _text(value: object, label: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit or not value.isprintable():
        raise DesignError(f"Use 1 to {limit} printable characters for {label}.")
    return value.strip()


def invent(prompt: str) -> dict:
    """Map a short idea to a feasible geometry recipe and show its assumptions."""
    if not isinstance(prompt, str):
        raise DesignError("Describe your toy in a short sentence.")
    prompt = _text(" ".join(prompt.split()), "the toy idea", 360)
    idea = prompt.casefold()
    concept = next((name for name, rule in _STYLE_RULES if re.search(rule, idea)), "Workshop Buggy")
    axles, length, width, height, diameter, thickness, wheelbase, profile = _RECIPES[concept]
    notes = []
    if not _VEHICLE.search(idea) and concept == "Workshop Buggy":
        notes.append("This idea has been translated into a rolling buggy, the workshop’s general vehicle recipe.")
    concept_only = [label for label, rule in _CONCEPT_ONLY.items() if re.search(rule, idea)]
    if concept_only:
        notes.append(f"Concept notes only: {', '.join(concept_only)}.")
    requested = _WHEEL_COUNT.search(idea)
    if requested:
        token = requested[1]
        count = _COUNT_WORDS.get(token) if not token.isdigit() else int(token)
        if count in (4, 6):
            axles = count // 2
        else:
            notes.append("Only four- and six-wheel chassis are available. This concept uses the recipe’s wheel count.")
    elif re.search(r"\b6\s*[x×]\s*6\b", idea):
        axles = 3
    elif re.search(r"\b4\s*[x×]\s*4\b", idea):
        axles = 2

    if re.search(r"\bwide wheels\b", idea):
        thickness = max(thickness, 13)
    if re.search(r"\blow[ -]profile wheels\b", idea):
        profile = "beveled"
    if re.search(r"\b(?:monster truck|oversized wheels)\b", idea):
        diameter, thickness, profile = max(diameter, 52), max(thickness, 16), "balloon"
    color, tires = _RECIPE_COLORS[concept]
    if requested_color := re.search(r"\b(?:" + "|".join(_COLORS) + r")\b", idea):
        color = _COLORS[requested_color[0]]
    dimensions = {
        "length": length, "width": width, "height": height,
        "wheel_diameter": diameter, "wheel_thickness": thickness, "wheelbase": wheelbase,
    }
    explicit = {}
    for key, (named, *phrases) in _MEASURES.items():
        values = {_parse_measure(match) for match in re.finditer(named, idea)}
        for phrase in phrases:
            values.update(_parse_measure(match) for match in re.finditer(phrase, idea) if match["unit"])
        label = key.replace("_", " ").capitalize()
        if len(values) > 1:
            raise DesignError(f"Give one value for {label.lower()} in the idea.")
        if values:
            explicit[key] = _dimension(values.pop(), label)
    dimensions.update(explicit)
    # Keep unspecified dimensions feasible while respecting the user's explicit targets.
    spacing = (dimensions["wheel_diameter"] + 2) * (axles - 1)
    if "wheelbase" not in explicit:
        dimensions["wheelbase"] = max(wheelbase, spacing)
    if "length" not in explicit:
        dimensions["length"] = max(length, dimensions["wheelbase"] + 15)
    if "height" not in explicit:
        dimensions["height"] = min(height, max(8, dimensions["wheel_diameter"] - 2))
    if "length" in explicit:
        notes.append("The requested length sizes the chassis. The full toy may extend beyond it at the wheels.")
    design = {
        "format": FORMAT, "version": VERSION, "units": "mm", "name": concept,
        "prompt": prompt, "concept": concept, "notes": [*notes, *_FEASIBILITY],
        "axle_count": axles, **dimensions, "wheel_bore": 6.2,
        "axle_diameter": 5.8, "axle_length": dimensions["width"] + 2 * (dimensions["wheel_thickness"] + 3),
        "wheel_gap": 1.2, "axle_clearance": 0.4, "wheel_profile": profile,
        "colors": {"chassis": color, "axle": "#c8d0dc", "wheel": tires},
    }
    return build(design).design


def build(design: object) -> "DreamSpec":
    """Validate a browser design or a saved Dream JSON object before meshing."""
    if not isinstance(design, dict) or design.get("format") != FORMAT:
        raise DesignError("Open a MAGTEL Dream design.")
    if type(design.get("version")) is not int or design["version"] != VERSION or design.get("units") != "mm":
        raise DesignError("Use MAGTEL Dream version 1 in millimeters.")
    if design.keys() - {
        "format", "version", "units", "name", "prompt", "concept", "notes", "axle_count",
        *_FIELDS, "wheel_profile", "colors", "variant",
    }:
        raise DesignError("This Dream design contains unknown parameters.")
    data = dict(design)
    data["name"] = _text(design.get("name"), "the toy name", 80)
    data["prompt"] = _text(design.get("prompt"), "the toy idea", 360)
    data["concept"] = _text(design.get("concept"), "the concept label", 80)
    if "variant" in design:
        data["variant"] = _text(design["variant"], "the variant label", 80)
    notes = design.get("notes")
    if not isinstance(notes, list) or len(notes) > 10:
        raise DesignError("Use a list of at most ten concept notes.")
    data["notes"] = [_text(note, "a concept note", 320) for note in notes]
    if type(design.get("axle_count")) is not int or design["axle_count"] not in (2, 3):
        raise DesignError("Use two or three axles for a four- or six-wheel toy.")
    profile = design.get("wheel_profile")
    if not isinstance(profile, str) or (profile != "straight" and profile not in _PROFILES):
        raise DesignError("Choose a supported wheel profile.")
    colors = design.get("colors")
    if not isinstance(colors, dict) or colors.keys() != set(_PARTS) or not all(
        isinstance(color, str) and re.fullmatch(r"#[\da-fA-F]{6}", color, re.ASCII) for color in colors.values()
    ):
        raise DesignError("Use a six-digit hex color for each part family.")
    data["colors"] = {key: color.lower() for key, color in colors.items()}
    for key in _FIELDS:
        data[key] = _dimension(design.get(key), key.replace("_", " ").capitalize())
    car = CarSpec(
        name=data["name"],
        chassis=ToySpec("block", "Chassis", width=data["length"], depth=data["width"], height=data["height"]),
        axle=ToySpec("axle", "Axle", diameter=data["axle_diameter"], thickness=data["axle_length"]),
        wheel=ToySpec("wheel", "Wheel", diameter=data["wheel_diameter"], thickness=data["wheel_thickness"],
                      hole=data["wheel_bore"]),
        wheelbase=data["wheelbase"], wheel_gap=data["wheel_gap"], axle_clearance=data["axle_clearance"],
    ).validate()
    if data["axle_count"] == 3:
        clearance = max(data["wheel_diameter"], data["axle_diameter"] + data["axle_clearance"]) + 0.1
        if data["wheelbase"] / 2 < clearance - 1e-9:
            raise DesignError(f"Six wheels need an outer wheelbase of at least {mm(2 * clearance)} mm.")
    return DreamSpec(data, car)


def from_car(car: CarSpec) -> dict:
    """Open an existing complete v0.3.0 car with its original nominal parameters."""
    chassis, axle, wheel, wheelbase = car._require_complete()
    return build({
        "format": FORMAT, "version": VERSION, "units": "mm",
        "name": car.name, "prompt": "Imported MAGTEL car assembly",
        "concept": "Imported car", "notes": list(_FEASIBILITY),
        "axle_count": 2, "length": chassis.width, "width": chassis.depth, "height": chassis.height,
        "wheel_diameter": wheel.diameter, "wheel_thickness": wheel.thickness, "wheel_bore": wheel.hole,
        "axle_diameter": axle.diameter, "axle_length": axle.thickness,
        "wheelbase": wheelbase, "wheel_gap": car.wheel_gap, "axle_clearance": car.axle_clearance,
        "wheel_profile": "straight", "colors": {"chassis": "#f08730", "axle": "#b0c2c9", "wheel": "#5299d4"},
    }).design


def variants(design: object) -> list[dict]:
    """Offer five wheel profiles and colorways within the same mounting envelope."""
    current = build(design).design
    return [
        {
            **current, "notes": list(current["notes"]), "variant": name, "wheel_profile": profile,
            "colors": {**current["colors"], "chassis": body_color, "wheel": wheel_color},
        }
        for profile, (name, body_color, wheel_color) in _PROFILES.items()
    ]


@dataclass(frozen=True)
class DreamSpec:
    """A validated set of toy dimensions with shared axle and wheel interfaces."""

    design: dict
    _car: CarSpec

    @property
    def name(self) -> str:
        return self.design["name"]

    def part_meshes(self) -> dict[str, list[Triangle]]:
        parts = self._car.part_meshes()
        d = self.design
        if d["axle_count"] == 3:
            parts["chassis"] = _three_bore_chassis(
                d["length"], d["width"], d["height"], d["wheelbase"],
                (d["axle_diameter"] + d["axle_clearance"]) / 2,
            )
        if d["wheel_profile"] != "straight":
            parts["wheel"] = _profiled_wheel(
                d["wheel_diameter"], d["wheel_thickness"], d["wheel_bore"], d["wheel_profile"],
            )
        return parts

    def components(self) -> dict[str, list[Triangle]]:
        d = self.design
        parts = self.part_meshes()
        radius = d["wheel_diameter"] / 2
        base = radius - d["height"] / 2
        placed = {
            "chassis": [tuple((x, y, z + base) for x, y, z in face) for face in parts["chassis"]]
        }
        positions = [("front", d["wheelbase"] / 2), ("rear", -d["wheelbase"] / 2)]
        if d["axle_count"] == 3:
            positions.insert(1, ("middle", 0))
        inside = d["width"] / 2 + d["wheel_gap"]
        for end, x in positions:
            placed[f"{end}-axle"] = _on_axle(parts["axle"], x, -d["axle_length"] / 2, radius)
            placed[f"{end}-left-wheel"] = _on_axle(parts["wheel"], x, inside, radius)
            placed[f"{end}-right-wheel"] = _on_axle(parts["wheel"], x, -inside - d["wheel_thickness"], radius)
        return placed

    def dimensions(self) -> dict:
        d = self.design
        return {
            "length": max(d["length"], d["wheelbase"] + d["wheel_diameter"]),
            "width": d["axle_length"], "height": d["wheel_diameter"],
        }

    def fit(self) -> dict:
        d = self.design
        return {
            "wheel_bore_clearance": round(d["wheel_bore"] - d["axle_diameter"], 12),
            "chassis_bore_clearance": d["axle_clearance"], "wheel_gap": d["wheel_gap"],
            "axle_overhang": round(max(0, (d["axle_length"] - d["width"]) / 2
                                      - d["wheel_gap"] - d["wheel_thickness"]), 12),
            "ground_clearance": round((d["wheel_diameter"] - d["height"]) / 2, 12),
        }

    def bom(self) -> list[dict]:
        d = self.design
        rows = (
            ("chassis", 1, f'{mm(d["length"])} × {mm(d["width"])} × {mm(d["height"])} mm'),
            ("axle", d["axle_count"], f'Ø{mm(d["axle_diameter"])} × {mm(d["axle_length"])} mm'),
            ("wheel", 2 * d["axle_count"], f'Ø{mm(d["wheel_diameter"])} × {mm(d["wheel_thickness"])} mm'
                                         f' · Ø{mm(d["wheel_bore"])} mm bore'),
        )
        return [
            {"part": part, "quantity": quantity, "dimensions": dimensions, "material": "User-selected"}
            for part, quantity, dimensions in rows
        ]

    def describe(self) -> str:
        d = self.design
        parts = [f'  {row["quantity"]} × {row["part"]} — {row["dimensions"]}' for row in self.bom()]
        return "\n".join((
            f'{self.name} — {2 * d["axle_count"]}-wheel Dream assembly',
            *parts, f'  Wheelbase — {mm(d["wheelbase"])} mm between outer axle centers',
            f'  Wheel profile — {d["wheel_profile"]}',
        ))

    def fit_report(self) -> str:
        return self._car.fit_report()


def _three_bore_chassis(length: float, width: float, height: float, wheelbase: float,
                        radius: float) -> list[Triangle]:
    """Join three bored sections at symmetric, coincident cap edges."""
    quarter = [
        (math.cos(math.tau * i / _CIRCLE_SEGMENTS), math.sin(math.tau * i / _CIRCLE_SEGMENTS))
        for i in range(1, _CIRCLE_SEGMENTS // 4)
    ]
    rays = [
        (1.0, 0.0), *quarter, (0.0, 1.0), *((-x, z) for x, z in reversed(quarter)),
        (-1.0, 0.0), *((-x, -z) for x, z in quarter), (0.0, -1.0),
        *((x, -z) for x, z in reversed(quarter)),
    ]
    seam, pitch = wheelbase / 4, wheelbase / 2
    faces = []
    for start, center, end in ((-length / 2, -pitch, -seam), (-seam, 0, seam), (seam, pitch, length / 2)):
        faces.extend(_bored_chassis_section(
            width, height / 2, radius, center, start, end, rays,
            open_start=center != -pitch, open_end=center != pitch,
        ))
    return faces


def _profiled_wheel(diameter: float, thickness: float, bore: float, profile: str) -> list[Triangle]:
    """Revolve a shoulder profile while preserving the through bore and mounting span."""
    profiles = {
        "beveled": ((0, 1), (0.22, 0), (0.78, 0), (1, 1)),
        "crowned": ((0, 1), (0.14, 0.46), (0.30, 0.13), (0.5, 0),
                    (0.70, 0.13), (0.86, 0.46), (1, 1)),
        "ribbed": ((0, 0.6), (0.14, 0), (0.23, 0), (0.34, 0.8), (0.40, 0.8),
                   (0.46, 0), (0.54, 0), (0.60, 0.8), (0.66, 0.8), (0.77, 0),
                   (0.86, 0), (1, 0.6)),
        "balloon": ((0, 1.4), (0.08, 0.8), (0.20, 0.24), (0.34, 0), (0.66, 0),
                    (0.80, 0.24), (0.92, 0.8), (1, 1.4)),
        "stepped": ((0, 0.55), (0.16, 0.55), (0.16, 1.25), (0.30, 1.25),
                    (0.30, 0), (0.70, 0), (0.70, 1.25), (0.84, 1.25),
                    (0.84, 0.55), (1, 0.55)),
    }
    radius = diameter / 2
    relief = min(diameter * 0.06, (radius - bore / 2) / 2, thickness / 3)
    directions = [
        (math.cos(math.tau * i / _CIRCLE_SEGMENTS), math.sin(math.tau * i / _CIRCLE_SEGMENTS))
        for i in range(_CIRCLE_SEGMENTS)
    ]
    rings = [
        [(x * (radius - relief * inset), y * (radius - relief * inset), depth * thickness) for x, y in directions]
        for depth, inset in profiles[profile]
    ]
    bore_base = [(x * bore / 2, y * bore / 2, 0) for x, y in directions]
    bore_top = [(x, y, thickness) for x, y, _ in bore_base]
    faces = []
    for i in range(_CIRCLE_SEGMENTS):
        j = (i + 1) % _CIRCLE_SEGMENTS
        for lower, upper in zip(rings, rings[1:]):
            _quad(faces, lower[i], lower[j], upper[j], upper[i])
        _quad(faces, bore_base[j], bore_base[i], bore_top[i], bore_top[j])
        _quad(faces, rings[0][j], rings[0][i], bore_base[i], bore_base[j])
        _quad(faces, rings[-1][i], rings[-1][j], bore_top[j], bore_top[i])
    return faces
