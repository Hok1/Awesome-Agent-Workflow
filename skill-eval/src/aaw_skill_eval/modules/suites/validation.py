from __future__ import annotations

from copy import deepcopy

from aaw_skill_eval.contracts.schemas import CaseSpec, GraderSpec, SuiteCreateRequest
from aaw_skill_eval.standards import CATALOG_VERSION, fixed_criteria, get_dimension


def code_graders(dimension: dict, sources: list[dict]) -> list[GraderSpec]:
    points = {point["id"]: point for point in dimension["checkpoints"] if point["type"] == "code"}
    covered = set()
    result = []
    for index, source in enumerate(sources, 1):
        if source.get("type") != "command" or source.get("result_format") != "json":
            raise ValueError("固定代码维度必须使用 JSON command 检查")
        ids = source.get("checkpoint_ids", [])
        if not ids or len(ids) != len(set(ids)) or set(ids) - set(points) or set(ids) & covered:
            raise ValueError("代码检查点缺失、重复或不属于当前维度")
        covered.update(ids)
        data = deepcopy(source)
        data.update(
            id=f"{dimension['id']}.code-{index}",
            name="代码检查 · " + "、".join(points[key]["name"] for key in ids),
            type="command",
            dimension_id=dimension["id"],
            hard_gate=False,
            weight=sum(points[key]["weight"] for key in ids)
            / sum(point["weight"] for point in points.values()),
            checkpoint_ids=ids,
            check_weights={key: points[key]["weight"] for key in ids},
            criteria=[],
            rubric=None,
            allowed_scores=[],
        )
        result.append(GraderSpec.model_validate(data))
    if covered != set(points):
        raise ValueError("每个场景必须覆盖该维度全部固定代码检查点")
    return result


def llm_grader(dimension: dict) -> GraderSpec | None:
    criteria = fixed_criteria(dimension)
    if not criteria:
        return None
    return GraderSpec(
        id=f"{dimension['id']}.llm",
        type="llm_rubric",
        name=dimension["name"],
        dimension_id=dimension["id"],
        weight=1,
        criteria=criteria,
        allowed_scores=[0, 60, 100],
    )


def compile_package_cases(cases: list[dict], dimension: dict) -> list[CaseSpec]:
    result = []
    for source in cases:
        checks = source.get("graders", [])
        if any(
            check.get("type") == "llm_rubric"
            or check.get("criteria")
            or check.get("rubric")
            or check.get("criteria_file")
            for check in checks
        ):
            raise ValueError("LLM 核心检查点和评分档位由系统提供，用例包不能覆盖")
        code = code_graders(dimension, checks)
        llm = llm_grader(dimension)
        result.append(CaseSpec.model_validate({**source, "graders": code + ([llm] if llm else [])}))
    return result


def validate_standard_request(request: SuiteCreateRequest) -> None:
    if (
        request.catalog_version != CATALOG_VERSION
        or not request.skill_type
        or not request.dimensions
    ):
        raise ValueError("新建测试必须选择固定维度目录及当前标准版本")
    definitions = {}
    for dimension in request.dimensions:
        standard = get_dimension(request.skill_type, dimension.id, request.catalog_version)
        if dimension.name != standard["name"] or dimension.method != standard["method"]:
            raise ValueError("维度名称与评价方式由系统固定，不能自定义")
        definitions[dimension.id] = standard
    protected = {
        "id",
        "name",
        "type",
        "weight",
        "hard_gate",
        "result_format",
        "criteria",
        "rubric",
        "checkpoint_ids",
        "check_weights",
        "allowed_scores",
    }
    for case in request.cases:
        for dimension_id in {grader.dimension_id for grader in case.graders}:
            standard = definitions[dimension_id]
            originals = [g for g in case.graders if g.dimension_id == dimension_id]
            canonical = code_graders(
                standard, [g.model_dump() for g in originals if g.type != "llm_rubric"]
            )
            llm = llm_grader(standard)
            if llm:
                canonical.append(llm)
            if len(originals) != len(canonical):
                raise ValueError("场景缺少或重复包含系统规定的评价检查")
            expected = {grader.id: grader for grader in canonical}
            for grader in originals:
                if grader.id not in expected or grader.model_dump(include=protected) != expected[
                    grader.id
                ].model_dump(include=protected):
                    raise ValueError("检查点、检查权重、评价方式和评分档位不能修改")
