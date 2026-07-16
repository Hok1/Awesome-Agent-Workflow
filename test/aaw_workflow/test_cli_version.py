"""Tests for the global `--version` flag."""

from __future__ import annotations

import re
import unittest

from _cli_base import ROOT, CliTestBase


class VersionTests(CliTestBase):
    def test_version_flag_prints_pyproject_version(self) -> None:
        pyproject = (ROOT / "pyproject.toml").read_text("utf-8")
        match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
        assert match is not None

        result = self.run_cli("--version")

        self.assertEqual(match.group(1), result.stdout.strip())


if __name__ == "__main__":
    unittest.main()
