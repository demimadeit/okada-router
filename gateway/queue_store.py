"""Offline queue: requests that could not be served are parked and replayed
by a background flusher when connectivity returns. Results are retrievable
by id via GET /okada/queue/{id}. In-memory with an append-only JSONL journal
(logs/queue.jsonl) so a gateway restart doesn't silently lose the backlog
story — full durable replay is week 2."""
import json
import time
import uuid
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


class QueueStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (LOG_DIR / "queue.jsonl")
        self.path.parent.mkdir(exist_ok=True)
        self.pending: dict[str, dict] = {}
        self.results: dict[str, dict] = {}

    def _journal(self, event: dict):
        with open(self.path, "a") as f:
            f.write(json.dumps(event) + "\n")

    def add(self, messages: list, max_tokens: int, temperature: float) -> str:
        qid = f"okq_{uuid.uuid4().hex[:10]}"
        item = {
            "id": qid,
            "queued_at": time.time(),
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        self.pending[qid] = item
        self._journal({"event": "queued", **{k: v for k, v in item.items() if k != "messages"},
                       "n_messages": len(messages)})
        return qid

    def complete(self, qid: str, response: dict):
        self.pending.pop(qid, None)
        self.results[qid] = {"completed_at": time.time(), "response": response}
        self._journal({"event": "completed", "id": qid, "completed_at": time.time()})

    def status(self) -> dict:
        return {
            "pending": [
                {"id": i["id"], "queued_at": i["queued_at"], "age_s": round(time.time() - i["queued_at"], 1)}
                for i in self.pending.values()
            ],
            "completed": list(self.results.keys()),
        }
