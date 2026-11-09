import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault(
    "ARIN_DB_PATH",
    str(Path(tempfile.gettempdir()) / ("arin-ai-test-" + next(tempfile._get_candidate_names()) + ".sqlite3")),
)
os.environ.pop("OPENAI_API_KEY", None)

from app import app


class ArinApiTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()
        response = self.client.post("/api/start")
        self.assertEqual(response.status_code, 200)
        self.token = response.get_json()["token"]
        self.headers = {"Authorization": "Bearer " + self.token}

    def test_version_endpoint(self):
        response = self.client.get("/api/version")
        self.assertEqual(response.status_code, 200)
        self.assertIn("version", response.get_json())

    def test_memory_create_list_and_delete(self):
        created = self.client.post(
            "/api/memory",
            json={"text": "Remember the ARIN project"},
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 201)
        memory_id = created.get_json()["id"]

        listed = self.client.get("/api/memory", headers=self.headers)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.get_json()["items"][0]["text"], "Remember the ARIN project")

        deleted = self.client.delete(f"/api/memory/{memory_id}", headers=self.headers)
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.get_json()["deleted"])

    def test_memory_requires_session(self):
        response = self.client.get("/api/memory")
        self.assertEqual(response.status_code, 401)

    def test_memory_rejects_empty_text(self):
        response = self.client.post("/api/memory", json={"text": " "}, headers=self.headers)
        self.assertEqual(response.status_code, 400)

    def test_chat_explains_missing_api_key(self):
        response = self.client.post(
            "/api/chat",
            json={"agent": "ARIN", "messages": [{"role": "user", "text": "Hello"}]},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 503)
        self.assertIn("OPENAI_API_KEY", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
