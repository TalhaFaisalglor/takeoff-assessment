from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from threading import Lock, Thread
from urllib.parse import urlparse

from .pipeline import BUILD_PROFILES, run_pipeline
from .service import TakeoffAppService
from .storage import get_review_record, save_review_record


class TakeoffAppServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], root: Path, output: Path):
        self.root = root.resolve()
        self.output = output.resolve()
        self.service = TakeoffAppService(self.root, self.output)
        self._build_lock = Lock()
        self.build_state = {
            "status": "idle",
            "profile": None,
            "message": "No build running.",
            "error": None,
            "started_at": None,
            "finished_at": None,
        }
        super().__init__(server_address, TakeoffAppHandler)

    def get_build_state(self) -> dict[str, object]:
        with self._build_lock:
            return dict(self.build_state)

    def start_build(self, profile: str) -> dict[str, object]:
        with self._build_lock:
            if self.build_state["status"] == "running":
                raise RuntimeError("A build is already running.")
            self.build_state = {
                "status": "running",
                "profile": profile,
                "message": f"Running {BUILD_PROFILES.get(profile, BUILD_PROFILES['full'])['label']}...",
                "error": None,
                "started_at": _utc_now(),
                "finished_at": None,
            }
        thread = Thread(target=self._run_build, args=(profile,), daemon=True)
        thread.start()
        return self.get_build_state()

    def _run_build(self, profile: str) -> None:
        try:
            summary = run_pipeline(self.root, self.output, profile=profile)
            self.service = TakeoffAppService(self.root, self.output)
            with self._build_lock:
                self.build_state = {
                    "status": "completed",
                    "profile": profile,
                    "message": f"Build complete: {summary['profile_label']}",
                    "error": None,
                    "started_at": self.build_state["started_at"],
                    "finished_at": _utc_now(),
                }
        except Exception as error:
            with self._build_lock:
                self.build_state = {
                    "status": "failed",
                    "profile": profile,
                    "message": "Build failed.",
                    "error": str(error),
                    "started_at": self.build_state["started_at"],
                    "finished_at": _utc_now(),
                }


class TakeoffAppHandler(BaseHTTPRequestHandler):
    server: TakeoffAppServer

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/" or path == "/app":
            self._serve_web_asset("index.html", "text/html; charset=utf-8")
            return
        if path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        if path.startswith("/assets/"):
            asset_name = path.removeprefix("/assets/")
            self._serve_web_asset(asset_name, _guess_type(asset_name))
            return
        if path.startswith("/artifacts/"):
            self._serve_file(self.server.output / path.removeprefix("/artifacts/"))
            return
        if path == "/api/health":
            self._json({"status": "ok", "available_profiles": BUILD_PROFILES})
            return
        if path == "/api/build-status":
            self._json(self.server.get_build_state())
            return
        if path == "/api/summary":
            self._json(self.server.service.get_summary())
            return
        if path == "/api/projects":
            self._json({"projects": self.server.service.list_projects()})
            return
        if path.startswith("/api/projects/"):
            takeoff_id = path.removeprefix("/api/projects/")
            try:
                self._json(self.server.service.get_project(takeoff_id))
            except KeyError:
                self.send_error(HTTPStatus.NOT_FOUND, "Unknown project")
            return
        if path.startswith("/api/reviews/"):
            takeoff_id = path.removeprefix("/api/reviews/")
            self._json(get_review_record(self.server.service.review_db_path, takeoff_id))
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/reviews/"):
            takeoff_id = path.removeprefix("/api/reviews/")
            payload = self._read_json()
            record = save_review_record(self.server.service.review_db_path, takeoff_id, payload)
            self._json(record, status=HTTPStatus.CREATED)
            return
        if path == "/api/rebuild" or path == "/api/build":
            payload = self._read_json()
            profile = str(payload.get("profile") or "full")
            try:
                state = self.server.start_build(profile)
            except RuntimeError as error:
                self._json({"status": "rejected", "error": str(error), "build_state": self.server.get_build_state()}, status=HTTPStatus.CONFLICT)
                return
            self._json({"status": "started", "build_state": state, "available_profiles": BUILD_PROFILES}, status=HTTPStatus.ACCEPTED)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, fmt: str, *args) -> None:
        return

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length).decode("utf-8") if length else "{}"
        return json.loads(payload or "{}")

    def _json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", _guess_type(path.name))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_web_asset(self, name: str, content_type: str) -> None:
        try:
            asset = resources.files("takeoff_builder").joinpath("web", name).read_bytes()
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND, "Asset not found")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(asset)))
        self.end_headers()
        self.wfile.write(asset)


def _guess_type(name: str) -> str:
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def serve_app(root: Path, output: Path, host: str, port: int) -> None:
    server = TakeoffAppServer((host, port), root=root, output=output)
    print(f"Takeoff Studio running at http://{host}:{port}")
    server.serve_forever()
