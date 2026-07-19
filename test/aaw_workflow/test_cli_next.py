"""Tests for the `aaw next` command."""

from __future__ import annotations

import json
import unittest

from _cli_base import CliTestBase


class NextCliTests(CliTestBase):
    def test_missing_sr_exits_with_error(self) -> None:
        result = self.run_cli("next", "--sr", "SR-NOPE", expect=1)

        self.assertIn("SR SR-NOPE 不存在", result.stderr)

    def test_marks_ready_skill_step_as_running(self) -> None:
        self.start_sr("SR-RUN")

        payload = json.loads(self.run_cli("next", "--sr", "SR-RUN", "--json").stdout)

        self.assertFalse(payload["done"])
        self.assertEqual([1], [s["id"] for s in payload["ready"]])
        step = self.status_json("SR-RUN")["steps"][0]
        self.assertEqual("running", step["execution_status"])
        self.assertEqual(1, step["attempt"])
        self.assertIsNotNone(step["started_at"])

    def test_repeated_next_is_idempotent_for_running_step(self) -> None:
        self.start_sr("SR-IDEM")
        self.run_cli("next", "--sr", "SR-IDEM", "--json")
        started_at = self.status_json("SR-IDEM")["steps"][0]["started_at"]

        self.run_cli("next", "--sr", "SR-IDEM", "--json")

        step = self.status_json("SR-IDEM")["steps"][0]
        self.assertEqual(1, step["attempt"])
        self.assertEqual(started_at, step["started_at"])

    def test_human_output_lists_ready_work_orders(self) -> None:
        self.start_sr("SR-READY")

        result = self.run_cli("next", "--sr", "SR-READY")

        self.assertIn("就绪工作单:", result.stdout)
        self.assertIn("[1]", result.stdout)
        self.assertIn("skill: repo-init", result.stdout)
        self.assertIn("done:", result.stdout)


if __name__ == "__main__":
    unittest.main()
