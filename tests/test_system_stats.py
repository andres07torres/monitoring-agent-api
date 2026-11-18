import os
import unittest

from fastapi.testclient import TestClient

from backend.main import app


class TestSystemStatsEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        api_key = os.getenv("API_SECRET_KEY", "test123")
        self.headers = {"X-API-Key": api_key}

    def test_stats_includes_dynamic_system_metadata(self):
        """El endpoint debe incluir los cinco campos dinámicos esperados por la app Android."""
        response = self.client.get("/api/v1/system/stats", headers=self.headers)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        for field in (
            "os",
            "architecture",
            "uptime",
            "protected_ports",
            "zero_trust_tunnel",
        ):
            self.assertIn(field, data)
            self.assertIsInstance(data[field], str)

        self.assertTrue(data["os"].strip())
        self.assertTrue(data["architecture"].strip())
        self.assertTrue(data["uptime"].strip())
        self.assertTrue(data["zero_trust_tunnel"].strip())

    def test_uptime_is_human_readable(self):
        """El uptime debe estar expresado en unidades legibles, no en segundos crudos."""
        response = self.client.get("/api/v1/system/stats", headers=self.headers)
        self.assertEqual(response.status_code, 200)

        uptime = response.json()["uptime"]
        self.assertRegex(uptime, r"^\d+ (segundo|minuto|día|hora)")

    def test_architecture_is_normalized(self):
        """La arquitectura no debe exponer alias como amd64/aarch64."""
        response = self.client.get("/api/v1/system/stats", headers=self.headers)
        self.assertEqual(response.status_code, 200)

        architecture = response.json()["architecture"].lower()
        self.assertNotIn(architecture, ("amd64", "aarch64"))

    def test_stats_requires_authentication(self):
        """Sin token la petición debe ser rechazada con 401."""
        response = self.client.get("/api/v1/system/stats")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
