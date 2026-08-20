"""Network state as seen by the router.

Two sources, same NetworkState — routing logic never knows the difference:
- "sim":  state comes from the simulator profile (demo/dev, default)
- "real": state comes from continuous probes of REAL targets.

Real mode probes two kinds of target and keeps them separate, because they
answer different questions:

  internet  — is the last mile alive at all? (generic anycast endpoints)
  provider  — is the path to THIS inference provider healthy right now?

A healthy path to Google says nothing about the path to a given model
provider: different transit, different submarine route, different POP. So
each provider is probed at its own base URL and scored independently, and
the router can prefer whichever provider the network can actually reach.
"""
import asyncio
import statistics
import time
from collections import defaultdict, deque
from dataclasses import dataclass, asdict, field

import httpx

INTERNET_TARGETS = [
    ("internet:gstatic", "https://www.gstatic.com/generate_204"),
    ("internet:cloudflare", "https://cloudflare.com/cdn-cgi/trace"),
]
PROBE_INTERVAL_S = 3.0
PROBE_TIMEOUT_S = 2.5
WINDOW = 10


@dataclass
class TargetHealth:
    """Rolling health of one probe target."""
    samples: deque = field(default_factory=lambda: deque(maxlen=WINDOW))

    def record(self, ok: bool, ms: float):
        self.samples.append((ok, ms))

    @property
    def reachable(self) -> bool:
        recent = list(self.samples)[-3:]
        return any(ok for ok, _ in recent) if recent else True

    @property
    def latency_ms(self) -> float:
        oks = [ms for ok, ms in self.samples if ok]
        return round(statistics.median(oks), 1) if oks else 0.0

    @property
    def loss(self) -> float:
        s = list(self.samples)
        return round(1 - sum(1 for ok, _ in s if ok) / len(s), 2) if s else 0.0

    def to_dict(self):
        return {"reachable": self.reachable, "latency_ms": self.latency_ms,
                "loss": self.loss, "samples": len(self.samples)}


@dataclass
class NetworkState:
    online: bool
    latency_ms: float
    packet_loss: float
    profile: str
    source: str                       # "simulated" | "probe"
    providers: dict = field(default_factory=dict)   # name -> health dict

    def to_dict(self):
        return asdict(self)

    def provider_reachable(self, name: str) -> bool:
        """Unknown providers are assumed reachable — absence of evidence is
        not evidence of failure, and the fallback chain catches the rest."""
        p = self.providers.get(name)
        return True if p is None else p["reachable"]


class NetworkMonitor:
    def __init__(self, simulator):
        self.simulator = simulator
        self.mode = "sim"
        self.targets: list[tuple[str, str]] = list(INTERNET_TARGETS)
        self._health: dict[str, TargetHealth] = defaultdict(TargetHealth)
        self._i = 0

    def register_provider(self, name: str, base_url: str):
        """Probe the provider's own endpoint, so 'is the cloud reachable'
        means the cloud we actually intend to call."""
        key = f"provider:{name}"
        if any(k == key for k, _ in self.targets):
            return
        self.targets.append((key, base_url.rstrip("/") + "/models"))

    def set_mode(self, mode: str):
        self.mode = mode
        self.simulator.enabled = mode == "sim"
        if mode == "real":
            self._health.clear()

    def get_state(self) -> NetworkState:
        if self.mode == "sim":
            p = self.simulator.profile
            return NetworkState(
                online=self.simulator.currently_online(),
                latency_ms=p.latency_ms, packet_loss=p.packet_loss,
                profile=p.name, source="simulated",
            )
        net = [h for k, h in self._health.items() if k.startswith("internet:")]
        online = any(h.reachable for h in net) if net else True
        lat = [h.latency_ms for h in net if h.latency_ms > 0]
        loss = [h.loss for h in net if h.samples]
        return NetworkState(
            online=online,
            latency_ms=round(statistics.median(lat), 1) if lat else 0.0,
            packet_loss=round(max(loss), 2) if loss else 0.0,
            profile="real", source="probe",
            providers={k.split(":", 1)[1]: h.to_dict()
                       for k, h in self._health.items() if k.startswith("provider:")},
        )

    async def probe_once(self) -> None:
        if not self.targets:
            return
        key, url = self.targets[self._i % len(self.targets)]
        self._i += 1
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_S) as client:
                r = await client.get(url) if key.startswith("provider:") else await client.head(url)
            # 401/403 from a provider still proves the PATH is healthy —
            # we are measuring reachability, not authorisation.
            ok = r.status_code < 500
            self._health[key].record(ok, (time.perf_counter() - t0) * 1000)
        except Exception:
            self._health[key].record(False, 0.0)

    async def probe_loop(self):
        while True:
            if self.mode == "real":
                await self.probe_once()
            await asyncio.sleep(PROBE_INTERVAL_S)
