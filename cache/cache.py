"""Exact-match response cache (week 1).

Key = hash of the normalised message list. TTL-bounded, LRU-evicted.
Semantic caching (embedding similarity) is deliberately week 2+: it needs an
embedding model, a similarity threshold study, and careful freshness/privacy
rules before it is safe to ship. Cached entries are single-tenant here —
multi-tenant namespacing must land before any shared deployment.
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
    def key(messages: list) -> str:
        norm = [(m.get("role"), (m.get("content") or "").strip()) for m in messages]
        return hashlib.sha256(json.dumps(norm, ensure_ascii=False).encode()).hexdigest()

    def get(self, messages: list):
        k = self.key(messages)
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

    def set(self, messages: list, response: dict):
        k = self.key(messages)
        self._store[k] = (time.time(), response)
        self._store.move_to_end(k)
        while len(self._store) > self.max_entries:
            self._store.popitem(last=False)

    def clear(self):
        self._store.clear()
