import math
import struct
import unittest
from collections import Counter
from pathlib import Path

from magtel.assembly_io import load_car
from magtel.dream_model import build, from_car, invent, variants
from magtel.mesh import stl_bytes
from magtel.model import DesignError


def bounds(faces):
    return [(min(axis), max(axis)) for axis in zip(*(point for face in faces for point in face))]


class DreamModelTests(unittest.TestCase):
    def assert_closed_stl(self, faces, euler):
        payload = stl_bytes(faces)
        triangles = [(row[3:6], row[6:9], row[9:12]) for row in struct.iter_unpack("<12fH", payload[84:])]
        edges = Counter(edge for a, b, c in triangles for edge in ((a, b), (b, c), (c, a)))
        for (start, end), count in edges.items():
            self.assertNotEqual(start, end)
            self.assertEqual(count, 1)
            self.assertEqual(edges[(end, start)], 1)
        vertices = {point for triangle in triangles for point in triangle}
        self.assertEqual(len(vertices) - len(edges) // 2 + len(triangles), euler)

    def test_natural_language_matches_recipes_and_explicit_dimensions(self):
        rover = invent("A futuristic six-wheeled moon rover in lime green with 3.8 cm wheels")
        self.assertEqual(rover["concept"], "Lunar Rover")
        self.assertEqual(rover["axle_count"], 3)
        self.assertEqual(rover["wheel_diameter"], 38)
        self.assertEqual(rover["colors"]["chassis"], "#b7ef58")
        self.assertEqual(invent("Pink pocket-sized race car")["concept"], "Pocket Racer")
        self.assertEqual(invent("Orange rescue truck with wide wheels")["concept"], "Rescue Truck")

    def test_notes_disclose_unimplemented_requests_and_fit(self):
        prototype = invent("Eight-wheeled flying electric monster truck with LED lights")
        self.assertEqual(prototype["axle_count"], 2)
        notes = " ".join(prototype["notes"])
        for detail in ("wheel count", "powered motion", "flight", "lighting", "retainers"):
            self.assertIn(detail, notes)

    def test_three_bore_chassis_is_one_watertight_stl(self):
        spec = build(invent("Six-wheel rover with wheelbase 90 mm and chassis height 18.6396 mm"))
        parts = spec.part_meshes()
        self.assert_closed_stl(parts["chassis"], euler=-4)
        d = spec.design
        vertices = {point for face in parts["chassis"] for point in face}
        radius = (d["axle_diameter"] + d["axle_clearance"]) / 2
        for center in (-45, 0, 45):
            bore = [(x, y, z) for x, y, z in vertices
                    if abs(x - center) < radius + 1 and abs(z - d["height"] / 2) < radius + 1]
            self.assertEqual(len(bore), 192)
            self.assertEqual({y for _, y, _ in bore}, {-d["width"] / 2, d["width"] / 2})
            for x, _, z in bore:
                self.assertAlmostEqual(math.hypot(x - center, z - d["height"] / 2), radius)

        placed = spec.components()
        self.assertEqual(len(placed), 10)
        for location, x in (("front", 45), ("middle", 0), ("rear", -45)):
            for side in ("left", "right"):
                horizontal, _, vertical = bounds(placed[f"{location}-{side}-wheel"])
                self.assertAlmostEqual(sum(horizontal) / 2, x)
                self.assertAlmostEqual(vertical[0], 0)
        self.assertEqual([row["quantity"] for row in spec.bom()], [1, 3, 6])

    def test_variants_preserve_mates_and_change_closed_wheel_geometry(self):
        source = invent("Six-wheeled moon rover")
        original = build(source)
        original_parts = original.part_meshes()
        alternatives = variants(source)
        self.assertEqual(len(alternatives), 3)
        self.assertEqual(len({d["wheel_profile"] for d in alternatives}), 3)
        for alternative in alternatives:
            with self.subTest(variant=alternative["variant"]):
                spec = build(alternative)
                parts = spec.part_meshes()
                for kind in ("chassis", "axle"):
                    self.assertEqual(original_parts[kind], parts[kind])
                self.assertEqual(spec.dimensions(), original.dimensions())
                self.assertEqual(spec.fit(), original.fit())
                self.assertEqual(spec.bom(), original.bom())
                self.assertNotEqual(original_parts["wheel"], parts["wheel"])
                self.assertEqual(bounds(original_parts["wheel"]), bounds(parts["wheel"]))
                self.assert_closed_stl(parts["wheel"], euler=0)

    def test_incompatible_edits_fail_before_meshing(self):
        design = invent("Six-wheel moon rover")
        for changes, reason in (
            ({"wheelbase": 65}, "Six wheels need"),
            ({"wheel_bore": 5.6}, "need a hole"),
            ({"wheel_gap": 4}, "to reach through"),
            ({"wheel_profile": ["straight"]}, "wheel profile"),
            ({"length": True}, "Length must be"),
            ({"colors": {"chassis": "<svg>", "wheel": "#123456", "axle": "#456789"}}, "hex color"),
        ):
            with self.subTest(changes=changes):
                with self.assertRaisesRegex(DesignError, reason):
                    build({**design, **changes})
        with self.assertRaisesRegex(DesignError, "Give one value"):
            invent("Make a rover with wheel diameter 35 mm and 40 mm wheels")
        with self.assertRaisesRegex(DesignError, "Wheel diameter must"):
            invent("Make a rover with -40 mm wheels")

    def test_legacy_import_preserves_all_meshes_and_nominal_fit(self):
        car = load_car(Path(__file__).resolve().parents[1] / "examples" / "toy-car.magtel.json")
        design = build(from_car(car))
        self.assertEqual(design.part_meshes(), car.part_meshes())
        self.assertEqual(design.components(), car.components())
        self.assertEqual(design.fit_report(), car.fit_report())
