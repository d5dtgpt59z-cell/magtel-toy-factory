import unittest
from pathlib import Path

from magtel.assembly_language import parse_car, starts_car
from magtel.model import DesignError, ToySpec


class CarLanguageTests(unittest.TestCase):
    def test_describe_a_complete_car_in_follow_up_turns(self):
        self.assertTrue(starts_car("Could you build me a toy car?"))
        self.assertTrue(starts_car("a toy car"))
        self.assertFalse(starts_car("Make a toy wheel"))

        car = parse_car("Build a toy car")
        car = parse_car("Use an 80 x 30 x 12 mm chassis", car)
        car = parse_car("Mount two 5.8 mm diameter, 60 mm long axles 55 mm apart", car)
        car = parse_car("Put a 40 mm wheel, 10 mm thick, with a 6 mm hole on each end of each axle", car)

        self.assertEqual((car.chassis.width, car.chassis.depth, car.chassis.height), (80, 30, 12))
        self.assertEqual((car.axle.diameter, car.axle.thickness), (5.8, 60))
        self.assertEqual((car.wheel.diameter, car.wheel.thickness, car.wheel.hole), (40, 10, 6))
        self.assertEqual(car.wheelbase, 55)
        self.assertFalse(car.missing())

        edited = parse_car(
            "Move the axles 58 mm apart; Leave 2 mm between each wheel and the chassis; "
            "Give the chassis axle holes 0.6 mm diametral clearance", car
        )
        self.assertEqual((edited.wheelbase, edited.wheel_gap, edited.axle_clearance), (58, 2, 0.6))
        self.assertEqual((car.wheelbase, car.wheel_gap, car.axle_clearance), (55, 1, 0.4))
        self.assertIs(edited.axle, car.axle)
        longer = parse_car("Make the chassis 85 mm long", edited)
        self.assertEqual((longer.chassis.width, longer.chassis.depth, longer.chassis.height), (85, 30, 12))
        self.assertEqual(longer.wheelbase, 58)

    def test_describe_a_complete_car_in_one_request(self):
        car = parse_car(
            'Build a toy car named "Track; Racer"; '
            "use a chassis 8 cm long, 30 mm wide and 12 mm high, "
            "then mount two axles 5.8 mm across, 6 cm long and 5.5 cm apart; "
            "attach four matching 40 mm wheels with a 6 mm bore to each axle end"
        )
        self.assertEqual(car.name, "Track; Racer")
        self.assertEqual((car.chassis.width, car.chassis.depth, car.chassis.height), (80, 30, 12))
        self.assertEqual(car.axle.thickness, 60)
        self.assertEqual(car.wheelbase, 55)
        self.assertFalse(car.missing())

    def test_reuses_existing_component_designs(self):
        axle = ToySpec("axle", "A fitted axle", diameter=5.8, thickness=60)
        wheel = ToySpec("wheel", "Wide wheel", diameter=40, thickness=10, hole=6)
        chassis = ToySpec("block", "My block", width=80, depth=30, height=12)
        library = {
            Path("wheel files/my wheel.json"): wheel,
            Path("axle.json"): axle,
            Path("my chassis.json"): chassis,
        }
        car = parse_car(
            'Build a toy car; use the chassis from "my chassis.json"; '
            'use the axles from axle.json 55 mm apart; '
            'use the wheels from "wheel files/my wheel.json" on each end',
            load_component=library.__getitem__,
        )
        self.assertEqual((car.chassis, car.axle, car.wheel), (chassis, axle, wheel))
        self.assertEqual(car.wheelbase, 55)

    def test_validates_after_related_edits_and_rejects_bad_commands(self):
        car = parse_car(
            "Use an 80 x 30 x 12 mm chassis; mount two 5.8 mm diameter axles 60 mm long 55 mm apart; "
            "put a 40 mm wheel with a 6 mm hole on each end"
        )
        edited = parse_car("Make the wheels 60 mm across; move the axles 65 mm apart", car)
        self.assertEqual((edited.wheel.diameter, edited.wheelbase), (60, 65))

        with self.assertRaises(DesignError):
            parse_car("Move the axles 10 mm apart", car)
        with self.assertRaisesRegex(DesignError, "four wheels"):
            parse_car("Put three 40 mm wheels", car)
        with self.assertRaises(DesignError):
            parse_car("put wheels on only the front axle", car)
        self.assertEqual((car.wheel.diameter, car.wheelbase), (40, 55))
