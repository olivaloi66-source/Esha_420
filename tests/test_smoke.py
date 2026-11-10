import os
import tempfile
import unittest
from unittest.mock import patch

DB = tempfile.mktemp(suffix=".sqlite3")
os.environ["ARIN_DB_PATH"] = DB

import server


class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.client = server.app.test_client()

    def test_frontend_routes(self):
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertEqual(self.client.get("/mobile").status_code, 200)
        self.assertEqual(self.client.get("/arin-agent-town.css").status_code, 200)

    def test_public_api_routes(self):
        self.assertEqual(self.client.get("/api/version").status_code, 200)
        agents = self.client.get("/api/agents")
        self.assertEqual(agents.status_code, 200)
        self.assertEqual(len(agents.get_json()["agents"]), 6)

    def test_device_session_and_private_memory(self):
        token_response = self.client.post("/api/start")
        self.assertEqual(token_response.status_code, 200)
        token = token_response.get_json()["token"]
        headers = {"Authorization": "Bearer " + token}

        created = self.client.post("/api/memory", json={"text": "smoke-test"}, headers=headers)
        self.assertEqual(created.status_code, 200)
        listed = self.client.get("/api/memory", headers=headers)
        self.assertEqual(listed.status_code, 200)
        self.assertIn("smoke-test", [item["text"] for item in listed.get_json()["items"]])

    def test_chat_uses_server_side_provider(self):
        token = self.client.post("/api/start").get_json()["token"]
        with patch.object(server, "call_model", return_value="test reply"):
            response = self.client.post(
                "/api/chat",
                json={"agent": "ARIN", "messages": [{"text": "hello"}]},
                headers={"Authorization": "Bearer " + token},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["reply"], "test reply")

    def test_protected_endpoints_reject_anonymous_requests(self):
        self.assertEqual(self.client.get("/api/memory").status_code, 401)
        self.assertEqual(self.client.post("/api/chat", json={"messages": [{"text": "hi"}]}).status_code, 401)

    def test_admin_is_disabled_without_secret(self):
        if not server.ADMIN_KEY:
            self.assertEqual(self.client.post("/api/admin/set", json={"version": "test"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
