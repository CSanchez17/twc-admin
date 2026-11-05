#!/usr/bin/env python3
"""Smoke-check a deployed twc-admin panel (stdlib only, no dependencies).

What it proves, in the order the platform cares about:

1. ``GET /healthz`` answers 200 ``ok`` — this is exactly what the Docker
   HEALTHCHECK probes, so a failure here means the container will be stopped.
2. ``GET /login/`` answers 200 with a form and a CSRF token — the host is in
   ``DJANGO_ALLOWED_HOSTS`` (otherwise Django answers 400) and the admin app is
   wired up.
3. ``GET /`` without a session redirects to ``/login/?next=/`` — the admin is
   mounted at the root and protected.

Optional ``--auth USER:PASSWORD`` additionally logs in (CSRF-cookie dance) and
asserts that ``/panel/`` renders, which is the end-to-end proof that the shared
MySQL of the project is reachable with the configured ``DATABASE_URL``.

Exit code 0 = every check passed, 1 = at least one failed (details on stdout).

Usage::

    python scripts/verify_deploy.py --base https://twc-prod-admin.58nbit.easypanel.host
    python scripts/verify_deploy.py --base https://<domain> --auth twcadmin:secret
"""

from __future__ import annotations

import argparse
import http.cookiejar
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 20


class Result:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
        if not ok:
            self.failures.append(name)


def build_opener() -> tuple[urllib.request.OpenerDirector, http.cookiejar.CookieJar]:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("User-Agent", "twc-admin-verify/1.0")]
    return opener, jar


def fetch(opener, url: str, data: dict | None = None, headers: dict | None = None):
    body = urllib.parse.urlencode(data).encode() if data else None
    request = urllib.request.Request(url, data=body, headers=headers or {})
    try:
        with opener.open(request, timeout=TIMEOUT) as response:
            return response.status, response.read().decode("utf-8", "replace"), response.geturl()
    except urllib.error.HTTPError as exc:  # 4xx/5xx are data, not crashes
        return exc.code, exc.read().decode("utf-8", "replace"), url
    except urllib.error.URLError as exc:
        return 0, f"connection error: {exc.reason}", url


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", required=True, help="https://<panel domain>")
    parser.add_argument("--auth", default="", metavar="USER:PASSWORD", help="also log in and open /panel/")
    args = parser.parse_args(argv)

    base = args.base.rstrip("/")
    result = Result()
    opener, jar = build_opener()

    print(f"target: {base}")

    status, body, _ = fetch(opener, f"{base}/healthz")
    result.check("GET /healthz -> 200 ok", status == 200 and body.strip() == "ok", f"status={status} body={body[:40]!r}")

    status, body, _ = fetch(opener, f"{base}/login/")
    has_form = "csrfmiddlewaretoken" in body and 'name="password"' in body
    result.check("GET /login/ -> 200 with CSRF form", status == 200 and has_form, f"status={status}")

    if status == 400:
        print("        hint: 400 = the domain is not in DJANGO_ALLOWED_HOSTS")

    status, _, final = fetch(opener, f"{base}/")
    # urllib follows the redirect; landing on the login page (with ?next=) is
    # the assertion, the status of the final response stays 200.
    result.check("GET / requires login", "/login/" in final, f"final={final}")

    if args.auth:
        user, _, password = args.auth.partition(":")
        token = next((cookie.value for cookie in jar if cookie.name == "csrftoken"), "")
        headers = {"Referer": f"{base}/login/", "Origin": base}
        status, body, final = fetch(
            opener,
            f"{base}/login/",
            data={
                "username": user,
                "password": password,
                "csrfmiddlewaretoken": token,
                "next": "/panel/",
            },
            headers=headers,
        )
        logged_in = status == 200 and "panel" in final
        result.check("POST /login/ with credentials", logged_in, f"status={status} final={final}")
        if status == 403:
            print("        hint: 403 = CSRF origin check (SECURE_PROXY_SSL_HEADER / CSRF_TRUSTED_ORIGINS)")
        if logged_in:
            status, body, _ = fetch(opener, f"{base}/panel/")
            rows = body.count("field-title")
            result.check("GET /panel/ lists content rows", status == 200 and rows > 0, f"status={status} rows={rows}")

    print()
    if result.failures:
        print(f"FAILED: {len(result.failures)} check(s): {', '.join(result.failures)}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
