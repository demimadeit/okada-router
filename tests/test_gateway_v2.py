"""End-to-end tests for streaming, idempotent queueing, feedback, tenants and
the model-probe endpoint through the FastAPI app."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from gateway import server
from gateway.providers import Role
from gateway.tenants import Tenant, TenantRegistry
from providers.mock_provider import MockLocalProvider


@pytest.fixture()
def client():
    server.registry.roles["local"] = Role(MockLocalProvider(), "mock-local-model")
    server.cache.clear()
    server.simulator.set_profile("excellent")
    with TestClient(server.app) as c:
        yield c
    server.simulator.set_profile("excellent")
    server.registry.roles["cloud-large"] = Role(server.registry.roles["cloud-small"].provider,
                                                "mock-large")
    server.registry.roles["cloud-large"].mark_model_ok()


def sse(client, text, **headers):
    r = client.post("/v1/chat/completions", headers=headers,
                    json={"model": "auto", "stream": True,
                          "messages": [{"role": "user", "content": text}]})
    assert r.status_code == 200
    events = [json.loads(line[5:]) for line in r.text.splitlines()
              if line.startswith("data:") and line[5:].strip() != "[DONE]"]
    return events


def test_streaming_relays_deltas_and_final_okada_block(client):
    events = sse(client, "stream me")
    deltas = [e["choices"][0]["delta"].get("content", "") for e in events]
    text = "".join(deltas)
    assert "[mock:mock-large]" in text and "stream me" in text
    assert events[0]["choices"][0]["delta"] == {"role": "assistant"}
    final = events[-1]
    assert final["choices"][0]["finish_reason"] == "stop"
    assert final["okada"]["route"] == "cloud-large"
    assert final["okada"]["request_id"].startswith("okr_")
    # streamed answers are cached like any other cloud answer
    second = client.post("/v1/chat/completions",
                         json={"messages": [{"role": "user", "content": "stream me"}]}).json()
    assert second["okada"]["route"] == "cache"


def test_streaming_offline_goes_local(client):
    client.post("/okada/network", json={"profile": "offline"})
    events = sse(client, "offline stream")
    assert events[-1]["okada"]["route"] == "local"
    assert any("mock-local" in (e["choices"][0]["delta"].get("content") or "") for e in events)


def test_retired_model_routes_around_after_probe(client):
    server.registry.roles["cloud-large"].model = "mock-retired"
    r = client.post("/okada/probe/models")
    assert r.status_code == 200
    assert r.json()["results"]["cloud-large"]["model_gone"] is True
    h = client.get("/okada/health").json()
    assert h["routes"]["cloud-large"]["model_ok"] is False
    body = client.post("/v1/chat/completions",
                       json={"messages": [{"role": "user", "content": "still works?"}]}).json()
    # mock mode has an alternate provider, so failover beats degrading
    assert body["okada"]["route"] in ("alternate", "cloud-small")
    assert "retired" in body["okada"]["reason"]


def test_idempotent_queue_and_feedback(client):
    server.registry.roles.pop("local")
    try:
        client.post("/okada/network", json={"profile": "offline"})
        # unique per run: the queue is durable, so a fixed key would find the
        # completed item from the previous test run (which is the correct behaviour)
        import uuid
        h = {"x-okada-idempotency-key": f"order-{uuid.uuid4().hex[:8]}"}
        a = client.post("/v1/chat/completions", headers=h,
                        json={"messages": [{"role": "user", "content": "queue me"}]}).json()
        b = client.post("/v1/chat/completions", headers=h,
                        json={"messages": [{"role": "user", "content": "queue me"}]}).json()
        assert a["okada_queue_id"] == b["okada_queue_id"]
        st = client.get("/okada/queue").json()
        assert len([p for p in st["pending"] if p["id"] == a["okada_queue_id"]]) == 1
        fb = client.post("/okada/feedback", json={"request_id": a["okada"]["request_id"],
                                                  "rating": "down", "comment": "slow"})
        assert fb.json() == {"ok": True, "known_request": True}
        assert client.post("/okada/feedback", json={"rating": "meh"}).status_code == 400
    finally:
        server.registry.roles["local"] = Role(MockLocalProvider(), "mock-local-model")
        client.post("/okada/network", json={"profile": "excellent"})


def test_tenant_keys_budget_and_no_offshore(client, monkeypatch):
    reg = TenantRegistry([
        Tenant(id="shop", key="k-shop", max_budget_usd=0.0, budget_duration="daily"),
        Tenant(id="clinic", key="k-clinic", no_offshore=True),
        Tenant(id="free", key="k-free"),
    ])
    monkeypatch.setattr(server, "tenants", reg)
    msg = {"messages": [{"role": "user", "content": "tenant test"}]}
    assert client.post("/v1/chat/completions", json=msg).status_code == 401
    assert client.post("/v1/chat/completions", json=msg,
                       headers={"authorization": "Bearer k-shop"}).status_code == 429
    r = client.post("/v1/chat/completions", json=msg,
                    headers={"authorization": "Bearer k-clinic"}).json()
    assert r["okada"]["route"] == "local" and "no-offshore" in r["okada"]["reason"]
    r = client.post("/v1/chat/completions", json=msg,
                    headers={"authorization": "Bearer k-free"}).json()
    assert r["okada"]["route"] == "cloud-large"
    # cache is namespaced per tenant: clinic's local answer never leaks to free
    r2 = client.post("/v1/chat/completions", json=msg,
                     headers={"authorization": "Bearer k-free"}).json()
    assert r2["okada"]["route"] == "cache" and "[mock:" in r2["choices"][0]["message"]["content"]
    me = client.get("/okada/tenant", headers={"authorization": "Bearer k-clinic"}).json()
    assert me["tenant"] == "clinic" and me["no_offshore"] is True
    assert client.get("/okada/queue").status_code == 401


def test_stats_include_new_fields(client):
    client.post("/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "abeg wetin dey happen"}]})
    s = client.get("/okada/stats").json()
    assert "served_without_cloud_rate" in s and "langs" in s and "tenants" in s
    assert s["langs"].get("pcm", 0) >= 1
