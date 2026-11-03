import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from magtel.assembly_io import load_car


def run_cli(*args: str, user_input: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "magtel", *args],
        input=user_input,
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=10,
    )


class WorkshopTest(unittest.TestCase):
    def test_invalid_edit_keeps_design_and_undo_restores_it(self):
        with TemporaryDirectory() as folder:
            part = str(Path(folder) / "wheel with spaces.magtel.json")
            stl = Path(folder) / "wheel.stl"
            result = run_cli(user_input="\n".join((
                "Make a wheel 40 mm across with a 6 mm hole",
                "Make it 45 mm across",
                "Make the hole 80 mm",
                "show",
                "undo",
                f'save "{part}"',
                f"export {stl}",
                "quit",
                "",
            )))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Ø45 × 10 mm thick, Ø6 mm through hole", result.stdout)
            self.assertIn("Try again:", result.stderr)
            self.assertIn("Ø40 × 10 mm thick, Ø6 mm through hole", run_cli("show", part).stdout)
            self.assertGreater(stl.stat().st_size, 84)

    def test_existing_part_requires_explicit_overwrite(self):
        with TemporaryDirectory() as folder:
            part = Path(folder) / "wheel.magtel.json"
            original = b"existing file"
            part.write_bytes(original)
            result = run_cli("Make a wheel", "-o", str(part))
            self.assertEqual(result.returncode, 2)
            self.assertIn("already exists", result.stderr)
            self.assertEqual(part.read_bytes(), original)
            result = run_cli("Make a wheel", "-o", str(part), "--force")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Ø40", run_cli("show", str(part)).stdout)

    def test_fit_exit_codes_follow_nominal_diameter_clearance(self):
        with TemporaryDirectory() as folder:
            wheel = str(Path(folder) / "wheel.json")
            axle = str(Path(folder) / "axle.json")
            self.assertEqual(run_cli("Make a wheel", "-o", wheel).returncode, 0)
            self.assertEqual(run_cli("Make an axle", "-o", axle).returncode, 0)
            clearance = run_cli("fit", wheel, axle)
            self.assertEqual(clearance.returncode, 0, clearance.stderr)
            self.assertIn("0.2 mm (0.1 mm per side)", clearance.stdout)
            result = run_cli("edit", axle, "make it 6.2 mm across", "-o", axle, "--force")
            self.assertEqual(result.returncode, 0, result.stderr)
            interference = run_cli("fit", wheel, axle)
            self.assertEqual(interference.returncode, 1)
            self.assertIn("interference", interference.stdout)

    def test_car_workshop_rejects_interference_and_exports_the_saved_assembly(self):
        with TemporaryDirectory() as folder:
            car = Path(folder) / "first car.magtel.json"
            stl = car.with_suffix(".stl")
            bundle = car.with_suffix(".zip")
            result = run_cli(user_input="\n".join((
                "Build a toy car.",
                "Use an 80 x 30 x 12 mm chassis.",
                "Mount two 5.8 mm diameter, 60 mm long axles 55 mm apart.",
                "Put a 40 mm wheel, 10 mm thick, with a 6 mm hole on each end.",
                "Move the axles 30 mm apart.",
                "Move the axles 58 mm apart.",
                "undo",
                "check the fit",
                f'save "{car}"',
                f'export "{stl}"',
                f'export "{bundle}"',
                "quit",
                "",
            )))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr.count("Try again:"), 1, result.stderr)
            self.assertEqual(load_car(car).wheelbase, 55)
            self.assertIn("0.2 mm", result.stdout)
            self.assertGreater(stl.stat().st_size, 84)
            with ZipFile(bundle) as files:
                self.assertEqual({name for name in files.namelist() if name.endswith(".stl")},
                                 {"chassis.stl", "axle.stl", "wheel.stl"})

    def test_batch_car_reuses_saved_parts_and_can_be_reopened_and_edited(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            chassis = root / "original chassis.magtel.json"
            axle = root / "original axle.magtel.json"
            wheel = root / "original wheel.magtel.json"
            car = root / "car.magtel.json"
            for text, path in (
                ("Make a 90 x 30 x 12 mm block", chassis),
                ("Make an axle 5.8 mm in diameter and 60 mm long", axle),
                ("Make a 40 mm wheel with a 6.4 mm hole", wheel),
            ):
                result = run_cli(text, "-o", str(path))
                self.assertEqual(result.returncode, 0, result.stderr)
            result = run_cli("assemble", (
                f'Use the chassis from "{chassis}"; use the axles from "{axle}"; '
                f'use the wheels from "{wheel}"; move the axles 60 mm apart'
            ), "-o", str(car))
            self.assertEqual(result.returncode, 0, result.stderr)
            wheel.unlink()
            result = run_cli("fit", str(car))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("0.6 mm", result.stdout)
            result = run_cli("edit", str(car), "Leave 2 mm between each wheel and the chassis",
                             "-o", str(car), "--force")
            self.assertEqual(result.returncode, 0, result.stderr)
            spec = load_car(car)
            self.assertEqual(spec.wheel_gap, 2)
            self.assertEqual(spec.chassis.width, 90)

    def test_incomplete_car_can_be_saved_but_cannot_be_exported(self):
        with TemporaryDirectory() as folder:
            car = str(Path(folder) / "draft.magtel.json")
            stl = Path(folder) / "draft.stl"
            result = run_cli("Build a toy car", "-o", car)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = run_cli("export", car, "-o", str(stl))
            self.assertEqual(result.returncode, 2)
            self.assertIn("chassis", result.stderr.lower())
            self.assertFalse(stl.exists())
