from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from urllib.parse import quote

from fastapi.responses import FileResponse

from aaw_skill_eval.config import Settings
from aaw_skill_eval.contracts.entities import Run
from aaw_skill_eval.errors import EvalError
from aaw_skill_eval.infrastructure.observability.logs import (
    MAX_LOG_READ_BYTES,
    display_record,
    read_log_index,
)

EVIDENCE_FILE_NAMES = {
    "changes.patch",
    "final-response.md",
    "scores.json",
    "input-and-rubric.json",
    "run.json",
}


TEXT_MEDIA_TYPES = {
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".patch": "text/x-diff",
    ".diff": "text/x-diff",
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".txt": "text/plain",
    ".log": "text/plain",
    ".yaml": "text/yaml",
    ".yml": "text/yaml",
    ".py": "text/plain",
    ".toml": "text/plain",
}


def _artifact_dir(settings: Settings, run: Run | None) -> Path:
    if run is None or not run.artifact_path:
        raise EvalError("RUN_NOT_FOUND", "Run or its artifacts were not found", status_code=404)
    artifact_dir = _safe_artifact_dir(settings, run.artifact_path)
    if artifact_dir is None:
        raise EvalError("ARTIFACT_NOT_FOUND", "Run artifacts were not found", status_code=404)
    return artifact_dir


def _judge_progress(settings: Settings, run: Run) -> dict:
    root = _safe_artifact_dir(
        settings, getattr(run, "assessment_artifact_path", None) or run.artifact_path
    )
    try:
        return (
            json.loads((root / "judge-progress.json").read_text(encoding="utf-8")) if root else {}
        )
    except (OSError, ValueError):
        return {}


def _safe_artifact_dir(settings: Settings, raw_path: str | None) -> Path | None:
    if not raw_path:
        return None
    root = settings.artifacts_dir.resolve()
    artifact_dir = Path(raw_path).resolve()
    if not artifact_dir.is_relative_to(root) or not artifact_dir.is_dir():
        return None
    return artifact_dir


def _run_output_bytes(settings: Settings, run: Run) -> dict[str, int]:
    artifact_dir = _safe_artifact_dir(settings, run.artifact_path)
    if artifact_dir is None:
        return {"stdout": 0, "stderr": 0}
    root = artifact_dir / "judge" if run.current_stage == "judge" else artifact_dir
    stdout = [*root.glob("chrys-turn-*.json"), *root.glob("*.jsonl"), *root.glob("*.stdout.txt")]
    stderr = list(root.glob("*.stderr.txt"))
    return {
        "stdout": sum(path.stat().st_size for path in stdout if path.is_file()),
        "stderr": sum(path.stat().st_size for path in stderr if path.is_file()),
    }


def _attempt_artifact_dir(settings: Settings, run: Run, attempt: int | None) -> Path | None:
    if attempt is None or attempt == run.current_attempt:
        return _safe_artifact_dir(settings, run.artifact_path)
    for previous in run.attempts:
        if previous.attempt_index == attempt:
            return _safe_artifact_dir(settings, previous.artifact_path)
    raise EvalError("ATTEMPT_NOT_FOUND", "Run attempt was not found", status_code=404)


def _attempt_dirs(settings: Settings, run: Run) -> list[tuple[int, Path]]:
    """All attempt artifact directories (oldest first), current attempt included."""
    found: list[tuple[int, Path]] = []
    seen: set[Path] = set()
    for attempt in sorted(run.attempts, key=lambda item: item.attempt_index):
        artifact_dir = _safe_artifact_dir(settings, attempt.artifact_path)
        if artifact_dir is not None and artifact_dir not in seen:
            seen.add(artifact_dir)
            found.append((attempt.attempt_index, artifact_dir))
    current = _safe_artifact_dir(settings, run.artifact_path)
    if current is not None and current not in seen:
        found.append((run.current_attempt, current))
    return sorted(found, key=lambda item: item[0])


