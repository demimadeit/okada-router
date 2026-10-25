"""Tests for the Oct 2026 hardening: retired models, rate limits, durable
queue, streaming relay with mid-stream failover, telemetry labels, tenants."""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from gateway.model_probe import ModelProbe
from gateway.providers import (ModelNotFoundError, ProviderError, RateLimitedError, Registry,
                               Role, StreamChunk, classify_http_error)
from gateway.queue_store import QueueStore
from gateway.router import Decision, RoutingEngine
from gateway.telemetry import Telemetry, detect_lang
from gateway.tenants import Tenant, TenantRegistry
from network.health import NetworkState
from providers.mock_provider import MockCloudProvider, MockLocalProvider

CFG = {
    "small_latency_ms": 600, "small_loss": 0.05,
    "local_latency_ms": 2500, "local_loss": 0.25,
    "provider_failure_threshold": 3, "provider_cooldown_s": 30,
}


def state(online=True, latency=40, loss=0.0):
    return NetworkState(online=online, latency_ms=latency, packet_loss=loss,
                        profile="test", source="simulated")


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


# ---- error classification -----------------------------------------------

def test_classify_http_errors():
    assert isinstance(classify_http_error("groq", 404, '{"error":{"message":"model x does not exist"}}'),
                      ModelNotFoundError)
    assert isinstance(classify_http_error("groq", 400,
                      '{"error":{"message":"The model `llama-3.1-8b-instant` has been decommissioned","code":"model_decommissioned"}}'),
                      ModelNotFoundError)
    assert isinstance(classify_http_error("groq", 429, "rate limit reached"), RateLimitedError)
    plain = classify_http_error("groq", 500, "boom")
    assert isinstance(plain, ProviderError) and not isinstance(plain, (ModelNotFoundError, RateLimitedError))
    # a 400 that is not about the model is a plain provider error
    assert type(classify_http_error("groq", 400, "messages: field required")) is ProviderError


# ---- router: retired model and rate limit -------------------------------

def test_retired_primary_model_skips_rung_without_blaming_provider():
    reg = Registry()
    primary = MockCloudProvider("mock-cloud")
    reg.roles["cloud-large"] = Role(primary, "mock-retired")
    reg.roles["cloud-small"] = Role(primary, "mock-small")
    reg.roles["local"] = Role(MockLocalProvider(), "mock-local-model")
    eng = RoutingEngine(reg, CFG)
    d = eng.decide(state(), cache_hit=False)
    assert d.route == "cloud-large"
    res = run(eng.execute(d, state(), [{"role": "user", "content": "hi"}], 100, 0.0))
    assert res.route == "cloud-small"
    assert res.attempts[0].error_class == "model_gone"
    assert reg.roles["cloud-large"].model_ok is False
    # the PROVIDER is still healthy — only the model is marked gone
    assert primary.health.consecutive_failures == 0
    # and the next decision routes around the dead model up front
    d2 = eng.decide(state(), cache_hit=False)
    assert d2.route == "cloud-small" and "retired" in d2.reason


def test_rate_limited_rung_is_not_retried():
    reg = Registry()
    primary = MockCloudProvider("mock-cloud")
    reg.roles["cloud-large"] = Role(primary, "mock-ratelimited")
    reg.roles["alternate"] = Role(MockCloudProvider("mock-alt"), "mock-alt")
    eng = RoutingEngine(reg, CFG)
    res = run(eng.execute(Decision("cloud-large", "t"), state(),
                          [{"role": "user", "content": "hi"}], 100, 0.0))
    assert res.route == "alternate"
    large_attempts = [a for a in res.attempts if a.route == "cloud-large"]
    assert len(large_attempts) == 1 and large_attempts[0].error_class == "rate_limited"


def test_model_probe_marks_gone_and_recovers():
    reg = Registry()
    primary = MockCloudProvider("mock-cloud")
    reg.roles["cloud-large"] = Role(primary, "mock-retired")
    reg.roles["cloud-small"] = Role(primary, "mock-small")
    reg.roles["local"] = Role(MockLocalProvider(), "x")
    probe = ModelProbe(reg, interval_s=999)
    results = run(probe.probe_all())
    assert results["cloud-large"]["model_gone"] is True
    assert results["cloud-small"]["ok"] is True
    assert reg.roles["cloud-large"].model_ok is False
    # provider ships a replacement under the same config name
    reg.roles["cloud-large"].model = "mock-large"
    run(probe.probe_all())
    assert reg.roles["cloud-large"].model_ok is True


