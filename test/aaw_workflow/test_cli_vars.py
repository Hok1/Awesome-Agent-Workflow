"""Tests for `_parse_vars` (--var / --sr / --ar / --title parsing)."""

from __future__ import annotations

import unittest

import _cli_base  # noqa: F401 — ensures scripts dir on sys.path

from cli.main import _parse_vars
from cli.models import WorkflowError


class ParseVarsTests(unittest.TestCase):
    def test_var_without_equals_raises(self) -> None:
        with self.assertRaisesRegex(WorkflowError, "格式错误"):
            _parse_vars(["SR-001"], None, None, None)

    def test_var_with_empty_key_raises(self) -> None:
        with self.assertRaisesRegex(WorkflowError, "缺少 key"):
            _parse_vars(["=value"], None, None, None)

    def test_explicit_options_override_var_entries(self) -> None:
        vars_ = _parse_vars(["SR=SR-A", "AR=AR-A", "描述=旧描述"], "SR-B", "AR-B", "新描述")

        self.assertEqual("SR-B", vars_["SR"])
        self.assertEqual("AR-B", vars_["AR"])
        self.assertEqual("新描述", vars_["描述"])

    def test_title_and_desc_aliases_fill_description(self) -> None:
        self.assertEqual("t", _parse_vars(["TITLE=t"], None, None, None)["描述"])
        self.assertEqual("d", _parse_vars(["DESC=d"], None, None, None)["描述"])

    def test_existing_description_wins_over_aliases(self) -> None:
        vars_ = _parse_vars(["描述=主描述", "TITLE=t", "DESC=d"], None, None, None)

        self.assertEqual("主描述", vars_["描述"])

    def test_value_may_contain_equals_sign(self) -> None:
        self.assertEqual("a=b", _parse_vars(["K=a=b"], None, None, None)["K"])


if __name__ == "__main__":
    unittest.main()
