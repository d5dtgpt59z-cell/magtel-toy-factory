"""Translate a small vocabulary of everyday CAD requests into editable dimensions."""

from dataclasses import replace
import re

from .model import DesignError, ToySpec


_EXAMPLE = 'Try "make a 40 mm wheel, 10 mm thick, with a 6 mm axle hole".'
_FLAGS = re.IGNORECASE
_ONES = (
    "zero one two three four five six seven eight nine ten eleven twelve "
    "thirteen fourteen fifteen sixteen seventeen eighteen nineteen"
).split()
_TENS = "twenty thirty forty fifty sixty seventy eighty ninety".split()
_INTEGER = (
    rf"(?:\d+|(?:{'|'.join(_TENS)})(?:[ -](?:{'|'.join(_ONES[1:10])}))?"
    rf"|{'|'.join(_ONES)})"
)
_NUMBER = rf"(?:[+\-]?(?:\d+(?:\.\d+)?|\.\d+)|{_INTEGER})"
_UNIT = (
    r"millimet(?:er|re)s?|centimet(?:er|re)s?|inches|inch|mm|cm"
    r"|in(?!\s+(?:diameter|width|depth|height|length|thickness)\b)"
)


def _measurement(prefix: str = "") -> str:
    return (
        rf"(?P<{prefix}value>{_NUMBER})(?:\s*[-‑]?\s*(?P<{prefix}unit>{_UNIT}))?"
        r"(?=$|[^\w.]|x(?=[+\-]?(?:\d|\.)))"
    )


_MEASURE = _measurement()
_CROSS = r"\s*(?:×|x|\bby\b)\s*"
_TRIPLE = _CROSS.join(_measurement(prefix) for prefix in ("w_", "d_", "h_"))
_GRID = rf"(?P<columns>{_INTEGER}){_CROSS}(?P<rows>{_INTEGER})(?!\w)"
_SHAPE = r"(?P<shape>toy\s+wheel|wheel|building\s+block|block|brick|axle|shaft)\b"
_MODIFIER = (
    rf"(?:(?P<solid>solid)\s+)?(?:(?P<size>{_TRIPLE}|(?:Ø|⌀)?\s*{_MEASURE})\s*[-‑]?\s*"
    r"(?:(?:in\s+)?(?P<pre_label>diameter|wide|across)\s+)?)?"
)
_NEW = re.compile(
    rf"^(?P<create>(?:make|build|design|create|model|start(?:\s+with)?)\s+"
    rf"(?:me\s+)?(?P<pronoun>it\s+)?)?(?P<article>(?:a|an|new)\s+(?:new\s+)?)?"
    rf"{_MODIFIER}{_SHAPE}(?!\s+(?:hole|bore)\b)",
    _FLAGS,
)
_EDIT = re.compile(
    rf"^(?:make|give|set|change|update|adjust|edit)\s+(?:it\b|(?:the\s+)?{_SHAPE})"
    rf"(?!\s+(?:hole|bore)\b)(?:\s+(?:to\s+have|so\s+it\s+has)\b)?",
    _FLAGS,
)
_POLITE = re.compile(
    r"^(?:(?:please|(?:can|could|would) you|i(?:['’]d| would) like|i want)\s+"
    r"(?:to\s+)?)+", _FLAGS,
)
_JOIN = re.compile(
    r"^(?:(?:,|;)|(?:and|then|with|a|an|the|of|to|set|change|update|adjust|add|"
    r"drill|(?:give|make)\s+it|make)\b)\s*",
    _FLAGS,
)
_NAME = re.compile(
    r"""^(?:call(?:\s+it)?|name(?:\s+it)?|named|rename(?:\s+it)?(?:\s+to)?)\s+"""
    r"""(?:"(?P<double>[^"]+)"|'(?P<single>[^']+)'|"""
    r"""(?P<plain>[^,;]+?)(?=\s+(?:with|without|and|then)\b|[,;]|$))""",
    _FLAGS,
)
_BORE = r"(?:(?:(?:center(?:ed)?|centre(?:d)?|central|through|axle)[\s-]+)*(?:hole|bore))"
_FIELD = (
    rf"stud\s+(?:diameter|height)|(?:outer\s+)?diameter|{_BORE}(?:\s+diameter)?"
    r"|width|depth|height|length|thickness|wide|deep|high|tall|long|thick|across"
)
_FIELD_CLAUSE = (
    ("size", rf"{_TRIPLE}(?:\s*\(\s*w\s*[×x]\s*d\s*[×x]\s*h\s*\))?"),
    ("remove_hole", rf"(?:without|no|remove)\s+(?:(?:an?|the)\s+)?{_BORE}\b|solid\b"),
    ("remove_studs", r"(?:without|no|remove(?:\s+the)?)\s+(?:the\s+)?studs\b"),
    ("studs", rf"{_GRID}\s+(?:(?:grid\s+of\s+)?studs?\b|stud\s+grid\b)"),
    ("studs", rf"studs?\s+(?:grid\s+|in\s+(?:an?\s+)?)?{_GRID}(?:\s+grid)?\b"),
    ("relative", rf"(?P<direction>increase|decrease|reduce)\s+(?:the\s+)?"
                 rf"(?P<label>{_FIELD})\s+by\s+{_MEASURE}"),
    ("relative", rf"(?P<label>{_FIELD})\s+{_MEASURE}\s+"
                 rf"(?P<direction>larger|bigger|smaller)\b"),
    ("comparative", rf"(?:by\s+)?{_MEASURE}\s+(?P<label>wider|narrower|deeper|"
                    r"shallower|taller|shorter|longer|thicker|thinner)\b"),
    ("comparative", r"(?P<label>wider|narrower|deeper|shallower|taller|shorter|"
                    rf"longer|thicker|thinner)\s+by\s+{_MEASURE}"),
    ("field", rf"{_MEASURE}\s*(?:in\s+)?(?P<label>{_FIELD})\b"
              rf"(?!\s+(?:of\b|to\b|{_BORE}\b|studs?\b))"),
    ("field", rf"(?:Ø|⌀)\s*{_MEASURE}"),
    ("field", rf"(?P<label>{_FIELD})\s*(?:of\b|to\b|is\b|at\b|=|:)?\s*"
              rf"(?:Ø|⌀)?\s*{_MEASURE}"),
    ("field", rf"{_MEASURE}\s+(?:diameter\s+|wide\s+)?(?P<label>{_BORE})\b"),
    ("stud_diameter", rf"{_MEASURE}\s+diameter\s+studs?\b"),
    ("stud_height", rf"{_MEASURE}\s+(?:high|tall)\s+studs?\b"),
    ("default_hole", rf"{_BORE}\b"),
)
_CLAUSES = tuple((kind, re.compile(rf"^(?:{pattern})", _FLAGS)) for kind, pattern in _FIELD_CLAUSE)
_COMPARATIVES = {
    "wider": ("wide", 1), "narrower": ("wide", -1),
    "deeper": ("deep", 1), "shallower": ("deep", -1),
    "taller": ("tall", 1), "shorter": ("height", -1),
    "longer": ("length", 1), "thicker": ("thick", 1), "thinner": ("thick", -1),
}
_FIELDS = {
    "wheel": {"diameter", "thickness", "hole"},
    "axle": {"diameter", "thickness"},
    "block": {"width", "depth", "height", "studs", "stud_diameter", "stud_height"},
}
_KIND = {
    "wheel": "wheel", "toy wheel": "wheel", "axle": "axle", "shaft": "axle",
    "block": "block", "building block": "block", "brick": "block",
}


