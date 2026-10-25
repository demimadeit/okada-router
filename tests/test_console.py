"""End-to-end tests for the Okada Cloud console API."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from gateway import server
from gateway.accounts import AccountStore
from gateway.providers import Role
from gateway.tenants import TenantRegistry
from providers.mock_provider import MockLocalProvider


@pytest.fixture()
def client(tmp_path, monkeypatch):
    store = AccountStore(tmp_path / "accounts.sqlite")
    monkeypatch.setattr(server, "accounts", store)
    monkeypatch.setattr(server, "tenants", TenantRegistry([], store=store))
    monkeypatch.setattr(server, "ADMIN_TOKEN", "adm-secret")
    server.registry.roles["local"] = Role(MockLocalProvider(), "mock-local-model")
    server.cache.clear()
    server.simulator.set_profile("excellent")
    with TestClient(server.app) as c:
        yield c
    store.close()


def signup(client, email="ada@example.com"):
    r = client.post("/console/api/signup", json={"email": email, "password": "hunter2hunter2",
                                                 "name": "Ada Pharmacy"})
    assert r.status_code == 200, r.text
    return r.json()


def auth(token):
    return {"authorization": f"Bearer {token}"}


def test_signup_gives_tenant_and_key_that_works_on_gateway(client):
    d = signup(client)
    assert d["first_key"].startswith("ok_live_") and d["token"].startswith("oks_")
    # gateway is no longer open once a key exists
    assert client.post("/v1/chat/completions",
                       json={"messages": [{"role": "user", "content": "hi"}]}).status_code == 401
    r = client.post("/v1/chat/completions", headers=auth(d["first_key"]),
                    json={"messages": [{"role": "user", "content": "hi from sdk"}]})
    assert r.status_code == 200 and r.json()["okada"]["route"] == "cloud-large"
    me = client.get("/console/api/me", headers=auth(d["token"])).json()
    assert me["account"]["email"] == "ada@example.com"
    t = me["tenants"][0]
    assert t["id"] == d["first_tenant"] and t["keys"][0]["prefix"] == d["first_key"][:12]
    assert t["requests_24h"] == 1


def test_login_logout_and_bad_password(client):
    signup(client)
    assert client.post("/console/api/login", json={"email": "ada@example.com",
                                                   "password": "wrong"}).status_code == 401
    tok = client.post("/console/api/login", json={"email": "ada@example.com",
                                                  "password": "hunter2hunter2"}).json()["token"]
    assert client.get("/console/api/me", headers=auth(tok)).status_code == 200
    client.post("/console/api/logout", headers=auth(tok))
    assert client.get("/console/api/me", headers=auth(tok)).status_code == 401
    assert client.post("/console/api/signup", json={"email": "ada@example.com", "password": "x" * 8,
                                                    "name": "dup"}).status_code == 400


def test_tenant_isolation_keys_budget_and_stats(client):
    a = signup(client, "a@example.com")
    b = signup(client, "b@example.com")
    # b cannot see or use a's tenant
    assert client.get(f"/console/api/tenants/{a['first_tenant']}", headers=auth(b["token"])).status_code == 404
    assert client.post(f"/console/api/tenants/{a['first_tenant']}/keys", headers=auth(b["token"]),
                       json={"name": "evil"}).status_code == 404
    # new tenant with a zero budget and no-offshore
    t = client.post("/console/api/tenants", headers=auth(a["token"]),
                    json={"name": "Clinic", "max_budget_usd": 0.0, "budget_duration": "daily",
                          "no_offshore": True}).json()
    assert t["no_offshore"] is True and t["id"].startswith("clinic-")
    k = client.post(f"/console/api/tenants/{t['id']}/keys", headers=auth(a["token"]),
                    json={"name": "prod"}).json()
    r = client.post("/v1/chat/completions", headers=auth(k["key"]),
                    json={"messages": [{"role": "user", "content": "x"}]})
    assert r.status_code == 429 and r.json()["error"]["type"] == "budget_exceeded"
    # lift the budget: local-only routing because of no_offshore
    client.patch(f"/console/api/tenants/{t['id']}", headers=auth(a["token"]),
                 json={"max_budget_usd": None})
    r = client.post("/v1/chat/completions", headers=auth(k["key"]),
                    json={"messages": [{"role": "user", "content": "private question"}]}).json()
    assert r["okada"]["route"] == "local"
    # revoke -> 401
    keys = client.get(f"/console/api/tenants/{t['id']}", headers=auth(a["token"])).json()["keys"]
    assert client.delete(f"/console/api/tenants/{t['id']}/keys/{keys[0]['id']}",
                         headers=auth(a["token"])).json()["ok"] is True
    assert client.post("/v1/chat/completions", headers=auth(k["key"]),
                       json={"messages": [{"role": "user", "content": "x"}]}).status_code == 401
    # stats are per tenant and carry no prompt text
    s = client.get(f"/console/api/tenants/{t['id']}/stats?hours=1", headers=auth(a["token"])).json()
    assert s["summary"]["requests"] == 1 and s["series"][0]["routes"] == {"local": 1}
    assert "private question" not in json.dumps(s)
    assert s["recent"][0]["route"] == "local"


def test_playground_streams_as_tenant_and_network_control(client):
    d = signup(client)
    r = client.post(f"/console/api/tenants/{d['first_tenant']}/chat", headers=auth(d["token"]),
                    json={"messages": [{"role": "user", "content": "playground"}], "stream": True})
    assert r.status_code == 200
    final = [json.loads(line[5:]) for line in r.text.splitlines()
             if line.startswith("data:") and "[DONE]" not in line][-1]
    assert final["okada"]["route"] == "cloud-large"
    # mock mode: signed-in users may flip the demo network
    n = client.post("/console/api/network", headers=auth(d["token"]), json={"profile": "offline"})
    assert n.status_code == 200
    net = client.get("/console/api/network", headers=auth(d["token"])).json()
    assert net["state"]["online"] is False and net["history"][-1]["online"] is False
    client.post("/console/api/network", headers=auth(d["token"]), json={"profile": "excellent"})


def test_admin_overview_requires_token(client):
    signup(client)
    assert client.get("/console/api/admin/overview").status_code == 403
    o = client.get("/console/api/admin/overview", headers={"x-okada-admin": "adm-secret"}).json()
    assert o["accounts"]["accounts"] == 1 and o["accounts"]["active_keys"] == 1


def test_console_page_served(client):
    r = client.get("/console/")
    assert r.status_code == 200 and "Okada Cloud" in r.text
