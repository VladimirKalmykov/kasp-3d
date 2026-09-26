#!/usr/bin/env python3
"""Build a static dist/ directory for GitHub Pages and other static hosts."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from config import ConfigError, MAX_FILE_BYTES, load_config

ROOT = SCRIPT_DIR.parent
DIST = ROOT / "dist"
WEB = ROOT / "web"

ROOT_INDEX = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Walk Viewer Web</title>
  <script>location.replace('demo3d/' + location.search + location.hash);</script>
</head>
<body><p><a href="demo3d/">Walk Viewer Web</a></p></body>
</html>
"""


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def check_file_size(path: Path, label: str) -> None:
    size = path.stat().st_size
    if size > MAX_FILE_BYTES:
        mib = size / (1024 * 1024)
        raise ConfigError(f"{label} is {mib:.2f} MiB; deploy limit is 25 MiB per file")


def build(root: Path = ROOT, output: Path = DIST) -> None:
    scenes = load_config(root)
    demo3d = output / "demo3d"
    models_dir = demo3d / "models"
    static_dir = demo3d / "static"

    if output.exists():
        shutil.rmtree(output)
    models_dir.mkdir(parents=True)
    static_dir.mkdir(parents=True)

    for entry in scenes.values():
        slug = entry["public"]["slug"]
        source = entry["path"]
        destination = models_dir / f"{slug}.glb"
        check_file_size(source, f"Scene {slug}: {source.name}")
        shutil.copy2(source, destination)

    public_scenes = [entry["public"] for entry in scenes.values()]
    (demo3d / "scenes.json").write_text(
        json.dumps({"scenes": public_scenes}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    shutil.copy2(WEB / "index.html", demo3d / "index.html")
    shutil.copy2(WEB / "main.js", static_dir / "main.js")
    shutil.copy2(WEB / "style.css", static_dir / "style.css")
    copy_tree(WEB / "vendor", static_dir / "vendor")

    for path in (static_dir / "main.js", static_dir / "style.css", demo3d / "index.html"):
        check_file_size(path, path.name)

    (output / "index.html").write_text(ROOT_INDEX, encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build static Walk Viewer Web")
    parser.add_argument("--root", type=Path, default=ROOT, help="Repository root")
    parser.add_argument("--output", type=Path, default=DIST, help="Output directory")
    args = parser.parse_args()
    try:
        build(args.root, args.output)
    except ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Built {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
