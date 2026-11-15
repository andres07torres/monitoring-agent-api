import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import os

from backend.main import app
import os

class TestHealthCheckEndpoint(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        api_key = os.getenv("API_SECRET_KEY", "test123")
        self.headers = {"X-API-Key": api_key}

    def test_local_healthcheck_without_params(self):
        """Verifica healthcheck local sin parámetros (200 OK, message: OK)"""
        response = self.client.get("/api/v1/healthcheck", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], 200)
        self.assertEqual(data["message"], "OK")

    @patch("api.routes.find_container")
    def test_database_container_running(self, mock_find_container):
        """
        Bases de datos / Servicios no HTTP:
        Si el contenedor está running, debe responder { "status": 200, "message": "Container is Running" }
        sin intentar hacer peticiones HTTP.
        """
        mock_container = MagicMock()
        mock_container.name = "mysql-database"
        mock_container.status = "running"
        mock_container.attrs = {
            "Config": {"Image": "mysql:8.0", "ExposedPorts": {"3306/tcp": {}}},
            "NetworkSettings": {"Ports": {"3306/tcp": None}}
        }
        mock_find_container.return_value = mock_container

        response = self.client.get("/api/v1/healthcheck?container=mysql-database", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], 200)
        self.assertEqual(data["message"], "Container is Running")

    @patch("api.routes.find_container")
    def test_redis_container_running(self, mock_find_container):
        """Prueba con contenedor Redis (no HTTP)"""
        mock_container = MagicMock()
        mock_container.name = "redis-cache"
        mock_container.status = "running"
        mock_container.attrs = {
            "Config": {"Image": "redis:alpine", "ExposedPorts": {"6379/tcp": {}}},
            "NetworkSettings": {"Ports": {}}
        }
        mock_find_container.return_value = mock_container

        response = self.client.get("/api/v1/healthcheck?container=redis-cache", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], 200)
        self.assertEqual(data["message"], "Container is Running")

    @patch("api.routes.find_container")
    def test_worker_container_running(self, mock_find_container):
        """Prueba con worker celery (no HTTP)"""
        mock_container = MagicMock()
        mock_container.name = "celery-worker"
        mock_container.status = "running"
        mock_container.attrs = {
            "Config": {"Image": "my-worker:latest", "ExposedPorts": {}},
            "NetworkSettings": {"Ports": {}}
        }
        mock_find_container.return_value = mock_container

        response = self.client.get("/api/v1/healthcheck?container=celery-worker", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], 200)
        self.assertEqual(data["message"], "Container is Running")

    @patch("api.routes.find_container")
    def test_database_container_stopped(self, mock_find_container):
        """Bases de datos detenidas retornan 503 en JSON y 200 a nivel HTTP."""
        mock_container = MagicMock()
        mock_container.name = "postgres-db"
        mock_container.status = "exited"
        mock_container.attrs = {
            "Config": {"Image": "postgres:15", "ExposedPorts": {"5432/tcp": {}}},
            "NetworkSettings": {"Ports": {}}
        }
        mock_find_container.return_value = mock_container

        response = self.client.get("/api/v1/healthcheck?container=postgres-db", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], 503)
        self.assertEqual(data["message"], "Connection refused / Timeout")

    @patch("httpx.AsyncClient.get")
    def test_web_service_success(self, mock_http_get):
        """Servicios Web disponibles devuelven 200 OK."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_http_get.return_value = mock_resp

        response = self.client.get("/api/v1/healthcheck?url=http://localhost:8080/health", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], 200)
        self.assertEqual(data["message"], "OK")

    @patch("httpx.AsyncClient.get")
    def test_web_service_connection_refused(self, mock_http_get):
        """Servicios Web caídos o connection refused devuelven 503."""
        import httpx
        mock_http_get.side_effect = httpx.ConnectError("Connection refused")

        response = self.client.get("/api/v1/healthcheck?url=http://localhost:8080", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], 503)
        self.assertEqual(data["message"], "Connection refused / Timeout")

    @patch("httpx.AsyncClient.get")
    def test_web_service_timeout(self, mock_http_get):
        """Servicios Web con timeout devuelven 503 'Connection refused / Timeout'."""
        import httpx
        mock_http_get.side_effect = httpx.TimeoutException("Read timed out")

        response = self.client.get("/api/v1/healthcheck?url=http://localhost:8080", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], 503)
        self.assertEqual(data["message"], "Connection refused / Timeout")

    def test_unauthorized_without_key(self):
        """Petición sin autenticación debe retornar 401."""
        response = self.client.get("/api/v1/healthcheck")
        self.assertEqual(response.status_code, 401)

    def test_authorized_with_bearer_token(self):
        """Petición con Authorization: Bearer <TOKEN> debe ser exitosa."""
        api_key = os.getenv("API_SECRET_KEY", "test123")
        headers = {"Authorization": f"Bearer {api_key}"}
        response = self.client.get("/api/v1/healthcheck", headers=headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], 200)
        self.assertEqual(data["message"], "OK")

    @patch("api.routes.find_container")
    def test_container_id_param(self, mock_find_container):
        """Soporta parámetro container_id para bases de datos."""
        mock_container = MagicMock()
        mock_container.name = "postgres-app"
        mock_container.status = "running"
        mock_container.attrs = {"Config": {"Image": "postgres:16"}}
        mock_find_container.return_value = mock_container

        response = self.client.get("/api/v1/healthcheck?container_id=abc12345", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], 200)
        self.assertEqual(data["message"], "Container is Running")

    @patch("api.routes.find_container")
    def test_php_fpm_container_running(self, mock_find_container):
        """symfony_php (contenedor php/fpm) corriendo debe responder 200 Container is Running."""
        mock_container = MagicMock()
        mock_container.name = "symfony_php"
        mock_container.status = "running"
        mock_container.attrs = {"Config": {"Image": "php:8.2-fpm"}}
        mock_find_container.return_value = mock_container

        response = self.client.get("/api/v1/healthcheck?container=symfony_php", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], 200)
        self.assertEqual(data["message"], "Container is Running")

    @patch("httpx.AsyncClient.get")
    @patch("api.routes.find_container")
    def test_web_container_running_fallback(self, mock_find_container, mock_http_get):
        """Contenedor web activo donde HTTP directo no conecta (ej. red bridge aislada) responde 200 Container is Running."""
        import httpx
        mock_http_get.side_effect = httpx.ConnectError("Connection refused")

        mock_container = MagicMock()
        mock_container.name = "sistema_tareas_app"
        mock_container.status = "running"
        mock_container.attrs = {
            "Config": {"Image": "sistema-tareas:latest"},
            "NetworkSettings": {"Ports": {"80/tcp": [{"HostPort": "8080"}]}}
        }
        mock_find_container.return_value = mock_container

        response = self.client.get("/api/v1/healthcheck?container=sistema_tareas_app", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], 200)
        self.assertEqual(data["message"], "Container is Running")

    @patch("api.routes.find_container")
    def test_explicit_service_type_db(self, mock_find_container):
        """Si service_type='db', trata el contenedor como base de datos aunque su nombre no lo indique."""
        mock_container = MagicMock()
        mock_container.name = "custom-storage-node"
        mock_container.status = "running"
        mock_container.attrs = {"Config": {"Image": "custom-image"}}
        mock_find_container.return_value = mock_container

        response = self.client.get("/api/v1/healthcheck?container=custom-storage-node&service_type=db", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], 200)
        self.assertEqual(data["message"], "Container is Running")

if __name__ == "__main__":
    unittest.main()