def test_tenant_allow_list_and_no_offshore():
    reg = Registry()
    primary = MockCloudProvider("mock-cloud")
    reg.roles["cloud-large"] = Role(primary, "mock-large")
    reg.roles["cloud-small"] = Role(primary, "mock-small")
    reg.roles["local"] = Role(MockLocalProvider(), "mock-local-model")
    eng = RoutingEngine(reg, CFG)
    chain = eng.chain(Decision("cloud-large", "t"), state(), allowed_models={"mock-small"})
    assert chain == ["cloud-small", "local", "queue"]
    d = eng.decide(state(), cache_hit=False, local_only=True)
    assert d.route == "local"
    assert eng.chain(d, state(), allow_cloud=False) == ["local", "queue"]


# ---- streaming relay with mid-stream failover ---------------------------

class DiesMidStream(MockCloudProvider):
    """Emits two words then fails, like a link that drops mid-answer."""
    async def chat_stream(self, messages, model, max_tokens, temperature):
        yield StreamChunk(text="Lagos is", model=model)
        yield StreamChunk(text=" the", model=model)
        raise ProviderError("connection reset by peer")


def test_stream_resumes_on_next_rung_without_restarting():
    reg = Registry()
    reg.roles["cloud-large"] = Role(DiesMidStream("flaky"), "mock-large")
    reg.roles["cloud-small"] = Role(MockCloudProvider("mock-cloud"), "mock-small")
    eng = RoutingEngine(reg, CFG)

    async def collect():
        out, routes, done = [], [], None
        async for kind, payload in eng.execute_stream(Decision("cloud-large", "t"), state(),
                                                      [{"role": "user", "content": "capital?"}],
                                                      100, 0.0):
            if kind == "delta":
                out.append(payload)
            elif kind == "route":
                routes.append(payload)
            else:
                done = payload
        return "".join(out), routes, done

    text, routes, result = run(collect())
    assert text.startswith("Lagos is the")
    assert "[mock:mock-small]" in text            # continuation came from the next rung
    assert routes == ["cloud-large", "cloud-small"]
    assert result.resumed == 1 and result.route == "cloud-small"
    assert result.response["choices"][0]["message"]["content"] == text
    assert result.attempts[0].ok is False and result.attempts[1].ok is True


def test_stream_with_no_rung_available_queues():
    reg = Registry()
    reg.roles["cloud-large"] = Role(MockCloudProvider("mock-cloud"), "mock-retired")
    eng = RoutingEngine(reg, CFG)

    async def last():
        final = None
        async for kind, payload in eng.execute_stream(Decision("cloud-large", "t"), state(),
                                                      [{"role": "user", "content": "x"}], 10, 0.0):
            final = (kind, payload)
        return final

    kind, result = run(last())
    assert kind == "done" and result.queued is True


# ---- durable queue -------------------------------------------------------

def test_queue_survives_restart_with_bodies(tmp_path):
    db = tmp_path / "q.sqlite"
    q = QueueStore(path=db, key=b"k" * 32)
    qid = q.add([{"role": "user", "content": "remember me"}], 50, 0.1, tenant="t1", idem_key="abc")
    assert q.add([{"role": "user", "content": "retry of the same"}], 50, 0.1, idem_key="abc") == qid
    q.close()

    q2 = QueueStore(path=db, key=b"k" * 32)       # "restart"
    assert qid in q2.pending
    assert q2.pending[qid]["messages"][0]["content"] == "remember me"
    assert q2.pending[qid]["tenant"] == "t1"
    # bodies are ciphertext on disk
    raw = q2.db.execute("SELECT body FROM queue WHERE id=?", (qid,)).fetchone()[0]
    assert b"remember me" not in bytes(raw)
    q2.complete(qid, {"choices": [{"message": {"content": "done"}}]})
    assert q2.db.execute("SELECT body FROM queue WHERE id=?", (qid,)).fetchone()[0] is None
    assert q2.get(qid)["status"] == "completed"
    q2.close()

    q3 = QueueStore(path=db, key=b"k" * 32)
    assert q3.get(qid)["response"]["choices"][0]["message"]["content"] == "done"
    q3.close()


