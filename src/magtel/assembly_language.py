"""Translate a toy-car description into components and mating dimensions."""

import re
from dataclasses import replace
from pathlib import Path
from typing import Callable

from .assembly import CarSpec
from .language import _POLITE, _dimension, _measurement, parse
from .model import DesignError, ToySpec


_FLAGS = re.IGNORECASE
_MEASURE = _measurement()
_CAR_START = re.compile(
    r"^(?:(?:make|build|assemble|design|create|model|start(?:\s+with)?)\s+(?:me\s+)?)?"
    r"(?:(?:a|an|new)\s+(?:new\s+)?)?(?:toy\s+car|car(?:\s+assembly)?)"
    r"(?=\s|$|[,.!?;:])",
    _FLAGS,
)
_SEPARATOR = re.compile(
    r""""[^"]*"|(?<!\w)'[^']*'|;|,\s*(?:and\s+)?(?:then\s+)?"""
    r"(?=(?:use|mount|install|put|attach|fit|move|set|leave|give|add)\b)",
    _FLAGS,
)
_NAME = re.compile(
    r"""^(?:named|called|call it|name it|rename(?:\s+it)?(?:\s+to)?)\s+"""
    r"""(?:"(?P<double>[^"]+)"|'(?P<single>[^']+)'|(?P<plain>[^"']+))$""",
    _FLAGS,
)
_ROLE = r"(?:chassis|axles?|wheels?)"
_ROLE_IN_TEXT = re.compile(rf"\b{_ROLE}\b(?![\s-]+(?:hole|bore)\b)", _FLAGS)
_COMPONENT_ACTION = re.compile(
    r"^(?:use|reuse|load|import|add|put|fit|attach|mount|install|make|set|change|replace|design|build)\s+",
    _FLAGS,
)
_DETERMINER = re.compile(r"^(?:(?:a|an|the|identical|matching)\s+)+", _FLAGS)
_COUNT = re.compile(r"^(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+", _FLAGS)
_COUNT_WORDS = "one two three four five six seven eight nine ten".split()
_DIAMETER = re.compile(rf"(?:Ø|⌀)?\s*{_MEASURE}", _FLAGS)
_SAVED = re.compile(
    rf"""^(?P<role>{_ROLE})\s+from\s+(?:"(?P<double>[^"]+)"|'(?P<single>[^']+)'|"""
    r"""(?P<plain>[^\s"']+))(?P<rest>.*)$""",
    _FLAGS,
)
_AXLE_SPACING = re.compile(rf"{_MEASURE}\s+apart\b", _FLAGS)
_AXLE_PLACEMENT = (
    r"(?:through\s+(?:the\s+)?chassis|(?:at|on)\s+(?:the\s+)?"
    r"front\s+and\s+(?:the\s+)?(?:rear|back))"
)
_WHEEL_PLACEMENT = (
    r"(?:(?:one\s+)?(?:on|at|onto|to)\s+(?:(?:each|every)\s+(?:axle\s+)?end"
    r"|(?:both|the)\s+ends?)(?:\s+of\s+(?:each|both|the)\s+axles?)?"
    r"|one\s+(?:per|at\s+each)\s+corner)"
)
_PLACEMENT = {
    role: re.compile(rf"(?:^|[\s,]+){pattern}\s*$", _FLAGS)
    for role, pattern in (("axle", _AXLE_PLACEMENT), ("wheel", _WHEEL_PLACEMENT))
}
_CHASSIS_WIDTH = re.compile(r"\b(width|wide|across)\b", _FLAGS)
_RELATIONS = (
    ("wheelbase", rf"(?:set|make|change|adjust)\s+(?:the\s+)?wheel\s*base\s+(?:to\s+)?{_MEASURE}"),
    ("wheelbase", rf"(?:move|space|set|position|place|put|mount)\s+(?:the\s+)?axles\s+{_MEASURE}\s+apart"),
    ("wheelbase", rf"(?:wheel\s*base|axle\s+spacing)(?:\s+of)?\s+{_MEASURE}"),
    ("wheel_gap", rf"(?:leave|allow|keep)\s+(?:a\s+)?{_MEASURE}\s+(?:gap\s+)?"
                  r"between\s+(?:each\s+|the\s+)?wheels?\s+and\s+(?:the\s+)?chassis"),
    ("wheel_gap", rf"(?:set|make|change|adjust)\s+(?:the\s+)?wheel\s+gap\s+(?:to\s+)?{_MEASURE}"),
    ("axle_clearance", rf"(?:set|make|change|adjust)\s+(?:the\s+)?"
                       rf"(?:chassis\s+)?axle\s+clearance\s+(?:to\s+)?{_MEASURE}"),
    ("axle_clearance", rf"(?:give|leave|allow)\s+(?:the\s+)?(?:chassis\s+)?axle\s+"
                       rf"(?:holes|bores)\s+{_MEASURE}\s+(?:diametral\s+)?clearance"),
)
_RELATION_PATTERNS = tuple((field, re.compile(pattern, _FLAGS)) for field, pattern in _RELATIONS)


def _clean(text: str) -> str:
    return _POLITE.sub("", text.strip()).rstrip(" .!?")


def starts_car(text: str) -> bool:
    """Recognize a request to start a car before parsing individual parts."""
    return bool(_CAR_START.match(_clean(text)))


