"""Small, allowlisted GLB server for Walk Viewer Web."""

from __future__ import annotations

import argparse
import json
import math
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
SLUG = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
STATIC_ROOT = ROOT / "web"
ALLOWED_STATIC = {
    "index.html",
    "main.js",
    "style.css",
    "vendor/three.module.js",
    "vendor/three.core.js",
    "vendor/controls/OrbitControls.js",
    "vendor/loaders/GLTFLoader.js",
    "vendor/utils/BufferGeometryUtils.js",
    "vendor/utils/SkeletonUtils.js",
}


class ConfigError(ValueError):
    pass


def load_config(root: Path = ROOT) -> dict[str, dict]:
    try:
        data = json.loads((root / "scenes.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Cannot read scenes.json: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("scenes"), list):
        raise ConfigError("scenes.json needs a scenes array")

    scenes = {}
    model_root = (root / "demo").resolve()
    for item in data["scenes"]:
        if not isinstance(item, dict):
            raise ConfigError("Each scene must be an object")
        slug = item.get("slug")
        title = item.get("title")
        file_name = item.get("file")
        if not isinstance(slug, str) or not SLUG.fullmatch(slug) or slug in scenes:
            raise ConfigError(f"Invalid or duplicate slug: {slug!r}")
        if not isinstance(title, str) or not title.strip():
            raise ConfigError(f"Scene {slug}: title is required")
        if not isinstance(file_name, str) or not file_name.lower().endswith(".glb"):
            raise ConfigError(f"Scene {slug}: file must be a .glb path")
        path = (root / file_name).resolve()
        if not path.is_relative_to(model_root):
            raise ConfigError(f"Scene {slug}: file must be inside demo/")

        public = {"slug": slug, "title": title}
        for name in ("anchor", "distance", "yaw", "pitch"):
            value = item.get(name)
            if value is None:
                continue
            if name == "anchor":
                if (not isinstance(value, list) or len(value) != 3 or
                        any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in value)):
                    raise ConfigError(f"Scene {slug}: anchor must contain three finite numbers")
            elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ConfigError(f"Scene {slug}: {name} must be a finite number")
            elif name == "distance" and value <= 0:
                raise ConfigError(f"Scene {slug}: distance must be positive")
            elif name == "pitch" and not -89 < value < 89:
                raise ConfigError(f"Scene {slug}: pitch must be between -89 and 89 degrees")
            public[name] = value
        scenes[slug] = {"public": public, "path": path}
    return scenes


class ViewerHandler(BaseHTTPRequestHandler):
    server: ViewerServer

    def do_GET(self):
        self._dispatch(False)

    def do_HEAD(self):
        self._dispatch(True)

    def _dispatch(self, head_only: bool):
        path = urlsplit(self.path).path
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/demo3d")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path in ("/demo3d", "/demo3d/"):
            self._send_file(STATIC_ROOT / "index.html", "text/html; charset=utf-8", head_only)
            return
        if path == "/demo3d/api/scenes":
            items = [entry["public"] for entry in self.server.scenes.values()]
            payload = json.dumps({"scenes": items}, ensure_ascii=False).encode("utf-8")
            self._send_bytes(payload, "application/json; charset=utf-8", head_only, "no-store")
            return
        prefix = "/demo3d/models/"
        if path.startswith(prefix):
            slug_part = path[len(prefix):]
            if not slug_part.endswith(".glb"):
                self.send_error(404, "Unknown scene")
                return
            slug = slug_part[:-4]
            scene = self.server.scenes.get(slug)
            if scene is None:
                self.send_error(404, "Unknown scene")
                return
            self._send_file(scene["path"], "model/gltf-binary", head_only)
            return
        static_prefix = "/demo3d/static/"
        if path.startswith(static_prefix):
            name = path[len(static_prefix):]
            if name not in ALLOWED_STATIC:
                self.send_error(404, "Unknown asset")
                return
            mime = "text/css" if name.endswith(".css") else "text/javascript"
            self._send_file(STATIC_ROOT / name, mime + "; charset=utf-8", head_only)
            return
        self.send_error(404, "Not found")

    def _send_file(self, path: Path, mime: str, head_only: bool):
        try:
            source = path.open("rb")
        except OSError:
            self.send_error(404, "File unavailable")
            return
        with source:
            size = path.stat().st_size
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if not head_only:
                while chunk := source.read(1024 * 256):
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        break

    def _send_bytes(self, payload: bytes, mime: str, head_only: bool, cache: str):
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if not head_only:
            self.wfile.write(payload)


class ViewerServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, scenes):
        super().__init__(address, ViewerHandler)
        self.scenes = scenes


def make_server(host="127.0.0.1", port=8000, root: Path = ROOT):
    return ViewerServer((host, port), load_config(root))


def main():
    parser = argparse.ArgumentParser(description="Walk Viewer Web")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    try:
        with make_server(args.host, args.port) as server:
            print(f"Open http://{args.host}:{server.server_port}/demo3d", flush=True)
            server.serve_forever()
    except (ConfigError, OSError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
