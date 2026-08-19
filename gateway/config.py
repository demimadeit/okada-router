import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "config.yaml"


def load_config() -> dict:
    path = Path(os.getenv("OKADA_CONFIG", CONFIG_PATH))
    with open(path) as f:
        return yaml.safe_load(f)
