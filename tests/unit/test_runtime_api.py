from __future__ import annotations

import os
import unittest

from fastapi.testclient import TestClient

import runtime.api as runtime_api
from runtime.api import create_app


class RuntimeAPITest(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["RUNTIME_INTERNAL_TOKEN"] = "test-runtime-token"
        runtime_api._jobs.clear()
        self.client = TestClient(create_app())

    def test_healthz(self) -> None:
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["runtime_ready"])

    def test_submit_task_requires_internal_token(self) -> None:
        response = self.client.post("/internal/v1/tasks", json={"instruction": "hello"})
        self.assertEqual(response.status_code, 401)

    def test_submit_task_and_poll_result(self) -> None:
        response = self.client.post(
            "/internal/v1/tasks",
            headers={"x-runtime-token": "test-runtime-token"},
            json={"instruction": "runtime api smoke"},
        )
        self.assertEqual(response.status_code, 202, response.text)
        accepted = response.json()
        self.assertIn("task_id", accepted)

        final_payload = None
        for _ in range(60):
            status_response = self.client.get(
                f"/internal/v1/tasks/{accepted['task_id']}",
                headers={"x-runtime-token": "test-runtime-token"},
            )
            self.assertEqual(status_response.status_code, 200, status_response.text)
            final_payload = status_response.json()
            if final_payload["completed"]:
                break
        self.assertIsNotNone(final_payload)
        self.assertTrue(final_payload["completed"])
        self.assertEqual(final_payload["status"], "completed")
        self.assertTrue(final_payload["result"]["ok"])
        self.assertIn("task_id", final_payload["result"])

    def test_cancel_queued_runtime_task(self) -> None:
        runtime_api._jobs["runtime_job_test"] = {
            "status": "queued",
            "completed": False,
            "submitted_at": 0.0,
            "cancel_requested": False,
            "result": None,
            "error": None,
        }
        response = self.client.delete(
            "/internal/v1/tasks/runtime_job_test",
            headers={"x-runtime-token": "test-runtime-token"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["status"], "cancelled")
        self.assertTrue(payload["completed"])

        status_response = self.client.get(
            "/internal/v1/tasks/runtime_job_test",
            headers={"x-runtime-token": "test-runtime-token"},
        )
        self.assertEqual(status_response.status_code, 200, status_response.text)
        status_payload = status_response.json()
        self.assertEqual(status_payload["status"], "cancelled")
        self.assertTrue(status_payload["completed"])


if __name__ == "__main__":
    unittest.main()
