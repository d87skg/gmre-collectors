"""配置加载: sources.yaml / series.yaml / regime.yaml。"""
import os
from typing import Any, Dict

import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_yaml(name: str) -> Dict[str, Any]:
    path = os.path.join(BASE_DIR, "config", name)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config() -> Dict[str, Any]:
    return {
        "sources": load_yaml("sources.yaml"),
        "series": load_yaml("series.yaml"),
        "regime": load_yaml("regime.yaml"),
    }
