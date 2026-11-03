from copy import deepcopy
from importlib.util import find_spec
from math import pi
import unittest

from magtel.art_geometry import ART_SCHEMA, build_art, validate_art
from magtel.art_io import art_preview_data
from magtel.model import DesignError


def feature(kind="box", *, operation="add", position=None, rotation=None, size=None, profile=None, sections=None):
    return {
        "operation": operation,
        "kind": kind,
        "position": [0, 0, 0] if position is None else position,
        "rotation": [0, 0, 0] if rotation is None else rotation,
        "size": [20, 16, 8] if size is None else size,
        "profile": [] if profile is None else profile,
        "sections": [] if sections is None else sections,
    }


def part(name, *features):
    return {"name": name, "color": "#28C4B4", "features": list(features)}


def recipe(*parts):
    return {"name": "Image-derived test", "assumptions": ["Millimeter scale assumed."], "parts": list(parts)}


class RecipeValidationTests(unittest.TestCase):
    def test_strict_json_schema_disallows_unlisted_keys(self):
        def check(schema):
            if schema.get("type") == "object":
                self.assertFalse(schema["additionalProperties"])
                self.assertEqual(set(schema["required"]), set(schema["properties"]))
                for child in schema["properties"].values():
                    check(child)
            if schema.get("type") == "array":
                check(schema["items"])

        check(ART_SCHEMA)
        data = recipe(part("Base", feature()))
        self.assertEqual(validate_art(data), data)
        data["parts"][0]["features"][0]["python"] = "print('untrusted')"
        with self.assertRaisesRegex(DesignError, r"exactly these fields"):
            validate_art(data)

    def test_bad_operations_colors_and_numeric_values_fail(self):
        source = recipe(part("Base", feature()))
        bad_inputs = (
            ("operation", "cut", "before any cut"),
            ("kind", "script", "kind must be"),
            ("position", [0, float("inf"), 0], "finite number"),
            ("rotation", [False, 0, 0], "finite number"),
            ("size", [20, 0, 8], "finite number"),
            ("profile", [[0, 0], [1, 0], [0, 1]], "array of 0 items"),
        )
        for field, value, message in bad_inputs:
            with self.subTest(field=field):
                data = deepcopy(source)
                data["parts"][0]["features"][0][field] = value
                with self.assertRaisesRegex(DesignError, message):
                    validate_art(data)
        source["parts"][0]["color"] = "transparent"
        with self.assertRaisesRegex(DesignError, "hex color"):
            validate_art(source)

    def test_polygons_are_simple_and_lofts_match_sections(self):
        cross = [[0, 0], [5, 5], [0, 5], [5, 0]]
        with self.assertRaisesRegex(DesignError, "must not cross"):
            validate_art(recipe(part("Sketch", feature("extrude", size=[1], profile=cross))))

        square = [[0, 0], [5, 0], [5, 5], [0, 5]]
        sections = [{"z": 0, "profile": square}, {"z": 3, "profile": list(reversed(square))}]
        with self.assertRaisesRegex(DesignError, "matching vertex counts and winding"):
            validate_art(recipe(part("Loft", feature("loft", size=[], sections=sections))))

    def test_rejects_duplicate_names_and_excessive_parts(self):
        with self.assertRaisesRegex(DesignError, "unique"):
            validate_art(recipe(part("Base", feature()), part("base", feature())))
        with self.assertRaisesRegex(DesignError, "1 to 24"):
            validate_art(recipe(*(part(str(i), feature()) for i in range(25))))

    def test_finishes_are_optional_for_saved_recipes_and_edge_sizes_are_bounded(self):
        legacy = recipe(part("Base", feature()))
        self.assertEqual(validate_art(legacy), legacy)
        finished = recipe({**part("Base", feature()), "finish": "metal"})
        self.assertEqual(validate_art(finished), finished)
        finished["parts"][0]["finish"] = "unknown"
        with self.assertRaisesRegex(DesignError, r"\.finish must be one of"):
            validate_art(finished)
        for kind in ("rounded_box", "chamfer_box"):
            with self.subTest(kind=kind), self.assertRaisesRegex(DesignError, "half the shortest side"):
                validate_art(recipe(part("Base", feature(kind, size=[20, 16, 8, 4]))))


