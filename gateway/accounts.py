"""Accounts, tenants and virtual API keys for the Okada Cloud console.

SQLite, single file (logs/accounts.sqlite by default, OKADA_ACCOUNTS_DB to
move it). Design choices that matter:

- API keys are stored as SHA-256 hashes; the full key is returned exactly
  once, at creation. A leaked database does not leak keys.
- Passwords use scrypt (stdlib) with a per-user salt.
- Console sessions are random bearer tokens, stored hashed, 30-day expiry.
- One account owns many tenants; one tenant owns many keys. Budgets and
  routing flags live on the tenant (see gateway/tenants.py), so every key
  of a tenant shares its budget.
- OKADA_ADMIN_TOKEN (env) unlocks the cross-account overview.
"""
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from pathlib import Path

from gateway.tenants import Tenant

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
SESSION_TTL_S = 30 * 24 * 3600
KEY_PREFIX = "ok_live_"

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id          TEXT PRIMARY KEY,
    email       TEXT UNIQUE NOT NULL,
    name        TEXT,
    pw_salt     BLOB NOT NULL,
    pw_hash     BLOB NOT NULL,
    created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    account_id  TEXT NOT NULL,
    created_at  REAL NOT NULL,
    expires_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tenants (
    id                  TEXT PRIMARY KEY,
    account_id          TEXT NOT NULL,
    name                TEXT NOT NULL,
    max_budget_usd      REAL,
    budget_duration     TEXT NOT NULL DEFAULT 'total',
    models_allowed      TEXT,            -- comma-separated or NULL
    no_offshore         INTEGER NOT NULL DEFAULT 0,
    degraded_max_tokens INTEGER,
    created_at          REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS api_keys (
    key_hash    TEXT PRIMARY KEY,
    prefix      TEXT NOT NULL,            -- first 12 chars, for display
    tenant_id   TEXT NOT NULL,
    name        TEXT,
    created_at  REAL NOT NULL,
    last_used   REAL,
    revoked_at  REAL
);
CREATE INDEX IF NOT EXISTS api_keys_tenant ON api_keys(tenant_id);
CREATE INDEX IF NOT EXISTS tenants_account ON tenants(account_id);
"""


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _slug(name: str) -> str:
    base = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-") or "tenant"
    return f"{base[:24]}-{secrets.token_hex(2)}"


class AccountError(Exception):
    pass


class AccountStore:
    def __init__(self, path: Path | None = None):
        self.path = path or Path(os.getenv("OKADA_ACCOUNTS_DB") or (LOG_DIR / "accounts.sqlite"))
        self.path.parent.mkdir(exist_ok=True, parents=True)
        self.db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)

    # ---- accounts ----------------------------------------------------------
    def signup(self, email: str, password: str, name: str = "") -> dict:
        email = email.strip().lower()
        if "@" not in email or len(password) < 8:
            raise AccountError("valid email and a password of at least 8 characters are required")
        if self.db.execute("SELECT 1 FROM accounts WHERE email=?", (email,)).fetchone():
            raise AccountError("an account with that email already exists")
        salt = os.urandom(16)
        pw = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
        aid = f"acc_{secrets.token_hex(6)}"
        self.db.execute("INSERT INTO accounts VALUES (?,?,?,?,?,?)",
                        (aid, email, name.strip()[:80], salt, pw, time.time()))
        return {"id": aid, "email": email, "name": name.strip()[:80]}

    def login(self, email: str, password: str) -> str:
        row = self.db.execute("SELECT id, pw_salt, pw_hash FROM accounts WHERE email=?",
                              (email.strip().lower(),)).fetchone()
        if not row:
            raise AccountError("invalid email or password")
        aid, salt, want = row
        got = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1)
        if not hmac.compare_digest(got, want):
            raise AccountError("invalid email or password")
        token = "oks_" + secrets.token_urlsafe(32)
        now = time.time()
        self.db.execute("INSERT INTO sessions VALUES (?,?,?,?)",
                        (_h(token), aid, now, now + SESSION_TTL_S))
        return token

    def logout(self, token: str):
        self.db.execute("DELETE FROM sessions WHERE token_hash=?", (_h(token),))

    def account_for_session(self, token: str | None) -> dict | None:
        if not token:
            return None
        row = self.db.execute(
            "SELECT a.id, a.email, a.name FROM sessions s JOIN accounts a ON a.id=s.account_id "
            "WHERE s.token_hash=? AND s.expires_at>?", (_h(token), time.time())).fetchone()
        return {"id": row[0], "email": row[1], "name": row[2]} if row else None

    # ---- tenants -----------------------------------------------------------
    def create_tenant(self, account_id: str, name: str, **opts) -> dict:
        name = (name or "").strip()
        if not name:
            raise AccountError("tenant name is required")
        tid = _slug(name)
        models = opts.get("models_allowed")
        self.db.execute(
            "INSERT INTO tenants (id, account_id, name, max_budget_usd, budget_duration, "
            "models_allowed, no_offshore, degraded_max_tokens, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (tid, account_id, name[:80], opts.get("max_budget_usd"),
             opts.get("budget_duration") or "total",
             ",".join(models) if models else None, 1 if opts.get("no_offshore") else 0,
             opts.get("degraded_max_tokens"), time.time()))
        return self.tenant(tid)

    def update_tenant(self, tid: str, **opts) -> dict:
        cols = {"max_budget_usd", "budget_duration", "no_offshore", "degraded_max_tokens",
                "models_allowed", "name"}
        sets, vals = [], []
        for k, v in opts.items():
            if k not in cols:
                continue
            if k == "models_allowed":
                v = ",".join(v) if v else None
            if k == "no_offshore":
                v = 1 if v else 0
            sets.append(f"{k}=?")
            vals.append(v)
        if sets:
            self.db.execute(f"UPDATE tenants SET {', '.join(sets)} WHERE id=?", (*vals, tid))
        return self.tenant(tid)

    def _row_to_tenant_dict(self, r) -> dict:
        return {"id": r[0], "account_id": r[1], "name": r[2], "max_budget_usd": r[3],
                "budget_duration": r[4], "models_allowed": r[5].split(",") if r[5] else None,
                "no_offshore": bool(r[6]), "degraded_max_tokens": r[7], "created_at": r[8]}

    def tenant(self, tid: str) -> dict | None:
        r = self.db.execute("SELECT * FROM tenants WHERE id=?", (tid,)).fetchone()
        return self._row_to_tenant_dict(r) if r else None

    def tenants_for_account(self, account_id: str) -> list[dict]:
        rows = self.db.execute("SELECT * FROM tenants WHERE account_id=? ORDER BY created_at",
                               (account_id,)).fetchall()
        return [self._row_to_tenant_dict(r) for r in rows]

    def owns(self, account_id: str, tid: str) -> bool:
        t = self.tenant(tid)
        return bool(t and t["account_id"] == account_id)

    # ---- keys --------------------------------------------------------------
    def create_key(self, tid: str, name: str = "") -> dict:
        if not self.tenant(tid):
            raise AccountError("unknown tenant")
        key = KEY_PREFIX + secrets.token_hex(16)
        self.db.execute("INSERT INTO api_keys (key_hash, prefix, tenant_id, name, created_at) "
                        "VALUES (?,?,?,?,?)", (_h(key), key[:12], tid, name[:60], time.time()))
        return {"key": key, "prefix": key[:12], "tenant_id": tid, "name": name[:60]}

    def keys_for_tenant(self, tid: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT prefix, name, created_at, last_used, revoked_at, key_hash FROM api_keys "
            "WHERE tenant_id=? ORDER BY created_at", (tid,)).fetchall()
        return [{"prefix": r[0], "name": r[1], "created_at": r[2], "last_used": r[3],
                 "revoked": r[4] is not None, "id": r[5][:16]} for r in rows]

    def revoke_key(self, tid: str, key_id: str) -> bool:
        cur = self.db.execute("UPDATE api_keys SET revoked_at=? WHERE tenant_id=? AND "
                              "substr(key_hash,1,16)=? AND revoked_at IS NULL",
                              (time.time(), tid, key_id))
        return cur.rowcount > 0

    def has_keys(self) -> bool:
        return self.db.execute(
            "SELECT 1 FROM api_keys WHERE revoked_at IS NULL LIMIT 1").fetchone() is not None

    def tenant_for_key(self, presented: str) -> Tenant | None:
        """Gateway auth path: hash lookup, constant-time on the hash."""
        if not presented.startswith(KEY_PREFIX):
            return None
        row = self.db.execute(
            "SELECT k.key_hash, t.id, t.max_budget_usd, t.budget_duration, t.models_allowed, "
            "t.no_offshore, t.degraded_max_tokens FROM api_keys k JOIN tenants t ON t.id=k.tenant_id "
            "WHERE k.key_hash=? AND k.revoked_at IS NULL", (_h(presented),)).fetchone()
        if not row or not hmac.compare_digest(row[0], _h(presented)):
            return None
        self.db.execute("UPDATE api_keys SET last_used=? WHERE key_hash=?", (time.time(), row[0]))
        return Tenant(id=row[1], key=None, max_budget_usd=row[2], budget_duration=row[3] or "total",
                      models_allowed=row[4].split(",") if row[4] else None,
                      no_offshore=bool(row[5]), degraded_max_tokens=row[6])

    # ---- admin -------------------------------------------------------------
    def overview(self) -> dict:
        n_acc = self.db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        n_ten = self.db.execute("SELECT COUNT(*) FROM tenants").fetchone()[0]
        n_key = self.db.execute("SELECT COUNT(*) FROM api_keys WHERE revoked_at IS NULL").fetchone()[0]
        tenants = [self._row_to_tenant_dict(r) for r in
                   self.db.execute("SELECT * FROM tenants ORDER BY created_at DESC LIMIT 200")]
        return {"accounts": n_acc, "tenants": n_ten, "active_keys": n_key, "recent_tenants": tenants}

    def close(self):
        self.db.close()
