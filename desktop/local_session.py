"""Only the Sora WebView2 window may access the local Flask server.

A loopback listener alone is NOT sufficient: another local application or
a malicious page can address http://127.0.0.1 directly. Session bootstrap
uses a one-time random secret known to the native Windows process only.
"""
from __future__ import annotations

from http.cookies import SimpleCookie
import hmac
from secrets import token_urlsafe
from urllib.parse import parse_qs


class ProtectedLocalApp:
    COOKIE = "sora_native_session"

    def __init__(self, app):
        self.app = app
        self.secret = token_urlsafe(40)

    def bootstrap_url(self, port):
        return f"http://127.0.0.1:{port}/?sora_launch={self.secret}"

    def _accepted_cookie(self, environ):
        raw = environ.get("HTTP_COOKIE", "")
        try:
            parsed = SimpleCookie()
            parsed.load(raw)
            value = parsed[self.COOKIE].value if self.COOKIE in parsed else ""
        except Exception:
            return False
        return bool(value) and hmac.compare_digest(value, self.secret)

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        method = environ.get("REQUEST_METHOD", "GET").upper()
        host = environ.get("HTTP_HOST", "")
        if not (host.startswith("127.0.0.1:") or host.startswith("localhost:")):
            return self._deny(start_response)
        if path == "/" and method == "GET":
            key = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True).get("sora_launch", [""])[0]
            if key and hmac.compare_digest(key, self.secret):
                # Redirect to remove bootstrap token from page URL/history.
                start_response("302 Found", [
                    ("Location", "/"),
                    ("Set-Cookie", f"{self.COOKIE}={self.secret}; Path=/; HttpOnly; SameSite=Strict"),
                    ("Cache-Control", "no-store"),
                    ("X-Content-Type-Options", "nosniff"),
                ])
                return [b""]
        if not self._accepted_cookie(environ):
            return self._deny(start_response)
        if method not in ("GET", "HEAD", "OPTIONS"):
            origin = environ.get("HTTP_ORIGIN")
            # WebView2 fetches may omit Origin; if present it must be first-party.
            if origin and origin != "http://" + host:
                return self._deny(start_response)
        return self.app(environ, start_response)

    @staticmethod
    def _deny(start_response):
        start_response("403 Forbidden", [
            ("Content-Type", "text/plain; charset=utf-8"),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
        ])
        return ["Brak dostępu do prywatnego panelu Sora PC.".encode("utf-8")]
