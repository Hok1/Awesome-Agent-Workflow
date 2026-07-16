from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / "skills" / "aaw-workflow" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cli.telemetry import (  # noqa: E402
    TelemetryClient,
    TelemetryError,
    TelemetryStore,
    build_patch,
    git_user,
    repository_name,
)


class TelemetryTests(unittest.TestCase):
    def _workflow(self):
        return SimpleNamespace(
            sr="SR-TIMESTAMPS",
            vars={},
            status="in_progress",
            created_at="2026-07-15T01:00:00Z",
        )

    def _step(self):
        return SimpleNamespace(
            id=1,
            type="module-design-gate",
            vars={},
            started_at="2026-07-15T01:02:03Z",
            ended_at="2026-07-15T01:07:03Z",
        )

    def _dev_step(self):
        return SimpleNamespace(
            id=2,
            type="task-dev",
            vars={},
            started_at="2026-07-15T01:02:03Z",
            ended_at="2026-07-15T01:07:03Z",
        )

    def _message(self, store: TelemetryStore, step=None):
        with (
            patch("cli.telemetry.git_user", return_value=("developer@example.com", "Z12345678")),
            patch("cli.telemetry.repository_name", return_value="example-service"),
        ):
            return store.step_message(self._workflow(), step or self._step(), "done")

    def test_repository_name_omits_organization(self) -> None:
        for remote in (
            "https://github.com/pi-ixel/Awesome-Agent-Workflow.git",
            "git@github.com:pi-ixel/Awesome-Agent-Workflow.git",
        ):
            with self.subTest(remote=remote), patch("cli.telemetry._git", return_value=remote):
                self.assertEqual("Awesome-Agent-Workflow", repository_name(Path.cwd()))

    def test_invalid_git_name_uses_server_compatible_display_name(self) -> None:
        with patch("cli.telemetry._git", side_effect=["developer@example.com", "Developer"]), patch.dict(os.environ, {}, clear=True):
            self.assertEqual(("developer@example.com", "Z00000000"), git_user(Path.cwd()))

    def test_patch_uses_d0_as_baseline_and_counts_categories(self) -> None:
        patch_text, statistics = build_patch(
            {"src/service.py": b"value = 'dirty-before-dev'\n"},
            {"src/service.py": b"value = 'changed-during-dev'\n", "tests/test_api.py": b"assert True\n"},
            [],
        )
        self.assertIn("changed-during-dev", patch_text)
        self.assertEqual(2, statistics["total_effective_lines"])

    def test_step_message_is_built_in_memory_from_yaml_timestamps(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = TelemetryStore(Path(temp))
            message = self._message(store)
            self.assertFalse(store.dir.exists())
        self.assertEqual("example-service", message["repository"])
        self.assertEqual("done", message["data"]["status"])
        self.assertEqual(1784077323000, message["data"]["started_at"])
        self.assertEqual(1784077623000, message["data"]["completed_at"])
        self.assertIsNone(message["data"]["file"])

    def test_send_posts_message_directly_without_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = TelemetryStore(Path(temp))
            message = self._message(store)
            seen = []

            def accept(url, method, body, headers=None):
                seen.append((url, method, headers))
                return 200, {"message_id": message["message_id"], "status": "accepted", "error": None}

            client = TelemetryClient(Path(temp))
            client.endpoint = "https://telemetry.example.test"
            client._request = staticmethod(accept)
            result = client.send(message)
            self.assertEqual("accepted", result["status"])
            self.assertFalse(store.dir.exists())
        self.assertEqual("https://telemetry.example.test/api/v1/telemetry/sync", seen[0][0])
        self.assertEqual("POST", seen[0][1])
        self.assertNotIn("Authorization", seen[0][2])

    def test_rejected_message_is_not_persisted_for_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = TelemetryStore(Path(temp))
            message = self._message(store)
            client = TelemetryClient(Path(temp))
            client._request = staticmethod(
                lambda *_args, **_kwargs: (400, {"code": "INVALID_REQUEST", "message": "bad data", "retryable": False})
            )
            with self.assertRaisesRegex(TelemetryError, "INVALID_REQUEST: bad data"):
                client.send(message)
            self.assertFalse(store.dir.exists())

    def test_dev_diff_is_uploaded_only_after_message_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            patch_path = root / "step.diff"
            patch_path.write_bytes(b"diff bytes")
            state = {
                "patch_path": str(patch_path),
                "file": {"file_name": "step.diff", "sha256": "a" * 64},
                "size_bytes": 10,
            }
            message = self._message(TelemetryStore(root))
            message["message_id"] = "message-1"
            seen = []

            def accept(url, method, body, headers=None):
                seen.append(method)
                if url.endswith("/telemetry/sync"):
                    return 200, {"message_id": "message-1", "status": "accepted", "error": None}
                if url.endswith("/objects/uploads"):
                    return 201, {"upload_id": "upload-1", "upload_url": "/api/v1/objects/uploads/upload-1/content"}
                return 200, {}

            client = TelemetryClient(root)
            client._request = staticmethod(accept)
            result = client.send(message, state)
            self.assertEqual(1, result["uploaded"])
            self.assertEqual(["POST", "POST", "PUT", "POST"], seen)

    def test_task_dev_temporary_files_are_cleaned_after_done(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            store = TelemetryStore(Path(temp))
            workflow = self._workflow()
            step = self._dev_step()
            with (
                patch("cli.telemetry.repository_name", return_value="example-service"),
                patch.object(store, "_worktree_files", return_value=({"src/service.py": b"before\n"}, [])),
            ):
                store.dev_started(workflow, step)
            with (
                patch("cli.telemetry.repository_name", return_value="example-service"),
                patch.object(store, "_worktree_files", return_value=({"src/service.py": b"after\n"}, [])),
            ):
                state = store.dev_finished(workflow, step)
                self.assertTrue(Path(state["state_path"]).exists())
                self.assertTrue(Path(state["patch_path"]).exists())
                store.cleanup_step(workflow, step, 1, state)
            self.assertFalse(Path(state["state_path"]).exists())
            self.assertFalse(Path(state["patch_path"]).exists())


if __name__ == "__main__":
    unittest.main()
