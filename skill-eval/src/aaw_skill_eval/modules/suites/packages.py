"""Portable test bundles. Import never executes code or extracts an archive."""

from __future__ import annotations

import base64
import io
import json
import stat
import zipfile
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from aaw_skill_eval.contracts.schemas import CaseSpec, PackageFile
from aaw_skill_eval.errors import EvalError
from aaw_skill_eval.modules.suites.validation import compile_package_cases
from aaw_skill_eval.standards import CATALOG_VERSION, get_dimension

MAX_BYTES = 20 * 1024 * 1024


class PackageImportRequest(BaseModel):
    files: list[PackageFile] = Field(default_factory=list, max_length=500)
    zip_base64: str | None = Field(default=None, max_length=30_000_000)
    catalog_version: int | None = None
    skill_type: str | None = None
    dimension_id: str | None = None


def import_package(request: PackageImportRequest, *, require_standard: bool = False) -> dict:
    try:
        dimension = None
        if require_standard or request.catalog_version is not None:
            if request.catalog_version != CATALOG_VERSION:
                raise ValueError("请选择当前固定评价标准版本")
            dimension = get_dimension(
                request.skill_type, request.dimension_id, request.catalog_version
            )
        if bool(request.files) == bool(request.zip_base64):
            raise ValueError("请选择一个目录或一个 ZIP 用例包")
        files = request.files
        if request.zip_base64:
            raw = base64.b64decode(request.zip_base64, validate=True)
            if len(raw) > MAX_BYTES:
                raise ValueError("ZIP 超过 20 MB")
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries = [entry for entry in archive.infolist() if not entry.is_dir()]
                if len(entries) > 500 or sum(entry.file_size for entry in entries) > MAX_BYTES:
                    raise ValueError("解压内容超过 20 MB 或 500 个文件")
                files = []
                for entry in entries:
                    if stat.S_ISLNK(entry.external_attr >> 16):
                        raise ValueError("用例包不能包含符号链接")
                    PackageFile.safe_path(entry.filename)
                    files.append(
                        PackageFile(
                            path=entry.filename,
                            content_base64=base64.b64encode(archive.read(entry)).decode("ascii"),
                        )
                    )
        paths = [file.path.casefold() for file in files]
        if len(paths) != len(set(paths)):
            raise ValueError("用例包存在重复路径")
        contents = {file.path: base64.b64decode(file.content_base64) for file in files}
        if sum(map(len, contents.values())) > MAX_BYTES:
            raise ValueError("用例包内容超过 20 MB")
        manifests = [
            path
            for path in contents
            if Path(path).name in {"suite.json", "suite.yaml", "suite.yml"}
        ]
        if len(manifests) != 1:
            raise ValueError("用例包必须包含唯一的 suite.json 或 suite.yaml")
        manifest_path = manifests[0]
        prefix = manifest_path.rsplit("/", 1)[0] + "/" if "/" in manifest_path else ""
        text = contents[manifest_path].decode("utf-8-sig")
        manifest = json.loads(text) if manifest_path.endswith(".json") else yaml.safe_load(text)
        if not isinstance(manifest, dict) or manifest.get("schema_version") != (
            3 if dimension else 2
        ):
            raise ValueError(f"用例包 schema_version 必须为 {3 if dimension else 2}")
        if dimension and any(
            manifest.get(key) != expected
            for key, expected in {
                "catalog_version": request.catalog_version,
                "dimension_id": request.dimension_id,
            }.items()
        ):
            raise ValueError("用例包的标准版本、Skill 类型或维度与当前选择不匹配")
        if dimension and manifest.get("skill_type") not in (
            {"workflow", dimension["group"]}
            if request.skill_type == "workflow"
            else {request.skill_type}
        ):
            raise ValueError("用例包维度分组与当前选择不匹配")

        def asset(path: str, target: str | None = None) -> dict:
            PackageFile.safe_path(path)
            if prefix + path not in contents:
                raise ValueError(f"用例包缺少文件：{path}")
            return PackageFile(
                path=target or path,
                content_base64=base64.b64encode(contents[prefix + path]).decode("ascii"),
            ).model_dump()

        cases = manifest.get("cases", [])
        if not isinstance(cases, list) or not 1 <= len(cases) <= 200:
            raise ValueError("用例包必须包含 1-200 个场景")
        for case in cases:
            # Scene assets explicitly map source path to destination in the workspace.
            case["files"] = [
                asset(source, target) for target, source in case.get("files", {}).items()
            ]
            if "expected_file" in case:
                file = asset(case.pop("expected_file"))
                case["expected"] = base64.b64decode(file["content_base64"]).decode("utf-8")
            for grader in case.get("graders", []):
                grader["files"] = [asset(path) for path in grader.get("files", [])]
                if "criteria_file" in grader:
                    file = asset(grader.pop("criteria_file"))
                    grader["criteria"] = json.loads(
                        base64.b64decode(file["content_base64"]).decode("utf-8")
                    )
        parsed = (
            compile_package_cases(cases, dimension)
            if dimension
            else [CaseSpec.model_validate(case) for case in cases]
        )
        if len({case.id for case in parsed}) != len(parsed):
            raise ValueError("场景 id 不能重复")
        return {
            "cases": [case.model_dump(mode="json") for case in parsed],
            "file_count": len(files),
            "bytes": sum(map(len, contents.values())),
        }
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        zipfile.BadZipFile,
        RuntimeError,
        yaml.YAMLError,
        ValidationError,
    ) as exc:
        raise EvalError("INVALID_TEST_PACKAGE", str(exc), status_code=422) from exc


