"""Offline queue: requests that could not be served are parked and replayed
by a background flusher when connectivity returns. Results are retrievable
by id via GET /okada/queue/{id}.

Durability (outbox pattern):
- SQLite in WAL mode holds the FULL request body, so a gateway restart (or
  a power cut, which is the normal case on this market's grid) replays the
  backlog instead of silently losing it.
- Idempotency keys: a client that retries after reconnecting gets the same
  queue id back instead of running the request twice.
- attempts + exponential backoff per item; items that fail max_attempts
  times are marked failed, not retried forever.
- Bodies and results are AES-GCM encrypted at rest when OKADA_QUEUE_KEY is
  set (64 hex chars = raw 32-byte key; any other string is SHA-256-derived).
  Without a key they are stored in plaintext and a warning is logged once.
- Purge-on-send: the request body is deleted the moment the result is
  stored; results expire after retention_s. Retained prompts are personal
  data under the NDPA — hold as little as possible, for as short as possible.
- logs/queue.jsonl stays as an append-only audit trail of events (no bodies).
"""
import hashlib
import json
import logging
import os
import sqlite3
import time
import uuid
from pathlib import Path

log = logging.getLogger("okada.queue")
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

SCHEMA = """
CREATE TABLE IF NOT EXISTS queue (
    id              TEXT PRIMARY KEY,
    idem_key        TEXT UNIQUE,
    tenant          TEXT NOT NULL DEFAULT 'default',
    status          TEXT NOT NULL,            -- pending | completed | failed
    queued_at       REAL NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL NOT NULL DEFAULT 0,
    completed_at    REAL,
    body            BLOB,                     -- encrypted JSON {messages,max_tokens,temperature}
    result          BLOB,                     -- encrypted JSON response
    error           TEXT
);
CREATE INDEX IF NOT EXISTS queue_status ON queue(status, next_attempt_at);
"""


def load_key_from_env() -> bytes | None:
    raw = os.getenv("OKADA_QUEUE_KEY")
    if not raw:
        return None
    raw = raw.strip()
    if len(raw) == 64:
        try:
            return bytes.fromhex(raw)
        except ValueError:
            pass
    return hashlib.sha256(raw.encode()).digest()


class _Cipher:
    """AES-256-GCM with a random 12-byte nonce prefix; identity when no key."""

    def __init__(self, key: bytes | None):
        self.key = key
        self._aead = None
        if key:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            self._aead = AESGCM(key)

    @property
    def enabled(self) -> bool:
        return self._aead is not None

    def seal(self, obj) -> bytes:
        data = json.dumps(obj, ensure_ascii=False).encode()
        if not self._aead:
            return data
        nonce = os.urandom(12)
        return nonce + self._aead.encrypt(nonce, data, None)

    def open(self, blob: bytes):
        if blob is None:
            return None
        if not self._aead:
            return json.loads(blob)
        return json.loads(self._aead.decrypt(bytes(blob[:12]), bytes(blob[12:]), None))


