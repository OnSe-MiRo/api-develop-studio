"""Persistent ownership challenges and narrowly scoped external setup grants."""
from __future__ import annotations

import hashlib
import hmac
import http.client
import ipaddress
import json
import os
import secrets
import socket
import sqlite3
import ssl
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from api_test.migrations import migrate_ownership_database


class OwnershipError(ValueError):
    pass


def local_policy():
    local = os.environ.get("LOCAL_SERVER", "false").strip().lower() == "true"
    skip = os.environ.get("SKIP_OWNERSHIP_VERIFICATION", "false").strip().lower() == "true"
    if skip and not local:
        raise OwnershipError("SKIP_OWNERSHIP_VERIFICATION=true는 LOCAL_SERVER=true에서만 가능합니다.")
    return {"local_server": local, "skip_verification": skip}


def origin(url):
    if not isinstance(url, str) or not url or any(ord(c) < 33 or c == "\\" for c in url):
        raise OwnershipError("유효한 HTTP(S) URL이 필요합니다.")
    try:
        p = urlsplit(url)
        if p.scheme not in ("http", "https") or not p.hostname or p.username or p.password or p.fragment:
            raise ValueError()
        host = p.hostname.encode("idna").decode("ascii").lower()
        port = p.port or (443 if p.scheme == "https" else 80)
    except (ValueError, TypeError, UnicodeError):
        raise OwnershipError("사용자정보와 fragment 없는 HTTP(S) URL이 필요합니다.") from None
    host = f"[{host}]" if ":" in host else host
    return f"{p.scheme}://{host}" + (f":{port}" if port != (443 if p.scheme == "https" else 80) else "")


def endpoint(url):
    base = origin(url)
    p = urlsplit(url)
    if p.query or "%" in p.path or "\\" in p.path or any(x in (".", "..") for x in p.path.split("/")):
        raise OwnershipError("외부 승인 URL에는 query, 인코딩 경로, 상대 경로를 사용할 수 없습니다.")
    return base + (p.path or "/")


def fingerprint(project):
    urls = [project.get("base_url", "")] + [x.get("url", "") for x in project.get("base_urls", [])]
    return hashlib.sha256(json.dumps(sorted({origin(x) for x in urls if x})).encode()).hexdigest()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def fetch_challenge(target, verification_id):
    """Pin public DNS addresses, keep hostname TLS validation, never follow redirects."""
    if urlsplit(target).scheme != "https":
        raise OwnershipError("소유권 검증은 HTTPS만 지원합니다.")
    p = urlsplit(target)
    addresses = socket.getaddrinfo(p.hostname, p.port or 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):
        raise OwnershipError("공개 IP의 HTTPS 대상만 검증할 수 있습니다.")
    family, socktype, proto, _, address = addresses[0]
    conn = http.client.HTTPSConnection(p.hostname, p.port or 443, timeout=5, context=ssl.create_default_context())
    raw = socket.socket(family, socktype, proto)
    try:
        raw.settimeout(5)
        raw.connect(address)
        conn.sock = conn._context.wrap_socket(raw, server_hostname=p.hostname)
        conn.request("GET", f"/.well-known/api-develop-studio-verification/{verification_id}",
                     headers={"Accept": "application/json", "Cache-Control": "no-cache"})
        response = conn.getresponse()
        if response.status != 200:
            raise OwnershipError("검증 응답은 redirect 없는 HTTP 200이어야 합니다.")
        body = response.read(4097)
        if len(body) > 4096:
            raise OwnershipError("검증 응답은 4KB 이하여야 합니다.")
        parsed = json.loads(body)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("challenge"), str):
            raise OwnershipError("JSON 응답의 challenge 문자열이 필요합니다.")
        return parsed["challenge"]
    finally:
        conn.close()
        raw.close()