def test_queue_wrong_key_marks_items_failed_not_crash(tmp_path):
    db = tmp_path / "q.sqlite"
    q = QueueStore(path=db, key=b"a" * 32)
    qid = q.add([{"role": "user", "content": "secret"}], 10, 0.0)
    q.close()
    q2 = QueueStore(path=db, key=b"b" * 32)
    assert qid not in q2.pending and q2.get(qid)["status"] == "failed"
    q2.close()


def test_queue_backoff_and_max_attempts(tmp_path):
    q = QueueStore(path=tmp_path / "q.sqlite", max_attempts=3)
    qid = q.add([{"role": "user", "content": "x"}], 10, 0.0)
    assert q.due() and q.due()[0]["id"] == qid
    q.fail_attempt(qid, "no route")
    assert not q.due()                                  # backing off
    assert q.due(now=time.time() + 11)                 # 5*2^1 = 10s later
    q.fail_attempt(qid, "no route")
    q.fail_attempt(qid, "no route")
    assert qid not in q.pending and q.get(qid)["status"] == "failed"
    q.close()


def test_queue_plaintext_without_key_and_purge(tmp_path):
    q = QueueStore(path=tmp_path / "q.sqlite", key=None, retention_s=1)
    qid = q.add([{"role": "user", "content": "plain"}], 10, 0.0)
    q.complete(qid, {"ok": True})
    q.purge(now=time.time() + 5)
    assert q.get(qid) is None
    assert q.status()["encrypted_at_rest"] is False
    q.close()


# ---- telemetry ------------------------------------------------------------

def test_lang_heuristic():
    assert detect_lang("abeg wetin dey happen for lagos") == "pcm"
    assert detect_lang("What is the capital of Nigeria and how do I get there?") == "en"
    assert detect_lang("sannu, yaya gida? ina lafiya") == "ha"
    assert detect_lang("habari yako, asante sana") == "sw"
    assert detect_lang("12345") == "und"


def test_telemetry_costs_and_reask(tmp_path):
    t = Telemetry(path=tmp_path / "t.jsonl", feedback_path=tmp_path / "f.jsonl")
    usage = {"prompt_tokens": 1_000_000, "completion_tokens": 1_000_000}
    list_cost, est = t.cost("openai/gpt-oss-120b", "groq", usage)
    assert list_cost == 0.75
    assert t.cost("local/qwen", "local-chain", usage) == (0.0, 0.0)
    msgs = [{"role": "user", "content": "how much is data?"}]
    kw = dict(network={}, decision={}, attempts=[], final_route="cloud-large", cache_hit=False,
              queued=False, retry_count=0, fallback_count=0, request_bytes=1, response_bytes=1,
              usage=usage, model="openai/gpt-oss-120b", total_ms=1.0, success=True,
              messages=msgs, provider="groq", tenant="t")
    r1 = t.record(request_id="a", **kw)
    assert "how much" not in json.dumps(r1)               # no prompt text retained
    assert r1["prompt_sha256"] and r1["lang"] == "en" and r1["reask_of"] is None
    r2 = t.record(request_id="b", **kw)
    assert r2["reask_of"] == "a"
    assert t._by_id["a"]["quality"] == "down(implicit)"
    assert t.feedback("b", "up") is True
    s = t.summary()
    assert s["reasks"] == 1 and s["feedback"] == {"up": 1, "down": 1}
    assert s["tenants"]["t"]["list_cost_usd"] == 1.5
    assert t.tenant_spend("t") == 1.5
    assert (tmp_path / "f.jsonl").read_text().count("\n") == 2


# ---- tenants ---------------------------------------------------------------

def test_tenant_registry_auth_and_windows():
    reg = TenantRegistry([Tenant(id="a", key="k1", max_budget_usd=1.0, budget_duration="daily")])
    assert reg.authenticate("Bearer k1").id == "a"
    assert reg.authenticate("Bearer nope") is None
    assert reg.authenticate(None) is None
    assert TenantRegistry([]).authenticate(None).id == "default"
    t = reg.by_key["k1"]
    assert time.time() - t.budget_window_start() < 86400
