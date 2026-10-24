#!/usr/bin/env python3
"""Personal review local service: public reads, owner-only SQLite writes."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import mimetypes
import secrets
import sqlite3
import time
from datetime import date, datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def connect(path):
    conn = sqlite3.connect(path, timeout=10, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS owner (id INTEGER PRIMARY KEY CHECK(id=1), salt TEXT NOT NULL, hash TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS reviews (place_id TEXT PRIMARY KEY, payload TEXT NOT NULL, revision INTEGER NOT NULL);
    """)
    return conn


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def validate_review(body):
    rating = body.get("rating", 0)
    if isinstance(rating, bool) or not isinstance(rating, int) or not 0 <= rating <= 5:
        raise ValueError("评分须为 1–5 星，也可以不评分。")
    comment = body.get("comment", "")
    if not isinstance(comment, str) or len(comment) > 5000:
        raise ValueError("感想最多 5000 字。")
    visit_date = body.get("visitDate", "")
    if not isinstance(visit_date, str):
        raise ValueError("到访日期格式不正确。")
    if visit_date:
        try:
            date.fromisoformat(visit_date)
        except ValueError:
            raise ValueError("到访日期格式不正确。") from None
    if not rating and not comment.strip():
        raise ValueError("选一个评分，或留下一句感想。")
    return {"rating": rating, "comment": comment.strip(), "visitDate": visit_date,
            "revisit": bool(body.get("revisit", False)), "updatedAt": datetime.now(timezone.utc).isoformat()}