def _statements(text: str) -> list[str]:
    statements = []
    start = 0
    for match in _SEPARATOR.finditer(text):
        if match[0].startswith(('"', "'")):
            continue
        statements.append(_clean(text[start:match.start()]))
        start = match.end()
    statements.append(_clean(text[start:]))
    return [statement for statement in statements if statement]


def _without_count(text: str, role: str) -> str:
    match = _COUNT.match(text)
    if not match:
        return text
    remaining = text[match.end():]
    if not (_ROLE_IN_TEXT.match(remaining) or _DIAMETER.match(remaining)
            or remaining.lower().startswith(("matching ", "identical ", "solid "))):
        return text
    value = match["count"].lower()
    expected = {"chassis": 1, "axle": 2, "wheel": 4}[role]
    if value not in (str(expected), _COUNT_WORDS[expected - 1]):
        label = {"chassis": "one chassis", "axle": "two axles", "wheel": "four wheels"}[role]
        raise DesignError(f"A toy car uses {label}. Give the dimensions for one design.")
    return _DETERMINER.sub("", remaining)


def _placements(role: str, description: str) -> tuple[str, dict[str, float]]:
    changes = {}
    if role in _PLACEMENT:
        description = _PLACEMENT[role].sub("", description).strip(" ,")
    if role == "axle":
        for match in _AXLE_SPACING.finditer(description):
            if description[match.end():].strip(" ,"):
                continue
            changes["wheelbase"] = _dimension(match)
            description = description[:match.start()].rstrip(" ,")
            description = re.sub(r"\s+(?:and|then|with)$", "", description, flags=_FLAGS)
            description = _PLACEMENT[role].sub("", description).strip(" ,")
            break
    return description, changes


def _saved_part(
    match: re.Match[str], load_component: Callable[[Path], ToySpec] | None,
) -> dict[str, object]:
    if load_component is None:
        raise DesignError("Use saved component files from the MAGTEL CLI.")
    role = _role(match["role"])
    extra, changes = _placements(role, match["rest"])
    if extra.strip():
        raise DesignError("Quote file paths with spaces and put the placement after the closing quote.")
    filename = match["double"] or match["single"] or match["plain"]
    try:
        path = Path(filename).expanduser()
    except RuntimeError as error:
        raise DesignError(f"Could not resolve the home folder in \"{filename}\".") from error
    return {role: load_component(path), **changes}


def _role(word: str) -> str:
    word = word.lower()
    return word if word == "chassis" else word.rstrip("s")


def _component(statement: str, car: CarSpec) -> dict[str, object]:
    match = _ROLE_IN_TEXT.search(statement)
    if not match:
        raise DesignError(
            f'I couldn’t understand "{statement[:100]}". Try "Use an 80 x 30 x 12 mm chassis" '
            'or "Move the axles 55 mm apart".'
        )
    role = _role(match[0])
    statement = _without_count(statement, role)
    match = _ROLE_IN_TEXT.search(statement)
    assert match is not None
    before, after = statement[:match.start()].strip(" ,"), statement[match.end():].strip(" ,")
    after, changes = _placements(role, after)
    kind = "block" if role == "chassis" else role
    current = getattr(car, role)

    if role == "chassis":
        # In a car, length runs from front to rear. A plain block stores that
        # dimension as width and the car's side-to-side width as depth.
        description = " ".join(part for part in (before, after) if part)
        description = _CHASSIS_WIDTH.sub(
            lambda label: "depth" if label[0].lower() == "width" else "deep", description
        )
        request = f"{kind} {description}".strip()
    elif before and _DIAMETER.fullmatch(before):
        # Put an unlabeled leading measurement before the part name so the
        # part parser uses it as the diameter.
        request = f"{before} {kind} {after}".strip()
    elif before.lower() == "solid":
        request = f"solid {kind} {after}".strip()
    else:
        request = " ".join(part for part in (kind, before, after) if part)

    part = current if request == kind and current else parse(request, current)
    return {role: part, **changes}


def parse_car(
    text: str,
    current: CarSpec | None = None,
    *,
    load_component: Callable[[Path], ToySpec] | None = None,
) -> CarSpec:
    """Describe or revise a symmetric toy car, one or more statements at a time."""
    statements = _statements(text)
    if not statements:
        raise DesignError('Describe the car or a change, such as "Move the axles 55 mm apart".')
    car = current if current is not None else CarSpec()
    start = _CAR_START.match(statements[0])
    if start:
        car = CarSpec()
        tail = statements[0][start.end():].lstrip(" ,:")
        statements = [re.sub(r"^with\s+", "", tail, flags=_FLAGS)] + statements[1:]

    for statement in statements:
        if not statement:
            continue
        match = _NAME.fullmatch(statement)
        if match:
            car = replace(car, name=match["double"] or match["single"] or match["plain"].strip())
            continue
        for field, pattern in _RELATION_PATTERNS:
            match = pattern.fullmatch(statement)
            if match:
                car = replace(car, **{field: _dimension(match)})
                break
        else:
            statement = _DETERMINER.sub("", _COMPONENT_ACTION.sub("", statement))
            saved = _SAVED.fullmatch(statement)
            if saved:
                changes = _saved_part(saved, load_component)
            else:
                changes = _component(statement, car)
            car = replace(car, **changes)
    return car.validate()
