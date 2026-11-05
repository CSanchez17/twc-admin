"""Proxy/TLS settings: CSRF origins, X-Forwarded-Proto and secure cookies.

A deployed panel sits behind Easypanel's TLS-terminating proxy. Two things
break without these settings, and neither shows up until someone tries to log
in:

* ``request.is_secure()`` is False (the proxy speaks HTTP to gunicorn), so the
  CSRF origin check rejects the login POST with "does not match any trusted
  origins";
* secure cookies are never set / accepted.

These tests pin the derivation so a future settings edit cannot regress it.
"""

import os

from django.conf import settings
from django.test import SimpleTestCase

from twc_project.settings import _allowed_hosts, _csrf_trusted_origins, _secure_cookies


class ProxyTlsSettingsTests(SimpleTestCase):
    def test_x_forwarded_proto_is_honoured(self):
        self.assertEqual(settings.SECURE_PROXY_SSL_HEADER, ("HTTP_X_FORWARDED_PROTO", "https"))

    def test_origins_are_derived_from_explicit_hosts(self):
        hosts = _allowed_hosts("admin.thewhitecode.com,panel.example.com")
        origins = _csrf_trusted_origins("", hosts)
        self.assertIn("https://admin.thewhitecode.com", origins)
        self.assertIn("https://panel.example.com", origins)

    def test_loopback_and_wildcard_are_not_origins(self):
        hosts = _allowed_hosts("admin.thewhitecode.com")
        origins = _csrf_trusted_origins("", hosts)
        self.assertNotIn("https://127.0.0.1", origins)
        self.assertNotIn("https://localhost", origins)
        self.assertEqual(_csrf_trusted_origins("", ["*"]), [])

    def test_explicit_env_list_wins(self):
        origins = _csrf_trusted_origins(" https://a.example.com , https://b.example.com ", ["*"])
        self.assertEqual(origins, ["https://a.example.com", "https://b.example.com"])

    def test_secure_cookies_default_follow_debug(self):
        # Django forces DEBUG=False while running tests, so this asserts the
        # rule itself rather than the value computed at import time.
        self.assertFalse(_secure_cookies("", debug=True))
        self.assertTrue(_secure_cookies("", debug=False))
        self.assertEqual(settings.CSRF_COOKIE_SECURE, settings.SESSION_COOKIE_SECURE)

    def test_secure_cookies_env_override(self):
        self.assertTrue(_secure_cookies("1", debug=True))
        self.assertFalse(_secure_cookies("0", debug=False))
