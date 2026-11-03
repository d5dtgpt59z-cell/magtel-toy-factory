"""Editable CAD recipes and exports from their exact geometry."""

from pathlib import Path

from .art_geometry import build_art, validate_art
from .model import DesignError, mm
from .preview import write_preview_data
from .project import read_json, write_json, write_output

FORMAT = "magtel-art"
MAX_ART_FILE_SIZE = 2 * 1024 * 1024


def save_art(recipe: dict, path: Path, *, force: bool = False) -> None:
    data = {"format": FORMAT, "version": 1, "units": "mm", "recipe": validate_art(recipe)}
    write_json(data, path, force=force)


def load_art(path: Path) -> dict:
    data = read_json(path, label="MAGTEL art project", limit=MAX_ART_FILE_SIZE)
    if (not isinstance(data, dict) or data.get("format") != FORMAT
            or type(data.get("version")) is not int or data["version"] != 1
            or data.get("units") != "mm"):
        raise DesignError("Open a version 1 MAGTEL art project in millimeters.")
    return validate_art(data.get("recipe"))


def _preview_meshes(solids, tolerance, angular_tolerance, triangle_limit):
    meshes = []
    triangle_count = 0
    for part in solids:
        vertices, triangles = part.tessellate(tolerance, angular_tolerance)
        if not triangles:
            raise DesignError(f"Could not preview {part.label}.")
        triangle_count += len(triangles)
        if triangle_limit is not None and triangle_count > triangle_limit:
            return None
        meshes.append([
            round(coord, 6) for face in triangles for index in face for coord in vertices[index]
        ])
    return meshes


def art_preview_data(
    recipe: dict, assembly, *, triangle_limit: int | None = None
) -> tuple[dict, list[dict]]:
    """Describe and tessellate the solids in an already-built art assembly."""
    meshes = _preview_meshes(assembly.children, 0.03, 0.06, triangle_limit)
    if meshes is None:
        from OCP.BRepTools import BRepTools

        # The kernel otherwise reuses the finer cached triangulation.
        for part in assembly.children:
            BRepTools.Clean_s(part.wrapped)
        meshes = _preview_meshes(assembly.children, 0.08, 0.1, triangle_limit)
        if meshes is None:
            raise DesignError("This model is too detailed for the workspace preview.")

    parts = []
    measurements = []
    lines = [f'{recipe["name"]} — editable CAD']
    for spec, part, vertices in zip(recipe["parts"], assembly.children, meshes):
        bounds = part.bounding_box().size
        dimensions = [bounds.X, bounds.Y, bounds.Z]
        measurements.append({"name": spec["name"], "size": dimensions})
        size = " × ".join(mm(value) for value in dimensions)
        lines.append(f'  {spec["name"]} — {size} mm')
        parts.append({
            "name": spec["name"],
            "color": [int(spec["color"][i:i + 2], 16) / 255 for i in (1, 3, 5)],
            "finish": spec.get("finish", "polymer"),
            "vertices": vertices,
            "explode": [0, 0, 0],
        })
    if recipe["assumptions"]:
        lines += ["", "Assumptions", *(f"  • {line}" for line in recipe["assumptions"])]
    return {
        "title": recipe["name"],
        "description": "\n".join(lines),
        "parts": parts,
        "assembly": False,
    }, measurements


def export_art(recipe: dict, path: Path, *, force: bool = False) -> None:
    suffix = path.suffix.lower()
    if suffix not in (".step", ".stp", ".stl", ".html"):
        raise DesignError("Choose .step, .stp, .stl, or .html for an art project export.")
    assembly = build_art(recipe)
    if suffix == ".html":
        data, _ = art_preview_data(recipe, assembly)
        write_preview_data(data, path, force=force)
        return

    from build123d import export_step, export_stl

    exporter = export_stl if suffix == ".stl" else export_step

    def write(temp: Path) -> None:
        if not exporter(assembly, temp):
            raise DesignError(f"Could not write the {suffix} geometry.")

    write_output(path, write, force=force)
