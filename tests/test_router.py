"""Unit tests for routing decisions and fallback chains."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.providers import Registry, Role
from gateway.router import RoutingEngine
from network.health import NetworkState
from providers.mock_provider import MockCloudProvider, MockLocalProvider

CFG = {
    "small_latency_ms": 600, "small_loss": 0.05,
    "local_latency_ms": 2500, "local_loss": 0.25,
    "provider_failure_threshold": 3, "provider_cooldown_s": 30,
}


def make_registry(with_local=True, with_alternate=True):
    reg = Registry()
    primary = MockCloudProvider("mock-cloud")
    reg.roles["cloud-large"] = Role(primary, "mock-large")
    reg.roles["cloud-small"] = Role(primary, "mock-small")
    if with_alternate:
        reg.roles["alternate"] = Role(MockCloudProvider("mock-alt"), "mock-alt")
    if with_local:
        reg.roles["local"] = Role(MockLocalProvider(), "mock-local-model")
    return reg


def state(online=True, latency=40, loss=0.0):
    return NetworkState(online=online, latency_ms=latency, packet_loss=loss,
                        profile="test", source="simulated")


def engine(**kw):
    return RoutingEngine(make_registry(**kw), CFG)


def test_healthy_network_uses_cloud_large():
    d = engine().decide(state(), cache_hit=False)
    assert d.route == "cloud-large"


def test_cache_hit_short_circuits():
    d = engine().decide(state(), cache_hit=True)
    assert d.route == "cache"


def test_degraded_latency_uses_cloud_small():
    d = engine().decide(state(latency=800), cache_hit=False)
    assert d.route == "cloud-small"


def test_packet_loss_uses_cloud_small():
    d = engine().decide(state(loss=0.10), cache_hit=False)
    assert d.route == "cloud-small"


def test_severe_network_prefers_local():
    d = engine().decide(state(latency=3000), cache_hit=False)
    assert d.route == "local"


def test_severe_loss_prefers_local():
    d = engine().decide(state(loss=0.30), cache_hit=False)
    assert d.route == "local"


def test_offline_with_local_uses_local():
    d = engine().decide(state(online=False), cache_hit=False)
    assert d.route == "local"


def test_offline_without_local_queues():
    d = engine(with_local=False).decide(state(online=False), cache_hit=False)
    assert d.route == "queue"


def test_unhealthy_primary_fails_over_to_alternate():
    e = engine()
    prov = e.registry.get("cloud-large").provider
    for _ in range(3):
        prov.health.record_failure("boom")
    d = e.decide(state(), cache_hit=False)
    assert d.route == "alternate"


def test_unhealthy_primary_no_alternate_degrades_to_small():
    e = engine(with_alternate=False)
    # cloud-small shares the primary provider, so failures also mark it —
    # but the policy explicitly degrades rather than erroring
    prov = e.registry.get("cloud-large").provider
    for _ in range(3):
        prov.health.record_failure("boom")
    d = e.decide(state(), cache_hit=False)
    assert d.route == "cloud-small"


def test_chain_from_cloud_large_ends_in_queue():
    e = engine()
    chain = e.chain(e.decide(state(), cache_hit=False), state())
    assert chain[0] == "cloud-large" and chain[-1] == "queue"
    assert "local" in chain


def test_offline_chain_never_tries_cloud():
    e = engine()
    s = state(online=False)
    chain = e.chain(e.decide(s, cache_hit=False), s)
    assert all(r in ("local", "queue") for r in chain)
