import os
import tempfile
import unittest
from pathlib import Path

# Give each test run its own database before importing the Flask application.
os.environ.setdefault(
    "ARIN_DB_PATH",
    str(Path(tempfile.gettempdir()) / ("arin-test-" + next(tempfile._get_candidate_names()) + ".sqlite3")),
)

import server


class ArinApiTests(unittest.TestCase):
    def setUp(self):
        server.app.config.update(TESTING=True)
        self.client = server.app.test_client()
        started = self.client.post("/api/start")
        self.assertEqual(started.status_code, 200)
        self.token = started.get_json()["token"]
        self.headers = {"Authorization": "Bearer " + self.token}

    def test_version_endpoint(self):
        response = self.client.get("/api/version")
        self.assertEqual(response.status_code, 200)
        self.assertIn("version", response.get_json())

    def test_shared_memory_create_list_delete(self):
        created = self.client.post(
            "/api/memory",
            json={"text": "Remember the ARIN project"},
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 200)
        memory_id = created.get_json()["id"]

        listed = self.client.get("/api/memory", headers=self.headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.get_json()["items"][0]["text"], "Remember the ARIN project")

        deleted = self.client.delete(f"/api/memory/{memory_id}", headers=self.headers)
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.get_json()["ok"])

    def test_memory_requires_session(self):
        response = self.client.get("/api/memory")
        self.assertEqual(response.status_code, 401)

    def test_memory_rejects_empty_text(self):
        response = self.client.post("/api/memory", json={"text": " "}, headers=self.headers)
        self.assertEqual(response.status_code, 400)

    def test_agent_list(self):
        response = self.client.get("/api/agents")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({a["id"] for a in response.get_json()["agents"]},
                         {"ARIN", "RONI", "DIVA", "ZARA", "MAYA", "NEXUS"})


if __name__ == "__main__":
    unittest.main()
