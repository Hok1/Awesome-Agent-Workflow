"""Transactional self-update from the telemetry server (auto + manual).

Design: docs/auto-update-design.md.  `aaw start` queries the latest release
first thing on entry (after local residue recovery) and auto-updates the full
skill package before any workflow state is touched; `aaw update` is the
explicit manual entry sharing the same pipeline.

Concurrency model (§4.3): every CLI command holds an install-level shared
lock for its lifetime.  An updater downloads and stages under the shared
lock inside its private `.aaw-stage-<id>/` workspace, then upgrades to the
exclusive lock, re-reads the local version, persists the write-ahead
transaction manifest inside the stage, atomically renames it to
`.aaw-txn-<id>/` and performs the swap.  Any failure either leaves the
install untouched or is rolled back / recoverable via the generated
recover.py.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import stat
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml

from .install_lock import InstallLock, LockTimeout, get_active_lock
from .version import FALLBACK_VERSION, is_newer, parse_version

TX_PREFIX = ".aaw-txn-"
STAGE_PREFIX = ".aaw-stage-"
HANDOFF_PREFIX = ".aaw-handoff-"
MANIFEST_NAME = "transaction.json"
RELEASE_MANIFEST = "release-manifest.json"
QUERY_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 30  # connect + each blocking read; no total-duration cap

HANDOFF_PATH_ENV = "AAW_UPDATE_HANDOFF"
HANDOFF_TOKEN_ENV = "AAW_UPDATE_HANDOFF_TOKEN"


class UpdateError(Exception):
    def __init__(self, message: str, hint: str = "", fatal: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        # fatal: the install may be inconsistent (rollback failed, lock lost,
        # broken handoff) -- callers must not continue `start`.
        self.fatal = fatal


# ---------------------------------------------------------------------------
# location & guards
# ---------------------------------------------------------------------------

def install_paths(install_dir: Path | None = None) -> tuple[Path, Path]:
    """Return (skill_dir, skills_root) for the running CLI.

    Lexical absolutisation only: fold the possibly-relative __file__ against
    the startup CWD without resolving symlinks (docs §4.3).
    """
    if install_dir is not None:
        skill_dir = Path(os.path.abspath(install_dir))
    else:
        skill_dir = Path(os.path.abspath(__file__)).parents[2]
    return skill_dir, skill_dir.parent


def _read_local_version(skill_dir: Path) -> str:
    """VERSION of the install being updated; a corrupted or partially
    recovered install reads as the lowest version so it can be repaired."""
    try:
        text = (skill_dir / "scripts" / "cli" / "VERSION").read_text("utf-8").strip()
    except OSError:
        return FALLBACK_VERSION
    return text or FALLBACK_VERSION


def _is_reparse_point(path: Path) -> bool:
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    if os.name == "nt":
        attributes = getattr(st, "st_file_attributes", 0)
        if attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            return True
    return False


def _guard_no_reparse(skill_dir: Path, skills_root: Path) -> None:
    """Reject when any level from the cli package up to the skills root is a
    symlink / junction / reparse point: renames would write through to a
    redirected location (e.g. the source repository)."""
    probes = [skill_dir / "scripts" / "cli", skill_dir / "scripts", skill_dir, skills_root]
    for probe in probes:
        if _is_reparse_point(probe):
            raise UpdateError(
                f"安装路径包含链接目录: {probe}",
                "链接式安装请到源仓库执行 git pull 更新",
            )


def _guard_targets_no_reparse(skills_root: Path, managed: list[str]) -> None:
    """lstat every existing managed target; any link/junction rejects the
    whole update (docs §4.4 step 5)."""
    for name in managed:
        target = skills_root / name
        if target.exists() or target.is_symlink():
            if _is_reparse_point(target):
                raise UpdateError(f"更新目标是链接目录: {target}", "已中止，未触碰安装")


# ---------------------------------------------------------------------------
# release manifest
# ---------------------------------------------------------------------------

def _validate_skill_name(name: object) -> str:
    if not isinstance(name, str) or not name or name in (".", ".."):
        raise UpdateError(f"发布清单包含非法 Skill 名称: {name!r}", "该发布包不可信，已中止")
    if "/" in name or "\\" in name or ":" in name or name.startswith("."):
        raise UpdateError(f"发布清单包含非法 Skill 名称: {name!r}", "该发布包不可信，已中止")
    return name


def _load_release_manifest(stage: Path) -> dict:
    path = stage / RELEASE_MANIFEST
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError) as e:
        raise UpdateError(f"发布包缺少或损坏 {RELEASE_MANIFEST}: {e}", "该发布包不可信，已中止")
    if not isinstance(data, dict):
        raise UpdateError(f"{RELEASE_MANIFEST} 结构非法", "该发布包不可信，已中止")
    lists: dict[str, list[str]] = {}
    for key in ("skills", "external_skills", "removed_skills"):
        raw = data.get(key, [])
        if not isinstance(raw, list):
            raise UpdateError(f"{RELEASE_MANIFEST} 的 {key} 必须是列表", "该发布包不可信，已中止")
        names = [_validate_skill_name(item) for item in raw]
        if len(names) != len(set(names)):
            raise UpdateError(f"{RELEASE_MANIFEST} 的 {key} 存在重复名称", "该发布包不可信，已中止")
        lists[key] = names
    seen: set[str] = set()
    for key, names in lists.items():
        overlap = seen & set(names)
        if overlap:
            raise UpdateError(
                f"{RELEASE_MANIFEST} 列表交叉: {sorted(overlap)}", "该发布包不可信，已中止"
            )
        seen |= set(names)
    version = data.get("version")
    if not isinstance(version, str) or parse_version(version) is None:
        raise UpdateError(f"{RELEASE_MANIFEST} 版本非法: {version!r}", "该发布包不可信，已中止")
    return {"version": version, **lists}


def _definition_skill_refs(defs_dir: Path) -> set[str]:
    """Skill names referenced by the bundled definitions (same semantics as
    scripts/make_release.py and cli.models.normalize_skill)."""
    refs: set[str] = set()
    if not defs_dir.is_dir():
        return refs
    for path in sorted(defs_dir.rglob("*.yaml")):
        if path.name == "flow.yaml":
            continue
        try:
            raw = yaml.safe_load(path.read_text("utf-8")) or {}
        except yaml.YAMLError as e:
            raise UpdateError(f"发布包 definitions 解析失败: {path.name}: {e}", "该发布包不可信，已中止")
        skill = raw.get("skill") if isinstance(raw, dict) else None
        items = [skill] if isinstance(skill, str) else skill if isinstance(skill, list) else []
        for item in items:
            if isinstance(item, str) and item.strip():
                refs.add(item.strip())
    return refs


# ---------------------------------------------------------------------------
# server API
# ---------------------------------------------------------------------------

def _endpoint() -> str:
    from .telemetry import DEFAULT_ENDPOINT

    return (os.environ.get("AAW_TELEMETRY_ENDPOINT") or DEFAULT_ENDPOINT).rstrip("/")


def query_latest(endpoint: str | None = None, timeout: float = QUERY_TIMEOUT) -> dict:
    base = (endpoint or _endpoint()).rstrip("/")
    request = Request(base + "/api/v1/client/release", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, HTTPError, ValueError) as e:
        raise UpdateError(f"查询最新版本失败: {e}", "检查网络与 AAW_TELEMETRY_ENDPOINT 后重试")
    return data if isinstance(data, dict) else {}


def _download(endpoint: str, version: str, file_name: str, size_bytes: int, target: Path) -> None:
    url = f"{endpoint}/api/v1/client/releases/{version}/download/{file_name}"
    try:
        with urlopen(Request(url), timeout=DOWNLOAD_TIMEOUT) as response, open(target, "wb") as out:
            shutil.copyfileobj(response, out)
    except (OSError, URLError, HTTPError) as e:
        raise UpdateError(f"下载发布包失败: {e}", "检查网络后重试")
    actual = target.stat().st_size
    if actual != size_bytes:
        raise UpdateError(
            f"下载不完整: 收到 {actual} 字节，期望 {size_bytes} 字节", "检查网络后重试"
        )


# ---------------------------------------------------------------------------
# staging: unzip + sanity
# ---------------------------------------------------------------------------

def _extract_zip(archive: Path, payload: Path) -> None:
    """Extract with zip-slip protection."""
    payload.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                name = member.filename.replace("\\", "/")
                parts = [p for p in name.split("/") if p not in ("", ".")]
                if not parts:
                    continue
                if ".." in parts or name.startswith("/") or ":" in parts[0]:
                    raise UpdateError(f"发布包含非法路径条目: {member.filename}", "该发布包不可信，已中止")
                destination = payload.joinpath(*parts)
                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as src, open(destination, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    except zipfile.BadZipFile as e:
        raise UpdateError(f"发布包损坏: {e}", "重新执行 aaw update 下载")


def _sanity_check(stage: Path, manifest: dict, latest_version: str, skills_root: Path) -> None:
    payload = stage / "payload"
    skills = manifest["skills"]
    top_dirs = sorted(p.name for p in payload.iterdir() if p.is_dir())
    top_files = sorted(p.name for p in payload.iterdir() if not p.is_dir())
    if top_files:
        raise UpdateError(f"发布包顶层包含多余文件: {top_files}", "该发布包不可信，已中止")
    if top_dirs != sorted(skills):
        raise UpdateError(
            f"发布包顶层目录与清单不一致: 包内 {top_dirs}，清单 {sorted(skills)}",
            "该发布包不可信，已中止",
        )
    for name in skills:
        if not (payload / name / "SKILL.md").is_file():
            raise UpdateError(f"发布包中 {name} 缺少 SKILL.md", "该发布包不可信，已中止")
    if "aaw-workflow" not in skills:
        raise UpdateError("发布包缺少 aaw-workflow 本体", "该发布包不可信，已中止")
    workflow = payload / "aaw-workflow"
    if not (workflow / "scripts" / "aaw.py").is_file():
        raise UpdateError("发布包缺少 scripts/aaw.py 入口", "该发布包不可信，已中止")
    version_file = workflow / "scripts" / "cli" / "VERSION"
    if not version_file.is_file():
        raise UpdateError("发布包缺少 scripts/cli/VERSION", "该发布包不可信，已中止")
    packaged = version_file.read_text("utf-8").strip()
    if parse_version(packaged) is None or parse_version(latest_version) is None:
        raise UpdateError(f"版本号不合法: 包内 {packaged!r} / 服务端 {latest_version!r}", "已中止")
    if not (packaged == latest_version == manifest["version"]):
        raise UpdateError(
            f"版本不一致: 包内 VERSION {packaged}, manifest {manifest['version']}, "
            f"服务端 {latest_version}",
            "该发布包不可信，已中止",
        )
    allowed = set(skills) | set(manifest["external_skills"])
    unknown = _definition_skill_refs(workflow / "scripts" / "cli" / "definitions") - allowed
    if unknown:
        raise UpdateError(
            f"发布包 definitions 引用了未声明的 Skill: {sorted(unknown)}",
            "该发布包不可信，已中止",
        )
    for name in manifest["external_skills"]:
        if not (skills_root / name / "SKILL.md").is_file():
            raise UpdateError(
                f"扩展 Skill {name} 在当前安装中不存在，换入后 workflow 将无法执行",
                "先安装该 Skill 或使用不依赖它的版本",
            )
    _guard_targets_no_reparse(skills_root, skills + manifest["removed_skills"])


# ---------------------------------------------------------------------------
# transaction (write-ahead manifest + renames)
# ---------------------------------------------------------------------------

def _write_json_fsync(target: Path, data: dict) -> None:
    """Atomic durable write: tmp + flush + fsync -> os.replace (+ dir fsync
    on POSIX; os.fsync is FlushFileBuffers on Windows)."""
    tmp = target.with_name(target.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, target)
    if os.name != "nt":
        fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _write_manifest(tx_dir: Path, manifest: dict) -> None:
    _write_json_fsync(tx_dir / MANIFEST_NAME, manifest)


def _remove_tree(path: Path) -> None:
    def _on_error(func, target, _exc):  # pragma: no cover - windows read-only fallback
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if path.exists():
        shutil.rmtree(path, onerror=_on_error)


def _rename_step(manifest: dict, tx_dir: Path, key: str, source: Path, target: Path) -> None:
    """WAL rename: persist intent, rename, persist completion."""
    manifest["steps"][key] = "started"
    _write_manifest(tx_dir, manifest)
    source.rename(target)
    manifest["steps"][key] = "done"
    _write_manifest(tx_dir, manifest)


def _managed_names(manifest: dict) -> list[str]:
    return list(manifest.get("skills", [])) + list(manifest.get("removed_skills", []))


def recover_transaction(tx_dir: Path) -> str:
    """Restore a clean state from a transaction directory.  Reentrant.

    Returns "committed" (new version kept, residue cleaned) or "rolled-back"
    (all old managed dirs restored).  Directory-existence beats manifest step
    state: a rename may have succeeded right before its completion record was
    lost."""
    manifest = json.loads((tx_dir / MANIFEST_NAME).read_text("utf-8"))
    skills_root = Path(manifest["skills_root"])
    committed = manifest.get("phase") == "committed"
    if not committed:
        displaced_root = tx_dir / "displaced"
        for name in _managed_names(manifest):
            official = skills_root / name
            backup = tx_dir / "backup" / name
            if not backup.is_dir():
                continue  # never backed up: official copy is still the old one
            if official.exists():
                # official position holds a swapped-in new copy: displace it
                displaced_root.mkdir(parents=True, exist_ok=True)
                slot = displaced_root / name
                while slot.exists():
                    slot = displaced_root / f"{name}-{secrets.token_hex(4)}"
                official.rename(slot)
            backup.rename(official)
    _remove_tree(tx_dir)
    return "committed" if committed else "rolled-back"


def find_residual_transactions(skills_root: Path) -> list[Path]:
    """`.aaw-txn-*` directories with a manifest.  `.aaw-stage-*` workspaces
    are deliberately excluded: they never touch the live install and belong
    to a possibly-live concurrent updater."""
    return sorted(
        p for p in skills_root.iterdir()
        if p.is_dir() and p.name.startswith(TX_PREFIX) and (p / MANIFEST_NAME).exists()
    )


def recover_all_residue(skills_root: Path, out) -> None:
    """Must be called under the exclusive lock."""
    for leftover in sorted(skills_root.iterdir()):
        if not leftover.is_dir() or not leftover.name.startswith(TX_PREFIX):
            continue
        if (leftover / MANIFEST_NAME).exists():
            state = recover_transaction(leftover)
            out(f"已处理残留更新事务 {leftover.name}: {state}")
        else:
            # a recovery interrupted mid-cleanup: manifest already gone
            _remove_tree(leftover)


def preflight_recover(skills_root: Path, lock: InstallLock, out) -> None:
    """Residue pre-check for every command (docs §4.4 step 0).

    Runs under the caller's shared lock; when residue is found, upgrades to
    the exclusive lock, re-scans, recovers, then downgrades back to shared.
    Raises LockTimeout / UpdateError(fatal); callers must not continue."""
    if not find_residual_transactions(skills_root):
        return
    lock.release()
    lock.acquire_exclusive()
    try:
        recover_all_residue(skills_root, out)
    except Exception as e:
        raise UpdateError(f"残留更新事务恢复失败: {e}", "请检查安装目录后重试", fatal=True)
    finally:
        lock.release()
        lock.acquire_shared()


_RECOVER_SCRIPT = '''\
"""Standalone recovery for an interrupted aaw update transaction.

