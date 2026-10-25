"""Okada Router gateway — OpenAI-compatible resilience layer.

Point any OpenAI SDK at http://localhost:8080/v1 and requests are routed
across cloud-large / cloud-small / alternate / cache / local / offline-queue
based on live network conditions.

Header `x-okada-mode: direct` bypasses all resilience (single attempt at the
primary cloud model, no cache, no fallback) — this emulates a naive app
calling the provider directly, and is what the benchmark compares against.

Other request headers:
  authorization: Bearer <key>     tenant virtual key (see gateway/tenants.py)
  x-okada-upstream-key: <key>     bring-your-own provider key for this call
  x-okada-idempotency-key: <id>   dedupe a retried request in the offline queue
"""
import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from cache.cache import ResponseCache
from gateway.config import load_config
from gateway.model_probe import ModelProbe
from gateway.providers import build_registry, upstream_key_override
from gateway.queue_store import QueueStore, load_key_from_env
from gateway.router import Decision, RoutingEngine
from gateway.telemetry import Telemetry
from gateway.tenants import Tenant, load_tenants
from network.health import NetworkMonitor
from network.simulator import PROFILES, simulator

log = logging.getLogger("okada")
logging.basicConfig(level=os.getenv("OKADA_LOG_LEVEL", "INFO"))

cfg = load_config()
simulator.enabled = cfg["network"]["simulator_enabled"]
simulator.set_profile(cfg["network"]["default_profile"])

registry = build_registry(cfg)
engine = RoutingEngine(registry, cfg["routing"])
monitor = NetworkMonitor(simulator)
# probe the path to each configured provider, not just "the internet"
for _route, _role in registry.roles.items():
    _base = getattr(_role.provider, "base_url", None)
    if _base and _role.provider.kind == "cloud":
        monitor.register_provider(_role.provider.name, _base)
# ...and the MODEL at each provider, with a real completion (path != model)
probe = ModelProbe(registry,
                   interval_s=cfg["routing"].get("model_probe_interval_s", 300),
                   enabled=os.getenv("OKADA_MODEL_PROBE", "1") != "0")
cache = ResponseCache(cfg["cache"]["ttl_s"], cfg["cache"]["max_entries"])
telemetry = Telemetry()
_qcfg = cfg.get("queue", {})
queue = QueueStore(path=Path(os.environ["OKADA_QUEUE_DB"]) if os.getenv("OKADA_QUEUE_DB") else None,
                   key=load_key_from_env(),
                   retention_s=_qcfg.get("retention_s", 86400),
                   max_attempts=_qcfg.get("max_attempts", 50))
tenants = load_tenants()


async def _flusher():
    """Replay queued requests when connectivity returns (and after a restart:
    the store reloads pending items from SQLite on construction)."""
    while True:
        await asyncio.sleep(2)
        queue.purge()
        if not queue.pending:
            continue
        state = monitor.get_state()
        if not state.online:
            continue
        for item in queue.due():
            qid = item["id"]
            decision = Decision("cloud-large", "queued request replay after reconnect")
            tenant = tenants.by_key and next(
                (t for t in tenants.by_key.values() if t.id == item.get("tenant")), None)
            result = await engine.execute(
                decision, state, item["messages"], item["max_tokens"], item["temperature"],
                allow_cloud=not (tenant and tenant.no_offshore))
            if result.response is not None:
                result.response.setdefault("okada", {})["replayed_from_queue"] = qid
                queue.complete(qid, result.response)
            else:
                err = result.attempts[-1].error if result.attempts else "no rung available"
                queue.fail_attempt(qid, err)


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [asyncio.create_task(_flusher()), asyncio.create_task(monitor.probe_loop()),
             asyncio.create_task(probe.loop())]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="Okada Router", lifespan=lifespan)
app.mount("/app", StaticFiles(directory=Path(__file__).resolve().parent.parent / "app", html=True))


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/app/")


def _auth(request: Request):
    """Resolve the tenant for this request. Returns (tenant, None) or
    (None, error response). With no keys configured the gateway is open."""
    tenant = tenants.authenticate(request.headers.get("authorization"))
    if tenant is None:
        return None, JSONResponse({"error": {"message": "missing or invalid Okada API key",
                                             "type": "auth_error"}}, status_code=401)
    return tenant, None


def _budget_exceeded(tenant: Tenant):
    if tenant.max_budget_usd is None:
        return None
    spent = telemetry.tenant_spend(tenant.id, tenant.budget_window_start())
    if spent >= tenant.max_budget_usd:
        return JSONResponse({"error": {
            "message": f"tenant budget exhausted ({spent:.4f} of {tenant.max_budget_usd} USD, "
                       f"{tenant.budget_duration})", "type": "budget_exceeded"}}, status_code=429)
    return None


