"""The platform health probe must not depend on the database.

The container is stopped by the platform when the Docker HEALTHCHECK fails,
so that probe points at /healthz: no DB, no template, no auth. If the shared
MySQL is unreachable the panel should show 500s on content pages, not vanish
from the proxy.
"""

from django.test import SimpleTestCase


class HealthzTests(SimpleTestCase):
    def test_healthz_returns_ok_without_db(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")
        self.assertEqual(response["Content-Type"], "text/plain")

    def test_healthz_works_for_a_non_browser_host(self):
        # The probe runs inside the container against 127.0.0.1.
        response = self.client.get("/healthz", SERVER_NAME="127.0.0.1")
        self.assertEqual(response.status_code, 200)

    def test_healthz_is_not_the_admin_index(self):
        response = self.client.get("/healthz")
        self.assertNotIn(b"Log in", response.content)
