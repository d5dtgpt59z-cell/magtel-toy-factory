import math
import struct
import tempfile
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path

from magtel.mesh import Triangle, mesh, write_stl
from magtel.model import ToySpec


class MeshTests(unittest.TestCase):
    def assert_closed_oriented_surface(self, faces: list[Triangle], euler: int) -> None:
        directions = Counter(
            edge for a, b, c in faces for edge in ((a, b), (b, c), (c, a))
        )
        for (start, end), count in directions.items():
            self.assertNotEqual(start, end)
            self.assertEqual(count, 1)
            self.assertEqual(directions[(end, start)], 1)
        vertices = {point for face in faces for point in face}
        self.assertEqual(len(vertices) - len(directions) // 2 + len(faces), euler)

    def assert_bounds(self, faces: list[Triangle], expected: list[tuple[float, float]]) -> None:
        for values, (low, high) in zip(zip(*(point for face in faces for point in face)), expected):
            self.assertAlmostEqual(min(values), low)
            self.assertAlmostEqual(max(values), high)

    def assert_volume(self, faces: list[Triangle], expected: float, relative_error: float) -> None:
        signed_volume = math.fsum(
            a[0] * (b[1] * c[2] - b[2] * c[1])
            + a[1] * (b[2] * c[0] - b[0] * c[2])
            + a[2] * (b[0] * c[1] - b[1] * c[0])
            for a, b, c in faces
        ) / 6
        self.assertAlmostEqual(signed_volume, expected, delta=expected * relative_error)

    def test_wheel_bore_goes_through_the_full_thickness(self):
        faces = mesh(ToySpec.default("wheel"))
        self.assert_bounds(faces, [(-20, 20), (-20, 20), (0, 10)])
        self.assert_closed_oriented_surface(faces, euler=0)
        self.assert_volume(faces, math.pi * (20**2 - 3**2) * 10, 0.001)
        bore_vertices = {
            (x, y, z) for face in faces for x, y, z in face if math.hypot(x, y) < 19
        }
        self.assertEqual({z for _, _, z in bore_vertices}, {0, 10})
        for x, y, _ in bore_vertices:
            self.assertAlmostEqual(math.hypot(x, y), 3)

    def test_axle_is_a_solid_cylinder(self):
        faces = mesh(ToySpec.default("axle"))
        self.assert_bounds(faces, [(-2.9, 2.9), (-2.9, 2.9), (0, 24)])
        self.assert_closed_oriented_surface(faces, euler=2)
        self.assert_volume(faces, math.pi * 2.9**2 * 24, 0.001)

    def test_plain_block(self):
        faces = mesh(ToySpec.default("block"))
        self.assert_bounds(faces, [(-20, 20), (-10, 10), (0, 10)])
        self.assert_closed_oriented_surface(faces, euler=2)
        self.assert_volume(faces, 40 * 20 * 10, 0.000001)

    def test_studs_fuse_to_block_with_no_separate_shells(self):
        spec = replace(ToySpec.default("block"), studs=(3, 2), stud_diameter=5, stud_height=2)
        faces = mesh(spec)
        self.assert_bounds(faces, [(-20, 20), (-10, 10), (0, 12)])
        self.assert_closed_oriented_surface(faces, euler=2)
        self.assert_volume(faces, 40 * 20 * 10 + 6 * math.pi * 2.5**2 * 2, 0.0001)

    def test_stl_encodes_closed_surface_and_unit_normals(self):
        spec = replace(ToySpec.default("block"), studs=(3, 2), stud_diameter=5, stud_height=2)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "stud-block.stl"
            write_stl(spec, path)
            data = path.read_bytes()
        (count,) = struct.unpack_from("<I", data, 80)
        self.assertEqual(len(data), 84 + 50 * count)
        faces = []
        for facet in struct.iter_unpack("<12fH", data[84:]):
            self.assertAlmostEqual(math.hypot(*facet[:3]), 1, places=6)
            faces.append((facet[3:6], facet[6:9], facet[9:12]))
        self.assert_closed_oriented_surface(faces, euler=2)
        self.assert_bounds(faces, [(-20, 20), (-10, 10), (0, 12)])
