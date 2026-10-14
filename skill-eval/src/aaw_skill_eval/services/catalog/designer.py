"""Persistent test designer drafts; generated rules use the same import contract as ZIPs."""

from __future__ import annotations

import base64
import json
import shutil
from pathlib import Path

from ...errors import EvalError
from ...schemas import CaseSpec, DimensionSpec, EvalProfile, GraderSpec, SuiteCreateRequest
from ...standards import CATALOG_VERSION, get_dimension
from ..evaluation.graders import parse_check_results
from ..providers.chrys.runner import ChrysRunner
from ..providers.chrys.runtime import enrich_profile, prepare_isolated_home
from ..storage.artifacts import canonical_json, content_hash
from ..workspace.repository import clone_at_commit, inspect_clean_project, run_trusted_command
from .contracts import validate_standard_request
from .packages import PackageImportRequest, import_package, materialize_files
from .skills import inspect_skill


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


class DesignerAgent:
    """Provider seam: implementations generate portable packages, never change standards."""

    def generate(self, settings, data, messages, root, progress, cancelled):
        raise NotImplementedError


class ChrysDesigner(DesignerAgent):
    def generate(self, settings, data, messages, root, progress, cancelled):
        project = inspect_clean_project(data["project_path"])
        skill = inspect_skill(data["skill_path"], settings.max_skill_bytes)
        workspace = root / "workspace"
        clone_at_commit(project, workspace / "project")
        shutil.copytree(skill.root, workspace / "target-skill", symlinks=False)
        standards = [
            get_dimension("workflow", dim["id"], CATALOG_VERSION) for dim in data["dimensions"]
        ]
        conversation = [item for item in messages if item.get("role") in {"user", "assistant"}]
        visible_data = {**data, "project_path": "project/", "skill_path": "target-skill/"}
        prompt = (
            "你是 Test Generation Agent。读取 project/ 项目及 target-skill/ 目标 Skill，"
            "不要调用目标 Skill 完成任务，不要修改这两份参考资料。输出真实、项目相关的测试用例。"
            "只在当前目录写 draft-packages.json，格式如下：\n"
            '{"message":"设计说明", "packages":[{"dimension_id":"选中的维度id",'
            '"manifest":{"cases":[{"id":"场景id","name":"名称","input":"Agent任务",'
            '"expected":"仅评分端参考","files":{},"graders":[]}]},'
            '"assets":{"validate.py":"脚本内容"}}]}\n'
            "每个选中维度必须有一个包。共享场景使用相同id、input、expected、files和workflow配置。"
            "代码检查必须type=command,result_format=json,checkpoint_ids覆盖该维度全部code检查点，"
            "command如 python validate.py，files引用assets中的文件。脚本stdout仅输出"
            '{"checks":[{"id":"检查点id","score":0到100,"weight":固定权重,"evidence":"依据"}]}。'
            "脚本必须真实断言，不能恒定满分。LLM检查由平台注入，不生成rubric或criteria。"
            "评分脚本在独立目录运行，须用环境变量AAW_WORKSPACE读取被测项目，"
            "用AAW_FINAL_RESPONSE读取Agent最终回复。断言不满足时输出score=0的检查结果，"
            "仍然exit 0；协议错误或脚本故障才非零退出。"
            "所有文件引用必须与assets键完全一致。例如assets键validate.py不能引用assets/validate.py。"
            "评分脚本只放grader.files，不要放入Agent可见的case.files。"
            "场景files是目标工作区路径到assets源路径的映射。普通Skill的场景不要包含workflow。"
            "仅目标Skill实际执行AAW流程时，workflow可配置entry(sr/ar/dev)、非空字符串sr、"
            "ar和明确的confirmation_reply；不要伪造流程状态。为代码和文档分别提供合适参考材料。\n"
            f"固定标准：{json.dumps(standards, ensure_ascii=False)}\n"
            f"草稿配置和既有用例：{json.dumps(visible_data, ensure_ascii=False)}\n"
            f"设计对话：{json.dumps(conversation, ensure_ascii=False)}"
        )
        profile = EvalProfile(
            name="chrys-designer",
            runner_provider="chrys",
            judge_provider="chrys",
            runner_model=data["generator_model"],
            judge_model=data["generator_model"],
            timeout_seconds=1800,
        )
        profile = enrich_profile(settings, profile, needs_judge=False)
        home = prepare_isolated_home(settings, root=root / "chrys-home")
        case = CaseSpec(
            id="designer",
            name="生成测试用例",
            input=prompt,
            expected="用例包",
            graders=[
                GraderSpec(
                    id="package",
                    type="file_exists",
                    name="输出",
                    path="draft-packages.json",
                    weight=1,
                )
            ],
        )
        for attempt in range(1, 4):
            if cancelled():
                raise ValueError("任务已停止")
            outcome = ChrysRunner(settings).run(
                workspace=workspace,
                artifact_dir=root / "events" / str(attempt),
                case=case,
                profile=profile,
                skill_name=None,
                chrys_home_root=home,
                on_progress=progress,
                is_cancelled=cancelled,
            )
            if outcome.error_kind or outcome.exit_code != 0:
                raise ValueError(outcome.error_message or "Chrys 生成失败")
            try:
                output = workspace / "draft-packages.json"
                if (
                    output.is_symlink()
                    or not output.is_file()
                    or output.stat().st_size > 20 * 1024 * 1024
                ):
                    raise ValueError("Agent 未生成有效的 draft-packages.json（上限20MB）")
                result = json.loads(output.read_text(encoding="utf-8-sig"))
                packages = {}
                for package in result["packages"]:
                    key = package["dimension_id"]
                    if key in packages:
                        raise ValueError("生成了重复维度包")
                    packages[key] = package_from_documents(
                        key, package["manifest"], package.get("assets", {})
                    )
                updated = {**data, "packages": packages}
                compile_draft(updated)
                return updated, str(result.get("message", outcome.final_response))[:20000]
            except (ValueError, KeyError, TypeError, EvalError) as exc:
                if attempt == 3:
                    raise ValueError(f"生成用例经过两次自动修复仍未通过结构校验：{exc}") from exc
                progress("generating", f"结构校验发现问题，自动修复 {attempt}/2：{exc}")
                case = case.model_copy(
                    update={
                        "input": prompt
                        + f"\n已有 draft-packages.json 未通过平台校验，错误：{exc}\n"
                        "读取该文件并修正上述问题及其他协议错误，写回原文件。不要重新设计有效的断言。"
                    }
                )
        raise AssertionError("unreachable")


DESIGNER_PROVIDERS: dict[str, type[DesignerAgent]] = {"chrys": ChrysDesigner}


def validate_draft(
    settings, data: dict, root: Path, *, run_scripts: bool, is_cancelled=lambda: False
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
                            command, cwd=cwd, timeout_seconds=300, env=environment
                        )
                        if setup["exit_code"] != 0:
                            raise ValueError("Setup 失败：" + setup["stderr"][-2000:])
                    outcome = run_trusted_command(
                        grader.command,
                        cwd=evaluator,
                        timeout_seconds=min(grader.timeout_seconds, 300),
                        env=environment,
                    )
                    code, stdout, stderr = (
                        outcome["exit_code"],
                        outcome["stdout"],
                        outcome["stderr"],
                    )
                    _, results = parse_check_results(stdout, grader.check_weights)
                    if is_cancelled():
                        raise ValueError("任务已停止")
                    log.append({"exit_code": code, "checks": results, "stderr": stderr[-2000:]})
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
