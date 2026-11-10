import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import server


class AgentTownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.temp.name, "test.db")

        def test_db():
            conn = sqlite3.connect(cls.db_path)
            conn.row_factory = sqlite3.Row
            return conn

        cls.original_db = server.db
        server.db = test_db
        with server.db() as conn:
            conn.executescript(
                "create table users(id integer primary key, name text unique, salt text, pw text, token text);"
                "create table memory(id integer primary key, uid int, text text);"
                "create table settings(k text primary key, v text);"
                "create table agent_memory(id integer primary key, uid int not null, agent text not null, text text not null, created_at text default current_timestamp);"
                "create table agent_shared_chat(id integer primary key, uid int not null, speaker text not null, text text not null, created_at text default current_timestamp);"
            )

    @classmethod
    def tearDownClass(cls):
        server.db = cls.original_db
        cls.temp.cleanup()

    def setUp(self):
        with server.db() as conn:
            for table in ("users", "memory", "settings", "agent_memory", "agent_shared_chat"):
                conn.execute("delete from " + table)
        self.client = server.app.test_client()
        response = self.client.post("/api/start")
        self.token = response.get_json()["token"]
        self.headers = {"Authorization": "Bearer " + self.token}

    def post_json(self, path, data):
        return self.client.post(path, json=data, headers=self.headers)

    def test_six_agents_are_available(self):
        response = self.client.get("/api/agents")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()["agents"]), 6)

    def test_private_memory_is_isolated_by_agent(self):
        saved = self.post_json("/api/agents/RONI/memory", {"text": "Roni-only note"})
        self.assertEqual(saved.status_code, 200)
        roni = self.client.get("/api/agents/RONI/memory", headers=self.headers).get_json()
        diva = self.client.get("/api/agents/DIVA/memory", headers=self.headers).get_json()
        self.assertEqual([x["text"] for x in roni["items"]], ["Roni-only note"])
        self.assertEqual(diva["items"], [])

    def test_chat_history_is_shared_between_agents(self):
        with patch("server.call_model", side_effect=["Roni reply", "Diva reply"]) as model:
            self.post_json("/api/chat", {"agent": "RONI", "messages": [{"role": "user", "text": "Build the app"}]})
            response = self.post_json("/api/chat", {"agent": "DIVA", "messages": [{"role": "user", "text": "Improve its look"}]})
        self.assertEqual(response.status_code, 200)
        second_context = model.call_args_list[1].args[1]
        self.assertTrue(any("[USER] Build the app" in m["content"] for m in second_context))
        self.assertTrue(any("[RONI] Roni reply" in m["content"] for m in second_context))

    def test_transfer_passes_shared_context_and_agent_role(self):
        with patch("server.call_model", side_effect=["Roni reply", "Diva took over"]) as model:
            self.post_json("/api/chat", {"agent": "RONI", "messages": [{"role": "user", "text": "Fix a bug"}]})
            response = self.post_json("/api/agents/transfer", {"from": "RONI", "to": "DIVA", "task": "Fix a bug"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["to_agent"], "DIVA")
        transferred_context = model.call_args_list[1].args[1]
        self.assertTrue(any(m["role"] == "assistant" and "[RONI] Roni reply" in m["content"] for m in transferred_context))

    def test_six_agent_team_is_sequential_and_logged(self):
        six = ["RONI", "DIVA", "ZARA", "MAYA", "ARIN", "NEXUS"]
        with patch("server.call_model", side_effect=[name + " result" for name in six]) as model:
            response = self.post_json("/api/team/run", {"task": "Review the release", "agents": six})
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["team_size"], 6)
        self.assertEqual(len(payload["contributions"]), 6)
        last_context = model.call_args_list[5].args[1]
        self.assertTrue(any("[RONI] RONI result" in m["content"] for m in last_context))
        self.assertTrue(any("[MAYA] MAYA result" in m["content"] for m in last_context))
        uid = server.db().execute("select id from users where token=?", (self.token,)).fetchone()["id"]
        logged = server.db().execute("select speaker,text from agent_shared_chat where uid=?", (uid,)).fetchall()
        self.assertEqual(sum(1 for row in logged if row["speaker"] in six), 6)


if __name__ == "__main__":
    unittest.main()
