"""Persistent test designer drafts; generated rules use the same import contract as ZIPs."""

from __future__ import annotations

import base64
import json
from pathlib import Path

from aaw_skill_eval.contracts.schemas import DimensionSpec, SuiteCreateRequest
from aaw_skill_eval.infrastructure.storage.artifacts import canonical_json, content_hash
from aaw_skill_eval.infrastructure.workspace.repository import (
    clone_at_commit,
    inspect_clean_project,
    run_trusted_command,
)
from aaw_skill_eval.modules.evaluations.graders import parse_check_results
from aaw_skill_eval.modules.suites.packages import (
    PackageImportRequest,
    import_package,
    materialize_files,
)
from aaw_skill_eval.modules.suites.validation import validate_standard_request
from aaw_skill_eval.standards import CATALOG_VERSION, get_dimension


def compile_draft(data: dict) -> SuiteCreateRequest:
    """Merge shared scenes once, while retaining independently weighted dimensions."""
    dimensions = []
    scenes: dict[str, dict] = {}
    packages = data.get("packages", {})
    for selected in data.get("dimensions", []):
        dim_id = selected["id"]
        standard = get_dimension("workflow", dim_id, CATALOG_VERSION)
        dimensions.append(
            DimensionSpec.model_validate(
                {
                    **standard,
                    **{
                        key: selected[key]
                        for key in ("weight", "hard_gate", "pass_score")
                        if key in selected
                    },
                }
            )
        )
        if dim_id not in packages:
            raise ValueError(f"请为 {standard['name']} 导入或生成用例")
        package = packages[dim_id]
        parsed = import_package(
            PackageImportRequest.model_validate(
                {
                    **package,
                    "dimension_id": dim_id,
                    "catalog_version": CATALOG_VERSION,
                    "skill_type": "workflow",
                }
            ),
            require_standard=True,
        )
        for source in parsed["cases"]:
            scene = {**source, "weight": 1, "graders": [], "dimension_weights": {}}
            if source["id"] in scenes:
                existing = scenes[source["id"]]
                identity = {**existing, "graders": [], "dimension_weights": {}}
                if canonical_json(identity) != canonical_json(scene):
                    raise ValueError(f"共用场景 {source['id']} 的任务或配置不一致")
            else:
                scenes[source["id"]] = scene
            scenes[source["id"]]["graders"].extend(source["graders"])
            scenes[source["id"]]["dimension_weights"][dim_id] = source.get("weight", 1)
    request = SuiteCreateRequest.model_validate(
        {
            "name": data.get("name", ""),
            "requirement": data.get("requirement", ""),
            "project_path": data.get("project_path", ""),
            "skill_path": data.get("skill_path", ""),
            "setup": data.get("setup", {}),
            "catalog_version": CATALOG_VERSION,
            "skill_type": "workflow",
            "dimensions": [dim.model_dump() for dim in dimensions],
            "cases": list(scenes.values()),
        }
    )
    validate_standard_request(request)
    return request


def package_from_documents(dimension_id: str, manifest: dict, assets: dict[str, str]) -> dict:
    files = [
        {"path": path, "content_base64": base64.b64encode(text.encode()).decode()}
        for path, text in assets.items()
    ]
    files.append(
        {
            "path": "suite.json",
            "content_base64": base64.b64encode(
                json.dumps(
                    {
                        **manifest,
                        "schema_version": 3,
                        "catalog_version": CATALOG_VERSION,
                        "skill_type": "workflow",
                        "dimension_id": dimension_id,
                    },
                    ensure_ascii=False,
                ).encode()
            ).decode(),
        }
    )
    result = {"files": files}
    import_package(
        PackageImportRequest(
            **result,
            dimension_id=dimension_id,
            catalog_version=CATALOG_VERSION,
            skill_type="workflow",
        ),
        require_standard=True,
    )
    return result


