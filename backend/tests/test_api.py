from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = cls.temp_dir.name

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp_dir.cleanup()

    def test_health(self) -> None:
        from fastapi.testclient import TestClient
        from backend.app.main import app

        with TestClient(app) as client:
            response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_create_job_returns_queued_job(self) -> None:
        from fastapi.testclient import TestClient
        from backend.app.main import app

        with patch("backend.app.main._schedule") as schedule, TestClient(app) as client:
            response = client.post(
                "/api/v1/jobs",
                json={"share_text": "https://v.douyin.com/AbC_12-xY/", "quality": "best"},
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "queued")
        schedule.assert_called_once()


if __name__ == "__main__":
    unittest.main()
