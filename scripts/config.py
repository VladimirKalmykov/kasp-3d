"""Scene catalog validation shared by the static build."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

SLUG = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
MAX_FILE_BYTES = 25 * 1024 * 1024


class ConfigError(ValueError):
    pass


def load_config(root: Path) -> dict[str, dict]:
    config_path = root / "scenes.json"
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Cannot read scenes.json: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("scenes"), list):
        raise ConfigError("scenes.json needs a scenes array")

    scenes: dict[str, dict] = {}
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
        if not path.is_file():
            raise ConfigError(f"Scene {slug}: file not found: {file_name}")

        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            mib = size / (1024 * 1024)
            raise ConfigError(
                f"Scene {slug}: {file_name} is {mib:.2f} MiB; deploy limit is 25 MiB per file"
            )

        public = {"slug": slug, "title": title}
        for name in ("anchor", "distance", "yaw", "pitch"):
            value = item.get(name)
            if value is None:
                continue
            if name == "anchor":
                if (
                    not isinstance(value, list)
                    or len(value) != 3
                    or any(
                        isinstance(x, bool)
                        or not isinstance(x, (int, float))
                        or not math.isfinite(x)
                        for x in value
                    )
                ):
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
