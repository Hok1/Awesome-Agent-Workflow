"""Digest the scoring inputs at publication and verify them before every assessment."""

from aaw_skill_eval.infrastructure.storage.artifacts import content_hash

FILES = ("terminal-evidence.json", "deterministic.json", "run.json", "compliance.json")


def artifact_hash(root):
    return content_hash({name: (root / name).read_text(encoding="utf-8") for name in FILES})