def _queued_response(qid: str, model_hint: str) -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_hint or "okada-queue",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": ("[Okada] No connectivity and no local model could serve this "
                            f"request. It has been queued (id: {qid}) and will run "
                            "automatically when the connection returns. "
                            f"Poll /okada/queue/{qid} for the result."),
            },
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _chunk(base: dict, delta: dict, finish: str | None = None, extra: dict | None = None) -> str:
    c = dict(base, choices=[{"index": 0, "delta": delta, "finish_reason": finish}])
    if extra:
        c.update(extra)
    return f"data: {json.dumps(c)}\n\n"


def _sse_wrap(response: dict):
    """Emit an already-complete response (cache hit, queued notice, direct
    mode) as OpenAI-style SSE chunks."""
    base = {"id": response["id"], "object": "chat.completion.chunk",
            "created": response["created"], "model": response["model"]}
    content = response["choices"][0]["message"]["content"]

    def gen():
        yield _chunk(base, {"role": "assistant"})
        for i in range(0, len(content), 48):
            yield _chunk(base, {"content": content[i:i + 48]})
        yield _chunk(base, {}, "stop", {"okada": response.get("okada", {})})
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    tenant, denied = _auth(request)
    if denied:
        return denied
    if denied := _budget_exceeded(tenant):
        return denied
    t0 = time.perf_counter()
    body = await request.json()
    messages = body.get("messages", [])
    if not messages:
        return JSONResponse({"error": {"message": "messages is required"}}, status_code=400)
    max_tokens = body.get("max_tokens") or cfg["routing"]["max_tokens_default"]
    temperature = body.get("temperature", 0.7)
    stream = bool(body.get("stream", False))
    direct = request.headers.get("x-okada-mode", "").lower() == "direct"
    request_id = f"okr_{uuid.uuid4().hex[:10]}"
    request_bytes = int(request.headers.get("content-length") or 0)
    idem_key = request.headers.get("x-okada-idempotency-key") or body.get("okada_idempotency_key")

    # bring-your-own upstream key: per-request header beats tenant config
    overrides = dict(tenant.upstream_keys)
    if request.headers.get("x-okada-upstream-key"):
        overrides["*"] = request.headers["x-okada-upstream-key"]
    token = upstream_key_override.set(overrides or None)
    try:
        state = monitor.get_state()
        allowed = set(tenant.models_allowed) if tenant.models_allowed else None

        if direct:
            return await _direct(request_id, tenant, state, messages, max_tokens, temperature,
                                 stream, request_bytes, t0)

        cached = cache.get(messages, tenant.id)
        decision = engine.decide(state, cache_hit=cached is not None,
                                 local_only=tenant.no_offshore)

        if decision.route == "cache":
            resp = json.loads(json.dumps(cached))  # copy
            return _finish(request_id, tenant, state, decision, [], "cache", resp, messages,
                           max_tokens, request_bytes, t0, stream, cache_hit=True)

        if stream:
            return _stream(request_id, tenant, state, decision, messages, max_tokens,
                           temperature, request_bytes, t0, idem_key, allowed, body.get("model", ""),
                           overrides)

        result = await engine.execute(decision, state, messages, max_tokens, temperature,
                                      degraded_cap=tenant.degraded_max_tokens,
                                      allow_cloud=not tenant.no_offshore, allowed_models=allowed)
        if result.queued:
            qid = queue.add(messages, max_tokens, temperature, tenant=tenant.id, idem_key=idem_key)
            resp = _queued_response(qid, body.get("model", ""))
            resp["okada_queue_id"] = qid
        else:
            resp = result.response
            if result.route in ("cloud-large", "cloud-small", "alternate"):
                cache.set(messages, resp, tenant.id)
        return _finish(request_id, tenant, state, decision, result.attempts, result.route, resp,
                       messages, max_tokens, request_bytes, t0, stream,
                       fallback_count=result.fallback_count, retry_count=result.retry_count,
                       queued=result.queued)
    finally:
        upstream_key_override.reset(token)


def _provider_for(route: str) -> str:
    role = registry.get(route)
    return role.provider.name if role else ("cache" if route == "cache" else "")


