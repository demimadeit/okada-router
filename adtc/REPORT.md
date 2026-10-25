# Okada Router — ADTC 2026 Gate 1 Report

> **Status: historical.** This was the Gate 1 submission draft (deadline 25 Aug
> 2026). The Africa Deep Tech Challenge 2026 concluded on 19 Oct 2026 and Okada
> Router was not among the published finalists. The document is kept as the
> record of what was claimed at the time; the figures in section 1 were
> corrected in Oct 2026 (see `docs/ROADMAP-2026-10.md` and the whitepaper's
> corrections log). Items marked ⏳ were never completed.

## 1. Problem definition

AI applications assume `app → stable internet → cloud API → response`. In
Nigeria that assumption fails daily: the NCC recorded **27,000+ fibre cuts
Jan–Nov 2025** (~75/day) and 5,000+ more in H1 2026; **82.5% of firms report
frequent power outages** (World Bank Enterprise Survey 2025); the NCC approved
a **50% rise in the 1GB data price cap** in Jan 2025; and frontier models are
served from the US and EU, so every Lagos request crosses a submarine cable.
(Earlier drafts said "~190 days/year of grid downtime", "data doubled in
price", "no inference capacity on the continent" and "~104ms floor" — none of
those survived source-checking and they are withdrawn.) When the link
degrades, every AI app shows a spinner and dies.

Okada Router makes AI answer anyway. It is an OpenAI-compatible gateway
that routes each request down a degradation ladder — cloud model → smaller
cloud model → alternate provider → cache → **local GGUF model via
llama.cpp** → offline queue with automatic sync on reconnect — driven by
measured network conditions. Offline is not an error state; it is a rung.

## 2. Identified constraints (challenge target: 8GB RAM, i5, no GPU)

- Model + KV cache + gateway + OS must fit ~8GB → 3B-class Q4 GGUF
  (~2.4GB weights) with 4K context, leaving headroom for the browser demo.
- CPU-only decode on an i5 → target usable throughput at 3B Q4;
  `max_tokens` capped at 512 so answers land in seconds, not minutes.
- Fully offline operation → llama.cpp serves GGUF locally; the gateway,
  cache and queue are pure Python with no external services.
- Cheap, intermittent power → gateway journals its queue to disk so a
  power cut does not silently lose pending work.

## 3. Design alternatives considered

| Alternative | Why rejected |
|---|---|
| Pure on-device app (no cloud tier) | Wastes the good-network case; 3B-class quality is a fallback, not a ceiling |
| Pure cloud gateway with retries (LiteLLM-style) | Dies exactly when Nigeria needs it: offline = failure |
| Ollama as the local runtime | Wraps llama.cpp with extra overhead; challenge targets llama.cpp/GGUF directly — we support both, llama.cpp preferred |
| Learned/ML routing policy | No training data yet; deterministic rules are debuggable and generate the labelled decision log a learned policy would need |
| OS-level network shaping (tc/netem) for the demo | Linux-only, root, another moving part; application-level simulation is deterministic and runtime-switchable |

## 4. Tools selected

llama.cpp (llama-server, GGUF Q4_K_M) · Qwen2.5-3B-Instruct GGUF (dev:
1.5B) · FastAPI + Uvicorn · httpx · pytest (19 tests) · vanilla-JS PWA-style
chat app served by the gateway.

## 5. Architecture

```
phone/laptop browser ──▶ Okada app (served at /)
                              │
                       Okada Gateway :8080  (OpenAI-compatible /v1)
                              │
              cache ── routing engine ── telemetry (JSONL)
                     │              │
              network healthy   degraded / offline
                     │              │
          cloud-large/small     llama-server :8081 (GGUF, offline)
          alternate provider    offline queue → auto-replay on reconnect
```

## 6. Performance benchmarks

Resilience, **real cloud** (Groq `openai/gpt-oss-120b` / `gpt-oss-20b`) vs
**real local GGUF** (Qwen2.5-1.5B Q4_K_M via llama-server), 8 requests per
cell, identical simulated network conditions applied to both modes.
Reproduce with `scripts/benchmark.py`; raw data in `logs/bench-*.json`.

| Network profile | Naive direct call | Okada | Okada's routes |
|---|---|---|---|
| excellent | 100% answered | 100% | cloud-large ×8 |
| 4g | 100% | 100% | cloud-large ×6, cloud-small ×2 |
| 3g | 50% | 100% | cloud-small ×7, local ×1 |
| high-latency | 100% | 100% | cloud-small ×8 |
| 30% packet loss | 75% | 100% | local ×8 |
| intermittent | 62% | 100% | local ×5, cloud-small ×3 |
| offline | **0%** | **100%** | local ×8 |
| **overall (n=56 per mode)** | **69.6% (39/56)** | **100% (56/56)** | |

Latency is the honest trade: Okada matches or beats the direct call on
healthy and high-latency links (p95 4029ms vs 4604ms on high-latency,
because the smaller model returns less data), and is deliberately slower
under heavy loss (p95 8400ms vs 1887ms) — the direct call is "faster" there
only because a quarter of its requests fail outright and are not counted.
Okada trades seconds for answers that arrive at all.

Honest scope note: network conditions are simulated at the application
layer, not measured on a Nigerian carrier. The cloud and local inference
are real.

Local throughput and memory (`scripts/measure_local.py`):

- Dev machine (Apple Silicon, Qwen2.5-1.5B Q4 via llama-server): median
  **12.5 tok/s**, min 8.3 tok/s, server RSS **974MB**; single-turn offline
  answer through the full gateway path in **~2.1s** (256-token cap on the
  local rung)
- **ADTC target (Ubuntu 22.04, 8GB, i5, no GPU, Qwen2.5-3B Q4): ⏳ MUST be
  measured on real target hardware before submission**

## 7. Localisation (⏳ before submission — worth +15%)

Planned: Nigerian Pidgin, Yoruba, Hausa, Igbo system-prompt evaluation set
with sample transcripts; document which languages the 3B model handles
usefully and where it degrades. Include honest failure examples.

## 8. Screenshots & video

- ⏳ Screenshot: app answering on `excellent` (route pill: cloud)
- ⏳ Screenshot: same conversation on `offline` (route pill: on-device)
- ⏳ 2-minute video per `adtc/VIDEO_SCRIPT.md`

## 9. Reproduce

```bash
./scripts/offline_setup.sh   # Ubuntu target: build llama.cpp, fetch GGUF, run
# then open http://127.0.0.1:8080 and pull the network cable
```

## 10. Team & stage

Solo founder, Nigeria-resident. Project age: < 1 month. External funding
raised: $0. Repository is open source.
