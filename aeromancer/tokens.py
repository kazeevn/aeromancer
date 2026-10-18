"""Who may read the hosted dashboard, and who may upload to it.

A token is a random secret handed to one person or machine. The database keeps
only its SHA-256, with a name, a scope and an expiry, so a token can be listed
and revoked, and a leaked database gives no working token. ``view`` tokens read
the dashboard, as the share links people open; ``write`` tokens upload the
meter's readings and placements, from the recording machines, and read nothing
else.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass

from .store import Store

SCOPES = ("view", "write")
PREFIX = "aer_"


@dataclass(frozen=True)
class Token:
    id: int
    name: str
    scope: str
    created: float
    expires: float | None
    revoked: float | None

    def valid(self, now: float) -> bool:
        return self.revoked is None and (self.expires is None or now < self.expires)


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def issue(store: Store, name: str, scope: str, seconds: float | None, now: float | None = None) -> str:
    """A new secret for ``name``, valid for ``seconds`` (None: until revoked)."""
    if scope not in SCOPES:
        raise ValueError(f"unknown scope {scope!r}; expected one of {', '.join(SCOPES)}")
    now = time.time() if now is None else now
    secret = PREFIX + secrets.token_urlsafe(32)
    with store.db:
        store.db.execute(
            "INSERT INTO tokens (name, scope, hash, created, expires) VALUES (?, ?, ?, ?, ?)",
            (name, scope, _hash(secret), now, None if seconds is None else now + seconds),
        )
    return secret


def check(store: Store, secret: str | None, scope: str, now: float | None = None) -> Token | None:
    """The token ``secret`` is, if it is valid and has ``scope``; None otherwise."""
    if not secret or not secret.startswith(PREFIX):
        return None
    row = store.db.execute(
        "SELECT id, name, scope, created, expires, revoked FROM tokens WHERE hash = ?", (_hash(secret),)
    ).fetchone()
    token = Token(*row) if row else None
    if token is None or token.scope != scope or not token.valid(time.time() if now is None else now):
        return None
    return token


def list_tokens(store: Store) -> list[Token]:
    return [Token(*row) for row in store.db.execute("SELECT id, name, scope, created, expires, revoked FROM tokens ORDER BY id")]


def revoke(store: Store, id: int, now: float | None = None) -> bool:
    with store.db:
        return (
            store.db.execute(
                "UPDATE tokens SET revoked = ? WHERE id = ? AND revoked IS NULL", (time.time() if now is None else now, id)
            ).rowcount
            > 0
        )
