import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


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
