from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_yaml(path: Path | str) -> dict[str, Any]:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    try:
        import yaml
    except ModuleNotFoundError:
        return json.loads(text)
    loaded = yaml.safe_load(text)
    return loaded or {}


def load_project_config(config_dir: Path | str = "config") -> dict[str, Any]:
    root = Path(config_dir)
    return {
        "queries": load_yaml(root / "queries.yaml"),
        "platforms": load_yaml(root / "platforms.yaml"),
        "companies": load_yaml(root / "companies.yaml"),
        "taxonomy": load_yaml(root / "taxonomy.yaml"),
        "llm": load_yaml(root / "llm.yaml"),
    }
