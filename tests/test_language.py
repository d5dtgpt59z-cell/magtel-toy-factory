import unittest

from magtel.language import parse
from magtel.model import DesignError


class LanguageTests(unittest.TestCase):
    def test_wheel_lesson_and_relative_edit(self):
        wheel = parse("Make a wheel 40 mm across and 10 mm thick with a 6 mm axle hole.")
        edited = parse("Make the wheel 5 mm wider and make the hole 6.4 mm.", wheel)

        self.assertEqual((edited.kind, edited.diameter, edited.thickness, edited.hole),
                         ("wheel", 45, 10, 6.4))
        self.assertEqual((wheel.diameter, wheel.hole), (40, 6))

    def test_pronoun_edit_preserves_existing_dimensions_and_name(self):
        wheel = parse("Make a 40 mm diameter wheel, 15 mm thick, with a 7 mm hole.")
        wheel = parse('Call it "Moon and Mars"', wheel)
        edited = parse("Make it a 45 mm wheel.", wheel)
        fresh = parse("Make a 45 mm wheel.", wheel)

        self.assertEqual((edited.name, edited.diameter, edited.thickness, edited.hole),
                         ("Moon and Mars", 45, 15, 7))
        self.assertEqual((fresh.thickness, fresh.hole), (10, 6))

    def test_axle_converts_units_and_spelled_values(self):
        axle = parse("Please make me an axle 0.25 inch in diameter and two centimetres long.")

        self.assertEqual((axle.kind, axle.diameter, axle.thickness), ("axle", 6.35, 20))

    def test_block_dimensions_and_custom_studs(self):
        block = parse("I’d like a 4 × 2 × 1 cm brick with two by three studs and 3 mm diameter studs.")
        edited = parse("Remove the studs.", block)

        self.assertEqual((block.width, block.depth, block.height), (40, 20, 10))
        self.assertEqual((block.studs, block.stud_diameter, block.stud_height), ((2, 3), 3, 2))
        self.assertEqual((edited.studs, edited.stud_diameter, edited.stud_height), (None, None, None))

    def test_block_accepts_compact_dimensions_but_requires_units_when_mixed(self):
        block = parse("make a 40mmx20mmx10mm block with 2x2 studs")
        self.assertEqual((block.width, block.depth, block.height), (40, 20, 10))
        with self.assertRaisesRegex(DesignError, "include the unit"):
            parse("make a block 40 mm x 20 x 1 cm")

    def test_removing_and_adding_a_hole(self):
        wheel = parse("Make a solid 40 mm wheel.")
        self.assertIsNone(wheel.hole)
        self.assertEqual(parse("Add a 5 mm through-hole.", wheel).hole, 5)
        self.assertIsNone(parse("Remove the axle hole.", parse("Make a wheel.")).hole)

    def test_unknown_or_conflicting_clauses_are_rejected(self):
        wheel = parse("Make a wheel.")
        requests = (
            ("Make it 5 mm wider and add spikes.", "spikes"),
            ("Make it 45 mm.", "understand"),
            ("Make it 45 mm wide and 50 mm in diameter.", "one value for diameter"),
            ("Make the hole 50 mm.", "smaller than the wheel diameter"),
            ("Make a wheel named Rocket with a dinosaur sticker.", "dinosaur sticker"),
        )
        for request, reason in requests:
            with self.subTest(request=request), self.assertRaisesRegex(DesignError, reason):
                parse(request, wheel)
        self.assertEqual((wheel.diameter, wheel.hole), (40, 6))


if __name__ == "__main__":
    unittest.main()
