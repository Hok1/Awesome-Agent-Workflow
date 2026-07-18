"""Process bootstrap: install-level shared lock + residue recovery.

Runs from aaw.py BEFORE cli.main (and typer/business modules) are imported,
so module import, definitions reads and workflow writes can never overlap
with another process's directory swap (docs/auto-update-design.md §4.3).
This module only depends on the update infrastructure (install_lock/update),
never on CLI business modules.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from .install_lock import InstallLock, LockTimeout, set_active_lock
from .update import preflight_recover, UpdateError


def _die(message: str, code: int) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def startup(entry_file: str) -> None:
    """Acquire the shared install lock (held until process exit) and recover
    local transaction residue.  Exits on failure -- a command must not run
    against an install that is mid-swap or unrecoverable."""
    skills_root = Path(os.path.abspath(entry_file)).parents[2]
    try:
        lock = InstallLock(skills_root)
    except OSError as e:
        _die(f"aaw: 无法打开安装锁 {skills_root / '.aaw-update.lock'}: {e}", 1)
    try:
        lock.acquire_shared()
    except LockTimeout:
        _die("aaw: 另一个更新/恢复进程正在执行，30 秒内未完成；稍后重试", 1)
    try:
        preflight_recover(skills_root, lock, lambda m: print(m, file=sys.stderr))
    except LockTimeout:
        _die("aaw: 等待独占安装锁恢复残留事务超时；稍后重试", 1)
    except UpdateError as e:
        hint = f"\n  {e.hint}" if e.hint else ""
        _die(f"aaw: {e.message}{hint}", 2)
    set_active_lock(lock)
