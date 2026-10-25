"""Exact-match response cache.

Key = hash of (namespace, normalised message list). The namespace is the
tenant id, so two tenants asking the same question never see each other's
answers; the system prompt is part of the message list, so a different
system prompt is a different key. TTL-bounded, LRU-evicted.

Semantic caching (embedding similarity) is deliberately not here yet: it
needs an embedding model on CPU, a similarity-threshold study per workload,
and a cache-poisoning threat model before it is safe to share across
tenants. PII scrubbing before caching is the other open item.
"""
import hashlib
import json
import time
from collections import OrderedDict


class ResponseCache:
    def __init__(self, ttl_s: int = 900, max_entries: int = 512):
        self.ttl_s = ttl_s
        self.max_entries = max_entries
        self._store: OrderedDict[str, tuple[float, dict]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(messages: list, namespace: str = "default") -> str:
        norm = [(m.get("role"), (m.get("content") or "").strip()) for m in messages]
        return hashlib.sha256(json.dumps([namespace, norm], ensure_ascii=False).encode()).hexdigest()

    def get(self, messages: list, namespace: str = "default"):
        k = self.key(messages, namespace)
        item = self._store.get(k)
        if item is None:
            self.misses += 1
            return None
        ts, resp = item
        if (time.time() - ts) > self.ttl_s:
            del self._store[k]
            self.misses += 1
            return None
        self._store.move_to_end(k)
        self.hits += 1
        return resp

    def set(self, messages: list, response: dict, namespace: str = "default"):
        k = self.key(messages, namespace)
        self._store[k] = (time.time(), response)
        self._store.move_to_end(k)
        while len(self._store) > self.max_entries:
            self._store.popitem(last=False)

    def clear(self):
        self._store.clear()