class QueueStore:
    def __init__(self, path: Path | None = None, key: bytes | None = None,
                 retention_s: float = 24 * 3600, max_attempts: int = 50,
                 journal_path: Path | None = None):
        self.db_path = path or (LOG_DIR / "queue.sqlite")
        self.db_path.parent.mkdir(exist_ok=True, parents=True)
        self.journal_path = journal_path or self.db_path.with_name("queue.jsonl")
        self.retention_s = retention_s
        self.max_attempts = max_attempts
        self.cipher = _Cipher(key)
        if not self.cipher.enabled:
            log.warning("OKADA_QUEUE_KEY not set: queued prompts are stored unencrypted at %s",
                        self.db_path)
        self.db = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript(SCHEMA)
        self.pending: dict[str, dict] = {}
        self.results: dict[str, dict] = {}
        self._load()

    # ---- persistence -----------------------------------------------------
    def _journal(self, event: dict):
        with open(self.journal_path, "a") as f:
            f.write(json.dumps(event) + "\n")

    def _load(self):
        """Replay after restart: pending rows come back into memory."""
        rows = self.db.execute(
            "SELECT id, tenant, queued_at, attempts, next_attempt_at, body FROM queue "
            "WHERE status='pending'").fetchall()
        for qid, tenant, queued_at, attempts, next_at, body in rows:
            try:
                b = self.cipher.open(body)
            except Exception as e:
                log.error("queue item %s undecryptable (key changed?): %s", qid, e)
                self.db.execute("UPDATE queue SET status='failed', error=? WHERE id=?",
                                (f"undecryptable: {e}", qid))
                continue
            self.pending[qid] = {"id": qid, "tenant": tenant, "queued_at": queued_at,
                                 "attempts": attempts, "next_attempt_at": next_at, **b}
        if rows:
            self._journal({"event": "restored", "n_pending": len(self.pending), "ts": time.time()})
        for qid, completed_at, result in self.db.execute(
                "SELECT id, completed_at, result FROM queue WHERE status='completed'"):
            try:
                self.results[qid] = {"completed_at": completed_at,
                                     "response": self.cipher.open(result)}
            except Exception:
                continue
        self.purge()

    # ---- API ---------------------------------------------------------------
    def add(self, messages: list, max_tokens: int, temperature: float,
            tenant: str = "default", idem_key: str | None = None) -> str:
        if idem_key:
            row = self.db.execute("SELECT id FROM queue WHERE idem_key=?", (idem_key,)).fetchone()
            if row:
                return row[0]
        qid = f"okq_{uuid.uuid4().hex[:10]}"
        now = time.time()
        body = {"messages": messages, "max_tokens": max_tokens, "temperature": temperature}
        self.db.execute(
            "INSERT INTO queue (id, idem_key, tenant, status, queued_at, attempts, next_attempt_at, body)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (qid, idem_key, tenant, "pending", now, 0, 0.0, self.cipher.seal(body)))
        self.pending[qid] = {"id": qid, "tenant": tenant, "queued_at": now, "attempts": 0,
                             "next_attempt_at": 0.0, **body}
        self._journal({"event": "queued", "id": qid, "tenant": tenant, "queued_at": now,
                       "n_messages": len(messages), "idempotent": bool(idem_key)})
        return qid

    def due(self, now: float | None = None) -> list[dict]:
        now = now or time.time()
        return [i for i in self.pending.values() if i["next_attempt_at"] <= now]

    def complete(self, qid: str, response: dict):
        now = time.time()
        self.pending.pop(qid, None)
        self.results[qid] = {"completed_at": now, "response": response}
        # purge-on-send: the prompt is gone the moment the answer exists
        self.db.execute("UPDATE queue SET status='completed', completed_at=?, result=?, body=NULL "
                        "WHERE id=?", (now, self.cipher.seal(response), qid))
        self._journal({"event": "completed", "id": qid, "completed_at": now})

    def fail_attempt(self, qid: str, error: str):
        item = self.pending.get(qid)
        if item is None:
            return
        item["attempts"] += 1
        backoff = min(5 * (2 ** item["attempts"]), 300)
        item["next_attempt_at"] = time.time() + backoff
        if item["attempts"] >= self.max_attempts:
            self.pending.pop(qid, None)
            self.db.execute("UPDATE queue SET status='failed', attempts=?, error=?, body=NULL "
                            "WHERE id=?", (item["attempts"], error[:200], qid))
            self._journal({"event": "failed", "id": qid, "attempts": item["attempts"]})
            return
        self.db.execute("UPDATE queue SET attempts=?, next_attempt_at=?, error=? WHERE id=?",
                        (item["attempts"], item["next_attempt_at"], error[:200], qid))

    def get(self, qid: str) -> dict | None:
        if qid in self.results:
            return {"status": "completed", **self.results[qid]}
        if qid in self.pending:
            i = self.pending[qid]
            return {"status": "pending", "attempts": i["attempts"],
                    "age_s": round(time.time() - i["queued_at"], 1)}
        row = self.db.execute("SELECT status, error FROM queue WHERE id=?", (qid,)).fetchone()
        if row:
            return {"status": row[0], "error": row[1]}
        return None

    def status(self) -> dict:
        now = time.time()
        return {
            "pending": [
                {"id": i["id"], "queued_at": i["queued_at"], "age_s": round(now - i["queued_at"], 1),
                 "attempts": i["attempts"]}
                for i in self.pending.values()
            ],
            "completed": list(self.results.keys()),
            "encrypted_at_rest": self.cipher.enabled,
            "db": str(self.db_path),
        }

    def purge(self, now: float | None = None):
        now = now or time.time()
        cutoff = now - self.retention_s
        old = [r[0] for r in self.db.execute(
            "SELECT id FROM queue WHERE status IN ('completed','failed') "
            "AND COALESCE(completed_at, queued_at) < ?", (cutoff,))]
        if old:
            self.db.executemany("DELETE FROM queue WHERE id=?", [(i,) for i in old])
            for i in old:
                self.results.pop(i, None)
            self._journal({"event": "purged", "n": len(old), "ts": now})

    def close(self):
        self.db.close()