def _words(text: str) -> str:
    return " ".join(text.lower().split())


def _number(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        words = value.lower().replace("-", " ").split()
        if words[0] in _TENS:
            tens = (_TENS.index(words[0]) + 2) * 10
            ones = _ONES.index(words[1]) if len(words) > 1 else 0
            return float(tens + ones)
        return float(_ONES.index(words[0]))


def _dimension(match: re.Match[str], prefix: str = "", fallback_unit: str | None = None) -> float:
    value = _number(match[prefix + "value"])
    unit = match[prefix + "unit"] or fallback_unit or "mm"
    return round(value * _unit_factor(unit), 12)


def _unit_factor(unit: str) -> float:
    unit = unit.lower()
    if unit.startswith("in"):
        return 25.4
    if unit.startswith(("cm", "centi")):
        return 10
    return 1


def _field(kind: str, label: str) -> str:
    label = _words(label)
    if label in ("width", "wide", "across"):
        return "width" if kind == "block" else "diameter"
    if label in ("length", "long"):
        return "width" if kind == "block" else "thickness"
    if label in ("thickness", "thick"):
        return "height" if kind == "block" else "thickness"
    if label in ("height", "high", "tall"):
        return "height"
    if label in ("depth", "deep"):
        return "depth"
    if re.fullmatch(rf"{_BORE}(?:\s+diameter)?", label):
        return "hole"
    if label == "outer diameter":
        return "diameter"
    return label.replace(" ", "_")


def _unknown(text: str) -> DesignError:
    return DesignError(f'I couldn’t understand "{text[:100]}". {_EXAMPLE}')


def _apply_clause(
    spec: ToySpec, changes: dict[str, object], operation: str, match: re.Match[str],
    *, label: str | None = None,
) -> None:
    def set_field(field: str, value: object) -> None:
        if field not in _FIELDS[spec.kind]:
            raise DesignError(f'The {spec.kind} does not support {field.replace("_", " ")} in MAGTEL.')
        if field in changes:
            raise DesignError(f'Give one value for {field.replace("_", " ")} at a time.')
        changes[field] = value

    if operation == "size":
        if spec.kind != "block":
            raise DesignError("Three dimensions describe a block. Give a wheel or axle a diameter and thickness.")
        units = [match[prefix + "unit"] for prefix in ("w_", "d_", "h_")]
        explicit = [unit for unit in units if unit]
        if len(explicit) < len(units) and len({_unit_factor(unit) for unit in explicit}) > 1:
            raise DesignError("When mixing units, include the unit for each block dimension.")
        fallback_unit = explicit[0] if explicit else None
        for field, prefix in (("width", "w_"), ("depth", "d_"), ("height", "h_")):
            set_field(field, _dimension(match, prefix, fallback_unit))
    elif operation == "studs":
        try:
            studs = tuple(int(_number(match[axis])) for axis in ("columns", "rows"))
        except OverflowError as error:
            raise DesignError("Use 1 to 20 columns and rows for the stud grid.") from error
        set_field("studs", studs)
    elif operation == "remove_studs":
        set_field("studs", None)
    elif operation in ("remove_hole", "default_hole"):
        hole = spec.hole if spec.hole is not None else ToySpec.default("wheel").hole
        set_field("hole", None if operation == "remove_hole" else hole)
    elif operation in ("relative", "comparative"):
        if operation == "comparative":
            label, direction = _COMPARATIVES[match["label"].lower()]
            if label == "height" and spec.kind == "axle":
                label = "length"
        else:
            label = match["label"]
            direction = -1 if match["direction"].lower() in ("decrease", "reduce", "smaller") else 1
        field = _field(spec.kind, label)
        previous = getattr(spec, field, None)
        if previous is None:
            raise DesignError(f'Give an exact value for {field.replace("_", " ")} first.')
        distance = _dimension(match)
        if distance <= 0:
            raise DesignError("Give a positive amount for a relative change.")
        set_field(field, round(previous + direction * distance, 12))
    else:
        label = label or match.groupdict().get("label")
        field = _field(spec.kind, label) if label else (
            operation if operation in ("stud_diameter", "stud_height") else "diameter"
        )
        set_field(field, _dimension(match))


def parse(text: str, current: ToySpec | None = None) -> ToySpec:
    """Build or revise a part. Unknown clauses and conflicting dimensions fail explicitly."""
    remaining = _POLITE.sub("", text.strip()).rstrip(" .!?")
    remaining = re.sub(r"\s*,?\s+please$", "", remaining, flags=_FLAGS)
    if not remaining:
        raise DesignError(f"Describe a toy part or a change. {_EXAMPLE}")

    spec = current
    changes = {}
    new = _NEW.match(remaining)
    edit = _EDIT.match(remaining)
    if new:
        kind = _KIND[_words(new["shape"])]
        editing_same = current and current.kind == kind and (
            new["pronoun"] or not (new["create"] or new["article"])
        )
        spec = current if editing_same else ToySpec.default(kind)
        if new["solid"] and kind == "wheel":
            changes["hole"] = None
        if new["size"]:
            if new["w_value"]:
                _apply_clause(spec, changes, "size", new)
            elif new["pre_label"]:
                _apply_clause(spec, changes, "field", new, label=new["pre_label"])
            elif kind == "block":
                raise DesignError("Give a block three dimensions as width × depth × height, or name each dimension.")
            else:
                changes["diameter"] = _dimension(new)
        remaining = remaining[new.end():]
    elif edit and current:
        if edit["shape"] and _KIND[_words(edit["shape"])] != current.kind:
            raise DesignError(f'The current part is a {current.kind}. Start a new {edit["shape"]} first.')
        remaining = remaining[edit.end():]

    if spec is None:
        raise DesignError(f"Start by describing a wheel, axle, or block. {_EXAMPLE}")

    while remaining.strip():
        remaining = remaining.lstrip()
        join = _JOIN.match(remaining)
        if join:
            remaining = remaining[join.end():]
            if not remaining:
                raise DesignError("Finish the last change after the connector.")
            continue
        name = _NAME.match(remaining)
        if name:
            if "name" in changes:
                raise DesignError("Give the part one name at a time.")
            plain = name["plain"]
            if plain and plain.startswith(('"', "'")):
                raise DesignError("Close the quotes around the part name.")
            changes["name"] = (name["double"] or name["single"] or plain).strip()
            remaining = remaining[name.end():]
            continue
        for operation, pattern in _CLAUSES:
            match = pattern.match(remaining)
            if match:
                _apply_clause(spec, changes, operation, match)
                remaining = remaining[match.end():]
                break
        else:
            raise _unknown(remaining)

    if current is spec and not changes:
        raise DesignError('Describe what to change, such as "make it 5 mm wider".')
    if spec.kind == "block":
        if changes.get("studs", spec.studs):
            changes.setdefault("stud_diameter", spec.stud_diameter if spec.stud_diameter is not None else 5.0)
            changes.setdefault("stud_height", spec.stud_height if spec.stud_height is not None else 2.0)
        elif "studs" in changes and not {"stud_diameter", "stud_height"} & changes.keys():
            changes.update(stud_diameter=None, stud_height=None)
    return replace(spec, **changes).validate()
