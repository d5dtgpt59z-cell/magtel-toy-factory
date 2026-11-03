import json
import re
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from magtel.assembly import CarSpec
from magtel.model import DesignError, ToySpec
from magtel.preview import export_preview


def preview_data(html):
    script = re.search(r'<script\b[^>]*\btype="application/json"[^>]*>(.*?)</script>', html, re.DOTALL)
    return json.loads(script[1])


def bounds(part, axis, *, exploded=False):
    coordinates = part["vertices"][axis::3]
    offset = part["explode"][axis] if exploded else 0
    return min(coordinates) + offset, max(coordinates) + offset


class PreviewTests(unittest.TestCase):
    def test_preview_contains_positioned_car_and_explodes_past_long_axles(self):
        car = CarSpec(
            chassis=replace(ToySpec.default("block"), width=80, depth=30, height=12),
            axle=replace(ToySpec.default("axle"), thickness=240),
            wheel=ToySpec.default("wheel"),
            wheelbase=55,
        )
        with TemporaryDirectory() as temp:
            path = Path(temp) / "car.html"
            export_preview(car, path)
            data = preview_data(path.read_text(encoding="utf-8"))
        self.assertTrue(data["assembly"])
        self.assertIn("55 mm between axle centers", data["description"])
        parts = {part["name"]: part for part in data["parts"]}
        self.assertEqual(len(parts), 7)
        self.assertTrue(all(len(part["vertices"]) % 9 == 0 for part in parts.values()))
        chassis = parts["Chassis"]
        axle = parts["Front Axle"]
        left_wheel = parts["Front Left Wheel"]
        right_wheel = parts["Front Right Wheel"]
        self.assertEqual(bounds(chassis, 2), (14, 26))
        self.assertEqual(bounds(left_wheel, 1), (16, 26))
        self.assertEqual(bounds(right_wheel, 1), (-26, -16))
        axle_min, axle_max = bounds(axle, 1, exploded=True)
        self.assertLess(axle_max, bounds(left_wheel, 1, exploded=True)[0])
        self.assertGreater(axle_min, bounds(right_wheel, 1, exploded=True)[1])
        self.assertGreater(bounds(chassis, 2, exploded=True)[0], bounds(axle, 2, exploded=True)[1])

    def test_preview_escapes_names_in_title_and_json_without_expanding_placeholders(self):
        name = "</script><svg onload=alert(1)> %%DATA%% & Ω"
        part = replace(ToySpec.default("wheel"), name=name)
        with TemporaryDirectory() as temp:
            path = Path(temp) / "part.html"
            export_preview(part, path)
            html = path.read_text(encoding="utf-8")
        self.assertNotIn("<svg onload", html)
        self.assertIn("&lt;/script&gt;&lt;svg onload=alert(1)&gt; %%DATA%% &amp; Ω", html)
        data = preview_data(html)
        self.assertFalse(data["assembly"])
        self.assertEqual(data["title"], name)
        self.assertEqual(data["parts"][0]["name"], name)
        self.assertEqual(data["parts"][0]["explode"], [0, 0, 0])

    def test_incomplete_assembly_does_not_create_a_preview(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "unfinished.html"
            with self.assertRaisesRegex(DesignError, "Finish the car"):
                export_preview(CarSpec(), path)
            self.assertFalse(path.exists())
