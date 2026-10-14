"""Build a portable candidate from the actual checkout, rather than copying stale vendors."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

DEPENDENCIES = (
    "aaw-workflow",
    "repo-init",
    "sr-design",
    "sr-design-gate",
    "ar-clarify",
    "module-boundary-design",
    "module-asis-analysis",
    "module-tobe-design",
    "module-design-gate",
    "dev-design",
    "dev-design-gate",
    "module-test-design",
    "task-split",
    "task-dev",
    "code-check",
    "effective-document-writing",
    "mermaid-diagram",
    "module-deep-research",
    "question-tracker-mcp",
)


def build_workflow_adapter(repository: Path, destination: Path) -> Path:
    repository, destination = repository.resolve(), destination.resolve()
    if destination.exists():
        raise ValueError("适配包输出目录已存在；请使用新目录保留候选版本")
    sources = [repository / "skills" / name for name in DEPENDENCIES]
    if any(not source.is_dir() for source in sources):
        raise ValueError("当前仓库缺少 AAW 工作流依赖目录")
    for source in sources:
        if any(p.is_symlink() for p in source.rglob("*")):
            raise ValueError("依赖目录不能包含符号链接")
    template = Path(__file__).resolve().parents[2] / "resources/aaw-workflow-eval.md"
    destination.mkdir(parents=True)
    shutil.copyfile(template, destination / "SKILL.md")
    vendor = destination / "vendor"
    vendor.mkdir()
    for source in sources:
        shutil.copytree(
            source,
            vendor / source.name,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git", ".venv"),
        )
    manifest = {}
    for file in sorted(vendor.rglob("*")):
        if file.is_file():
            manifest[file.relative_to(destination).as_posix()] = hashlib.sha256(
                file.read_bytes()
            ).hexdigest()
    (destination / "dependency-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return destination