def documents_from_package(package: dict, dimension_id: str) -> dict:
    # Normalize ZIPs through the importer but keep the editable source manifest and assets.
    import_package(
        PackageImportRequest(
            **package,
            dimension_id=dimension_id,
            catalog_version=CATALOG_VERSION,
            skill_type="workflow",
        ),
        require_standard=True,
    )
    import io
    import zipfile

    import yaml

    if package.get("zip_base64"):
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(package["zip_base64"]))) as archive:
            contents = {
                item.filename: archive.read(item)
                for item in archive.infolist()
                if not item.is_dir()
            }
    else:
        contents = {
            item["path"]: base64.b64decode(item["content_base64"]) for item in package["files"]
        }
    manifest_path = next(
        path for path in contents if Path(path).name in {"suite.json", "suite.yaml", "suite.yml"}
    )
    prefix = manifest_path.rsplit("/", 1)[0] + "/" if "/" in manifest_path else ""
    raw = contents[manifest_path].decode("utf-8-sig")
    manifest = json.loads(raw) if manifest_path.endswith(".json") else yaml.safe_load(raw)
    assets = {
        path.removeprefix(prefix): text.decode("utf-8")
        for path, text in contents.items()
        if path != manifest_path and path.startswith(prefix)
    }
    return {"manifest": manifest, "assets": assets}


def validate_draft(
    settings,
    data: dict,
    root: Path,
    *,
    run_scripts: bool,
    is_cancelled=lambda: False,
    command_timeout_seconds: int = 300,
) -> dict:
    request = compile_draft(data)
    checks = []
    project = inspect_clean_project(request.project_path)
    if run_scripts:
        for case in request.cases:
            for grader in case.graders:
                if is_cancelled():
                    raise ValueError("任务已停止")
                if grader.type != "command":
                    continue
                work = root / content_hash({"case": case.id, "grader": grader.id})[:8]
                workspace = work / "project"
                evaluator = work / "evaluator"
                clone_at_commit(project, workspace)
                materialize_files(workspace, case.files)
                materialize_files(evaluator, grader.files)
                response = work / "final-response.md"
                response.write_text("", encoding="utf-8")
                environment = {
                    "AAW_WORKSPACE": str(workspace.resolve()),
                    "AAW_FINAL_RESPONSE": str(response.resolve()),
                }
                log = []
                try:
                    for command, cwd in [(cmd, workspace) for cmd in request.setup.commands] + [
                        (cmd, evaluator) for cmd in grader.setup_commands
                    ]:
                        if is_cancelled():
                            raise ValueError("任务已停止")
                        setup = run_trusted_command(
                            command,
                            cwd=cwd,
                            timeout_seconds=command_timeout_seconds,
                            env=environment,
                        )
                        if setup["exit_code"] != 0:
                            raise ValueError("Setup 失败：" + setup["stderr"][-2000:])
                    outcome = run_trusted_command(
                        grader.command,
                        cwd=evaluator,
                        timeout_seconds=min(grader.timeout_seconds, command_timeout_seconds),
                        env=environment,
                    )
                    code, stdout, stderr = (
                        outcome["exit_code"],
                        outcome["stdout"],
                        outcome["stderr"],
                    )
                    log.append(
                        {"exit_code": code, "stdout": stdout[-5000:], "stderr": stderr[-2000:]}
                    )
                    _, results = parse_check_results(stdout, grader.check_weights)
                    if is_cancelled():
                        raise ValueError("任务已停止")
                    log[-1]["checks"] = results
                    checks.append(
                        {
                            "case_id": case.id,
                            "grader_id": grader.id,
                            "runnable": code == 0,
                            "details": log,
                        }
                    )
                except Exception as exc:
                    checks.append(
                        {
                            "case_id": case.id,
                            "grader_id": grader.id,
                            "runnable": False,
                            "error": str(exc)[:2000],
                            "details": log,
                        }
                    )
    return {
        "structure_passed": True,
        "scripts_checked": run_scripts,
        "scripts_runnable": all(item["runnable"] for item in checks) if run_scripts else None,
        "assertion_validity": "待人工确认",
        "checks": checks,
        "definition_hash": content_hash(data),
        "project_commit": project.commit,
        "case_count": len(request.cases),
    }
