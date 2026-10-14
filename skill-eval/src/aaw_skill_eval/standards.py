"""Versioned, system-owned evaluation standards. No project-specific assertions here."""

from __future__ import annotations

from copy import deepcopy

CATALOG_VERSION = 1


def _check(check_id: str, name: str, description: str, kind: str) -> dict:
    return {
        "id": check_id,
        "name": name,
        "description": description,
        "type": kind,
        "weight": 1,
        "levels": {
            "0": "未满足，或缺少可核实的依据",
            "60": "主要要求满足，但存在明确缺项",
            "100": "全部满足，依据充分且与实际产出一致",
        }
        if kind == "llm"
        else {"0": "没有满足检查要求", "100": "全部满足检查要求；中间分按满足比例计算"},
        "evidence_required": "引用实际产出中的具体位置、检查结果及对应任务要求；不能仅复述任务",
    }


def _dimension(dim_id: str, name: str, method: str, description: str, checks: list[dict]) -> dict:
    return {
        "id": dim_id,
        "name": name,
        "method": method,
        "description": description,
        "weight": 1,
        "hard_gate": False,
        "pass_score": 60,
        "checkpoints": checks,
    }


CATALOG = {
    "development": [
        _dimension(
            "correctness",
            "功能正确性",
            "code",
            "验证明确的功能需求与边界行为。",
            [
                _check(
                    "required-behavior", "需求行为", "验证任务要求的功能、输入输出和结果。", "code"
                ),
                _check("edge-cases", "边界与异常行为", "验证边界输入和要求的异常处理。", "code"),
            ],
        ),
        _dimension(
            "regression",
            "回归兼容性",
            "code",
            "验证修改保留已有行为与兼容契约。",
            [
                _check("existing-behavior", "已有行为", "验证已有功能和回归用例仍通过。", "code"),
                _check("compatibility", "兼容契约", "验证既有接口、数据格式及调用契约。", "code"),
            ],
        ),
        _dimension(
            "architecture",
            "架构约束符合性",
            "code",
            "验证声明的架构规则，不评价方案本身是否合理。",
            [
                _check(
                    "dependency-direction", "依赖方向", "按项目声明的分层规则验证依赖方向。", "code"
                ),
                _check(
                    "module-boundaries",
                    "模块边界",
                    "验证模块接口与禁止跨层、跨模块调用规则。",
                    "code",
                ),
                _check("dependency-cycles", "循环依赖", "检测模块或层级间禁止的循环依赖。", "code"),
            ],
        ),
        _dimension(
            "maintainability",
            "可维护性",
            "llm",
            "检查代码阅读、职责理解和修改便利性。",
            [
                _check(
                    "readability",
                    "代码可读性",
                    "命名、控制流和必要说明是否清晰，避免重复与无谓复杂性。",
                    "llm",
                ),
                _check(
                    "responsibilities",
                    "职责与修改便利性",
                    "职责是否清晰、修改是否局部且可验证；不评价整体架构选型。",
                    "llm",
                ),
            ],
        ),
    ],
    "documents_analysis": [
        _dimension(
            "completeness",
            "内容完整性与约束符合性",
            "hybrid",
            "检查必要内容及明确可断言的输出约束。",
            [
                _check(
                    "output-constraints",
                    "输出约束",
                    "用代码验证要求的文件、章节、结构或格式约束。",
                    "code",
                ),
                _check(
                    "required-content",
                    "必要内容",
                    "检查任务要求的内容是否充分覆盖，避免仅有标题而无实质内容。",
                    "llm",
                ),
            ],
        ),
        _dimension(
            "accuracy",
            "事实与证据质量",
            "llm",
            "检查事实、引用和证据的可靠性。",
            [
                _check(
                    "factual-consistency",
                    "事实一致性",
                    "核对产出与提供的项目事实、参考材料，识别无依据断言。",
                    "llm",
                ),
                _check(
                    "evidence-quality",
                    "证据质量",
                    "检查关键事实的证据可追溯性、相关性与充分性。",
                    "llm",
                ),
            ],
        ),
        _dimension(
            "reasoning",
            "分析与设计合理性",
            "llm",
            "检查推理、结论和方案是否获得充分支持。",
            [
                _check(
                    "logical-support",
                    "推理与结论",
                    "判断推理是否连贯，结论是否由所给事实和证据支持。",
                    "llm",
                ),
                _check(
                    "design-tradeoffs",
                    "方案与取舍",
                    "判断方案是否响应任务目标，关键取舍和前提是否明确。",
                    "llm",
                ),
            ],
        ),
        _dimension(
            "clarity",
            "表达清晰度",
            "llm",
            "检查组织方式和表达是否便于理解和使用。",
            [
                _check(
                    "organization",
                    "内容组织",
                    "信息层次是否清楚，读者能否找到关键结论和行动。",
                    "llm",
                ),
                _check(
                    "precise-expression",
                    "表达准确",
                    "术语、句子和说明是否准确清晰，避免歧义与不必要重复。",
                    "llm",
                ),
            ],
        ),
    ],
}


def get_dimension(skill_type: str, dimension_id: str, version: int = CATALOG_VERSION) -> dict:
    if version != CATALOG_VERSION:
        raise ValueError("Unsupported evaluation catalog version")
    groups = (
        CATALOG.items() if skill_type == "workflow" else [(skill_type, CATALOG.get(skill_type, []))]
    )
    for group, dimensions in groups:
        for dimension in dimensions:
            if dimension["id"] == dimension_id:
                return {**deepcopy(dimension), "group": group}
    raise ValueError("Unknown dimension for the selected skill type")


def catalog_payload() -> dict:
    return {
        "catalog_version": CATALOG_VERSION,
        "items": deepcopy(CATALOG),
        "labels": {"development": "软件开发", "documents_analysis": "文档与分析设计"},
    }


def fixed_criteria(dimension: dict) -> list[dict]:
    return [
        {
            "id": point["id"],
            "checkpoint": point["name"] + "：" + point["description"],
            "weight": point["weight"],
            "levels": point["levels"],
            "evidence_required": point["evidence_required"],
        }
        for point in dimension["checkpoints"]
        if point["type"] == "llm"
    ]
