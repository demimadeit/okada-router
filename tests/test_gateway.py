"""End-to-end gateway tests through the FastAPI app with mock providers.

The simulator is the real one; profiles are switched via the API exactly as
the demo does. Ollama is replaced by a mock local provider so tests do not
depend on a running Ollama.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from gateway import server
from gateway.providers import Role
from providers.mock_provider import MockLocalProvider


@pytest.fixture()
def client():
    # deterministic test setup: mock local model, clean cache/telemetry state
    server.registry.roles["local"] = Role(MockLocalProvider(), "mock-local-model")
    server.cache.clear()
    server.simulator.set_profile("excellent")
    with TestClient(server.app) as c:
        yield c
    server.simulator.set_profile("excellent")


def chat(client, text, **extra):
    return client.post("/v1/chat/completions",
                       json={"model": "auto", "messages": [{"role": "user", "content": text}], **extra})


def test_healthy_network_routes_to_cloud_large(client):
    r = chat(client, "hello okada")
    assert r.status_code == 200
    body = r.json()
    assert body["okada"]["route"] == "cloud-large"
    assert "choices" in body and body["choices"][0]["message"]["content"]


def test_degraded_network_routes_to_cloud_small(client):
    client.post("/okada/network", json={"profile": "high-latency"})
    r = chat(client, "hello under high latency")
    # 2% simulated loss can push one rung down the ladder
    assert r.json()["okada"]["route"] in ("cloud-small", "alternate", "local")


def test_offline_routes_to_local(client):
    client.post("/okada/network", json={"profile": "offline"})
    r = chat(client, "hello while offline")
    body = r.json()
    assert body["okada"]["route"] == "local"
    assert "mock-local" in body["choices"][0]["message"]["content"]


def test_offline_without_local_queues_and_flusher_replays(client):
    server.registry.roles.pop("local")
    try:
        client.post("/okada/network", json={"profile": "offline"})
        r = chat(client, "queue me please")
        body = r.json()
        assert body["okada"]["route"] == "queue"
        qid = body["okada_queue_id"]
        assert client.get(f"/okada/queue/{qid}").json()["status"] == "pending"

        # connection returns; flusher (2s loop) replays the queued request
        client.post("/okada/network", json={"profile": "excellent"})
        import time
        deadline = time.time() + 8
        status = "pending"
        while time.time() < deadline and status != "completed":
            time.sleep(0.5)
            status = client.get(f"/okada/queue/{qid}").json()["status"]
        assert status == "completed"
    finally:
        server.registry.roles["local"] = Role(MockLocalProvider(), "mock-local-model")


def test_exact_cache_hit_on_repeat(client):
    q = "what are your opening hours?"
    first = chat(client, q).json()
    assert first["okada"]["route"] == "cloud-large"
    second = chat(client, q).json()
    assert second["okada"]["route"] == "cache"


def test_direct_mode_fails_offline_where_okada_survives(client):
    client.post("/okada/network", json={"profile": "offline"})
    direct = client.post("/v1/chat/completions",
                         headers={"x-okada-mode": "direct"},
                         json={"messages": [{"role": "user", "content": "hi"}]})
    assert direct.status_code == 502  # naive app: hard failure
    okada = chat(client, "hi")
    assert okada.status_code == 200
    assert okada.json()["okada"]["route"] == "local"


def test_real_mode_toggle(client):
    r = client.post("/okada/network", json={"profile": "real"})
    assert r.status_code == 200
    state = client.get("/okada/network").json()
    assert state["source"] == "probe" and state["profile"] == "real"
    r = client.post("/okada/network", json={"profile": "excellent"})
    assert client.get("/okada/network").json()["source"] == "simulated"


def test_stats_endpoint_reports(client):
    chat(client, "stats please")
    s = client.get("/okada/stats").json()
    assert s["requests"] >= 1
    assert "p50_ms" in s