def _csv_filter(value: str | None) -> set[str] | None:
    if value is None or not value.strip():
        return None
    return {item.strip() for item in value.split(",") if item.strip()}


def _log_stream_payload(
    path: Path,
    *,
    cursor: str | None,
    channels: str | None,
    sources: str | None,
    mode: str,
    unmasked: bool,
    limit_bytes: int,
) -> dict:
    if mode not in {"events", "raw"}:
        raise EvalError("INVALID_LOG_MODE", "Log mode must be events or raw")
    payload = read_log_index(
        path,
        cursor=cursor,
        limit_bytes=min(max(limit_bytes, 1), MAX_LOG_READ_BYTES),
    )
    channel_filter = _csv_filter(channels)
    source_filter = _csv_filter(sources)
    records = []
    for record in payload.pop("records"):
        if channel_filter is not None and record.get("channel") not in channel_filter:
            continue
        if source_filter is not None and record.get("source") not in source_filter:
            continue
        records.append(display_record(record, mode=mode, unmasked=unmasked and mode == "raw"))
    return {**payload, "records": records, "mode": mode}


def _media_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in TEXT_MEDIA_TYPES:
        base = TEXT_MEDIA_TYPES[suffix]
        return f"{base}; charset=utf-8" if base.startswith("text/") else base
    guessed = mimetypes.guess_type(path.name)[0]
    if guessed and guessed.startswith("text/"):
        return f"{guessed}; charset=utf-8"
    return guessed or "application/octet-stream"


def _is_log_file(path: Path) -> bool:
    if path.parent.name == "invocations" and path.name.endswith(".prompt.txt"):
        return True
    if path.name in EVIDENCE_FILE_NAMES:
        return True
    return path.name.endswith((".jsonl", ".stderr.txt", ".stdout.txt")) or path.name.startswith(
        "chrys-turn-"
    )


def _legacy_log_items(artifact_dir: Path | None, tail: int) -> list[dict]:
    if artifact_dir is None:
        return []
    tail = min(max(tail, 20), 5000)
    candidates = [path for path in artifact_dir.rglob("*") if path.is_file() and _is_log_file(path)]
    items = []
    for path in sorted(candidates, key=lambda item: (item.stat().st_mtime, item.name)):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        items.append(
            {
                "name": str(path.relative_to(artifact_dir)),
                "content": "\n".join(lines[-tail:]),
                "truncated": len(lines) > tail,
            }
        )
    return items


def _log_file_items(root: Path, url_prefix: str, *, suffix: str = "") -> list[dict]:
    if not root.is_dir():
        return []
    candidates = [path for path in root.rglob("*") if path.is_file() and _is_log_file(path)]
    return [
        {
            "name": path.relative_to(root).as_posix(),
            "size": path.stat().st_size,
            "url": f"{url_prefix}/{quote(path.relative_to(root).as_posix())}{suffix}",
        }
        for path in sorted(candidates, key=lambda item: item.relative_to(root).as_posix())
    ]


def _log_file_path(root: Path, name: str) -> Path:
    base = root.resolve()
    path = (base / name).resolve()
    if not path.is_relative_to(base) or not path.is_file() or not _is_log_file(path):
        raise EvalError("LOG_FILE_NOT_FOUND", "Log file was not found", status_code=404)
    return path


def _log_file_preview(root: Path, name: str, *, unmasked: bool) -> dict:
    path = _log_file_path(root, name)
    size = path.stat().st_size
    with path.open("rb") as stream:
        if size > MAX_LOG_READ_BYTES:
            stream.seek(size - MAX_LOG_READ_BYTES)
        content = stream.read(MAX_LOG_READ_BYTES).decode("utf-8", "replace")
    return {
        "name": name,
        "content": display_record({"text": content}, mode="raw", unmasked=unmasked)["text"],
        "size": size,
        "truncated": size > MAX_LOG_READ_BYTES,
    }


def _log_file_response(root: Path, name: str) -> FileResponse:
    path = _log_file_path(root, name)
    return FileResponse(path, media_type=_media_type_for(path), filename=path.name)
