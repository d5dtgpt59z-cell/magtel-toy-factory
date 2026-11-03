import struct
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from zipfile import ZipFile

from magtel.assembly import CarSpec
from magtel.assembly_io import export_car, export_parts, load_car, load_design, save_car
from magtel.model import DesignError, ToySpec
from magtel.project import save_part


def car() -> CarSpec:
    return CarSpec(
        name="Café Racer",
        chassis=ToySpec("block", "Chassis", width=80, depth=30, height=12),
        axle=replace(ToySpec.default("axle"), thickness=60),
        wheel=ToySpec.default("wheel"),
        wheelbase=55,
    )


def shell_count(data: bytes) -> int:
    (triangles,) = struct.unpack_from("<I", data, 80)
    if len(data) != 84 + 50 * triangles:
        raise AssertionError("Invalid binary STL length")
    neighbors = {}
    for facet in struct.iter_unpack("<12fH", data[84:]):
        vertices = (facet[3:6], facet[6:9], facet[9:12])
        for vertex in vertices:
            neighbors.setdefault(vertex, set()).update(vertices)
    remaining = set(neighbors)
    count = 0
    while remaining:
        stack = [remaining.pop()]
        count += 1
        while stack:
            connected = neighbors[stack.pop()] & remaining
            remaining.difference_update(connected)
            stack.extend(connected)
    return count


class AssemblyIOTests(unittest.TestCase):
    def test_round_trip_complete_and_partial_assemblies_alongside_legacy_parts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "design.magtel.json"
            part = ToySpec.default("wheel")
            save_part(part, path)
            self.assertEqual(load_design(path), part)
            for assembly in (car(), replace(car(), wheel=None, wheelbase=None)):
                save_car(assembly, path, force=True)
                self.assertEqual(load_design(path), assembly)
                self.assertEqual(load_car(path), assembly)

    def test_exports_positioned_shells_and_separate_print_meshes(self):
        with tempfile.TemporaryDirectory() as folder:
            assembled = Path(folder) / "car.stl"
            parts = Path(folder) / "parts.zip"
            export_car(car(), assembled)
            export_parts(car(), parts)
            self.assertEqual(shell_count(assembled.read_bytes()), 7)
            with ZipFile(parts) as archive:
                manifest = archive.read("README.txt").decode("utf-8")
                self.assertEqual(
                    set(archive.namelist()), {"chassis.stl", "axle.stl", "wheel.stl", "README.txt"}
                )
                for name, quantity in (("chassis", 1), ("axle", 2), ("wheel", 4)):
                    self.assertEqual(shell_count(archive.read(f"{name}.stl")), 1)
                    self.assertIn(f"{quantity} × {name}.stl", manifest)

    def test_incomplete_assembly_does_not_create_an_export(self):
        with tempfile.TemporaryDirectory() as folder:
            for export, filename in ((export_car, "car.stl"), (export_parts, "parts.zip")):
                with self.subTest(filename=filename):
                    path = Path(folder) / filename
                    with self.assertRaises(DesignError):
                        export(CarSpec(), path)
                    self.assertFalse(path.exists())