@unittest.skipUnless(find_spec("build123d"), "optional CAD dependencies are unavailable")
class GeometryTests(unittest.TestCase):
    def test_box_cut_and_placed_extrude_and_loft(self):
        outline = [[-5, -3], [5, -3], [5, 3], [-5, 3]]
        sections = [
            {"z": 0, "profile": outline},
            {"z": 7, "profile": [[-3, -2], [3, -2], [3, 2], [-3, 2]]},
            {"z": 10, "profile": [[-2, -1], [2, -1], [2, 1], [-2, 1]]},
        ]
        model = build_art(recipe(
            part("Pierced base", feature(), feature(
                "cylinder", operation="cut", position=[0, 0, -1], size=[2.5, 10])),
            part("Rotated fin", feature(
                "extrude", position=[40, 0, 3], rotation=[0, 0, 90], size=[2], profile=outline)),
            part("Tapered cap", feature("loft", position=[60, 0, 5], size=[], sections=sections)),
        ))
        self.assertEqual(model.label, "Image-derived test")
        self.assertEqual([child.label for child in model.children],
                         ["Pierced base", "Rotated fin", "Tapered cap"])
        self.assertTrue(model.is_valid)
        self.assertEqual(len(model.solids()), 3)
        pierced, fin, cap = model.children
        self.assertAlmostEqual(pierced.volume, 20 * 16 * 8 - pi * 2.5**2 * 8, places=5)
        self.assertAlmostEqual(fin.volume, 120)
        self.assertAlmostEqual(fin.bounding_box().size.X, 6, places=5)
        self.assertAlmostEqual(fin.bounding_box().min.Z, 3, places=5)
        self.assertAlmostEqual(cap.bounding_box().max.Z, 15, places=5)
        self.assertTrue(cap.color is not None)

    def test_rejects_disconnected_part_and_ineffective_cut(self):
        with self.assertRaisesRegex(DesignError, "one connected solid"):
            build_art(recipe(part("Base", feature(), feature(position=[100, 0, 0]))))
        with self.assertRaisesRegex(DesignError, "cut does not intersect"):
            build_art(recipe(part("Base", feature(), feature(
                "cylinder", operation="cut", position=[100, 0, 0], size=[2, 10]))))

    def test_edge_boxes_remove_material_without_reducing_outer_dimensions(self):
        model = build_art(recipe(
            part("Rounded housing", feature("rounded_box", size=[20, 16, 8, 1.5])),
            part("Beveled housing", feature("chamfer_box", position=[40, 0, 0], size=[20, 16, 8, 1.5])),
        ))
        self.assertEqual(len(model.solids()), 2)
        for solid in model.children:
            self.assertTrue(solid.is_valid)
            self.assertLess(solid.volume, 20 * 16 * 8)
            for dimension, expected in zip(solid.bounding_box().size, (20, 16, 8)):
                self.assertAlmostEqual(dimension, expected)
        self.assertNotAlmostEqual(model.children[0].volume, model.children[1].volume)

    def test_preview_keeps_finish_and_falls_back_under_triangle_budget(self):
        data = recipe({**part("Pin", feature("cylinder", size=[12, 8])), "finish": "metal"})
        model = build_art(data)
        detailed, measures = art_preview_data(data, model)
        coarse, coarse_measures = art_preview_data(data, model, triangle_limit=600)
        self.assertEqual(detailed["parts"][0]["finish"], "metal")
        self.assertEqual(coarse["parts"][0]["finish"], "metal")
        self.assertGreater(len(detailed["parts"][0]["vertices"]) // 9, 600)
        self.assertLessEqual(len(coarse["parts"][0]["vertices"]) // 9, 600)
        self.assertEqual(measures, coarse_measures)
        with self.assertRaisesRegex(DesignError, "too detailed"):
            art_preview_data(data, model, triangle_limit=12)
