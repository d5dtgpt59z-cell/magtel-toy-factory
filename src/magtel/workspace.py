"""Loopback browser workspace for editing art-derived parts and toy cars."""

import base64
import json
import secrets
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory

from .art_geometry import build_art
from .art_io import MAX_ART_FILE_SIZE, art_preview_data, export_art
from .art_provider import (
    _EXTENSIONS,
    _MAX_BRIEF_CHARS,
    _MAX_IMAGE_BYTES,
    _MAX_IMAGES,
    _MAX_TOTAL_IMAGE_BYTES,
    interpret_art,
)
from .assembly_io import FORMAT as CAR_FORMAT
from .assembly_io import car_project_data, decode_car, export_parts
from .mesh import stl_bytes
from .model import DesignError
from .preview import car_preview_data, write_preview_data
from .project import MAX_PART_FILE_SIZE

_MAX_GENERATE_BYTES = 4 * ((_MAX_TOTAL_IMAGE_BYTES + 2) // 3) + 64 * 1024
_MAX_PREVIEW_TRIANGLES = 200_000
_CAR_PROJECT = Path("Car project")
_CONTENT_POLICY = (
    "default-src 'none'; script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' blob: data:; "
    "connect-src 'self'; frame-src 'self' blob:; object-src 'none'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


class _RequestError(Exception):
    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status = status


def _recipe_request(data: dict):
    if data.keys() != {"recipe"}:
        raise DesignError("Supply an editable CAD recipe.")
    return data["recipe"]


def _generate_recipe(data: dict, directory: Path) -> dict:
    if data.keys() != {"brief", "images"}:
        raise DesignError("Supply a build brief and a list of optional reference images.")
    brief = data["brief"]
    if not isinstance(brief, str) or not brief.strip() or len(brief) > _MAX_BRIEF_CHARS:
        raise DesignError(f"Describe the part in 1 to {_MAX_BRIEF_CHARS:,} characters.")
    images = data["images"]
    if not isinstance(images, list) or len(images) > _MAX_IMAGES:
        raise DesignError(f"Attach up to {_MAX_IMAGES} reference images.")

    attachments = []
    remaining = _MAX_TOTAL_IMAGE_BYTES
    for index, image in enumerate(images, 1):
        if not isinstance(image, dict) or image.keys() != {"name", "data"}:
            raise DesignError("Each reference image needs a file name and image data.")
        name, encoded = image["name"], image["data"]
        suffix = _EXTENSIONS.get(Path(name).suffix.lower()) if isinstance(name, str) else None
        if suffix is None:
            raise DesignError("Use PNG, JPEG, or WebP reference images.")
        limit = min(remaining, _MAX_IMAGE_BYTES)
        if not isinstance(encoded, str) or len(encoded) > 4 * ((limit + 2) // 3):
            raise DesignError("Reference images must be at most 16 MiB each and 32 MiB total.")
        try:
            image_bytes = base64.b64decode(encoded, validate=True)
        except ValueError as error:
            raise DesignError("Could not decode a reference image.") from error
        if len(image_bytes) > limit:
            raise DesignError("Reference images must be at most 16 MiB each and 32 MiB total.")
        remaining -= len(image_bytes)
        path = directory / f"reference-{index}{suffix}"
        path.write_bytes(image_bytes)
        attachments.append(path)

    try:
        import build123d  # noqa: F401
    except ImportError as error:
        raise DesignError("Install MAGTEL with the optional CAD dependencies first.") from error
    return interpret_art(attachments, brief.strip())


def _model_response(recipe, directory: Path) -> dict:
    result = {}
    if isinstance(recipe, dict) and recipe.get("format") == CAR_FORMAT:
        car = decode_car(recipe, _CAR_PROJECT)
        result["fit"] = car.fit_report()
        viewer = car_preview_data(car)
        parts = []
        for part in viewer["parts"]:
            axes = [part["vertices"][index::3] for index in range(3)]
            parts.append({
                "name": part["name"],
                "kind": part["kind"],
                "size": [round(max(axis) - min(axis), 6) for axis in axes],
            })
        recipe = car_project_data(car)
    else:
        assembly = build_art(recipe)
        viewer, parts = art_preview_data(recipe, assembly, triangle_limit=_MAX_PREVIEW_TRIANGLES)
    viewer["embed"] = True
    path = directory / "preview.html"
    write_preview_data(viewer, path)
    return {"recipe": recipe, "viewer": path.read_text(encoding="utf-8"), "parts": parts, **result}


class WorkspaceServer(ThreadingHTTPServer):
    """A workspace tied to one loopback origin and an unguessable session path."""

    def __init__(self, port: int = 0):
        super().__init__(("127.0.0.1", port), _WorkspaceHandler)
        self.host = f"127.0.0.1:{self.server_port}"
        self.origin = f"http://{self.host}"
        self.prefix = f"/{secrets.token_urlsafe(24)}/"
        self.url = self.origin + self.prefix
        self.generation = threading.Lock()
        # The CAD kernel shares export settings. Serialize its use within a workspace.
        self.cad = threading.Lock()


class _WorkspaceHandler(BaseHTTPRequestHandler):
    server: WorkspaceServer

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, format, *args):
        # Request paths carry the private workspace token.
        return

    def _send(self, status, content_type: str, payload: bytes, *, download: str | None = None):
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", _CONTENT_POLICY)
            if download:
                self.send_header("Content-Disposition", f'attachment; filename="{download}"')
            self.end_headers()
            self.wfile.write(payload)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            # Navigation or cancellation may close the browser's connection.
            return

    def _json(self, status, data):
        payload = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._send(status, "application/json; charset=utf-8", payload)

    def _route(self) -> str:
        if self.headers.get_all("Host") != [self.server.host]:
            raise _RequestError(HTTPStatus.FORBIDDEN, "Use the workspace's local address.")
        path = self.path.partition("?")[0]
        if not path.startswith(self.server.prefix):
            raise _RequestError(HTTPStatus.NOT_FOUND, "Workspace session not found.")
        return path[len(self.server.prefix):]

    def _read_request(self, limit: int) -> dict:
        if self.headers.get_content_type() != "application/json":
            raise _RequestError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Send a JSON request.")
        lengths = self.headers.get_all("Content-Length")
        if self.headers.get("Transfer-Encoding") or lengths is None or len(lengths) != 1:
            raise _RequestError(HTTPStatus.BAD_REQUEST, "Send a request with a fixed content length.")
        length = lengths[0]
        if not length.isdecimal():
            raise _RequestError(HTTPStatus.BAD_REQUEST, "Invalid content length.")
        if len(length) > 9 or int(length) > limit:
            raise _RequestError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "This workspace request is too large.")
        try:
            size = int(length)
            payload = self.rfile.read(size)
            if len(payload) != size:
                raise ValueError("incomplete request")
            data = json.loads(payload)
        except TimeoutError as error:
            raise _RequestError(HTTPStatus.REQUEST_TIMEOUT, "The upload did not finish.") from error
        except (ValueError, RecursionError) as error:
            raise _RequestError(HTTPStatus.BAD_REQUEST, "Invalid JSON request.") from error
        if not isinstance(data, dict):
            raise _RequestError(HTTPStatus.BAD_REQUEST, "Send a JSON object.")
        return data

    def _with_errors(self, action):
        try:
            action()
        except _RequestError as error:
            self._json(error.status, {"error": str(error)})
        except DesignError as error:
            self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(error)})
        except (OSError, RuntimeError, ValueError):
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "The workspace could not complete the build."})

    def do_GET(self):
        self._with_errors(self._get)

    def _get(self):
        route = self._route()
        assets = {
            "": ("workspace.html", "text/html; charset=utf-8"),
            "workspace.js": ("workspace.js", "text/javascript; charset=utf-8"),
        }
        if route in assets:
            asset, media_type = assets[route]
            self._send(HTTPStatus.OK, media_type, files("magtel").joinpath(asset).read_bytes())
            return
        demos = {
            "api/demo": "workspace_demo.json",
            "api/car": "workspace_car.json",
            "api/gripper": "workspace_gripper.json",
        }
        if route in demos:
            recipe = json.loads(files("magtel").joinpath(demos[route]).read_text(encoding="utf-8"))
            with self.server.cad, TemporaryDirectory(prefix="magtel-workspace-") as temp:
                result = _model_response(recipe, Path(temp))
            self._json(HTTPStatus.OK, result)
            return
        raise _RequestError(HTTPStatus.NOT_FOUND, "Workspace route not found.")

    def do_POST(self):
        self._with_errors(self._post)

    def _post(self):
        route = self._route()
        if self.headers.get_all("Origin") != [self.server.origin]:
            raise _RequestError(HTTPStatus.FORBIDDEN, "Open this action from the MAGTEL workspace.")
        if route == "api/generate":
            if not self.server.generation.acquire(blocking=False):
                raise _RequestError(HTTPStatus.CONFLICT, "A design is already being generated.")
            try:
                data = self._read_request(_MAX_GENERATE_BYTES)
                with TemporaryDirectory(prefix="magtel-workspace-") as temp:
                    directory = Path(temp)
                    recipe = _generate_recipe(data, directory)
                    with self.server.cad:
                        result = _model_response(recipe, directory)
                self._json(HTTPStatus.OK, result)
            finally:
                self.server.generation.release()
            return
        if route in ("api/fit", "api/part", "api/parts"):
            self._car_action(route)
            return
        if route not in ("api/rebuild", "api/step"):
            raise _RequestError(HTTPStatus.NOT_FOUND, "Workspace route not found.")
        recipe = _recipe_request(self._read_request(MAX_ART_FILE_SIZE))
        with self.server.cad, TemporaryDirectory(prefix="magtel-workspace-") as temp:
            directory = Path(temp)
            if route == "api/rebuild":
                result = _model_response(recipe, directory)
            else:
                path = directory / "model.step"
                export_art(recipe, path)
                payload = path.read_bytes()
        if route == "api/rebuild":
            self._json(HTTPStatus.OK, result)
        else:
            self._send(HTTPStatus.OK, "application/step", payload, download="magtel-model.step")

    def _car_action(self, route: str):
        data = self._read_request(MAX_PART_FILE_SIZE)
        if route == "api/part":
            part = data.get("part")
            if data.keys() != {"recipe", "part"} or part not in ("chassis", "axle", "wheel"):
                raise DesignError("Choose a chassis, axle, or wheel to export.")
            car = decode_car(data["recipe"], _CAR_PROJECT)
            mesh = car.part_meshes()[part]
            self._send(HTTPStatus.OK, "model/stl", stl_bytes(mesh), download=f"{part}.stl")
            return

        car = decode_car(_recipe_request(data), _CAR_PROJECT)
        if route == "api/fit":
            self._json(HTTPStatus.OK, {"fit": car.fit_report()})
            return
        with TemporaryDirectory(prefix="magtel-workspace-") as temp:
            path = Path(temp) / "parts.zip"
            export_parts(car, path)
            payload = path.read_bytes()
        self._send(HTTPStatus.OK, "application/zip", payload, download="car-parts.zip")


def run_workspace(*, open_browser: bool = True, port: int = 0) -> int:
    """Start the local server until the user closes it with Ctrl+C."""
    if not 0 <= port <= 65535:
        raise DesignError("Choose a workspace port between 0 and 65535.")
    try:
        import build123d  # noqa: F401
    except ImportError as error:
        raise DesignError("Studio requires Python 3.11+ and the MAGTEL cad extra.") from error
    try:
        server = WorkspaceServer(port)
    except OSError as error:
        raise DesignError(f"Could not start the local workspace: {error}.") from error
    with server:
        print(f"MAGTEL workspace: {server.url}", flush=True)
        if open_browser:
            try:
                opened = webbrowser.open(server.url)
            except (OSError, webbrowser.Error):
                opened = False
            if not opened:
                print("Open the workspace URL in your browser.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            return 0
    return 0
