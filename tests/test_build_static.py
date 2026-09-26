import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from config import ConfigError, MAX_FILE_BYTES, load_config

spec = importlib.util.spec_from_file_location("build_static", SCRIPTS / "build-static.py")
build_static = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(build_static)
build = build_static.build


class BuildStaticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output = self.root / "dist"
        (self.root / "demo").mkdir()
        (self.root / "demo" / "one.glb").write_bytes(b"test-glb")
        self.write_scenes([{"slug": "one", "title": "Первая", "file": "demo/one.glb"}])
        self.copy_minimal_web()

    def tearDown(self):
        self.temp.cleanup()

    def write_scenes(self, scenes):
        (self.root / "scenes.json").write_text(
            json.dumps({"scenes": scenes}, ensure_ascii=False),
            encoding="utf-8",
        )

    def copy_minimal_web(self):
        repo_web = Path(__file__).resolve().parents[1] / "web"
        web = self.root / "web"
        web.mkdir()
        for name in ("index.html", "main.js", "style.css"):
            shutil.copy2(repo_web / name, web / name)
        shutil.copytree(repo_web / "vendor", web / "vendor")

    def test_build_succeeds(self):
        with mock.patch.object(build_static, "WEB", self.root / "web"):
            build(self.root, self.output)

        demo3d = self.output / "demo3d"
        self.assertTrue((demo3d / "index.html").is_file())
        self.assertTrue((demo3d / "scenes.json").is_file())
        self.assertEqual((demo3d / "models" / "one.glb").read_bytes(), b"test-glb")
        self.assertTrue((demo3d / "static" / "main.js").is_file())
        self.assertTrue((demo3d / "static" / "vendor" / "three.module.js").is_file())
        self.assertTrue((self.output / "index.html").is_file())
        self.assertTrue((self.output / ".nojekyll").is_file())
        index_html = (demo3d / "index.html").read_text(encoding="utf-8")
        main_js = (demo3d / "static" / "main.js").read_text(encoding="utf-8")
        self.assertNotIn('"/demo3d/', index_html)
        self.assertNotIn("'/demo3d/", index_html)
        self.assertNotIn('"/demo3d/', main_js)
        self.assertNotIn("'/demo3d/", main_js)

        scenes = json.loads((demo3d / "scenes.json").read_text(encoding="utf-8"))["scenes"]
        self.assertEqual(scenes[0]["slug"], "one")
        self.assertNotIn("file", scenes[0])

    def test_dist_contains_only_publishable_files(self):
        with mock.patch.object(build_static, "WEB", self.root / "web"):
            build(self.root, self.output)

        names = {path.name for path in self.output.rglob("*") if path.is_file()}
        self.assertNotIn("server.py", names)
        for path in self.output.rglob("scenes.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            for scene in data["scenes"]:
                self.assertNotIn("file", scene)

    def test_missing_file_fails_build(self):
        self.write_scenes([{"slug": "missing", "title": "Пропала", "file": "demo/missing.glb"}])
        with mock.patch.object(build_static, "WEB", self.root / "web"):
            with self.assertRaises(ConfigError):
                build(self.root, self.output)

    def test_bad_config_is_rejected(self):
        for file_name in ("../secrets.glb", "demo/../secrets.glb", "demo/file.txt"):
            with self.subTest(file=file_name):
                self.write_scenes([{"slug": "bad", "title": "Bad", "file": file_name}])
                with self.assertRaises(ConfigError):
                    load_config(self.root)

        self.write_scenes([
            {"slug": "bad", "title": "Bad", "file": "demo/one.glb", "anchor": [0, "x", 1]},
        ])
        with self.assertRaises(ConfigError):
            load_config(self.root)

        self.write_scenes([
            {"slug": "one", "title": "One", "file": "demo/one.glb"},
            {"slug": "one", "title": "Duplicate", "file": "demo/one.glb"},
        ])
        with self.assertRaises(ConfigError):
            load_config(self.root)

    def test_file_size_limit(self):
        oversized = self.root / "demo" / "big.glb"
        oversized.write_bytes(b"x" * (MAX_FILE_BYTES + 1))
        self.write_scenes([{"slug": "big", "title": "Big", "file": "demo/big.glb"}])
        with self.assertRaises(ConfigError):
            load_config(self.root)


if __name__ == "__main__":
    unittest.main()
