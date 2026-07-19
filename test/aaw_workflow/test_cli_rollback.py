"""Tests for the `aaw rollback` command."""

from __future__ import annotations

import json
import unittest

from _cli_base import CliTestBase


class RollbackCliTests(CliTestBase):
    def test_missing_sr_exits_with_error(self) -> None:
        result = self.run_cli("rollback", "--sr", "SR-NOPE", "1", expect=1)

        self.assertIn("SR SR-NOPE 不存在", result.stderr)

    def test_nonexistent_step_exits_with_error(self) -> None:
        self.start_sr("SR-RBERR")

        result = self.run_cli("rollback", "--sr", "SR-RBERR", "99", expect=1)

        self.assertIn("step 99 不存在", result.stderr)

    def test_rollback_removes_downstream_and_reopens_step(self) -> None:
        self.start_sr("SR-RB")
        self.complete_step_1("SR-RB")

        payload = json.loads(self.run_cli("rollback", "--sr", "SR-RB", "1", "--json").stdout)

        self.assertTrue(payload["ok"])
        self.assertEqual(1, payload["removed"])
        data = self.status_json("SR-RB")
        self.assertEqual([1], [s["id"] for s in data["steps"]])
        self.assertFalse(data["steps"][0]["finished"])
        self.assertEqual([], data["steps"][0]["next"])

    def test_human_output_reports_removed_count(self) -> None:
        self.start_sr("SR-RBOUT")
        self.complete_step_1("SR-RBOUT")

        result = self.run_cli("rollback", "--sr", "SR-RBOUT", "1")

        self.assertIn("已回退到 step 1", result.stdout)
        self.assertIn("移除 1 个下游 step", result.stdout)


if __name__ == "__main__":
    unittest.main()