class OwnershipStore:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get("STUDIO_OWNERSHIP_DB_PATH", Path(__file__).resolve().parents[1] / "data" / "ownership.db"))

    @contextmanager
    def db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            migrate_ownership_database(conn)
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def status(self, project, document):
        now = time.time()
        with self.db() as db:
            db.execute("UPDATE proofs SET state='expired' WHERE project=? AND "
                       "(fingerprint<>? OR (state='pending' AND issued<=?) OR "
                       "(state='verified' AND (verified<=? OR last_used<=?)))",
                       (project, fingerprint(document), now-1800, now-90*86400, now-30*86400))
            proofs = [dict(x) for x in db.execute("SELECT origin,id,state,issued,verified,last_used FROM proofs WHERE project=?", (project,))]
            grants = [dict(x) for x in db.execute("SELECT url,method,last_used FROM grants WHERE project=?", (project,))]
        for proof in proofs:
            proof["expires_at"] = (min(proof["verified"]+90*86400, proof["last_used"]+30*86400)
                                   if proof["verified"] else proof["issued"]+1800)
        return {**local_policy(), "proofs": proofs, "grants": grants}

    def issue(self, project, document, url, session):
        target = origin(url)
        allowed = {origin(x) for x in [document.get("base_url", "")] + [x["url"] for x in document.get("base_urls", [])] if x}
        if target not in allowed or not target.startswith("https://"):
            raise OwnershipError("저장된 프로젝트의 HTTPS Base URL을 선택하세요.")
        token, vid, now = secrets.token_urlsafe(32), secrets.token_urlsafe(18), time.time()
        with self.db() as db:
            previous = db.execute("SELECT issued FROM proofs WHERE project=? AND origin=?", (project, target)).fetchone()
            if previous and now-previous[0] < 10:
                raise OwnershipError("토큰 재발급은 10초 후 가능합니다.")
            db.execute("INSERT OR REPLACE INTO proofs VALUES (?,?,?,?,?,?,'pending',?,NULL,NULL,0)",
                       (project, target, fingerprint(document), vid, digest(session), digest(token), now))
        return {"verification_id": vid, "challenge": token, "expires_at": now+1800,
                "verification_url": f"{target}/.well-known/api-develop-studio-verification/{vid}"}

    def verify(self, project, document, vid, session):
        if not isinstance(vid, str) or not vid:
            raise OwnershipError("verification_id 문자열이 필요합니다.")
        self.status(project, document)
        with self.db() as db:
            row = db.execute("SELECT * FROM proofs WHERE project=? AND id=?", (project, vid)).fetchone()
            if not row or row["state"] != "pending" or not hmac.compare_digest(row["session_hash"], digest(session)):
                raise OwnershipError("유효한 검증 요청과 발급한 브라우저 세션이 필요합니다.")
            if row["attempts"] >= 10:
                raise OwnershipError("검증 시도 한도를 초과했습니다. 토큰을 재발급하세요.")
            db.execute("UPDATE proofs SET attempts=attempts+1 WHERE id=?", (vid,))
        try:
            value = fetch_challenge(row["origin"], vid)
        except (OSError, ValueError, http.client.HTTPException) as exc:
            raise OwnershipError("대상 API의 검증 응답을 확인할 수 없습니다.") from exc
        if not hmac.compare_digest(digest(value), row["token_hash"]):
            raise OwnershipError("배포된 challenge가 발급값과 다릅니다.")
        now = time.time()
        with self.db() as db:
            changed = db.execute("UPDATE proofs SET state='verified',verified=?,last_used=? "
                                 "WHERE id=? AND state='pending' AND issued>? AND fingerprint=?",
                                 (now, now, vid, now-1800, fingerprint(document))).rowcount
            if not changed:
                raise OwnershipError("만료되거나 교체된 검증 요청입니다.")
        return {"state": "verified"}

    def grant(self, project, url, method, remove=False):
        url, method = endpoint(url), str(method).upper()
        if not url.startswith("https://") or method not in ("GET", "POST", "HEAD", "PUT", "PATCH", "DELETE", "OPTIONS"):
            raise OwnershipError("외부 예외는 HTTPS URL과 유효한 HTTP 메서드가 필요합니다.")
        with self.db() as db:
            if remove:
                db.execute("DELETE FROM grants WHERE project=? AND url=? AND method=?", (project, url, method))
            else:
                db.execute("INSERT OR IGNORE INTO grants(project,url,method) VALUES(?,?,?)", (project, url, method))

    def revoke(self, project, remove=False):
        # Do not create a database just because an unrelated project is saved.
        if not self.path.exists():
            return
        with self.db() as db:
            if remove:
                db.execute("DELETE FROM proofs WHERE project=?", (project,))
                db.execute("DELETE FROM grants WHERE project=?", (project,))
            else:
                db.execute("UPDATE proofs SET state='revoked' WHERE project=?", (project,))

    def authorize(self, project, document, url, method, *, external=False):
        policy = local_policy()
        if external:
            url = endpoint(url)
            now = time.time()
            with self.db() as db:
                row = db.execute("SELECT last_used FROM grants WHERE project=? AND url=? AND method=?", (project, url, method)).fetchone()
                if not row:
                    raise OwnershipError("승인된 외부 Setup URL과 메서드가 필요합니다.")
                if now-row[0] < 60:
                    raise OwnershipError("외부 Setup 호출은 같은 대상에 60초에 한 번만 허용됩니다.")
                db.execute("UPDATE grants SET last_used=? WHERE project=? AND url=? AND method=?", (now, project, url, method))
            return
        if policy["skip_verification"]:
            return
        target = origin(url)
        self.status(project, document)
        with self.db() as db:
            row = db.execute("SELECT state FROM proofs WHERE project=? AND origin=?", (project, target)).fetchone()
            if not row or row[0] != "verified":
                raise OwnershipError("대상 API 소유권 확인이 필요하거나 만료되었습니다. 프로젝트 설정에서 인증하세요.")
            db.execute("UPDATE proofs SET last_used=? WHERE project=? AND origin=?", (time.time(), project, target))


def execution_guard(project, project_root, external=False):
    def check(url, method):
        if local_policy()["skip_verification"] and not external:
            return
        if not isinstance(project, str) or not project:
            raise OwnershipError("소유권 확인을 위한 프로젝트가 필요합니다.")
        path = (project_root / project).resolve()
        if project_root.resolve() not in path.parents:
            raise OwnershipError("프로젝트 경로가 올바르지 않습니다.")
        document = json.loads(path.read_text(encoding="utf-8"))
        OwnershipStore().authorize(project, document, url, method, external=external)
    return check
