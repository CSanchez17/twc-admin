"""ALLOWED_HOSTS must always include loopback (healthcheck regression).

The image's HEALTHCHECK probes ``http://127.0.0.1:8000/login/`` from inside
the container. A deployed panel pins real domains (DJANGO_ALLOWED_HOSTS), so
without the loopback entries Django answered 400 DisallowedHost, the
container went unhealthy and the platform stopped it ~70 s after every boot —
surfacing as a 502 from the proxy. This test pins the helper so that failure
mode cannot come back.
"""

from django.test import SimpleTestCase

from twc_project.settings import _allowed_hosts


class AllowedHostsTests(SimpleTestCase):
    def test_loopback_is_added_to_explicit_domains(self):
        hosts = _allowed_hosts("admin.thewhitecode.com,twc-prod-admin.58nbit.easypanel.host")
        self.assertIn("admin.thewhitecode.com", hosts)
        self.assertIn("twc-prod-admin.58nbit.easypanel.host", hosts)
        for loopback in ("127.0.0.1", "localhost", "[::1]"):
            self.assertIn(loopback, hosts)

    def test_empty_value_falls_back_to_wildcard(self):
        self.assertEqual(_allowed_hosts(""), ["*"])
        self.assertEqual(_allowed_hosts("   "), ["*"])

    def test_wildcard_is_not_duplicated(self):
        self.assertEqual(_allowed_hosts("*"), ["*"])

    def test_no_duplicates_when_operator_already_listed_loopback(self):
        hosts = _allowed_hosts("127.0.0.1,localhost,panel.example.com")
        self.assertEqual(len(hosts), len(set(hosts)))
        self.assertEqual(hosts.count("127.0.0.1"), 1)
