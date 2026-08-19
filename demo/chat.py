#!/usr/bin/env python3
"""Terminal chat demo against the Okada gateway.

Usage:  python demo/chat.py
Commands inside the chat:
  /network <profile>   switch simulated network (excellent|4g|3g|edge|high-latency|packet-loss|intermittent|offline)
  /stats               gateway telemetry summary
  /queue               offline queue status
  /quit
"""
import sys

import httpx
from openai import OpenAI

BASE = "http://127.0.0.1:8080"
client = OpenAI(base_url=f"{BASE}/v1", api_key="okada")

ROUTE_ICON = {"cloud-large": "☁️ ", "cloud-small": "🌥 ", "alternate": "🔀",
              "cache": "⚡", "local": "📱", "queue": "📥"}


def main():
    print("Okada Router demo — /network <profile>, /stats, /queue, /quit")
    history = []
    while True:
        try:
            text = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text == "/quit":
            break
        if text.startswith("/network"):
            profile = text.split(maxsplit=1)[1] if " " in text else ""
            r = httpx.post(f"{BASE}/okada/network", json={"profile": profile})
            print(r.json())
            continue
        if text == "/stats":
            print(httpx.get(f"{BASE}/okada/stats").json())
            continue
        if text == "/queue":
            print(httpx.get(f"{BASE}/okada/queue").json())
            continue

        history.append({"role": "user", "content": text})
        resp = client.chat.completions.create(model="auto", messages=history)
        msg = resp.choices[0].message.content
        history.append({"role": "assistant", "content": msg})
        okada = getattr(resp, "okada", None) or resp.model_extra.get("okada", {})
        icon = ROUTE_ICON.get(okada.get("route", ""), "·")
        net = okada.get("network", {})
        print(f"\nokada[{icon} {okada.get('route')} | {net.get('profile')} "
              f"| {okada.get('total_ms')}ms | {okada.get('reason', '')}]")
        print(f"assistant> {msg}")


if __name__ == "__main__":
    sys.exit(main())
