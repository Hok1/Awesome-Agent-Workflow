import zipfile
from pathlib import Path

from aaw_skill_eval.contracts.schemas import CaseSpec


def _inside(workspace: Path, path: str) -> Path:
    candidate = (workspace / path).resolve()
    if not candidate.is_relative_to(workspace.resolve()):
        raise ValueError("证据路径超出工作区")
    return candidate


def collect_terminal_outputs(
    workspace: Path, case: CaseSpec, changed: list[str], artifact_dir: Path
) -> dict:
    """Archive terminal files even when ignored by Git; give the judge a bounded text view."""
    paths = list(case.output_paths)
    if case.workflow:
        root = workspace / ".sdd"
        if root.is_dir():
            paths += [
                p.relative_to(workspace).as_posix() for p in sorted(root.rglob("*")) if p.is_file()
            ]
    paths += changed
    outputs, inventory = {}, []
    budget = 240_000
    archived_bytes = 0
    with zipfile.ZipFile(
        artifact_dir / "terminal-outputs.zip", "w", zipfile.ZIP_DEFLATED
    ) as archive:
        for relative in dict.fromkeys(paths):
            try:
                candidate = _inside(workspace, relative)
                if not candidate.is_file():
                    continue
                size = candidate.stat().st_size
                archived = size <= 5_000_000 and archived_bytes + size <= 50_000_000
                if archived:
                    archive.write(candidate, relative)
                    archived_bytes += size
                inventory.append({"path": relative, "size": size, "archived": archived})
                if budget > 0:
                    with candidate.open("rb") as stream:
                        raw = stream.read(min(budget, 30_000))
                        if b"\0" in raw:
                            continue
                        content = raw.decode("utf-8", errors="replace")
                    outputs[relative] = content
                    budget -= len(content)
            except (OSError, UnicodeError, ValueError):
                continue
    return {"output_files": outputs, "terminal_inventory": inventory}
