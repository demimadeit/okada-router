#!/usr/bin/env python3
"""Verify every model ID in config/config.yaml against the provider's live
/v1/models, and optionally run a one-token completion per model.

    .venv/bin/python scripts/check_models.py            # list check only
    .venv/bin/python scripts/check_models.py --complete # also a real 1-token call

Exit status 1 if any configured model is missing. Run this after any provider
deprecation notice and before a demo; Groq removed two model families in
Aug–Sep 2026 and path health checks kept passing.
"""
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gateway.config import load_config          # noqa: E402
from gateway.providers import COMPAT_SOURCES     # noqa: E402

cfg = load_config()
do_complete = "--complete" in sys.argv
bad = 0

for key_env, name, base_url in COMPAT_SOURCES:
    key = os.getenv(key_env)
    if not key or name not in cfg["models"]:
        continue
    want = {cfg["models"][name]["large"], cfg["models"][name]["small"]}
    if name == "anthropic":
        url, headers = "https://api.anthropic.com/v1/models", {"x-api-key": key,
                                                               "anthropic-version": "2023-06-01"}
    else:
        url, headers = f"{base_url}/models", {"Authorization": f"Bearer {key}"}
    try:
        r = httpx.get(url, headers=headers, timeout=15)
        live = {m["id"] for m in r.json().get("data", [])}
    except Exception as e:
        print(f"[{name}] could not list models: {e}")
        bad += 1
        continue
    for m in sorted(want):
        ok = m in live
        print(f"[{name}] {m:40s} {'OK' if ok else 'MISSING from /models'}")
        bad += 0 if ok else 1
        if do_complete and name != "anthropic":
            try:
                c = httpx.post(f"{base_url}/chat/completions", headers=headers, timeout=30,
                               json={"model": m, "max_tokens": 1,
                                     "messages": [{"role": "user", "content": "ping"}]})
                print(f"    completion -> HTTP {c.status_code}"
                      + ("" if c.status_code == 200 else f": {c.text[:120]}"))
                bad += 0 if c.status_code == 200 else 1
            except Exception as e:
                print(f"    completion failed: {e}")
                bad += 1

print("\nall configured models present" if bad == 0 else f"\n{bad} problem(s)")
sys.exit(1 if bad else 0)
