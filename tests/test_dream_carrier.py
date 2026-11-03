import math
import struct
import unittest
from collections import Counter

from magtel.assembly import _bored_chassis
from magtel.dream_body import body_parts
from magtel.dream_carrier import shape_carrier
from magtel.dream_model import _three_bore_chassis
from magtel.mesh import stl_bytes

from test_dream_body import in_triangle


class DreamCarrierTests(unittest.TestCase):
    def test_styled_carriers_taper_the_nose_and_preserve_bore_rings(self):
        length, width, height, bore = 120, 42, 17, 6.2
        for builder, wheelbase in ((_bored_chassis, 70), (_three_bore_chassis, 90)):
            base = builder(length, width, height, wheelbase, bore / 2)
            self.assertIs(shape_carrier(base, "plain", length, height, wheelbase, bore), base)
            for style in ("lunar", "racer", "truck"):
                with self.subTest(axle_count=2 if builder is _bored_chassis else 3, style=style):
                    shaped = shape_carrier(base, style, length, height, wheelbase, bore)
                    half_nose = max(abs(y) for face in shaped for x, y, _ in face if x == length / 2)
                    self.assertLess(half_nose, width / 3)
                    for triangle, original in zip(shaped, base):
                        for (x, y, z), (sx, sy, sz) in zip(original, triangle):
                            self.assertEqual((sx, sz), (x, z))
                            for center in (-wheelbase / 2, 0, wheelbase / 2):
                                if abs(math.hypot(x - center, z - height / 2) - bore / 2) < 1e-7:
                                    self.assertEqual(sy, y)
                    packed = stl_bytes(shaped)
                    edges = Counter(
                        edge for row in struct.iter_unpack("<12fH", packed[84:])
                        for edge in ((row[3:6], row[6:9]), (row[6:9], row[9:12]), (row[9:12], row[3:6]))
                    )
                    self.assertTrue(all(a != b and count == edges[b, a] == 1 for (a, b), count in edges.items()))

    def test_glue_on_module_footprints_are_supported_by_sculpted_roof(self):
        for length, width, height, wheelbase in (
            (132, 46, 7.8, 95), (127, 43, 19, 90), (86, 33, 9, 62), (112, 47, 25, 73), (68, 26, 12, 58),
        ):
            base = _bored_chassis(length, width, height, wheelbase, 3.1)
            for style in ("lunar", "racer", "truck", "stream"):
                with self.subTest(length=length, width=width, height=height, style=style):
                    shaped = shape_carrier(base, style, length, height, wheelbase, 6.2)
                    roof = [face for face in shaped if all(z == height for _, _, z in face)]
                    for module in body_parts(style, length, width):
                        footprint = {(x, y) for face in module.faces for x, y, z in face if z == 0}
                        for point in footprint:
                            self.assertTrue(any(in_triangle(point, face) for face in roof), (module.id, point))
