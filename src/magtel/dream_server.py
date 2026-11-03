"""Serve the Dream studio and geometry API on loopback, with no remote services."""

import json
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path

from .assembly_io import FORMAT as CAR_FORMAT, decode_car
from .dream_export import invention_bundle, studio_data
from .dream_model import build, from_car, invent, variants
from .model import DesignError
from .project import MAX_PART_FILE_SIZE

_ASSETS = {
    "/": ("dream.html", "text/html; charset=utf-8"),
    "/dream.css": ("dream.css", "text/css; charset=utf-8"),
    "/dream_stage.js": ("dream_stage.js", "text/javascript; charset=utf-8"),
    "/dream_physics.js": ("dream_physics.js", "text/javascript; charset=utf-8"),
    "/dream_ui.js": ("dream_ui.js", "text/javascript; charset=utf-8"),
}
_API = {"/api/invent", "/api/design", "/api/import", "/api/variants", "/api/export"}


class DreamServer(ThreadingHTTPServer):
    def __init__(self, port: int = 0):
        super().__init__(("127.0.0.1", port), DreamHandler)
        self.host_header = f"127.0.0.1:{self.server_port}"
        self.url = f"http://{self.host_header}"

    def get_request(self):
        socket, address = super().get_request()
        socket.settimeout(10)
        return socket, address


class DreamHandler(BaseHTTPRequestHandler):
    server: DreamServer

    def log_message(self, _format, *args):
        pass  # Keep the CLI focused on the studio URL and server lifecycle.

    def _send(self, status, body, content_type, *, attachment=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; "
                         "base-uri 'none'; form-action 'self'")
        if attachment:
            self.send_header("Content-Disposition", f'attachment; filename="{attachment}"')
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, data):
        self._send(status, json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _error(self, status, message):
        self._json(status, {"error": message})

    def _local_request(self):
        # A Host check blocks DNS rebinding. Origin and JSON-only POSTs prevent
        # a different website from using a browser to submit API operations.
        origin = self.headers.get("Origin")
        if self.headers.get_all("Host") != [self.server.host_header] or (
            origin is not None and origin != self.server.url
        ):
            self._error(HTTPStatus.FORBIDDEN, "Open Dream Mode at the loopback URL printed by MAGTEL.")
            return False
        return True

    def do_GET(self):
        if not self._local_request():
            return
        asset = _ASSETS.get(self.path)
        if not asset:
            self._error(HTTPStatus.NOT_FOUND, "That studio page does not exist.")
            return
        filename, content_type = asset
        self._send(HTTPStatus.OK, files("magtel").joinpath(filename).read_bytes(), content_type)

    def do_POST(self):
        if not self._local_request():
            return
        if self.path not in _API:
            self._error(HTTPStatus.NOT_FOUND, "That studio operation does not exist.")
            return
        if self.headers.get_content_type() != "application/json" or self.headers.get("Transfer-Encoding"):
            self._error(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Send a JSON request with a Content-Length.")
            return
        lengths = self.headers.get_all("Content-Length") or []
        try:
            size = int(lengths[0]) if len(lengths) == 1 else 0
        except ValueError:
            size = 0
        if size <= 0:
            self._error(HTTPStatus.BAD_REQUEST, "Send a non-empty JSON request.")
            return
        if size > MAX_PART_FILE_SIZE:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Dream Mode accepts designs up to 64 KiB.")
            return
        try:
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError
            request = json.loads(raw)
        except (ValueError, RecursionError, TimeoutError):
            self._error(HTTPStatus.BAD_REQUEST, "Send a readable JSON request.")
            return
        if not isinstance(request, dict):
            self._error(HTTPStatus.BAD_REQUEST, "Send a JSON object.")
            return

        try:
            if self.path == "/api/invent":
                spec = build(invent(request.get("prompt")))
            else:
                design = request.get("design")
                if self.path == "/api/import" and isinstance(design, dict) and design.get("format") == CAR_FORMAT:
                    design = from_car(decode_car(design, Path("Uploaded assembly")))
                spec = build(design)
            if self.path == "/api/variants":
                self._json(HTTPStatus.OK, {"variants": variants(spec.design)})
            elif self.path == "/api/export":
                self._send(HTTPStatus.OK, invention_bundle(spec), "application/zip",
                           attachment="magtel-invention.zip")
            else:
                self._json(HTTPStatus.OK, studio_data(spec))
        except DesignError as error:
            self._error(HTTPStatus.BAD_REQUEST, str(error))


def serve_dream(port: int, *, open_browser: bool = True) -> None:
    if not 0 <= port <= 65535:
        raise DesignError("Choose a port between 0 (automatic) and 65535.")
    with DreamServer(port) as server:
        print(f"Dream Mode: {server.url}/", flush=True)
        print("Keep this window open while you invent. Press Ctrl+C to close the studio.", flush=True)
        if open_browser:
            try:
                webbrowser.open_new_tab(server.url)
            except (OSError, webbrowser.Error):
                pass  # The printed URL also works when a browser cannot be opened.
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nDream Mode closed.")
