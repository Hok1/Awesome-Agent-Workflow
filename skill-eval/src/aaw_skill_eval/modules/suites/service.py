from __future__ import annotations

import json
import re

import yaml
from pydantic import ValidationError
from sqlalchemy.orm import Session

from aaw_skill_eval.config import Settings
from aaw_skill_eval.contracts.entities import Suite
from aaw_skill_eval.contracts.schemas import (
    CaseSpec,
    GraderSpec,
    RubricDraftRequest,
    SuiteCreateRequest,
)
from aaw_skill_eval.errors import EvalError
from aaw_skill_eval.infrastructure.storage.artifacts import (
    atomic_write_text,
    canonical_json,
    content_hash,
)
from aaw_skill_eval.infrastructure.workspace.repository import inspect_clean_project
from aaw_skill_eval.modules.executions.skills import inspect_skill
from aaw_skill_eval.modules.suites.validation import validate_standard_request
from aaw_skill_eval.standards import get_dimension


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-").lower()
    return value[:80] or "case-1"


def build_rubric_draft(request: RubricDraftRequest, settings: Settings) -> dict:
    project = inspect_clean_project(request.project_path)
    skill = inspect_skill(request.skill_path, settings.max_skill_bytes)
    rubric = (
        "按 0-100 分评价候选结果。重点检查：\n"
        "1. 是否完成用户任务并产出可使用的结果；\n"
        "2. 是否满足全部预期效果；\n"
        "3. 内容是否与项目事实一致，且没有无依据的断言；\n"
        "4. 结果是否清晰、完整、可维护。\n\n"
        f"预期效果：\n{request.expected}"
    )
    case = CaseSpec(
        id=_slug(skill.name + "-case-1"),
        name=f"{skill.name} 默认测试",
        input=request.input,
        expected=request.expected,
        graders=[
            GraderSpec(
                id="outcome-quality",
                type="llm_rubric",
                name="结果质量",
                weight=100,
                rubric=rubric,
            )
        ],
    )
    return {
        "project": {
            "path": str(project.path),
            "name": project.name,
            "commit": project.commit,
            "tree": project.tree,
        },
        "skill": {
            "path": str(skill.root),
            "name": skill.name,
            "description": skill.description,
            "content_hash": skill.content_hash,
            "total_bytes": skill.total_bytes,
        },
        "case": case.model_dump(mode="json"),
    }


def _expand_criteria(request: SuiteCreateRequest) -> SuiteCreateRequest:
    if request.dimensions:
        # Each rubric checkpoint gets its own judge result and evidence. Normalize
        # checkpoint weights within the original check, preserving hybrid ratios.
        cases = []
        for case in request.cases:
            graders = []
            for grader in case.graders:
                if grader.type == "llm_rubric" and (
                    len(grader.criteria) > 1 or request.catalog_version
                ):
                    total = sum(item.weight for item in grader.criteria)
                    for index, criterion in enumerate(grader.criteria, 1):
                        data = grader.model_dump()
                        data.update(
                            id=f"{grader.dimension_id}.{criterion.id}"
                            if request.catalog_version
                            else f"{grader.id[:65]}.criterion-{index}",
                            name=f"{grader.name[:120]} · {criterion.checkpoint[:30]}",
                            weight=grader.weight * criterion.weight / total,
                            criteria=[criterion.model_dump()],
                        )
                        graders.append(GraderSpec.model_validate(data))
                else:
                    graders.append(grader)
            cases.append(CaseSpec.model_validate({**case.model_dump(), "graders": graders}))
        request = SuiteCreateRequest.model_validate({**request.model_dump(), "cases": cases})
    return request


def create_suite(
    session: Session,
    settings: Settings,
    request: SuiteCreateRequest,
    *,
    allow_legacy: bool = False,
    commit: bool = True,
) -> Suite:
    try:
        if not allow_legacy:
            validate_standard_request(request)
        request = _expand_criteria(request)
    except (ValueError, ValidationError) as exc:
        raise EvalError("INVALID_CHECKS", str(exc), status_code=422) from exc
    project = inspect_clean_project(request.project_path)
    for case in request.cases:
        if not case.workflow:
            continue
        if (project.path / f".sdd/{case.workflow.sr}/workflow.yaml").exists():
            raise EvalError(
                "SCENE_WORKFLOW_EXISTS",
                "该 SR 已存在流程状态，请使用新的评测 SR 编号",
                status_code=422,
            )
        if case.workflow.entry == "ar" and not (
            (project.path / ".sdd/software_architecture.md").is_file()
            or any(file.path == ".sdd/software_architecture.md" for file in case.files)
        ):
            raise EvalError(
                "SCENE_ARCHITECTURE_MISSING",
                "ar 入口需要已有软件架构文档，请在场景中导入",
                status_code=422,
            )
    definition = {
        "schema_version": 3 if request.catalog_version else 2 if request.dimensions else 1,
        "name": request.name,
        "requirement": request.requirement,
        "project": {
            "path": str(project.path),
            "commit_at_creation": project.commit,
        },
        "reference_skill_path": request.skill_path,
        "setup": request.setup.model_dump(mode="json"),
        "cases": [case.model_dump(mode="json") for case in request.cases],
    }
    if request.dimensions:
        definition["dimensions"] = [item.model_dump(mode="json") for item in request.dimensions]
    if request.catalog_version:
        definition["catalog_version"] = request.catalog_version
        definition["skill_type"] = request.skill_type
        definition["dimensions"] = [
            {
                **get_dimension(request.skill_type, item.id, request.catalog_version),
                "weight": item.weight,
                "hard_gate": item.hard_gate,
                "pass_score": item.pass_score,
            }
            for item in request.dimensions
        ]
    definition_json = canonical_json(definition)
    digest = content_hash(definition)
    suite = Suite(
        name=request.name,
        skill_id=None,
        project_path=str(project.path),
        definition_path="",
        definition_hash=digest,
        definition_json=definition_json,
    )
    session.add(suite)
    session.flush()
    definition_path = settings.suites_dir / f"{suite.id}.yaml"
    atomic_write_text(
        definition_path,
        yaml.safe_dump(definition, allow_unicode=True, sort_keys=False),
    )
    suite.definition_path = str(definition_path)
    if commit:
        session.commit()
    else:
        session.flush()
    session.refresh(suite)
    return suite


def suite_definition(suite: Suite) -> dict:
    return json.loads(suite.definition_json)