def _finish(request_id, tenant, state, decision, attempts, final_route, resp, messages,
            max_tokens, request_bytes, t0, stream, *, cache_hit=False, fallback_count=0,
            retry_count=0, queued=False):
    total_ms = (time.perf_counter() - t0) * 1000
    model_used = resp.get("model", "")
    telemetry.record(
        request_id=request_id, network=state.to_dict(),
        decision={"route": decision.route, "reason": decision.reason},
        attempts=attempts, final_route=final_route,
        cache_hit=cache_hit, queued=queued,
        retry_count=retry_count, fallback_count=fallback_count,
        request_bytes=request_bytes, response_bytes=len(json.dumps(resp)),
        usage=resp.get("usage", {}), model=model_used,
        total_ms=total_ms, success=not queued, messages=messages,
        provider=_provider_for(final_route), tenant=tenant.id,
        response_text=resp["choices"][0]["message"].get("content", ""))
    resp["okada"] = {
        "request_id": request_id,
        "route": final_route,
        "reason": decision.reason,
        "network": state.to_dict(),
        "fallback_count": fallback_count,
        "retry_count": retry_count,
        "total_ms": round(total_ms, 1),
    }
    return _sse_wrap(resp) if stream else resp


async def _direct(request_id, tenant, state, messages, max_tokens, temperature, stream,
                  request_bytes, t0):
    role = registry.get("cloud-large")
    err = ""
    try:
        resp = await role.provider.chat(messages, role.model, max_tokens, temperature)
        ok = True
    except Exception as e:
        resp, ok, err = None, False, str(e)[:200]
    total_ms = (time.perf_counter() - t0) * 1000
    telemetry.record(
        request_id=request_id, network=state.to_dict(),
        decision={"route": "direct-cloud", "reason": "resilience bypassed (x-okada-mode: direct)"},
        attempts=[], final_route="direct-cloud", cache_hit=False, queued=False,
        retry_count=0, fallback_count=0, request_bytes=request_bytes,
        response_bytes=len(json.dumps(resp)) if resp else 0,
        usage=(resp or {}).get("usage", {}), model=role.model, provider=role.provider.name,
        total_ms=total_ms, success=ok, messages=messages, tenant=tenant.id,
        response_text=(resp or {}).get("choices", [{}])[0].get("message", {}).get("content", ""))
    if not ok:
        return JSONResponse(
            {"error": {"message": f"upstream failure (no resilience): {err}", "type": "upstream_error"}},
            status_code=502)
    resp["okada"] = {"request_id": request_id, "mode": "direct", "route": "direct-cloud",
                     "network": state.to_dict()}
    return _sse_wrap(resp) if stream else resp


def _stream(request_id, tenant, state, decision, messages, max_tokens, temperature,
            request_bytes, t0, idem_key, allowed, model_hint, overrides):
    """True token relay: provider SSE -> client SSE, with mid-stream failover
    handled by the engine (the client sees one continuous answer)."""
    base = {"id": f"chatcmpl-{request_id}", "object": "chat.completion.chunk",
            "created": int(time.time()), "model": "okada"}

    async def gen():
        token = upstream_key_override.set(overrides or None)
        sent_role = False
        text_out = ""
        try:
            events = engine.execute_stream(decision, state, messages, max_tokens, temperature,
                                           degraded_cap=tenant.degraded_max_tokens,
                                           allow_cloud=not tenant.no_offshore,
                                           allowed_models=allowed)
            async for kind, payload in events:
                if kind == "route":
                    if not sent_role:
                        yield _chunk(base, {"role": "assistant"})
                        sent_role = True
                    yield _chunk(base, {}, None, {"okada": {"route": payload, "event": "rung"}})
                elif kind == "delta":
                    text_out += payload
                    yield _chunk(base, {"content": payload})
                else:
                    result = payload
                    total_ms = (time.perf_counter() - t0) * 1000
                    if result.queued:
                        qid = queue.add(messages, max_tokens, temperature, tenant=tenant.id,
                                        idem_key=idem_key)
                        resp = _queued_response(qid, model_hint)
                        resp["okada_queue_id"] = qid
                        if not sent_role:
                            yield _chunk(base, {"role": "assistant"})
                        yield _chunk(base, {"content": resp["choices"][0]["message"]["content"]})
                    else:
                        resp = result.response
                        if result.route in ("cloud-large", "cloud-small", "alternate") \
                                and resp["choices"][0]["finish_reason"] == "stop":
                            cache.set(messages, resp, tenant.id)
                    okada = {
                        "request_id": request_id,
                        "route": result.route,
                        "reason": decision.reason,
                        "network": state.to_dict(),
                        "fallback_count": result.fallback_count,
                        "retry_count": result.retry_count,
                        "resumed": result.resumed,
                        "total_ms": round(total_ms, 1),
                    }
                    if result.queued:
                        okada["queue_id"] = resp["okada_queue_id"]
                    telemetry.record(
                        request_id=request_id, network=state.to_dict(),
                        decision={"route": decision.route, "reason": decision.reason},
                        attempts=result.attempts, final_route=result.route,
                        cache_hit=False, queued=result.queued,
                        retry_count=result.retry_count, fallback_count=result.fallback_count,
                        request_bytes=request_bytes, response_bytes=len(text_out),
                        usage=resp.get("usage", {}), model=resp.get("model", ""),
                        total_ms=total_ms, success=not result.queued, messages=messages,
                        provider=_provider_for(result.route), tenant=tenant.id,
                        streamed=True, resumed=result.resumed, response_text=text_out)
                    yield _chunk(dict(base, model=resp.get("model", "okada")), {},
                                 resp["choices"][0]["finish_reason"], {"okada": okada})
            yield "data: [DONE]\n\n"
        finally:
            upstream_key_override.reset(token)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/v1/models")
