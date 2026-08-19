import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "config.yaml"


def _load_dotenv():
    """Minimal .env support: KEY=VALUE lines in the repo root, never
    overriding variables already set in the environment."""
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def load_config() -> dict:
    _load_dotenv()
    path = Path(os.getenv("OKADA_CONFIG", CONFIG_PATH))
    with open(path) as f:
        return yaml.safe_load(f)
