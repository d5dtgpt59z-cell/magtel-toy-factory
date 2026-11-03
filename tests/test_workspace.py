"""Exercise the workspace over HTTP without launching a browser or Codex."""

import base64
import json
import sys
import threading
import unittest
from http.client import HTTPConnection
from importlib.util import find_spec
from types import ModuleType
from unittest.mock import patch

from magtel.workspace import WorkspaceServer, _MAX_GENERATE_BYTES


RECIPE = {
    "name": "Test block",
    "assumptions": [],
    "parts": [{
        "name": "Block",
        "color": "#00ff00",
        "features": [{
            "kind": "box",
            "operation": "add",
            "position": [0, 0, 0],
            "rotation": [0, 0, 0],
            "size": [10, 12, 2],
            "profile": [],
            "sections": [],
        }],
    }],
}


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.server = WorkspaceServer()
        self.addCleanup(self.server.server_close)
        thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        thread.start()
        self.addCleanup(thread.join, 2)
        self.addCleanup(self.server.shutdown)

    def _request(self, method, route, data=None, *, headers=None, prefix=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=15)
        defaults = {"Origin": self.server.origin, "Content-Type": "application/json"}
        if headers:
            defaults.update(headers)
        try:
            connection.request(
                method,
                (self.server.prefix if prefix is None else prefix) + route,
                body=json.dumps(data).encode("utf-8") if data is not None else None,
                headers=defaults,
            )
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_other_origins_and_wrong_session_cannot_generate(self):
        with patch("magtel.workspace.interpret_art") as provider:
            cases = (
                (403, {"Origin": "https://other.example"}, None),
                (403, {"Host": "other.example"}, None),
                (404, {}, "/other-session/"),
            )
            for expected, headers, prefix in cases:
                with self.subTest(expected=expected, headers=headers, prefix=prefix):
                    status, _, _ = self._request(
                        "POST", "api/generate", {}, headers=headers, prefix=prefix
                    )
                    self.assertEqual(status, expected)
            provider.assert_not_called()

    def test_oversized_generation_is_refused_before_reading_an_upload(self):
        status, _, body = self._request(
            "POST", "api/generate", headers={"Content-Length": str(_MAX_GENERATE_BYTES + 1)}
        )
        self.assertEqual(status, 413)
        self.assertIn("too large", json.loads(body)["error"])

    def test_generate_uses_only_temporary_attachments_with_safe_names(self):
        image_bytes = b"\x89PNG\r\n\x1a\nfixture"
        staged = []

        def interpret(attachments, brief):
            staged.extend(attachments)
            self.assertEqual(brief, "Build a block")
            self.assertEqual(attachments[0].name, "reference-1.png")
            self.assertEqual(attachments[0].read_bytes(), image_bytes)
            return RECIPE

        with (
            patch.dict(sys.modules, {"build123d": ModuleType("build123d")}),
            patch("magtel.workspace.interpret_art", side_effect=interpret),
            patch("magtel.workspace._model_response", return_value={"recipe": RECIPE}),
        ):
            status, _, body = self._request("POST", "api/generate", {
                "brief": "Build a block",
                "images": [{
                    "name": "../../original.PNG",
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }],
            })
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["recipe"], RECIPE)
        self.assertTrue(staged)
        self.assertFalse(staged[0].exists())

    @unittest.skipUnless(find_spec("build123d"), "requires the optional CAD engine")
    def test_dimension_edit_rebuilds_preview_and_step_without_the_provider(self):
        edited = json.loads(json.dumps(RECIPE))
        edited["parts"][0]["features"][0]["size"][2] = 7
        with patch("magtel.workspace.interpret_art") as provider:
            status, _, body = self._request("POST", "api/rebuild", {"recipe": edited})
            self.assertEqual(status, 200, body)
            data = json.loads(body)
            self.assertEqual(data["parts"][0]["size"], [10, 12, 7])
            self.assertIn('"embed":true', data["viewer"])
            status, headers, body = self._request("POST", "api/step", {"recipe": edited})
            self.assertEqual(status, 200, body)
            self.assertIn("attachment", headers["Content-Disposition"])
            self.assertTrue(body.startswith(b"ISO-10303-21;"))
            provider.assert_not_called()