async def models():
    data = [{"id": role.model, "object": "model", "owned_by": role.provider.name,
             "okada_route": route, "model_ok": role.model_ok}
            for route, role in registry.roles.items()]
    return {"object": "list", "data": data}


@app.get("/okada/health")
async def health():
    return {
        "status": "ok",
        "mock_mode": registry.mock_mode,
        "auth": "open" if tenants.open else f"{len(tenants.by_key)} key(s)",
        "queue_encrypted_at_rest": queue.cipher.enabled,
        "routes": {
            route: {"provider": role.provider.name, "model": role.model,
                    "available": role.provider.available(),
                    "model_ok": role.model_ok,
                    "model_error": role.model_error or None,
                    "consecutive_failures": role.provider.health.consecutive_failures}
            for route, role in registry.roles.items()
        },
        "model_probe": {"enabled": probe.enabled, "interval_s": probe.interval_s,
                        "last_run": probe.last_run, "results": probe.last_results},
    }


@app.post("/okada/probe/models")
async def probe_models(request: Request):
    _, denied = _auth(request)
    if denied:
        return denied
    return {"ok": True, "results": await probe.probe_all()}


@app.get("/okada/network")
async def get_network():
    return monitor.get_state().to_dict()


@app.post("/okada/network")
async def set_network(request: Request):
    _, denied = _auth(request)
    if denied:
        return denied
    body = await request.json()
    profile = body.get("profile")
    if profile == "real":
        monitor.set_mode("real")
        # prime the window so the switch reflects reality immediately
        for _ in range(3):
            await monitor.probe_once()
        return {"ok": True, "profile": "real", "state": monitor.get_state().to_dict()}
    try:
        monitor.set_mode("sim")
        p = simulator.set_profile(profile)
    except KeyError as e:
        return JSONResponse({"error": str(e), "profiles": sorted(PROFILES) + ["real"]},
                            status_code=400)
    return {"ok": True, "profile": p.name, "state": monitor.get_state().to_dict()}


@app.get("/okada/stats")
async def stats():
    return telemetry.summary()


@app.post("/okada/feedback")
async def feedback(request: Request):
    """Explicit quality label for a request_id (found in the okada block)."""
    tenant, denied = _auth(request)
    if denied:
        return denied
    body = await request.json()
    rating = body.get("rating")
    if rating not in ("up", "down") or not body.get("request_id"):
        return JSONResponse({"error": "request_id and rating (up|down) are required"},
                            status_code=400)
    known = telemetry.feedback(body["request_id"], rating, body.get("comment", ""), tenant.id)
    return {"ok": True, "known_request": known}


@app.get("/okada/queue")
async def queue_status(request: Request):
    _, denied = _auth(request)
    if denied:
        return denied
    return queue.status()


@app.get("/okada/queue/{qid}")
async def queue_item(qid: str, request: Request):
    _, denied = _auth(request)
    if denied:
        return denied
    item = queue.get(qid)
    if item is None:
        return JSONResponse({"error": "unknown queue id"}, status_code=404)
    return item


@app.post("/okada/cache/clear")
async def cache_clear(request: Request):
    _, denied = _auth(request)
    if denied:
        return denied
    cache.clear()
    return {"ok": True}


@app.get("/okada/tenant")
async def whoami(request: Request):
    tenant, denied = _auth(request)
    if denied:
        return denied
    return {**tenant.public(),
            "spent_usd_window": telemetry.tenant_spend(tenant.id, tenant.budget_window_start())}
