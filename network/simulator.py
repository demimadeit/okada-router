"""Application-level network condition simulator.

Week-1 choice: simulate at the application layer (inject latency, loss and
outages into outbound cloud calls) instead of OS-level shaping (tc/netem is
Linux-only, Toxiproxy is another moving part). This is deterministic,
cross-platform, and switchable at runtime via POST /okada/network — which is
exactly what the demo needs. OS-level shaping can be layered on in week 2+
for more realistic transport behaviour.
"""
import asyncio
import random
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class NetworkProfile:
    name: str
    online: bool = True
    latency_ms: float = 40.0       # one-way; a request pays ~2x (RTT)
    packet_loss: float = 0.0       # probability a cloud attempt fails
    bandwidth_kbps: float = 50_000
    flap_period_s: float = 0.0     # >0: alternate online/offline windows


PROFILES = {
    "excellent":    NetworkProfile("excellent", True, 40, 0.00, 50_000),
    "4g":           NetworkProfile("4g", True, 120, 0.01, 12_000),
    "3g":           NetworkProfile("3g", True, 350, 0.05, 2_000),
    "edge":         NetworkProfile("edge", True, 900, 0.10, 240),
    "high-latency": NetworkProfile("high-latency", True, 1_600, 0.02, 5_000),
    "packet-loss":  NetworkProfile("packet-loss", True, 300, 0.30, 5_000),
    "intermittent": NetworkProfile("intermittent", True, 400, 0.10, 3_000, flap_period_s=8.0),
    "offline":      NetworkProfile("offline", False, 0, 1.0, 0),
}


class SimulatedNetworkError(Exception):
    pass


class NetworkSimulator:
    def __init__(self, enabled: bool = True, profile: str = "excellent"):
        self.enabled = enabled
        self.profile = PROFILES[profile]
        self._start = time.monotonic()

    def set_profile(self, name: str) -> NetworkProfile:
        if name not in PROFILES:
            raise KeyError(f"unknown profile {name!r}; options: {sorted(PROFILES)}")
        self.profile = PROFILES[name]
        self._start = time.monotonic()
        return self.profile

    def currently_online(self) -> bool:
        if not self.enabled:
            return True
        p = self.profile
        if not p.online:
            return False
        if p.flap_period_s > 0:
            phase = (time.monotonic() - self._start) % (2 * p.flap_period_s)
            return phase < p.flap_period_s
        return True

    async def impose(self, payload_bytes: int = 800) -> None:
        """Apply the simulated network to one outbound cloud attempt."""
        if not self.enabled:
            return
        if not self.currently_online():
            raise SimulatedNetworkError("network offline")
        p = self.profile
        if random.random() < p.packet_loss:
            # a lost/timed-out attempt still costs wall-clock time
            await asyncio.sleep(min(3.0, (p.latency_ms / 1000) * 4))
            raise SimulatedNetworkError("packet loss / timeout")
        transfer_s = (payload_bytes * 8 / 1000) / max(p.bandwidth_kbps, 1)
        await asyncio.sleep((p.latency_ms / 1000) * 2 + transfer_s)


simulator = NetworkSimulator()