class Handler(BaseHTTPRequestHandler):
    server_version = "ReviewMap/2.0"

    def log_message(self, fmt, *args):
        # URLs never carry credentials; authentication bodies are never logged.
        super().log_message(fmt, *args)

    def api_path(self):
        path = urlsplit(self.path).path
        return path[4:] if path.startswith("/map/") else path

    def local_setup_allowed(self):
        host = urlsplit("//" + self.headers.get("Host", "")).hostname
        return self.client_address[0] in {"127.0.0.1", "::1"} and host in {"localhost", "127.0.0.1", "::1"}

    def send_json(self, status, payload, cookie=None):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length > 32768:
            raise ValueError("内容过长。")
        try:
            result = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            raise ValueError("请求内容无效。") from None
        if not isinstance(result, dict):
            raise ValueError("请求内容无效。")
        return result

    def is_owner(self, conn):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            token = cookie.get("review_map_session")
            if not token:
                return False
            digest = hashlib.sha256(token.value.encode()).hexdigest()
            return conn.execute("SELECT 1 FROM sessions WHERE token=? AND expires>?", (digest, time.time())).fetchone() is not None
        except Exception:
            return False

    def same_origin(self):
        origin = self.headers.get("Origin")
        return (self.headers.get("X-Personal-Review") == "1"
                and (not origin or urlsplit(origin).netloc == self.headers.get("Host")))

    def session_cookie(self, value, age):
        # Configure --secure-cookie when served behind HTTPS reverse proxy.
        secure = "; Secure" if self.server.secure_cookie else ""
        return f"review_map_session={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}{secure}"

    def do_GET(self):
        path = self.api_path()
        with connect(self.server.db_path) as conn:
            if path == "/api/session":
                configured = conn.execute("SELECT 1 FROM owner").fetchone() is not None
                return self.send_json(200, {"owner": self.is_owner(conn), "configured": configured,
                    "canSetup": not configured and self.local_setup_allowed()})
            if path in {"/api/reviews", "/api/export"}:
                if path == "/api/export" and not self.is_owner(conn):
                    return self.send_json(401, {"error": "请先登录。"})
                reviews = {row["place_id"]: {**json.loads(row["payload"]), "revision": row["revision"]}
                           for row in conn.execute("SELECT * FROM reviews")}
                return self.send_json(200, {"schemaVersion": 1, "reviews": reviews})
        if path.startswith("/api/"):
            return self.send_json(404, {"error": "接口不存在。"})
        route = unquote(urlsplit(self.path).path)
        if route in {"/", "/map/", "/map", "/index.html"}:
            file = ROOT / "dist" / "Review-Map.html"
        elif route in {'/calibrate', '/calibrate/', '/map/calibrate/'}:
            with connect(self.server.db_path) as conn:
                if not self.local_setup_allowed() and not self.is_owner(conn):
                    return self.send_json(401, {'error': 'Log in on the map before opening the calibration desk.'})
            file = ROOT / 'dist' / 'Calibration-Desk.html'
        else:
            return self.send_error(404)
        if not file.exists():
            return self.send_json(503, {"error": "请先运行 python3 scripts/build_single_file.py。"})
        data = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(file)[0] or "text/html")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        self.mutate()

    def do_PUT(self):
        self.mutate()

    def do_DELETE(self):
        self.mutate()

    def mutate(self):
        if not self.same_origin():
            return self.send_json(403, {"error": "请从个人点评页面操作。"})
        try:
            body = self.body()
            path = self.api_path()
            with connect(self.server.db_path) as conn:
                if path == "/api/session" and self.command == "POST":
                    ip = self.client_address[0]
                    attempts, until = self.server.failures.get(ip, (0, 0))
                    if until > time.time():
                        return self.send_json(429, {"error": "尝试次数较多，请一分钟后再试。"})
                    password = body.get("password", "")
                    if not isinstance(password, str) or not 8 <= len(password) <= 256:
                        raise ValueError("密码需要 8–256 个字符。")
                    owner = conn.execute("SELECT * FROM owner").fetchone()
                    if owner is None:
                        if not body.get("setup") or not self.local_setup_allowed():
                            return self.send_json(403, {"error": "请在服务器本机完成首次密码设置。"})
                        salt = secrets.token_hex(16)
                        try:
                            conn.execute("INSERT INTO owner VALUES (1,?,?)", (salt, password_hash(password, salt)))
                        except sqlite3.IntegrityError:
                            return self.send_json(409, {"error": "密码已设置，请重新登录。"})
                    elif not hmac.compare_digest(owner["hash"], password_hash(password, owner["salt"])):
                        attempts += 1
                        self.server.failures[ip] = (attempts, time.time() + 60 if attempts >= 5 else 0)
                        return self.send_json(401, {"error": "密码不正确，请再试一次。"})
                    self.server.failures.pop(ip, None)
                    token = secrets.token_urlsafe(32)
                    conn.execute("DELETE FROM sessions WHERE expires<?", (time.time(),))
                    conn.execute("INSERT INTO sessions VALUES (?,?)", (hashlib.sha256(token.encode()).hexdigest(), time.time() + 604800))
                    conn.commit()
                    return self.send_json(200, {"owner": True}, self.session_cookie(token, 604800))
                if path == "/api/logout" and self.command == "POST":
                    cookie = SimpleCookie(self.headers.get("Cookie", ""))
                    if cookie.get("review_map_session"):
                        conn.execute("DELETE FROM sessions WHERE token=?", (hashlib.sha256(cookie["review_map_session"].value.encode()).hexdigest(),))
                    conn.commit()
                    return self.send_json(200, {"owner": False}, self.session_cookie("", 0))
                if not self.is_owner(conn):
                    return self.send_json(401, {"error": "请先登录后再编辑。"})
                if path.startswith("/api/reviews/") and self.command in {"PUT", "DELETE"}:
                    place_id = unquote(path.removeprefix("/api/reviews/"))
                    if place_id not in self.server.place_ids:
                        return self.send_json(404, {"error": "地点不存在。"})
                    payload = validate_review(body) if self.command == "PUT" else None
                    conn.execute("BEGIN IMMEDIATE")
                    row = conn.execute("SELECT revision FROM reviews WHERE place_id=?", (place_id,)).fetchone()
                    revision = row["revision"] if row else 0
                    if body.get("revision", 0) != revision:
                        return self.send_json(409, {"error": "另一台设备已更新这条点评，请刷新后再编辑。"})
                    if self.command == "DELETE":
                        conn.execute("DELETE FROM reviews WHERE place_id=?", (place_id,))
                        conn.commit()
                        return self.send_json(200, {"deleted": True})
                    conn.execute("INSERT OR REPLACE INTO reviews VALUES (?,?,?)", (place_id, json.dumps(payload, ensure_ascii=False), revision + 1))
                    conn.commit()
                    return self.send_json(200, {"review": {**payload, "revision": revision + 1}})
                return self.send_json(404, {"error": "接口不存在。"})
        except ValueError as exc:
            self.send_json(400, {"error": str(exc)})
        except Exception:
            self.send_json(500, {"error": "保存失败，请稍后再试。"})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "personal" / "reviews.sqlite3")
    parser.add_argument("--secure-cookie", action="store_true")
    args = parser.parse_args()
    args.db.parent.mkdir(parents=True, exist_ok=True)
    connect(args.db).close()
    generated = (ROOT / "data" / "generated" / "places-data.js").read_text()
    places = json.loads(generated.split(" = ", 1)[1].rstrip(";\n"))
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.db_path = args.db
    server.place_ids = {place["id"] for place in places}
    server.secure_cookie = args.secure_cookie
    server.failures = {}
    version_path = ROOT / 'VERSION'
    version = version_path.read_text().strip() if version_path.exists() else 'V2.0'
    print(f"Review Map {version} — http://{args.host}:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
