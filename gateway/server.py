"""Okada Router gateway — OpenAI-compatible resilience layer.

Point any OpenAI SDK at http://localhost:8080/v1 and requests are routed
across cloud-large / cloud-small / alternate / cache / local / offline-queue
based on live network conditions.

Header `x-okada-mode: direct` bypasses all resilience (single attempt at the
primary cloud model, no cache, no fallback) — this emulates a naive app
calling the provider directly, and is what the benchmark compares against.
"""
import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from cache.cache import ResponseCache
from gateway.config import load_config
from gateway.providers import build_registry
from gateway.queue_store import QueueStore
from gateway.router import Decision, RoutingEngine
from gateway.telemetry import Telemetry
from network.health import NetworkMonitor
from network.simulator import PROFILES, simulator

cfg = load_config()
simulator.enabled = cfg["network"]["simulator_enabled"]
simulator.set_profile(cfg["network"]["default_profile"])

registry = build_registry(cfg)
engine = RoutingEngine(registry, cfg["routing"])
monitor = NetworkMonitor(simulator)
cache = ResponseCache(cfg["cache"]["ttl_s"], cfg["cache"]["max_entries"])
telemetry = Telemetry()
queue = QueueStore()


async def _flusher():
    """Replay queued requests when connectivity returns."""
    while True:
        await asyncio.sleep(2)
        if not queue.pending:
            continue
        state = monitor.get_state()
        if not state.online:
            continue
        for qid, item in list(queue.pending.items()):
            decision = Decision("cloud-large", "queued request replay after reconnect")
            result = await engine.execute(
                decision, state, item["messages"], item["max_tokens"], item["temperature"])
            if result.response is not None:
                result.response.setdefault("okada", {})["replayed_from_queue"] = qid
                queue.complete(qid, result.response)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_flusher())
    yield
    task.cancel()


app = FastAPI(title="Okada Router", lifespan=lifespan)
app.mount("/app", StaticFiles(directory=Path(__file__).resolve().parent.parent / "app", html=True))


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/app/")


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


def _sse(response: dict):
    """Wrap a complete response as OpenAI-style SSE chunks so stream=True
    clients work. True incremental streaming from providers is week 2."""
    base = {"id": response["id"], "object": "chat.completion.chunk",
            "created": response["created"], "model": response["model"]}
    content = response["choices"][0]["message"]["content"]

    def gen():
        first = dict(base, choices=[{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}])
        yield f"data: {json.dumps(first)}\n\n"
        for i in range(0, len(content), 48):
            chunk = dict(base, choices=[{"index": 0, "delta": {"content": content[i:i + 48]},
                                         "finish_reason": None}])
            yield f"data: {json.dumps(chunk)}\n\n"
        last = dict(base, choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}])
        yield f"data: {json.dumps(last)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
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

    state = monitor.get_state()

    if direct:
        role = registry.get("cloud-large")
        try:
            resp = await role.provider.chat(messages, role.model, max_tokens, temperature)
            ok, route, queued = True, "direct-cloud", False
        except Exception as e:
            resp = None
            ok, route, queued = False, "direct-cloud", False
            err = str(e)[:200]
        total_ms = (time.perf_counter() - t0) * 1000
        telemetry.record(
            request_id=request_id, network=state.to_dict(),
            decision={"route": "direct-cloud", "reason": "resilience bypassed (x-okada-mode: direct)"},
            attempts=[], final_route=route, cache_hit=False, queued=queued,
            retry_count=0, fallback_count=0, request_bytes=request_bytes,
            response_bytes=len(json.dumps(resp)) if resp else 0,
            usage=(resp or {}).get("usage", {}), model=role.model,
            total_ms=total_ms, success=ok)
        if not ok:
            return JSONResponse(
                {"error": {"message": f"upstream failure (no resilience): {err}", "type": "upstream_error"}},
                status_code=502)
        resp["okada"] = {"mode": "direct", "route": route, "network": state.to_dict()}
        return _sse(resp) if stream else resp

    cached = cache.get(messages)
    decision = engine.decide(state, cache_hit=cached is not None)

    if decision.route == "cache":
        resp = json.loads(json.dumps(cached))  # copy
        result_attempts, fallback_count, retry_count, queued = [], 0, 0, False
        final_route = "cache"
    else:
        result = await engine.execute(decision, state, messages, max_tokens, temperature)
        result_attempts = result.attempts
        fallback_count, retry_count, queued = result.fallback_count, result.retry_count, result.queued
        final_route = result.route
        if result.queued:
            qid = queue.add(messages, max_tokens, temperature)
            resp = _queued_response(qid, body.get("model", ""))
            resp["okada_queue_id"] = qid
        else:
            resp = result.response
            if final_route in ("cloud-large", "cloud-small", "alternate"):
                cache.set(messages, resp)

    total_ms = (time.perf_counter() - t0) * 1000
    model_used = resp.get("model", "")
    telemetry.record(
        request_id=request_id, network=state.to_dict(),
        decision={"route": decision.route, "reason": decision.reason},
        attempts=result_attempts, final_route=final_route,
        cache_hit=final_route == "cache", queued=queued,
        retry_count=retry_count, fallback_count=fallback_count,
        request_bytes=request_bytes, response_bytes=len(json.dumps(resp)),
        usage=resp.get("usage", {}), model=model_used.removeprefix("local/"),
        total_ms=total_ms, success=not queued)

    resp["okada"] = {
        "route": final_route,
        "reason": decision.reason,
        "network": state.to_dict(),
        "fallback_count": fallback_count,
        "retry_count": retry_count,
        "total_ms": round(total_ms, 1),
    }
    return _sse(resp) if stream else resp


@app.get("/v1/models")
async def models():
    data = [{"id": role.model, "object": "model", "owned_by": role.provider.name,
             "okada_route": route}
            for route, role in registry.roles.items()]
    return {"object": "list", "data": data}


@app.get("/okada/health")
async def health():
    return {
        "status": "ok",
        "mock_mode": registry.mock_mode,
        "routes": {
            route: {"provider": role.provider.name, "model": role.model,
                    "available": role.provider.available(),
                    "consecutive_failures": role.provider.health.consecutive_failures}
            for route, role in registry.roles.items()
        },
    }


@app.get("/okada/network")
async def get_network():
    return monitor.get_state().to_dict()


@app.post("/okada/network")
async def set_network(request: Request):
    body = await request.json()
    profile = body.get("profile")
    try:
        p = simulator.set_profile(profile)
    except KeyError as e:
        return JSONResponse({"error": str(e), "profiles": sorted(PROFILES)}, status_code=400)
    return {"ok": True, "profile": p.name, "state": monitor.get_state().to_dict()}


@app.get("/okada/stats")
async def stats():
    return telemetry.summary()


@app.get("/okada/queue")
async def queue_status():
    return queue.status()


@app.get("/okada/queue/{qid}")
async def queue_item(qid: str):
    if qid in queue.results:
        return {"status": "completed", **queue.results[qid]}
    if qid in queue.pending:
        return {"status": "pending"}
    return JSONResponse({"error": "unknown queue id"}, status_code=404)


@app.post("/okada/cache/clear")
async def cache_clear():
    cache.clear()
    return {"ok": True}
