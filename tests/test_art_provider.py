import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from magtel.art_provider import interpret_art
from magtel.model import DesignError


_PNG = b"\x89PNG\r\n\x1a\nfixture"
_RECIPE = {
    "name": "Draft",
    "assumptions": ["Height assumed."],
    "parts": [{
        "name": "Housing",
        "color": "#289AA1",
        "features": [{
            "operation": "add", "kind": "box",
            "position": [0, 0, 0], "rotation": [0, 0, 0], "size": [15, 8, 12],
            "profile": [], "sections": [],
        }],
    }],
}


class ArtProviderTests(unittest.TestCase):
    def test_provider_uses_safe_attachment_names_and_validates_result(self):
        def write_result(command, *, cwd, input, **kwargs):
            self.assertEqual(command[command.index("--image") + 1:], ["reference-1.png", "--", "-"])
            self.assertEqual((cwd / "reference-1.png").read_bytes(), _PNG)
            self.assertNotIn(str(image), command)
            self.assertEqual(command[command.index("--sandbox") + 1], "read-only")
            self.assertIn("--ephemeral", command)
            self.assertIn("--ignore-user-config", command)
            self.assertIn("shell_tool", command)
            self.assertIn("Use no tools.", input)
            self.assertIn('"Make a 12 mm housing"', input)
            self.assertTrue((cwd / "art-schema.json").is_file())
            (cwd / "art-result.json").write_text(json.dumps(_RECIPE), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0)

        with TemporaryDirectory() as directory:
            image = Path(directory) / "--reference, 1.PNG"
            image.write_bytes(_PNG)
            with patch("magtel.art_provider.shutil.which", return_value="/test/codex"), patch(
                "magtel.art_provider.subprocess.run", side_effect=write_result,
            ):
                self.assertEqual(interpret_art([image], "Make a 12 mm housing"), _RECIPE)

    def test_invalid_attachment_is_rejected_before_provider(self):
        with TemporaryDirectory() as directory:
            image = Path(directory) / "fake.png"
            image.write_bytes(b"not an image")
            with patch("magtel.art_provider.shutil.which", return_value="/test/codex"), patch(
                "magtel.art_provider.subprocess.run",
            ) as run:
                with self.assertRaisesRegex(DesignError, "do not match"):
                    interpret_art([image], "")
                run.assert_not_called()

    def test_unrecognized_provider_fields_do_not_pass_validation(self):
        def write_result(command, *, cwd, **kwargs):
            (cwd / "art-result.json").write_text(
                json.dumps({**_RECIPE, "python": "print('unexpected')"}), encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0)

        with TemporaryDirectory() as directory:
            image = Path(directory) / "ref.png"
            image.write_bytes(_PNG)
            with patch("magtel.art_provider.shutil.which", return_value="/test/codex"), patch(
                "magtel.art_provider.subprocess.run", side_effect=write_result,
            ):
                with self.assertRaisesRegex(DesignError, "exactly these fields"):
                    interpret_art([image], "")

    def test_provider_timeout_becomes_design_error(self):
        with TemporaryDirectory() as directory:
            image = Path(directory) / "ref.png"
            image.write_bytes(_PNG)
            with patch("magtel.art_provider.shutil.which", return_value="/test/codex"), patch(
                "magtel.art_provider.subprocess.run",
                side_effect=subprocess.TimeoutExpired(["codex"], 180),
            ):
                with self.assertRaisesRegex(DesignError, "timed out after 180 seconds"):
                    interpret_art([image], "")