def materialize_files(root: Path, files: list[PackageFile]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for file in files:
        target = (root / file.path).resolve()
        if not target.is_relative_to(root.resolve()):
            raise ValueError("package file escaped its destination")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(file.content_base64))


def example_package(method: str) -> bytes:
    criteria = [
        {
            "checkpoint": "产出充分解释了实现和验证依据",
            "weight": 1,
            "levels": {
                "0": "没有解释或与产出矛盾",
                "60": "说明主要结果但依据不足",
                "100": "解释清晰，依据充分且与实际产出一致",
            },
            "evidence_required": "引用产出中的具体段落，不得仅引用任务描述",
        }
    ]
    code = {
        "id": "output-check",
        "name": "结果文件检查",
        "type": "command",
        "weight": 1,
        "command": "python validate.py",
        "result_format": "json",
        "files": ["validate.py"],
    }
    llm = {
        "id": "explanation",
        "name": "解释质量",
        "type": "llm_rubric",
        "weight": 1,
        "criteria": criteria,
    }
    manifest = {
        "schema_version": 2,
        "cases": [
            {
                "id": "shared-result",
                "name": "生成并解释结果",
                "weight": 1,
                "input": "阅读 brief.md，生成 result.md 并解释你的处理依据。",
                "expected": "result.md 包含有效结果，最终响应解释处理依据。",
                "files": {"brief.md": "scene/brief.md"},
                "graders": [code]
                if method == "code"
                else [llm]
                if method == "llm"
                else [code, llm],
            }
        ],
    }
    script = (
        "import json, os\nfrom pathlib import Path\n"
        "path = Path(os.environ['AAW_WORKSPACE']) / 'result.md'\n"
        "exists = path.is_file()\n"
        "content = path.read_text(encoding='utf-8') if exists else ''\n"
        "print(json.dumps({'checks': [\n"
        " {'id': 'exists', 'score': 100 if exists else 0, 'weight': 1, "
        "'evidence': 'result.md exists=' + str(exists)},\n"
        " {'id': 'content', 'score': 100 if content.strip() else 0, 'weight': 1, "
        "'evidence': content[:500] or 'Empty/missing file'}\n"
        "]}))\n"
    )
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("suite.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("scene/brief.md", "# 任务\n生成一份简洁、可使用的结果说明。\n")
        if method != "llm":
            archive.writestr("validate.py", script)
    return stream.getvalue()


def standard_example_package(skill_type: str, dimension_id: str, entry: str | None = None) -> bytes:
    if entry not in {None, "sr", "ar", "dev"}:
        raise ValueError("工作流入口必须为 sr、ar 或 dev")
    dimension = get_dimension(skill_type, dimension_id)
    points = [point for point in dimension["checkpoints"] if point["type"] == "code"]
    graders = []
    if points:
        graders = [
            {
                "type": "command",
                "command": "python validate.py",
                "result_format": "json",
                "files": ["validate.py"],
                "checkpoint_ids": [point["id"] for point in points],
            }
        ]
    manifest = {
        "schema_version": 3,
        "catalog_version": CATALOG_VERSION,
        "skill_type": skill_type,
        "dimension_id": dimension_id,
        "cases": [
            {
                "id": "shared-result",
                "name": "生成并解释结果",
                "weight": 1,
                "input": "阅读 brief.md，生成 result.md 并解释你的处理依据。",
                "expected": "result.md 包含有效结果，最终响应解释处理依据。",
                "files": {"brief.md": "scene/brief.md"},
                "graders": graders,
            }
        ],
    }
    if entry:
        scene = manifest["cases"][0]
        scene.update(
            id="shared-aaw-" + entry,
            name="AAW " + entry + " 文档与代码联合交付",
            input=(
                "阅读 brief.md，按声明的 AAW 入口完成需求，保留设计文档、实现代码、测试与验证证据。"
            ),
            expected="终态文档与代码一致，功能及回归测试通过，流程及任务验证记录完整。",
            workflow={
                "entry": entry,
                "sr": "SR-EVAL-001",
                **({"ar": "AR-001"} if entry == "ar" else {}),
                "confirmation_reply": (
                    "确认当前步骤的交付件并放行；按已提供需求和默认值继续流程。"
                    "遇到真实阻塞请明确报告。"
                ),
            },
            max_turns=30,
        )
        if entry == "ar":
            scene["files"][".sdd/software_architecture.md"] = "scene/software_architecture.md"
    checks = [
        {
            "id": point["id"],
            "score": 0,
            "weight": point["weight"],
            "evidence": "示例尚未实现：" + point["description"] + "请替换为项目实际断言。",
        }
        for point in points
    ]
    script = (
        "# Replace these placeholders with assertions against AAW_WORKSPACE.\n"
        "import json, os\nfrom pathlib import Path\n"
        "workspace = Path(os.environ['AAW_WORKSPACE'])\n"
        f"checks = json.loads({json.dumps(json.dumps(checks, ensure_ascii=False))})\n"
        "print(json.dumps({'checks': checks}))\n"
    )
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("suite.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("scene/brief.md", "# 任务\n请提供实际任务、项目约束与参考材料。\n")
        if entry == "ar":
            archive.writestr(
                "scene/software_architecture.md",
                "# 已有软件架构\n请替换为项目实际架构、模块边界和依赖规则。\n",
            )
        archive.writestr("standard.json", json.dumps(dimension, ensure_ascii=False, indent=2))
        if points:
            archive.writestr("validate.py", script)
    return stream.getvalue()
