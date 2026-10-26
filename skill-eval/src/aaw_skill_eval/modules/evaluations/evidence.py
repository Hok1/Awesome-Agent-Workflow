"""Build auditable, dimension-specific views of an immutable evidence snapshot."""

from __future__ import annotations

from pathlib import PurePosixPath


def dimension_evidence(evidence: dict, dimension: str, budget: int = 60_000) -> dict:
    files = evidence.get("output_files", {})
    if not isinstance(files, dict):
        files = {}

    def priority(path):
        p = PurePosixPath(path.replace("\\", "/"))
        document = p.suffix.lower() in {".md", ".rst", ".txt"}
        internal = (
            any(part in {".aaw", ".context"} for part in p.parts) or p.name == "workflow.yaml"
        )
        code = p.suffix.lower() in {".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".vue"}
        test = any(part in {"test", "tests", "__tests__"} for part in p.parts)
        if internal:
            return 8
        if dimension == "maintainability":
            return 0 if code and not test else 2 if code else 5
        if dimension == "clarity":
            return 0 if document else 8
        return 0 if document else 2 if code and not test else 7

    selected, omitted = {}, []
    remaining = budget
    for path, text in sorted(files.items(), key=lambda item: (priority(item[0]), item[0])):
        if not isinstance(text, str):
            continue
        # Never silently truncate a file into apparently complete evidence.
        if priority(path) >= 7 or len(text) > remaining:
            omitted.append({"path": path, "characters": len(text)})
        else:
            selected[path] = text
            remaining -= len(text)
    result = {
        key: evidence[key]
        for key in (
            "final_response",
            "changed_files",
            "validator_results",
            "agent_exit_code",
            "agent_error_kind",
            "skill_invoked",
            "workflow_completion",
            "terminal_inventory",
        )
        if key in evidence
    }
    result.update(
        output_files=selected,
        omitted_files=omitted,
        evidence_scope="Complete selected files. Omitted files are not absent deliverables.",
    )
    if not files:
        patch = evidence.get("git_patch", "")
        result["git_patch"] = patch[:budget]
        result["patch_truncated"] = len(patch) > budget
    return result
