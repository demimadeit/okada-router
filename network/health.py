"""Network state as seen by the router.

Two sources, same NetworkState — routing logic never knows the difference:
- "sim":  state comes from the simulator profile (demo/dev, default)
- "real": state comes from continuous lightweight probes of the actual
  network — latency is the median of recent successful probes, packet loss
  is the failure fraction of the probe window, offline means the last
  probes actually failed. Kill the WiFi and the router notices by itself.
"""
import asyncio
import statistics
import time
from collections import deque
from dataclasses import dataclass, asdict

import httpx

from network.simulator import NetworkSimulator

PROBE_URLS = [
    "https://www.gstatic.com/generate_204",
    "https://cloudflare.com/cdn-cgi/trace",
]
PROBE_INTERVAL_S = 2.0
PROBE_TIMEOUT_S = 2.0
WINDOW = 10


@dataclass
class NetworkState:
    online: bool
    latency_ms: float
    packet_loss: float
    profile: str
    source: str  # "simulated" | "probe"

    def to_dict(self):
        return asdict(self)


class NetworkMonitor:
    def __init__(self, simulator: NetworkSimulator):
        self.simulator = simulator
        self.mode = "sim"
        self._window: deque[tuple[bool, float]] = deque(maxlen=WINDOW)
        self._probe_i = 0

    def set_mode(self, mode: str):
        self.mode = mode
        self.simulator.enabled = mode == "sim"
        if mode == "real":
            self._window.clear()

    def get_state(self) -> NetworkState:
        if self.mode == "sim":
            p = self.simulator.profile
            return NetworkState(
                online=self.simulator.currently_online(),
                latency_ms=p.latency_ms,
                packet_loss=p.packet_loss,
                profile=p.name,
                source="simulated",
            )
        window = list(self._window)
        oks = [ms for ok, ms in window if ok]
        # offline = the last 2 consecutive probes both actually failed
        recent = window[-2:]
        online = not (len(recent) == 2 and not any(ok for ok, _ in recent))
        return NetworkState(
            online=online,
            latency_ms=round(statistics.median(oks), 1) if oks else 0.0,
            packet_loss=round(1 - len(oks) / len(window), 2) if window else 0.0,
            profile="real",
            source="probe",
        )

    async def probe_once(self) -> None:
        url = PROBE_URLS[self._probe_i % len(PROBE_URLS)]
        self._probe_i += 1
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=PROBE_TIMEOUT_S) as client:
                await client.head(url)
            self._window.append((True, (time.perf_counter() - t0) * 1000))
        except Exception:
            self._window.append((False, 0.0))

    async def probe_loop(self):
        while True:
            if self.mode == "real":
                await self.probe_once()
            await asyncio.sleep(PROBE_INTERVAL_S)
