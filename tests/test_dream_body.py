import math
import struct
import unittest
from collections import Counter
from itertools import combinations

from magtel.dream_body import body_parts
from magtel.mesh import stl_bytes


def bounds(faces):
    return [(min(axis), max(axis)) for axis in zip(*(point for face in faces for point in face))]


def in_triangle(point, triangle):
    """Check whether an XY point lies in a horizontal triangle."""
    def cross(a, b):
        return (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])

    a, b, c = triangle
    signs = [cross(a, b), cross(b, c), cross(c, a)]
    return min(signs) >= -1e-9 or max(signs) <= 1e-9


class DreamBodyTests(unittest.TestCase):
    def test_each_module_exports_one_closed_positive_volume_shell(self):
        for profile in ("lunar", "racer", "truck"):
            for part in body_parts(profile, 127, 43):
                with self.subTest(profile=profile, part=part.id):
                    binary = stl_bytes(part.faces)
                    triangles = [(row[3:6], row[6:9], row[9:12])
                                 for row in struct.iter_unpack("<12fH", binary[84:])]
                    edges = Counter(edge for a, b, c in triangles for edge in ((a, b), (b, c), (c, a)))
                    for (start, end), count in edges.items():
                        self.assertNotEqual(start, end)
                        self.assertEqual(count, 1)
                        self.assertEqual(edges[end, start], 1)
                    vertices = {vertex for triangle in triangles for vertex in triangle}
                    self.assertEqual(len(vertices) - len(edges) // 2 + len(triangles), 2)
                    volume = math.fsum(
                        a[0] * (b[1] * c[2] - b[2] * c[1])
                        + a[1] * (b[2] * c[0] - b[0] * c[2])
                        + a[2] * (b[0] * c[1] - b[1] * c[0])
                        for a, b, c in triangles
                    ) / 6
                    self.assertGreater(volume, 0)

    def test_modules_mount_to_the_chassis_or_each_other_with_no_volume_overlap(self):
        top_z = 23.5
        for profile in ("lunar", "racer", "truck"):
            for length, width in ((127, 43), (45, 12), (30, 120)):
                parts = body_parts(profile, length, width, top_z)
                envelopes = {part.id: bounds(part.faces) for part in parts}
                for part in parts:
                    x, y, z = envelopes[part.id]
                    with self.subTest(profile=profile, length=length, width=width, part=part.id):
                        self.assertTrue(-length / 2 < x[0] < x[1] < length / 2)
                        self.assertTrue(-width / 2 < y[0] < y[1] < width / 2)
                        self.assertGreaterEqual(z[0], top_z)
                        if z[0] == top_z:
                            continue
                        mount_vertices = {(x, y) for face in part.faces for x, y, point_z in face if point_z == z[0]}
                        support_faces = [
                            face for support in parts if envelopes[support.id][2][1] == z[0]
                            for face in support.faces if all(point[2] == z[0] for point in face)
                        ]
                        self.assertTrue(all(any(in_triangle(point, face) for face in support_faces)
                                            for point in mount_vertices))
                for a, b in combinations(envelopes.values(), 2):
                    self.assertTrue(any(a_min >= b_max or b_min >= a_max
                                        for (a_min, a_max), (b_min, b_max) in zip(a, b)))

    def test_cargo_bed_has_an_open_recess_with_a_floor(self):
        cargo = next(part for part in body_parts("truck", 110, 45) if part.id == "body-cargo")
        center = (-0.29 * 110, 0)
        horizontal_levels_at_center = {
            a[2] for a, b, c in cargo.faces if a[2] == b[2] == c[2] and in_triangle(center, (a, b, c))
        }
        self.assertEqual(horizontal_levels_at_center, {0, 0.105 * 45})
        self.assertEqual(bounds(cargo.faces)[2][1], 0.30 * 45)

    def test_plain_profile_retains_legacy_chassis(self):
        self.assertEqual(body_parts("plain", 80, 30), ())
