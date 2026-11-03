import math
import struct
import unittest
from collections import Counter
from dataclasses import replace

from magtel.assembly import CarSpec
from magtel.model import DesignError, ToySpec


def example_car() -> CarSpec:
    return CarSpec(
        chassis=replace(ToySpec.default("block"), width=80, depth=30, height=12),
        axle=replace(ToySpec.default("axle"), thickness=60),
        wheel=ToySpec.default("wheel"),
        wheelbase=55,
    )


def bounds(faces):
    return [(min(axis), max(axis)) for axis in zip(*(point for face in faces for point in face))]


class AssemblyTests(unittest.TestCase):
    def test_wheels_and_axles_follow_chassis_mates(self):
        car = example_car()
        parts = car.components()
        self.assertEqual(set(parts), {
            "chassis", "front-axle", "rear-axle", "front-left-wheel",
            "front-right-wheel", "rear-left-wheel", "rear-right-wheel",
        })
        self.assertEqual(bounds(parts["chassis"]), [(-40, 40), (-15, 15), (14, 26)])
        for end, center in (("front", 27.5), ("rear", -27.5)):
            axle_x, axle_y, axle_z = bounds(parts[f"{end}-axle"])
            self.assertAlmostEqual(sum(axle_x) / 2, center)
            self.assertEqual(axle_y, (-30, 30))
            self.assertAlmostEqual(sum(axle_z) / 2, 20)
            for side, span in (("left", (16, 26)), ("right", (-26, -16))):
                wheel_x, wheel_y, wheel_z = bounds(parts[f"{end}-{side}-wheel"])
                self.assertEqual(wheel_x, (center - 20, center + 20))
                self.assertEqual(wheel_y, span)
                self.assertEqual(wheel_z, (0, 40))
        self.assertIn("0.2 mm across (0.1 mm per side)", car.fit_report())
        self.assertIn("Ground clearance below chassis — 14 mm", car.fit_report())

    def test_printable_chassis_is_one_closed_body_with_two_through_bores(self):
        faces = example_car().part_meshes()["chassis"]
        # Check that coincident vertices still join after binary STL quantization.
        faces = [
            tuple(struct.unpack("<3f", struct.pack("<3f", *point)) for point in face)
            for face in faces
        ]
        edges = Counter(edge for a, b, c in faces for edge in ((a, b), (b, c), (c, a)))
        for (start, end), count in edges.items():
            self.assertNotEqual(start, end)
            self.assertEqual(count, 1)
            self.assertEqual(edges[(end, start)], 1)
        vertices = {point for face in faces for point in face}
        self.assertEqual(len(vertices) - len(edges) // 2 + len(faces), -2)
        self.assertEqual(bounds(faces), [(-40, 40), (-15, 15), (0, 12)])
        for center in (-27.5, 27.5):
            hole = [(x, y, z) for x, y, z in vertices if abs(x - center) < 4 and abs(z - 6) < 4]
            self.assertEqual({y for _, y, _ in hole}, {-15, 15})
            self.assertGreater(len(hole), 100)
            for x, _, z in hole:
                self.assertAlmostEqual(math.hypot(x - center, z - 6), 3.1, places=5)

    def test_incompatible_mates_are_rejected_before_export(self):
        car = example_car()
        invalid = (
            (replace(car, axle=replace(car.axle, thickness=50)), "52 mm long"),
            (replace(car, axle=replace(car.axle, diameter=6.2)), "hole at least 6.3 mm"),
            (replace(car, wheelbase=35), "wheelbase of at least 40.1 mm"),
            (replace(car, wheelbase=79), "chassis at least 85.4 mm long"),
            (replace(car, chassis=replace(car.chassis, height=6)), "at least 6.4 mm tall"),
            (replace(car, chassis=replace(car.chassis, height=42)), "clears the ground"),
        )
        for assembly, message in invalid:
            with self.subTest(message=message):
                with self.assertRaisesRegex(DesignError, message):
                    assembly.validate()

    def test_incomplete_car_can_be_described_and_later_finished(self):
        car = CarSpec(chassis=example_car().chassis)
        self.assertIs(car.validate(), car)
        self.assertIn("Still needed — axles, wheels, wheelbase", car.describe())
        with self.assertRaisesRegex(DesignError, "specifying axles, wheels, wheelbase"):
            car.components()
