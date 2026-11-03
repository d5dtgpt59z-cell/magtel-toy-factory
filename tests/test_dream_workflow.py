"""Exercise the browser API and inspect the invention bundle as a downloaded file."""

import io
import json
import struct
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from magtel.assembly_io import load_design
from magtel.cli import main
from magtel.dream_server import DreamServer


class DreamWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = DreamServer()
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def request(self, path, payload=None, *, headers=None):
        conn = HTTPConnection("127.0.0.1", self.server.server_port, timeout=10)
        try:
            if payload is None:
                conn.request("GET", path, headers=headers or {})
            else:
                body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
                conn.request("POST", path, body,
                             {"Content-Type": "application/json", **(headers or {})})
            response = conn.getresponse()
            body = response.read()
            if response.getheader("Content-Type", "").startswith("application/json"):
                body = json.loads(body)
            return response.status, response.headers, body
        finally:
            conn.close()

    def test_invent_edit_variant_export_and_reopen(self):
        status, _, made = self.request("/api/invent", {"prompt": "Design a blue six-wheeled moon rover."})
        self.assertEqual(status, 200)
        body_parts = [part for part in made["parts"] if part.get("kind") == "body"]
        self.assertEqual(len(made["parts"]) - len(body_parts), 10)
        self.assertTrue(body_parts)
        self.assertGreater(made["dimensions"]["height"], made["design"]["wheel_diameter"])
        self.assertTrue(all(part["dimensions"]["height"] > 0 for part in body_parts))
        design = made["design"]
        edited_design = {**design, "length": design["length"] + 4}
        status, _, edited = self.request("/api/design", {"design": edited_design})
        self.assertEqual(status, 200)
        self.assertEqual(edited["dimensions"]["length"], made["dimensions"]["length"] + 4)
        self.assertNotEqual(edited["parts"][0]["vertices"], made["parts"][0]["vertices"])
        status, _, _ = self.request("/api/design", {"design": {**design, "wheel_bore": 0.1}})
        self.assertEqual(status, 400)

        status, _, options = self.request("/api/variants", {"design": edited["design"]})
        self.assertEqual(status, 200)
        self.assertEqual(len(options["variants"]), 5)
        variant = options["variants"][0]
        self.assertEqual(variant["wheel_bore"], design["wheel_bore"])
        self.assertNotEqual(variant["wheel_profile"], design["wheel_profile"])
        status, _, variant_model = self.request("/api/design", {"design": variant})
        self.assertEqual(status, 200)
        self.assertNotEqual(variant["body_style"], design["body_style"])
        body_ids = {part["id"] for part in variant_model["parts"] if part.get("kind") == "body"}
        self.assertTrue(body_ids)
        status, headers, body = self.request("/api/export", {"design": variant})
        self.assertEqual(status, 200)
        self.assertIn("attachment", headers["Content-Disposition"])

        with ZipFile(io.BytesIO(body)) as archive, TemporaryDirectory() as folder:
            self.assertEqual(set(archive.namelist()), {
                "invention-sheet.html", "hero.png", "exploded.png", "orthographic.svg", "preview.html",
                "design.magtel.json", "stl/chassis.stl", "stl/axle.stl", "stl/wheel.stl", "START HERE.txt",
                *(f"stl/{part}.stl" for part in body_ids),
            })
            self.assertIsNone(archive.testzip())
            sheet = archive.read("invention-sheet.html").decode()
            self.assertIn("Prototype bill of materials", sheet)
            self.assertIn('<td>6</td>', sheet)
            self.assertIn("stl/wheel.stl", sheet)
            self.assertNotEqual(archive.read("hero.png"), archive.read("exploded.png"))
            drawing = archive.read("orthographic.svg").decode()
            self.assertIn("SIDE VIEW", drawing)
            self.assertIn("TOP VIEW", drawing)
            for part in ("chassis", "axle", "wheel", *body_ids):
                stl = archive.read(f"stl/{part}.stl")
                count, = struct.unpack_from("<I", stl, 80)
                self.assertGreater(count, 0)
                self.assertEqual(len(stl), 84 + 50 * count)
                if part in body_ids:
                    facets = struct.iter_unpack("<12fH", stl[84:])
                    self.assertEqual(min(min(face[5], face[8], face[11]) for face in facets), 0)
            saved = Path(archive.extract("design.magtel.json", folder))
            self.assertEqual(load_design(saved).design, variant)
            preview = Path(folder) / "share.html"
            self.assertEqual(main(["preview", str(saved), "-o", str(preview)]), 0)
            self.assertNotIn('<script src=', preview.read_text(encoding="utf-8"))
            self.assertEqual(main(["fit", str(saved)]), 0)

        status, _, reopened = self.request("/api/import", {"design": variant})
        self.assertEqual(status, 200)
        self.assertEqual(reopened["design"], variant)

    def test_slipstream_paint_regions_and_stl_share_one_shell(self):
        status, _, model = self.request("/api/invent", {"prompt": "A sleek midnight blue speedform"})
        self.assertEqual(status, 200)
        parts = {part["id"]: part for part in model["parts"]}
        self.assertEqual([key for key in parts if key.startswith("body-")], ["body-stream"])
        for key in ("body-stream", "front-left-wheel", "rear-right-wheel"):
            region = parts[key]["paint"]
            self.assertTrue(region["faces"])
            self.assertLess(max(region["faces"]), len(parts[key]["vertices"]) // 9)
        status, _, body = self.request("/api/export", {"design": model["design"]})
        self.assertEqual(status, 200)
        with ZipFile(io.BytesIO(body)) as archive:
            self.assertIn("stl/body-stream.stl", archive.namelist())
            self.assertIn(b'"paint":', archive.read("preview.html"))

    def test_accepts_legacy_complete_car(self):
        path = Path(__file__).resolve().parents[1] / "examples" / "toy-car.magtel.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        status, _, converted = self.request("/api/import", {"design": original})
        self.assertEqual(status, 200)
        self.assertEqual(len(converted["parts"]), 7)
        self.assertEqual(converted["design"]["body_style"], "plain")
        legacy_dream = {key: val for key, val in converted["design"].items()
                        if key not in ("body_style", "body_colors")}
        legacy_dream["version"] = 1
        status, _, imported = self.request("/api/import", {"design": legacy_dream})
        self.assertEqual(status, 200)
        self.assertEqual(imported["parts"], converted["parts"])
        self.assertEqual(converted["design"]["wheelbase"], original["assembly"]["wheelbase"])

    def test_loopback_boundary_and_malformed_input(self):
        status, headers, html = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Invent a Toy", html)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        for path in ("/dream.css", "/dream_stage.js", "/dream_physics.js", "/dream_ui.js"):
            self.assertEqual(self.request(path)[0], 200)
        self.assertEqual(self.request("/", headers={"Host": "other.example"})[0], 403)
        self.assertEqual(self.request("/api/invent", {"prompt": "rover"},
                                      headers={"Origin": "https://other.example"})[0], 403)
        self.assertEqual(self.request("/api/invent", b"//")[0], 400)
        self.assertEqual(self.request("/api/design", {"design": []})[0], 400)
        self.assertEqual(self.request("/api/invent", {"prompt": "x" * (64 * 1024)})[0], 413)
        self.assertEqual(self.request("/api/invent", {"prompt": "rover"},
                                      headers={"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.request("/README.md")[0], 404)
