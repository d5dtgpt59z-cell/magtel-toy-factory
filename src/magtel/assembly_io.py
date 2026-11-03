"""Save editable car assemblies and export their assembled or loose meshes."""

from dataclasses import fields
from itertools import chain
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .assembly import CarSpec
from .dream_model import DreamSpec, build as build_dream
from .mesh import stl_bytes, write_mesh_stl
from .model import DesignError, ToySpec
from .project import (
    decode_part,
    decode_part_parameters,
    part_parameters,
    read_json,
    write_json,
    write_output,
)

FORMAT = "magtel-assembly"
VERSION = 1
_CAR_FIELDS = tuple(field.name for field in fields(CarSpec))
_PRINT_COUNTS = {"chassis": 1, "axle": 2, "wheel": 4}


def load_design(path: Path) -> ToySpec | CarSpec | DreamSpec:
    """Open an existing MAGTEL design from its format marker."""
    data = read_json(path, label="MAGTEL design")
    if isinstance(data, dict):
        if data.get("format") == FORMAT:
            return decode_car(data, path)
        if data.get("format") == "magtel-dream":
            return build_dream(data)
    return decode_part(data, path)


def load_car(path: Path) -> CarSpec:
    return decode_car(read_json(path, label="MAGTEL assembly"), path)


def decode_car(data: object, path: Path) -> CarSpec:
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise DesignError(f"{path} is not a MAGTEL assembly. Open an editable car file.")
    if type(data.get("version")) is not int or data["version"] != VERSION:
        raise DesignError(f"{path} uses an unsupported MAGTEL assembly version.")
    if data.get("units") != "mm":
        raise DesignError("MAGTEL assembly files must use millimeters.")
    parameters = data.get("assembly")
    if not isinstance(parameters, dict) or parameters.get("kind") != "car":
        raise DesignError(f"{path} does not describe a MAGTEL toy car.")
    if not parameters.keys() <= {"kind", *_CAR_FIELDS}:
        raise DesignError(f"{path} contains unknown assembly parameters.")
    values = {field: parameters[field] for field in _CAR_FIELDS if field in parameters}
    for component in _PRINT_COUNTS:
        if values.get(component) is not None:
            values[component] = decode_part_parameters(values[component], path)
    return CarSpec(**values).validate()


def save_car(spec: CarSpec, path: Path, *, force: bool = False) -> None:
    spec.validate()
    parameters: dict[str, object] = {"kind": "car"}
    for field in _CAR_FIELDS:
        value = getattr(spec, field)
        if value is not None:
            parameters[field] = part_parameters(value) if isinstance(value, ToySpec) else value
    data = {"format": FORMAT, "version": VERSION, "units": "mm", "assembly": parameters}
    write_json(data, path, force=force)


def export_car(spec: CarSpec, path: Path, *, force: bool = False) -> None:
    """Export the seven positioned solids as one STL for viewing."""
    triangles = list(chain.from_iterable(spec.components().values()))
    write_output(path, lambda temp: write_mesh_stl(triangles, temp), force=force)


def export_parts(spec: CarSpec, path: Path, *, force: bool = False) -> None:
    """Export one printable STL per unique part with the quantities to print."""
    meshes = spec.part_meshes()
    instructions = [
        spec.name,
        "",
        "Import the STL files in millimeters and print these quantities.",
        "",
        *(f"{quantity} × {part}.stl" for part, quantity in _PRINT_COUNTS.items()),
        "",
        "Slide one axle through each chassis bore and put a wheel on each axle end.",
        "The wheels use a slip fit. Use retainers to keep them on the axles.",
        "Check the fit on a test print for your printer and material.",
        "",
    ]

    def write_bundle(temp: Path) -> None:
        with ZipFile(temp, "w") as archive:
            for part in _PRINT_COUNTS:
                entry = ZipInfo(f"{part}.stl")
                archive.writestr(entry, stl_bytes(meshes[part]), compress_type=ZIP_DEFLATED)
            archive.writestr(ZipInfo("README.txt"), "\n".join(instructions), compress_type=ZIP_DEFLATED)

    write_output(path, write_bundle, force=force)
