"""
会话隔离标记（.sdd/.current_session）由 CLI 维护的测试。

背景：原设计中标记由 LLM 按 aaw-workflow SKILL.md 第 6 步手工写入，
改为 aaw start / aaw next 命令自动写入，保证确定性和跨平台一致性。
question-tracker MCP Server 读取该标记定位 .question_state.json。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AAW_SCRIPT = ROOT / "skills" / "aaw-workflow" / "scripts" / "aaw.py"
SCRIPTS_DIR = AAW_SCRIPT.parent
sys.path.insert(0, str(SCRIPTS_DIR))

from cli.workflow import write_session_marker  # noqa: E402

MARKER_REL = Path(".sdd") / ".current_session"


def run_cli(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(AAW_SCRIPT), *args],
        cwd=cwd,
        check=check,
        text=True,
        capture_output=True,
    )


def read_marker(cwd: Path) -> str:
    return (cwd / MARKER_REL).read_text("utf-8")


class SessionMarkerHelperTests(unittest.TestCase):
    """write_session_marker 辅助函数单元测试"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = Path(self.tmp.name)
        self._old_cwd = os.getcwd()
        os.chdir(self.cwd)

    def tearDown(self) -> None:
        os.chdir(self._old_cwd)
        self.tmp.cleanup()

    def test_writes_marker_with_exact_content(self) -> None:
        """写入标记，内容精确为 ./.sdd/<SR>/（单行、无引号、无尾随空格）"""
        write_session_marker(Path(".sdd"), "SR-001")

        self.assertEqual("./.sdd/SR-001/", read_marker(self.cwd))

    def test_creates_sdd_dir_if_missing(self) -> None:
        """.sdd 目录不存在时自动创建"""
        self.assertFalse((self.cwd / ".sdd").exists())

        write_session_marker(Path(".sdd"), "SR-002")

        self.assertTrue((self.cwd / MARKER_REL).is_file())

    def test_overwrites_existing_marker(self) -> None:
        """重复写入时覆盖旧值（切换 SR 场景）"""
        write_session_marker(Path(".sdd"), "SR-001")

        write_session_marker(Path(".sdd"), "SR-002")

        self.assertEqual("./.sdd/SR-002/", read_marker(self.cwd))


class SessionMarkerCliTests(unittest.TestCase):
    """CLI 命令对标记的维护行为"""

    def test_start_writes_marker(self) -> None:
        """aaw start 后标记指向该 SR"""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            run_cli(cwd, "start", "--entry", "sr", "--sr", "SR-001", "--json")

            self.assertEqual("./.sdd/SR-001/", read_marker(cwd))

    def test_start_ar_entry_writes_sr_scoped_marker(self) -> None:
        """AR 入口的 start 同样写标记，且指向 SR 目录（per-SR 隔离，非 per-AR）"""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            run_cli(
                cwd,
                "start", "--entry", "ar",
                "--sr", "SR-100", "--ar", "AR-001", "--title", "用户管理",
                "--json",
            )

            self.assertEqual("./.sdd/SR-100/", read_marker(cwd))

    def test_next_writes_marker(self) -> None:
        """aaw next 后标记指向该 SR（覆盖 start 之后的每次循环）"""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            run_cli(cwd, "start", "--entry", "sr", "--sr", "SR-001", "--json")
            (cwd / MARKER_REL).unlink(missing_ok=True)  # 删掉标记，验证 next 会重建

            run_cli(cwd, "next", "--sr", "SR-001", "--json")

            self.assertEqual("./.sdd/SR-001/", read_marker(cwd))

    def test_next_switches_marker_to_latest_sr(self) -> None:
        """多 SR 交错时，标记跟随最近一次 next 的 SR"""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            run_cli(cwd, "start", "--entry", "sr", "--sr", "SR-A", "--json")
            run_cli(cwd, "start", "--entry", "sr", "--sr", "SR-B", "--json")

            run_cli(cwd, "next", "--sr", "SR-A", "--json")

            self.assertEqual("./.sdd/SR-A/", read_marker(cwd))

    def test_failed_next_does_not_touch_marker(self) -> None:
        """next 的 SR 不存在（load 失败）时不得写入或破坏已有标记"""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            run_cli(cwd, "start", "--entry", "sr", "--sr", "SR-OK", "--json")
            before = read_marker(cwd)

            run_cli(cwd, "next", "--sr", "SR-MISSING", "--json", check=False)

            self.assertEqual(before, read_marker(cwd))

    def test_status_does_not_write_marker(self) -> None:
        """status 是只读巡检命令，不写标记"""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            run_cli(cwd, "start", "--entry", "sr", "--sr", "SR-001", "--json")
            (cwd / MARKER_REL).unlink(missing_ok=True)

            run_cli(cwd, "status", "--sr", "SR-001", "--json")

            self.assertFalse((cwd / MARKER_REL).exists())

    def test_rollback_does_not_write_marker(self) -> None:
        """rollback 不写标记（与 done/status 同类，非子技能前置命令）"""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            run_cli(cwd, "start", "--entry", "sr", "--sr", "SR-001", "--json")
            (cwd / MARKER_REL).unlink(missing_ok=True)

            run_cli(cwd, "rollback", "--sr", "SR-001", "1", "--json")

            self.assertFalse((cwd / MARKER_REL).exists())

    def test_done_does_not_write_marker(self) -> None:
        """done 不写标记（done 后必然紧跟 next，由 next 维护）"""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            run_cli(cwd, "start", "--entry", "sr", "--sr", "SR-001", "--json")
            (cwd / ".sdd" / "software_architecture.md").write_text("architecture", "utf-8")
            (cwd / MARKER_REL).unlink(missing_ok=True)

            run_cli(cwd, "done", "--sr", "SR-001", "1", "--json")

            self.assertFalse((cwd / MARKER_REL).exists())

    def test_repeated_next_is_idempotent(self) -> None:
        """同一 SR 连续多次 next，标记内容稳定不损坏"""
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path(tmp)
            run_cli(cwd, "start", "--entry", "sr", "--sr", "SR-001", "--json")

            run_cli(cwd, "next", "--sr", "SR-001", "--json")
            first = read_marker(cwd)
            run_cli(cwd, "next", "--sr", "SR-001", "--json")

            self.assertEqual(first, read_marker(cwd))


if __name__ == "__main__":
    unittest.main()