Usage: python recover.py [--assume-locked]
Depends only on the standard library and transaction.json; never imports the
CLI being updated.  Reentrant: rerunning after another interruption is safe.
"""
import json, os, secrets, shutil, stat, sys, time

from pathlib import Path

TX_DIR = Path(os.path.abspath(__file__)).parent


def _remove_tree(path):
    def _on_error(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)
    if path.exists():
        shutil.rmtree(path, onerror=_on_error)


def _acquire_exclusive(lock_path, timeout=30.0):
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.monotonic() + timeout
    if os.name == "nt":
        import ctypes, msvcrt
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class OVERLAPPED(ctypes.Structure):
            _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p),
                        ("Offset", wintypes.DWORD), ("OffsetHigh", wintypes.DWORD),
                        ("hEvent", wintypes.HANDLE)]

        handle = msvcrt.get_osfhandle(fd)
        while True:
            if kernel32.LockFileEx(wintypes.HANDLE(handle), 0x3, 0, 1, 0,
                                   ctypes.byref(OVERLAPPED())):
                return fd
            if time.monotonic() >= deadline:
                print("另一个更新/恢复进程正在执行，稍后重试", file=sys.stderr)
                sys.exit(1)
            time.sleep(0.15)
    else:
        import fcntl
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except OSError:
                if time.monotonic() >= deadline:
                    print("另一个更新/恢复进程正在执行，稍后重试", file=sys.stderr)
                    sys.exit(1)
                time.sleep(0.15)


def main():
    manifest = json.loads((TX_DIR / "transaction.json").read_text("utf-8"))
    skills_root = Path(manifest["skills_root"])
    if "--assume-locked" not in sys.argv:
        _acquire_exclusive(skills_root / ".aaw-update.lock")
    committed = manifest.get("phase") == "committed"
    managed = list(manifest.get("skills", [])) + list(manifest.get("removed_skills", []))
    if not committed:
        for name in managed:
            official = skills_root / name
            backup = TX_DIR / "backup" / name
            if not backup.is_dir():
                continue
            if official.exists():
                displaced = TX_DIR / "displaced"
                displaced.mkdir(parents=True, exist_ok=True)
                slot = displaced / name
                while slot.exists():
                    slot = displaced / (name + "-" + secrets.token_hex(4))
                official.rename(slot)
            backup.rename(official)
    _remove_tree(TX_DIR)
    print("已恢复: " + ("保留新版本 (committed)" if committed else "回滚到旧版本"))


if __name__ == "__main__":
    main()
'''


# ---------------------------------------------------------------------------
# update flow (shared by `aaw update` and `aaw start` auto-update)
# ---------------------------------------------------------------------------

def _stderr(message: str) -> None:
    print(message, file=sys.stderr)


def _to_shared(lock: InstallLock) -> None:
    """Downgrade exclusive -> shared; failure means another process holds the
    install exclusively and we must not continue."""
    if lock.mode == "exclusive":
        lock.release()
        try:
            lock.acquire_shared()
        except LockTimeout:
            raise UpdateError(
                "安装锁被其他更新进程占用，无法恢复共享访问", "稍后重试", fatal=True
            )


def _perform_update(
    skill_dir: Path,
    skills_root: Path,
    lock: InstallLock,
    latest: str,
    file_name: str,
    size_bytes: int,
    base: str,
    out,
) -> dict | None:
    """Stage under the shared lock, upgrade to exclusive, swap (docs §4.4).

    Enters with `lock` held shared.  Returns the result dict (lock held
    exclusive), or None when after the lock upgrade the install already
    reached `latest` (lock held exclusive, stage removed).  On non-fatal
    failure the lock is back to shared and UpdateError is raised;
    fatal=True means the install may be inconsistent."""
    _guard_no_reparse(skill_dir, skills_root)

    tx_id = secrets.token_hex(8)
    stage = skills_root / f"{STAGE_PREFIX}{tx_id}"
    stage.mkdir()
    try:
        archive = stage / file_name
        _download(base, latest, file_name, size_bytes, archive)
        payload = stage / "payload"
        _extract_zip(archive, payload)
        bundled_manifest = payload / RELEASE_MANIFEST
        if bundled_manifest.is_file():
            bundled_manifest.rename(stage / RELEASE_MANIFEST)
        release = _load_release_manifest(stage)
        _sanity_check(stage, release, latest, skills_root)
        archive.unlink(missing_ok=True)
    except BaseException:
        _remove_tree(stage)  # only our own exact stage path, never a glob
        raise

    # upgrade shared -> exclusive
    lock.release()
    try:
        lock.acquire_exclusive()
    except LockTimeout:
        _remove_tree(stage)
        try:
            lock.acquire_shared()
        except LockTimeout:
            raise UpdateError("安装锁等待超时，且无法恢复共享访问", "稍后重试", fatal=True)
        raise UpdateError("等待独占安装锁超时", "另一进程可能正在更新，稍后重试")

    try:
        recover_all_residue(skills_root, out)
    except Exception as e:
        _remove_tree(stage)
        raise UpdateError(f"残留更新事务恢复失败: {e}", "请检查安装目录后重试", fatal=True)

    # another updater may have swapped while we waited for the lock
    current = _read_local_version(skill_dir)
    if not is_newer(latest, current):
        _remove_tree(stage)
        return None

    skills = release["skills"]
    removed = release["removed_skills"]
    managed = skills + removed
    try:
        _guard_targets_no_reparse(skills_root, managed)
    except UpdateError:
        _remove_tree(stage)
        _to_shared(lock)
        raise

    actually_removed = [n for n in removed if (skills_root / n).exists()]
    manifest = {
        "schema": 2,
        "tx_id": tx_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "skills_root": str(skills_root),
        "lock_path": str(lock.path),
        "latest_version": latest,
        "skills": skills,
        "removed_skills": removed,
        "phase": "staged",
        "steps": {},
    }
    tx_dir = skills_root / f"{TX_PREFIX}{tx_id}"
    try:
        # persist the WAL inside the stage BEFORE it becomes a visible .aaw-txn-*
        _write_manifest(stage, manifest)
        (stage / "recover.py").write_text(_RECOVER_SCRIPT, "utf-8")
        stage.rename(tx_dir)
    except OSError as e:
        _remove_tree(stage)
        _to_shared(lock)
        raise UpdateError(f"创建更新事务失败: {e}", "稍后重试")

    out(f"如更新被中断，运行: python {tx_dir / 'recover.py'} 恢复现场")
    try:
        backup = tx_dir / "backup"
        backup.mkdir()
        manifest["phase"] = "backup"
        for name in managed:
            official = skills_root / name
            if official.exists():
                _rename_step(manifest, tx_dir, f"backup:{name}", official, backup / name)
        manifest["phase"] = "swap"
        for name in skills:
            _rename_step(manifest, tx_dir, f"swap:{name}", tx_dir / "payload" / name, skills_root / name)

        # pre-commit verification from the official location
        manifest["phase"] = "verify"
        _write_manifest(tx_dir, manifest)
        landed = skills_root / "aaw-workflow" / "scripts" / "cli" / "VERSION"
        landed_version = landed.read_text("utf-8").strip() if landed.is_file() else None
        if landed_version != latest:
            raise UpdateError(f"换入后版本校验失败: {landed_version!r} != {latest!r}", "已回滚")
        for name in skills:
            if not (skills_root / name / "SKILL.md").is_file():
                raise UpdateError(f"换入后 {name} 缺少 SKILL.md", "已回滚")
        if not (skills_root / "aaw-workflow" / "scripts" / "aaw.py").is_file():
            raise UpdateError("换入后缺少 scripts/aaw.py 入口", "已回滚")
        for name in removed:
            if (skills_root / name).exists():
                raise UpdateError(f"换入后 removed skill {name} 仍存在", "已回滚")

        manifest["phase"] = "committed"
        _write_manifest(tx_dir, manifest)
    except (UpdateError, OSError) as e:
        try:
            recover_transaction(tx_dir)
        except Exception as rollback_error:  # noqa: BLE001
            raise UpdateError(
                f"更新失败: {e}；且自动回滚未完成: {rollback_error}",
                f"安装可能不一致，请运行: python {tx_dir / 'recover.py'} 恢复现场",
                fatal=True,
            )
        _to_shared(lock)
        if isinstance(e, UpdateError):
            raise
        raise UpdateError(
            f"更新失败: {e}", "可能有进程占用 skill 目录（关闭后重试）；现场已回滚"
        )
    _remove_tree(tx_dir)  # committed: drop backup + payload residue
    return {
        "status": "updated",
        "from_version": current,
        "to_version": latest,
        "updated_skills": skills,
        "removed_skills": actually_removed,
    }


def _obtain_lock(skills_root: Path, lock: InstallLock | None) -> tuple[InstallLock, bool]:
    """Use the caller's / process-wide shared lock, or create one (tests and
    direct invocation).  Returns (lock, owns)."""
    if lock is None:
        lock = get_active_lock()
    if lock is not None:
        return lock, False
    lock = InstallLock(skills_root)
    try:
        lock.acquire_shared()
    except LockTimeout:
        lock.close()
        raise UpdateError("另一个 aaw 更新/恢复进程正在执行", "稍后重试")
    return lock, True


def run_update(
    install_dir: Path | None = None,
    endpoint: str | None = None,
    out=None,
    lock: InstallLock | None = None,
) -> dict:
    """Manual `aaw update`: real-time query, then the staged swap transaction.

    Returns {"status": "up_to_date"|"updated", "from_version", "to_version",
    "updated_skills", "removed_skills"}.  Raises UpdateError on any failure
    (fatal=True -> recovery_required)."""
    out = out or _stderr
    skill_dir, skills_root = install_paths(install_dir)
    if not skills_root.is_dir():
        raise UpdateError(f"未找到 skills 目录: {skills_root}", "请重新安装")
    lock, owns = _obtain_lock(skills_root, lock)
    try:
        try:
            preflight_recover(skills_root, lock, out)
        except LockTimeout:
            raise UpdateError("等待独占安装锁超时，无法恢复残留事务", "稍后重试")

        current = _read_local_version(skill_dir)
        base = (endpoint or _endpoint()).rstrip("/")
        info = query_latest(base)
        latest = info.get("latest_version")
        if not isinstance(latest, str) or not is_newer(latest, current):
            return {
                "status": "up_to_date",
                "from_version": current,
                "to_version": current,
                "updated_skills": [],
                "removed_skills": [],
            }
        file_name = info.get("file_name")
        size_bytes = info.get("size_bytes")
        if not isinstance(file_name, str) or not file_name:
            raise UpdateError("服务端响应缺少 file_name", "稍后重试")
        if not isinstance(size_bytes, int) or size_bytes < 0:
            raise UpdateError("服务端响应缺少 size_bytes", "稍后重试")

        result = _perform_update(
            skill_dir, skills_root, lock, latest, file_name, size_bytes, base, out
        )
        if result is None:
            current = _read_local_version(skill_dir)
            return {
                "status": "up_to_date",
                "from_version": current,
                "to_version": current,
                "updated_skills": [],
                "removed_skills": [],
            }
        return result
    finally:
        try:
            _to_shared(lock)
        except UpdateError:
            pass
        if owns:
            lock.close()


# ---------------------------------------------------------------------------
# `aaw start` auto-update: query -> update -> handoff -> re-exec
# ---------------------------------------------------------------------------

def auto_update_on_start(
    argv: list[str],
    install_dir: Path | None = None,
    endpoint: str | None = None,
    out=None,
    lock: InstallLock | None = None,
) -> None:
    """First operation of `aaw start` after residue recovery (docs §4.2/§4.4).

    Returns to let `start` continue with the current local version (no newer
    release, or any recoverable failure -- reported as a stderr warning).  On
    a successful update this never returns: it writes a one-shot handoff file
    and re-executes the swapped-in aaw.py with the original argv.  Raises
    UpdateError only for fatal states: `start` must abort rather than create
    workflow state on an inconsistent install."""
    out = out or _stderr
    owns = False
    lock_ref: InstallLock | None = None
    try:
        skill_dir, skills_root = install_paths(install_dir)
        if not skills_root.is_dir():
            raise UpdateError(f"未找到 skills 目录: {skills_root}")
        lock, owns = _obtain_lock(skills_root, lock)
        lock_ref = lock

        try:
            preflight_recover(skills_root, lock, out)
        except LockTimeout:
            raise UpdateError(
                "等待独占安装锁超时，无法恢复残留事务", "稍后重试", fatal=True
            )

        current = _read_local_version(skill_dir)
        base = (endpoint or _endpoint()).rstrip("/")
        info = query_latest(base)
        latest = info.get("latest_version")
        if not isinstance(latest, str) or not is_newer(latest, current):
            if owns:
                lock.close()
            return
        file_name = info.get("file_name")
        size_bytes = info.get("size_bytes")
        if not isinstance(file_name, str) or not file_name:
            raise UpdateError("服务端响应缺少 file_name")
        if not isinstance(size_bytes, int) or size_bytes < 0:
            raise UpdateError("服务端响应缺少 size_bytes")

        out(f"发现 AAW 新版本 {latest}（当前 {current}），自动更新中...")
        result = _perform_update(
            skill_dir, skills_root, lock, latest, file_name, size_bytes, base, out
        )
    except UpdateError as e:
        if e.fatal:
            raise
        if lock_ref is not None and lock_ref.mode == "exclusive":
            _to_shared(lock_ref)  # fatal UpdateError propagates
        if owns and lock_ref is not None:
            lock_ref.close()
        out(f"aaw update warning: {e.message}，使用当前版本继续")
        return

    # updated by us, or by a concurrent updater while we waited for the lock:
    # either way this process has old modules imported and must re-exec.
    if result is None:
        target_version = _read_local_version(skill_dir)
        out(f"检测到安装已被并发更新到 {target_version}，重新执行 start")
    else:
        target_version = result["to_version"]
        out(f"更新完成: {result['from_version']} -> {target_version}，重新执行 start")
    _reexec_start(skills_root, argv, target_version, lock)


def _reexec_start(skills_root: Path, argv: list[str], target_version: str, lock: InstallLock) -> None:
    """Hand off to the swapped-in CLI without running any freshly-imported
    old-version code paths (docs §4.4 step 9).  Never returns on success."""
    token = secrets.token_hex(16)
    handoff = skills_root / f"{HANDOFF_PREFIX}{secrets.token_hex(8)}.json"
    handoff.write_text(
        json.dumps({
            "schema": 1,
            "token": token,
            "target_version": target_version,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }),
        "utf-8",
    )
    entry = skills_root / "aaw-workflow" / "scripts" / "aaw.py"
    args = [sys.executable, str(entry), *argv]
    env = {**os.environ, HANDOFF_PATH_ENV: str(handoff), HANDOFF_TOKEN_ENV: token}
    sys.stdout.flush()
    sys.stderr.flush()
    lock.release()  # explicit: the re-executed process takes its own shared lock
    try:
        if os.name == "nt":
            # Windows execv detaches the console/pipes from the caller's
            # perspective; run the new CLI as a child and mirror its exit code.
            completed = subprocess.run(args, env=env)
            raise SystemExit(completed.returncode)
        os.execve(sys.executable, args, env)
    except OSError as e:
        handoff.unlink(missing_ok=True)
        raise UpdateError(
            f"更新已完成，但 start 未执行: {e}",
            "请直接重跑原 start 命令（无需再次更新）",
            fatal=True,
        )


def consume_handoff(install_dir: Path | None = None) -> bool:
    """Consume the one-shot handoff in a re-executed `start` process.

    Returns True when a valid handoff was consumed (skip the server query and
    run the original start argv directly); False when this is a normal start.
    Raises UpdateError (fatal) on forged/replayed handoffs or when the local
    version did not reach the handoff target -- breaking re-exec loops."""
    path_raw = os.environ.pop(HANDOFF_PATH_ENV, None)
    token = os.environ.pop(HANDOFF_TOKEN_ENV, None)
    if not path_raw:
        return False
    path = Path(path_raw)
    claimed = path.with_name(path.name + f".consumed-{os.getpid()}")
    try:
        path.rename(claimed)  # atomic claim: a handoff is consumed exactly once
    except OSError:
        raise UpdateError(
            "更新交接文件缺失或已被消费",
            "请直接重跑原 start 命令",
            fatal=True,
        )
    try:
        data = json.loads(claimed.read_text("utf-8"))
    except (OSError, ValueError):
        data = None
    finally:
        try:
            claimed.unlink()
        except OSError:
            pass
    if not isinstance(data, dict) or not token or data.get("token") != token:
        raise UpdateError("更新交接文件校验失败", "请直接重跑原 start 命令", fatal=True)

    target = data.get("target_version")
    target_parts = parse_version(target) if isinstance(target, str) else None
    skill_dir, _ = install_paths(install_dir)
    current = _read_local_version(skill_dir)
    current_parts = parse_version(current) or (0, 0, 0)
    if target_parts is None or current_parts < target_parts:
        raise UpdateError(
            f"更新后版本校验失败: 本地 {current}，目标 {target}",
            "请运行 aaw update 或重新安装",
            fatal=True,
        )
    return True
