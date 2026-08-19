"""Network state as seen by the router.

Simulated mode (default in week 1): state comes from the simulator profile.
Live mode: state comes from lightweight probes against a well-known endpoint.
The router only ever consumes NetworkState, so swapping the source later
does not touch routing logic.
"""
import time
from dataclasses import dataclass, asdict

import httpx

from network.simulator import NetworkSimulator

PROBE_URL = "https://www.gstatic.com/generate_204"


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
        self._probe_latency_ms: float = 0.0
        self._probe_online: bool = True
        self._probe_ts: float = 0.0

    def get_state(self) -> NetworkState:
        if self.simulator.enabled:
            p = self.simulator.profile
            return NetworkState(
                online=self.simulator.currently_online(),
                latency_ms=p.latency_ms,
                packet_loss=p.packet_loss,
                profile=p.name,
                source="simulated",
            )
        return NetworkState(
            online=self._probe_online,
            latency_ms=self._probe_latency_ms,
            packet_loss=0.0,  # loss estimation needs repeated probes; week 2
            profile="live",
            source="probe",
        )

    async def probe(self) -> NetworkState:
        """One live reachability/latency probe (used when simulator is off)."""
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                await client.head(PROBE_URL)
            self._probe_online = True
            self._probe_latency_ms = (time.perf_counter() - t0) * 1000
        except Exception:
            self._probe_online = False
            self._probe_latency_ms = 0.0
        self._probe_ts = time.time()
        return self.get_state()
