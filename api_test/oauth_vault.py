"""Encrypted, workspace-scoped OAuth token cache and single-use browser state."""
from __future__ import annotations

from contextlib import closing, contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
import re
from pathlib import Path
import secrets
import time

from .database import LOCAL_CONTEXT, connect, initialize_local_context, require_membership
from .migrations import migrate_studio_database
from .project_variables import decrypt_secret, encrypt_secret


UNKNOWN_EXPIRY_RETENTION = 3600
MAX_RETENTION = 86400
MAX_REFRESH_RETENTION = 7 * 86400
LEASE_SECONDS = 30
PENDING_SECONDS = 300


class OAuthVaultError(ValueError):
    pass


class OAuthTokenResponseError(OAuthVaultError):
    pass


@dataclass(frozen=True)
class Lease:
    identity: tuple[str, str, str, str, str]
    config_hash: str
    lease_id: str
    generation: int
    action: str
    refresh_token: str | None


class Vault:
    def __init__(self, path: Path | None = None, context=LOCAL_CONTEXT):
        self.path = path or Path(os.environ.get("STUDIO_DB_PATH", Path(__file__).resolve().parents[1] / "data/studio.db"))
        self.context = context

    @contextmanager
    def connection(self, *, write=False):
        with closing(connect(self.path)) as db:
            migrate_studio_database(db)
            with db:
                initialize_local_context(db)
            require_membership(db, self.context)
            if write:
                role = db.execute(
                    "SELECT role FROM memberships WHERE workspace_id=? AND user_id=? AND status='active'",
                    (self.context.workspace_id, self.context.user_id),
                ).fetchone()
                if role is None or role["role"] not in ("owner", "admin", "editor", "runner"):
                    raise PermissionError("Active runner membership is required for OAuth token state")
                now = int(time.time())
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("DELETE FROM oauth_pending WHERE workspace_id=? AND user_id=? AND expires_at<=?",
                               (self.context.workspace_id, self.context.user_id, now))
                    db.execute("DELETE FROM oauth_tokens WHERE workspace_id=? AND user_id=? AND retained_until<=?",
                               (self.context.workspace_id, self.context.user_id, now))
            yield db

    def identity(self, project: str, environment: str, profile: str):
        return (self.context.workspace_id, self.context.user_id, project, environment, profile)

    def _identity(self, identity):
        if not isinstance(identity, tuple) or len(identity) != 5 or identity[:2] != (
                self.context.workspace_id, self.context.user_id):
            raise PermissionError("OAuth token identity does not match the active context")
        return identity

    def status(self, identity, config_hash: str) -> dict:
        self._identity(identity)
        now = int(time.time())
        with self.connection() as db:
            row = db.execute(
                "SELECT config_hash,access_ciphertext,refresh_ciphertext,expires_at,retained_until,updated_at FROM oauth_tokens "
                "WHERE workspace_id=? AND user_id=? AND project_reference=? AND environment=? AND profile=?",
                identity,
            ).fetchone()
        usable = bool(row and row["config_hash"] == config_hash and row["access_ciphertext"] and
                      row["retained_until"] > now and (row["expires_at"] > now if row["expires_at"] is not None else row["updated_at"] + UNKNOWN_EXPIRY_RETENTION > now))
        refresh = bool(row and row["config_hash"] == config_hash and row["refresh_ciphertext"] and row["retained_until"] > now)
        return {"connected": usable or refresh, "expiresAt": row["expires_at"] if row and row["config_hash"] == config_hash else None,
                "canRefresh": refresh}

    def acquire(self, identity, config_hash: str, grant: str, *, force=False) -> str | Lease:
        self._identity(identity)
        deadline = time.monotonic() + 10
        while True:
            now = int(time.time())
            state, result = None, None
            with self.connection(write=True) as db, db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT config_hash,access_ciphertext,refresh_ciphertext,expires_at,retained_until,generation,lease_id,lease_until,updated_at "
                    "FROM oauth_tokens WHERE workspace_id=? AND user_id=? AND project_reference=? AND environment=? AND profile=?",
                    identity,
                ).fetchone()
                if row and (row["config_hash"] != config_hash or row["retained_until"] <= now):
                    db.execute("DELETE FROM oauth_tokens WHERE workspace_id=? AND user_id=? AND project_reference=? AND environment=? AND profile=?", identity)
                    row = None
                if row and row["lease_id"] and row["lease_until"] and row["lease_until"] > now:
                    state = "busy" if force else "wait"
                elif row and row["lease_id"] and row["refresh_ciphertext"] and grant == "authorization_code":
                    # A crashed/expired refresh may already have rotated the token.
                    db.execute("DELETE FROM oauth_tokens WHERE workspace_id=? AND user_id=? AND project_reference=? AND environment=? AND profile=?", identity)
                    state = "reconnect"
                elif row and not force and row["access_ciphertext"] and row["retained_until"] > now and (
                        row["expires_at"] is None and row["updated_at"] + UNKNOWN_EXPIRY_RETENTION > now or
                        row["expires_at"] is not None and row["expires_at"] > now + min(30, max(1, (row["expires_at"] - row["updated_at"]) // 10))):
                    result = ("cached", row["access_ciphertext"])
                elif grant == "authorization_code" and not (row and row["refresh_ciphertext"]):
                    state = "reconnect"
                else:
                    action = "refresh" if grant == "authorization_code" else "issue"
                    lease_id = secrets.token_urlsafe(24)
                    generation = row["generation"] if row else 0
                    refresh_ciphertext = row["refresh_ciphertext"] if row else None
                    if row:
                        db.execute(
                            "UPDATE oauth_tokens SET lease_id=?,lease_until=?,updated_at=? WHERE workspace_id=? AND user_id=? AND project_reference=? AND environment=? AND profile=?",
                            (lease_id, now + LEASE_SECONDS, now, *identity),
                        )
                    else:
                        db.execute(
                            "INSERT INTO oauth_tokens(workspace_id,user_id,project_reference,environment,profile,config_hash,access_ciphertext,refresh_ciphertext,expires_at,retained_until,generation,lease_id,lease_until,updated_at) "
                            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (*identity, config_hash, "", None, None, now + UNKNOWN_EXPIRY_RETENTION, 0, lease_id, now + LEASE_SECONDS, now),
                        )
                    result = ("lease", (lease_id, generation, action, refresh_ciphertext))
            if result and result[0] == "cached":
                return decrypt_secret(result[1])
            if result and result[0] == "lease":
                lease_id, generation, action, refresh_ciphertext = result[1]
                refresh = decrypt_secret(refresh_ciphertext) if refresh_ciphertext else None
                return Lease(identity, config_hash, lease_id, generation, action, refresh)
            if state == "reconnect":
                raise OAuthVaultError("OAuth authorization must be reconnected")
            if state == "busy":
                raise OAuthVaultError("OAuth issuance is already in progress")
            if state != "wait" or time.monotonic() >= deadline:
                raise OAuthVaultError("OAuth issuance is already in progress")
            time.sleep(.1)

    def finish(self, lease: Lease, payload: dict, *, public_client=False) -> str:
        self._identity(lease.identity)
        access = payload.get("access_token")
        if not isinstance(access, str) or len(access) > 16384 or not re.fullmatch(r"[A-Za-z0-9._~+/-]+={0,}", access) or str(payload.get("token_type", "")).lower() != "bearer":
            raise OAuthTokenResponseError("OAuth token response is invalid")
        expires_in = payload.get("expires_in")
        if expires_in is not None and (type(expires_in) is not int or not 1 <= expires_in <= 31 * 86400):
            raise OAuthTokenResponseError("OAuth token expiry is invalid")
        refresh = payload.get("refresh_token")
        if refresh is not None and (not isinstance(refresh, str) or not refresh or len(refresh) > 16384):
            raise OAuthTokenResponseError("OAuth refresh token is invalid")
        if lease.action == "refresh" and not refresh:
            if public_client:
                raise OAuthVaultError("OAuth refresh token rotation is required; reconnect")
            refresh = lease.refresh_token
        if lease.action == "issue" and not refresh:
            refresh = None
        now = int(time.time())
        expires_at = now + expires_in if expires_in is not None else None
        retained_until = now + MAX_REFRESH_RETENTION if refresh else min(expires_at, now + MAX_RETENTION) if expires_at is not None else now + UNKNOWN_EXPIRY_RETENTION
        access_ciphertext = encrypt_secret(access)
        refresh_ciphertext = encrypt_secret(refresh) if refresh else None
        with self.connection(write=True) as db, db:
            db.execute("BEGIN IMMEDIATE")
            result = db.execute(
                "UPDATE oauth_tokens SET access_ciphertext=?,refresh_ciphertext=?,expires_at=?,retained_until=?,generation=?,lease_id=NULL,lease_until=NULL,updated_at=? "
                "WHERE workspace_id=? AND user_id=? AND project_reference=? AND environment=? AND profile=? AND config_hash=? AND generation=? AND lease_id=?",
                (access_ciphertext, refresh_ciphertext, expires_at, retained_until,
                 lease.generation + 1, now, *lease.identity, lease.config_hash, lease.generation, lease.lease_id),
            )
            if result.rowcount != 1:
                raise OAuthVaultError("OAuth issuance ownership changed")
        return access

    def abort(self, lease: Lease):
        self._identity(lease.identity)
        with self.connection(write=True) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if lease.action == "refresh":
                db.execute(
                    "DELETE FROM oauth_tokens WHERE workspace_id=? AND user_id=? AND project_reference=? AND environment=? AND profile=? AND config_hash=? AND lease_id=?",
                    (*lease.identity, lease.config_hash, lease.lease_id),
                )
            else:
                db.execute(
                    "UPDATE oauth_tokens SET lease_id=NULL,lease_until=NULL WHERE workspace_id=? AND user_id=? AND project_reference=? AND environment=? AND profile=? AND config_hash=? AND lease_id=?",
                    (*lease.identity, lease.config_hash, lease.lease_id),
                )

    def create_pending(self, identity, provider_key: str, config_hash: str, callback_uri: str,
                       user_agent: str) -> tuple[str, str, str]:
        self._identity(identity)
        state = secrets.token_urlsafe(32)
        cookie = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        now = int(time.time())
        with self.connection(write=True) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM oauth_pending WHERE expires_at<=?", (now,))
            db.execute("DELETE FROM oauth_pending WHERE workspace_id=? AND user_id=? AND project_reference=? AND environment=? AND profile=?",
                       identity)
            count = db.execute("SELECT COUNT(*) AS count FROM oauth_pending WHERE workspace_id=? AND user_id=?",
                               identity[:2]).fetchone()["count"]
            if count >= 20:
                raise OAuthVaultError("Too many pending OAuth authorizations")
            db.execute(
                "INSERT INTO oauth_pending(state_hash,cookie_hash,workspace_id,user_id,project_reference,environment,profile,provider_key,config_hash,verifier_ciphertext,callback_uri,user_agent_hash,expires_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (hashlib.sha256(state.encode()).hexdigest(), hashlib.sha256(cookie.encode()).hexdigest(), *identity,
                 provider_key, config_hash, encrypt_secret(verifier), callback_uri,
                 hashlib.sha256(user_agent.encode()).hexdigest(), now + PENDING_SECONDS),
            )
        return state, cookie, verifier

    def peek_pending(self, state: str, cookie: str, provider_key: str, user_agent: str):
        if not state or not cookie:
            raise OAuthVaultError("OAuth browser state is missing")
        now = int(time.time())
        with self.connection() as db:
            row = db.execute("SELECT * FROM oauth_pending WHERE state_hash=? AND workspace_id=? AND user_id=?",
                             (hashlib.sha256(state.encode()).hexdigest(),
                              self.context.workspace_id, self.context.user_id)).fetchone()
        if not row or row["expires_at"] <= now or row["cookie_hash"] != hashlib.sha256(cookie.encode()).hexdigest() or (
                row["provider_key"] != provider_key or row["user_agent_hash"] != hashlib.sha256(user_agent.encode()).hexdigest()):
            raise OAuthVaultError("OAuth browser state does not match")
        return {"identity": (row["workspace_id"], row["user_id"], row["project_reference"], row["environment"], row["profile"]),
                "configHash": row["config_hash"], "callbackUri": row["callback_uri"]}

    def consume_pending(self, state: str, cookie: str, provider_key: str, user_agent: str):
        if not state or not cookie:
            raise OAuthVaultError("OAuth browser state is missing")
        now = int(time.time())
        with self.connection(write=True) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM oauth_pending WHERE state_hash=? AND workspace_id=? AND user_id=?",
                             (hashlib.sha256(state.encode()).hexdigest(),
                              self.context.workspace_id, self.context.user_id)).fetchone()
            if not row or row["expires_at"] <= now or row["cookie_hash"] != hashlib.sha256(cookie.encode()).hexdigest() or (
                    row["provider_key"] != provider_key or row["user_agent_hash"] != hashlib.sha256(user_agent.encode()).hexdigest()):
                raise OAuthVaultError("OAuth browser state does not match")
            db.execute("DELETE FROM oauth_pending WHERE state_hash=?", (row["state_hash"],))
            identity = (row["workspace_id"], row["user_id"], row["project_reference"], row["environment"], row["profile"])
            token_row = db.execute(
                "SELECT generation,lease_id,lease_until,config_hash FROM oauth_tokens "
                "WHERE workspace_id=? AND user_id=? AND project_reference=? AND environment=? AND profile=?", identity,
            ).fetchone()
            if token_row and token_row["lease_id"] and token_row["lease_until"] > now:
                raise OAuthVaultError("OAuth issuance is already in progress")
            if token_row and token_row["config_hash"] != row["config_hash"]:
                db.execute("DELETE FROM oauth_tokens WHERE workspace_id=? AND user_id=? AND project_reference=? AND environment=? AND profile=?", identity)
                token_row = None
            lease_id = secrets.token_urlsafe(24)
            generation = token_row["generation"] if token_row else 0
            if token_row:
                db.execute(
                    "UPDATE oauth_tokens SET lease_id=?,lease_until=?,updated_at=? "
                    "WHERE workspace_id=? AND user_id=? AND project_reference=? AND environment=? AND profile=?",
                    (lease_id, now + LEASE_SECONDS, now, *identity),
                )
            else:
                db.execute(
                    "INSERT INTO oauth_tokens(workspace_id,user_id,project_reference,environment,profile,config_hash,access_ciphertext,refresh_ciphertext,expires_at,retained_until,generation,lease_id,lease_until,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (*identity, row["config_hash"], "", None, None, now + UNKNOWN_EXPIRY_RETENTION, 0, lease_id, now + LEASE_SECONDS, now),
                )
        lease = Lease(identity, row["config_hash"], lease_id, generation, "authorization_code", None)
        try:
            verifier = decrypt_secret(row["verifier_ciphertext"])
        except Exception:
            self.abort(lease)
            raise
        return {"identity": identity, "configHash": row["config_hash"], "callbackUri": row["callback_uri"],
                "verifier": verifier, "lease": lease}

    def disconnect(self, identity):
        self._identity(identity)
        with self.connection(write=True) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM oauth_tokens WHERE workspace_id=? AND user_id=? AND project_reference=? AND environment=? AND profile=?", identity)
            db.execute("DELETE FROM oauth_pending WHERE workspace_id=? AND user_id=? AND project_reference=? AND environment=? AND profile=?", identity)
