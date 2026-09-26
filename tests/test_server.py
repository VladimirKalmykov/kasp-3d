import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import ConfigError, load_config, make_server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "demo").mkdir()
        (self.root / "demo" / "one.glb").write_bytes(b"test-glb")
        self.write_scenes([{"slug": "one", "title": "Первая", "file": "demo/one.glb"}])
        self.server = None
        self.thread = None

    def tearDown(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=2)
        self.temp.cleanup()

    def write_scenes(self, scenes):
        (self.root / "scenes.json").write_text(
            json.dumps({"scenes": scenes}, ensure_ascii=False), encoding="utf-8"
        )

    def start_server(self):
        self.server = make_server(port=0, root=self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return f"http://127.0.0.1:{self.server.server_port}"

    def test_routes_and_allowlist(self):
        base = self.start_server()
        with urlopen(base + "/demo3d?scene=one") as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b"Walk Viewer", response.read())
        with urlopen(base + "/demo3d/api/scenes") as response:
            self.assertEqual(json.load(response)["scenes"][0]["slug"], "one")
        with urlopen(base + "/demo3d/models/one.glb") as response:
            self.assertEqual(response.read(), b"test-glb")
        for path in ("/demo3d/models/other.glb", "/demo3d/models/../scenes.json",
                     "/demo3d/static/../scenes.json", "/scenes.json"):
            with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                urlopen(base + path)
            self.assertEqual(error.exception.code, 404)

    def test_config_is_frozen_until_restart(self):
        base = self.start_server()
        self.write_scenes([{"slug": "two", "title": "Вторая", "file": "demo/one.glb"}])
        with urlopen(base + "/demo3d/api/scenes") as response:
            self.assertEqual(json.load(response)["scenes"][0]["slug"], "one")
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.server = None
        base = self.start_server()
        with urlopen(base + "/demo3d/api/scenes") as response:
            self.assertEqual(json.load(response)["scenes"][0]["slug"], "two")

    def test_missing_file_is_reported(self):
        self.write_scenes([{"slug": "missing", "title": "Пропала", "file": "demo/missing.glb"}])
        base = self.start_server()
        with self.assertRaises(HTTPError) as error:
            urlopen(base + "/demo3d/models/missing.glb")
        self.assertEqual(error.exception.code, 404)

    def test_bad_config_is_rejected(self):
        for file_name in ("../secrets.glb", "demo/../secrets.glb", "demo/file.txt"):
            with self.subTest(file=file_name):
                self.write_scenes([{"slug": "bad", "title": "Bad", "file": file_name}])
                with self.assertRaises(ConfigError):
                    load_config(self.root)
        self.write_scenes([{"slug": "bad", "title": "Bad", "file": "demo/one.glb",
                            "anchor": [0, "x", 1]}])
        with self.assertRaises(ConfigError):
            load_config(self.root)


if __name__ == "__main__":
    unittest.main()
