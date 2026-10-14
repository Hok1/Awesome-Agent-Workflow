"""Suite-oriented product API. Legacy experiment APIs remain readable."""

from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, update

from .api import _experiment_summary, _iso, _suite_payload
from .errors import EvalError
from .models import Experiment, Suite, SuiteDraft
from .schemas import EvalProfile, ExperimentCreateRequest
from .services.catalog.designer import (
    DESIGNER_PROVIDERS,
    documents_from_package,
    validate_draft,
)
from .services.catalog.designer import (
    compile_draft as _compile_draft,
)
from .services.catalog.suites import create_suite, suite_definition
from .services.providers.chrys.runtime import ChrysRuntime
from .services.providers.registry import RUNTIME_FACTORIES
from .services.storage.artifacts import canonical_json, content_hash

BUSY = {"analyzing", "generating", "validating"}
ACTIVE = {"queued", "preparing", "running"}


def compile_draft(data):
    try:
        return _compile_draft(data)
    except (ValueError, KeyError, TypeError) as exc:
        raise EvalError("INVALID_DRAFT", str(exc), status_code=422) from exc


class DraftInput(BaseModel):
    data: dict
    revision: int | None = None


class MessageInput(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    revision: int


class RevisionInput(BaseModel):
    revision: int


class ArchiveInput(BaseModel):
    archived: bool = True


class BaselineInput(BaseModel):
    experiment_id: str | None = None
    group: Literal["current", "no_skill"] = "current"


class ExecuteInput(BaseModel):
    mode: str = "formal"
    profile: EvalProfile


def draft_payload(item):
    return {
        "id": item.id,
        "data": json.loads(item.data_json),
        "messages": json.loads(item.messages_json),
        "validation": json.loads(item.validation_json),
        "revision": item.revision,
        "status": item.status,
        "error": item.error,
        "suite_id": item.suite_id,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }


def baseline_ready(summary, group="current"):
    state = summary["conclusion"]["groups"][group]
    return (
        not state["missing"]
        and not state["provisional"]
        and not state["gates_failed"]
        and summary["scores"][group] is not None
        and all(not dim["incomplete"] for dim in summary["dimension_scores"].get(group, []))
    )


def comparison(current, baseline, baseline_group="current"):
    if not current or not baseline:
        return {"formal": False, "reasons": ["尚未选择对比基线"], "delta": None}
    reasons = []
    for key, label in (
        ("suite_hash", "用例定义"),
        ("project_commit", "项目提交"),
        ("profile_hash", "模型或运行配置"),
        ("mode", "Trial 模式"),
    ):
        if getattr(current, key) != getattr(baseline, key):
            reasons.append(label + "有变化")
    a, b = _experiment_summary(current), _experiment_summary(baseline)
    if not baseline_ready(a) or not baseline_ready(b, baseline_group):
        reasons.append("存在未完成 Trial 或未通过门禁")
    delta = (
        a["scores"]["current"] - b["scores"][baseline_group]
        if a["scores"]["current"] is not None and b["scores"][baseline_group] is not None
        else None
    )
    return {"formal": not reasons, "reasons": reasons, "delta": delta}


class DraftJobs:
    def __init__(self, settings, factory):
        self.settings, self.factory = settings, factory
        self.tasks = set()
        self.cancellations = {}

    def recover(self):
        with self.factory() as session:
            session.execute(
                update(SuiteDraft)
                .where(SuiteDraft.status.in_(BUSY))
                .values(status="failed", error="服务重启，任务已中断；草稿保留，可重试")
            )
            session.commit()

    async def stop(self):
        for signal in self.cancellations.values():
            signal.set()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

    def enqueue(self, draft_id, operation):
        signal = threading.Event()
        self.cancellations[draft_id] = signal
        task = asyncio.create_task(asyncio.to_thread(self.work, draft_id, operation, signal))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def work(self, draft_id, operation, signal):
        try:
            with self.factory() as session:
                item = session.get(SuiteDraft, draft_id)
                data = json.loads(item.data_json)
                messages = json.loads(item.messages_json)
            root = self.settings.data_dir / "designer" / draft_id[:8] / uuid.uuid4().hex[:8]
            root.mkdir(parents=True)

            def progress(stage, message):
                with self.factory() as session:
                    item = session.get(SuiteDraft, draft_id)
                    history = json.loads(item.messages_json)
                    if len(history) < 500:
                        history.append({"role": "status", "content": str(message)[:2000]})
                    item.messages_json = canonical_json(history)
                    item.status = "generating"
                    session.commit()

            if operation == "generate":
                provider = DESIGNER_PROVIDERS[data.get("generator_provider", "chrys")]()
                data, reply = provider.generate(
                    self.settings, data, messages, root, progress, signal.is_set
                )
                validation = validate_draft(
                    self.settings, data, root / "validation", run_scripts=False
                )
            else:
                validation = validate_draft(
                    self.settings,
                    data,
                    root / "validation",
                    run_scripts=True,
                    is_cancelled=signal.is_set,
                )
                reply = (
                    "结构校验完成；验证脚本可运行，断言有效性待确认。"
                    if validation["scripts_runnable"]
                    else "结构校验通过，但部分脚本不能运行，请查看校验明细。"
                )
            if signal.is_set():
                raise ValueError("任务已停止")
            with self.factory() as session:
                item = session.get(SuiteDraft, draft_id)
                history = json.loads(item.messages_json)
                history.append({"role": "assistant", "content": reply})
                item.messages_json = canonical_json(history)
                item.data_json = canonical_json(data)
                item.validation_json = canonical_json(validation)
                item.revision += 1
                item.status = "ready"
                session.commit()
        except Exception as exc:
            with self.factory() as session:
                item = session.get(SuiteDraft, draft_id)
                item.status = "failed"
                item.error = str(exc)[:3000]
                session.commit()
        finally:
            self.cancellations.pop(draft_id, None)


def build_benchmark_router(settings, factory, dependency, orchestrator, jobs, designer):
    router = APIRouter(prefix="/api/v1/benchmark")

    @router.get("/directories")
    def directories(path: str = ""):
        if not path and os.name == "nt":
            return {
                "path": "",
                "parent": None,
                "items": [
                    {"name": f"{letter}:\\", "path": f"{letter}:\\"}
                    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                    if Path(f"{letter}:\\").is_dir()
                ],
            }
        root = Path(path).expanduser().resolve() if path else Path.home()
        if not root.is_dir():
            raise EvalError("DIRECTORY_NOT_FOUND", "目录不存在", status_code=404)
        try:
            children = sorted(
                (p for p in root.iterdir() if p.is_dir() and not p.is_symlink()),
                key=lambda p: p.name.casefold(),
            )
        except OSError as exc:
            raise EvalError("DIRECTORY_UNREADABLE", "无法读取目录", status_code=422) from exc
        return {
            "path": str(root),
            "parent": str(root.parent) if root.parent != root else None,
            "items": [{"name": p.name, "path": str(p)} for p in children[:1000]],
        }

    def suite(session, key):
        item = session.get(Suite, key)
        if item is None:
            raise EvalError("SUITE_NOT_FOUND", "测试套不存在", status_code=404)
        return item

    def draft(session, key, revision=None):
        item = session.get(SuiteDraft, key)
        if item is None:
            raise EvalError("DRAFT_NOT_FOUND", "草稿不存在", status_code=404)
        if revision is not None and (
            item.revision != revision or item.status in BUSY or item.status == "saved"
        ):
            raise EvalError(
                "DRAFT_CONFLICT", "草稿正在处理、已保存或已更新，请刷新", status_code=409
            )
        return item

    def claim(session, item, **values):
        result = session.execute(
            update(SuiteDraft)
            .where(
                SuiteDraft.id == item.id,
                SuiteDraft.revision == item.revision,
                SuiteDraft.status.not_in([*BUSY, "saved"]),
            )
            .values(**values, revision=item.revision + 1)
        )
        if result.rowcount != 1:
            raise EvalError("DRAFT_CONFLICT", "草稿已更新，请刷新", status_code=409)
        session.flush()
        session.refresh(item)

    def suite_view(session, item):
        experiments = session.scalars(
            select(Experiment)
            .where(Experiment.suite_id == item.id)
            .order_by(Experiment.created_at.desc())
        ).all()
        latest = experiments[0] if experiments else None
        baseline = (
            session.get(Experiment, item.baseline_experiment_id)
            if item.baseline_experiment_id
            else None
        )
        return {
            **_suite_payload(item),
            "archived": item.archived,
            "locked": True,
            "baseline_experiment_id": item.baseline_experiment_id,
            "baseline_group": item.baseline_group,
            "baseline": (
                {**_experiment_summary(baseline), "selected_group": item.baseline_group}
                if baseline
                else None
            ),
            "latest": _experiment_summary(latest) if latest else None,
            "comparison": comparison(latest, baseline, item.baseline_group),
            "execution_count": len(experiments),
        }

    @router.get("/agents")
    def agents():
        items = []
        for key, factory in {"chrys": ChrysRuntime, **RUNTIME_FACTORIES}.items():
            info = factory(settings).payload(ensure_profiles=True)
            items.append(
                {
                    "id": key,
                    "name": "Chrys" if key == "chrys" else key,
                    "roles": ["runner", "judge"]
                    + (["designer"] if key in DESIGNER_PROVIDERS else []),
                    "available": info.get("available", False),
                    "version": info.get("version"),
                    "error": info.get("error"),
                    "models": [
                        {field: model.get(field) for field in ("id", "name", "active", "modelId")}
                        for model in info.get("models", [])
                    ],
                }
            )
        return {"items": items}

    @router.get("/suites")
    def suites(session=Depends(dependency)):
        return {
            "items": [
                suite_view(session, item)
                for item in session.scalars(select(Suite).order_by(Suite.created_at.desc())).all()
            ]
        }

    @router.get("/suites/{key}")
    def suite_detail(key: str, session=Depends(dependency)):
        item = suite(session, key)
        return {
            **suite_view(session, item),
            "definition": suite_definition(item),
            "experiments": [
                _experiment_summary(exp)
                for exp in session.scalars(
                    select(Experiment)
                    .where(Experiment.suite_id == key)
                    .order_by(Experiment.created_at.desc())
                ).all()
            ],
        }

    @router.post("/suites/{key}/archive")
    def archive(key: str, request: ArchiveInput, session=Depends(dependency)):
        item = suite(session, key)
        if request.archived and session.scalar(
            select(Experiment.id).where(Experiment.suite_id == key, Experiment.status.in_(ACTIVE))
        ):
            raise EvalError("SUITE_RUNNING", "请先停止当前执行，再归档测试套", status_code=409)
        item.archived = request.archived
        session.commit()
        return suite_view(session, item)

    @router.post("/suites/{key}/baseline")
    def baseline(key: str, request: BaselineInput, session=Depends(dependency)):
        item = suite(session, key)
        if request.experiment_id:
            exp = session.get(Experiment, request.experiment_id)
            if (
                not exp
                or exp.suite_id != key
                or not baseline_ready(_experiment_summary(exp), request.group)
            ):
                raise EvalError(
                    "INVALID_BASELINE",
                    "请选择本测试套 Trial 齐全、有得分且门禁通过的结果组",
                    status_code=422,
                )
        item.baseline_experiment_id = request.experiment_id
        item.baseline_group = request.group if request.experiment_id else "current"
        session.commit()
        return suite_view(session, item)

    @router.post("/suites/{key}/execute", status_code=202)
    async def execute(key: str, request: ExecuteInput, session=Depends(dependency)):
        suite(session, key)
        if any(
            provider not in {"chrys", *RUNTIME_FACTORIES}
            for provider in (request.profile.runner_provider, request.profile.judge_provider)
        ):
            raise EvalError("UNSUPPORTED_AGENT", "新流程仅提供 Chrys Agent", status_code=422)
        if session.scalar(
            select(Experiment.id).where(Experiment.suite_id == key, Experiment.status.in_(ACTIVE))
        ):
            raise EvalError("SUITE_RUNNING", "测试套已有正在执行的任务", status_code=409)
        exp = orchestrator.create(
            ExperimentCreateRequest(
                suite_id=key,
                profile=request.profile,
                mode=request.mode,
                evaluation_mode="current_only",
            )
        )
        await jobs.enqueue(exp.id)
        return {"id": exp.id}

    @router.get("/suites/{key}/comparison/{experiment_id}")
    def compare(key: str, experiment_id: str, session=Depends(dependency)):
        item = suite(session, key)
        exp = session.get(Experiment, experiment_id)
        if not exp or exp.suite_id != key:
            raise EvalError("EXPERIMENT_NOT_FOUND", "执行记录不存在", status_code=404)
        base = (
            session.get(Experiment, item.baseline_experiment_id)
            if item.baseline_experiment_id
            else None
        )
        return comparison(exp, base, item.baseline_group)

    @router.get("/drafts")
    def drafts(session=Depends(dependency)):
        return {
            "items": [
                draft_payload(item)
                for item in session.scalars(
                    select(SuiteDraft)
                    .where(SuiteDraft.status != "saved")
                    .order_by(SuiteDraft.updated_at.desc())
                ).all()
            ]
        }

    @router.post("/drafts", status_code=201)
    def create_draft(request: DraftInput, session=Depends(dependency)):
        if len(canonical_json(request.data).encode()) > 30 * 1024 * 1024:
            raise EvalError("DRAFT_TOO_LARGE", "草稿超过30MB", status_code=422)
        item = SuiteDraft(data_json=canonical_json(request.data))
        session.add(item)
        session.commit()
        return draft_payload(item)

    @router.get("/drafts/{key}")
    def get_draft(key: str, session=Depends(dependency)):
        return draft_payload(draft(session, key))

    @router.put("/drafts/{key}")
    def edit_draft(key: str, request: DraftInput, session=Depends(dependency)):
        item = draft(session, key, request.revision if request.revision is not None else -1)
        if len(canonical_json(request.data).encode()) > 30 * 1024 * 1024:
            raise EvalError("DRAFT_TOO_LARGE", "草稿超过30MB", status_code=422)
        claim(
            session,
            item,
            data_json=canonical_json(request.data),
            validation_json="{}",
            error=None,
            status="draft",
        )
        session.commit()
        return draft_payload(item)

    @router.post("/drafts/{key}/generate", status_code=202)
    async def generate(key: str, request: MessageInput, session=Depends(dependency)):
        item = draft(session, key, request.revision)
        data = json.loads(item.data_json)
        if data.get("generator_provider", "chrys") not in DESIGNER_PROVIDERS:
            raise EvalError("UNSUPPORTED_AGENT", "生成 Agent 尚未接入", status_code=422)
        if not all(
            data.get(name)
            for name in ("project_path", "skill_path", "generator_model", "dimensions")
        ):
            raise EvalError(
                "MISSING_CONFIG", "请填写项目、Skill、生成模型并选择维度", status_code=422
            )
        history = json.loads(item.messages_json)
        history.append({"role": "user", "content": request.message})
        claim(session, item, messages_json=canonical_json(history), status="analyzing", error=None)
        session.commit()
        designer.enqueue(key, "generate")
        return draft_payload(item)

    @router.post("/drafts/{key}/validate", status_code=202)
    async def validate(key: str, request: RevisionInput, session=Depends(dependency)):
        item = draft(session, key, request.revision)
        compile_draft(json.loads(item.data_json))
        claim(session, item, status="validating", error=None)
        session.commit()
        designer.enqueue(key, "validate")
        return draft_payload(item)

    @router.post("/drafts/{key}/save", status_code=201)
    def save(key: str, request: RevisionInput, session=Depends(dependency)):
        item = draft(session, key, request.revision)
        data = json.loads(item.data_json)
        validation = json.loads(item.validation_json)
        if (
            validation.get("definition_hash") != content_hash(data)
            or not validation.get("scripts_checked")
            or not validation.get("scripts_runnable")
        ):
            raise EvalError(
                "VALIDATION_REQUIRED", "请先完成隔离校验，并修复不能运行的脚本", status_code=422
            )
        claim(session, item, status="saved")
        created = create_suite(session, settings, compile_draft(data), commit=False)
        item.suite_id = created.id
        item.status = "saved"
        session.commit()
        return suite_view(session, created)

    @router.post("/drafts/{key}/cancel", status_code=202)
    async def cancel_draft(key: str, session=Depends(dependency)):
        item = draft(session, key)
        if key in designer.cancellations:
            designer.cancellations[key].set()
        return {**draft_payload(item), "cancel_requested": True}

    @router.post("/suites/{key}/copy", status_code=201)
    def copy(key: str, session=Depends(dependency)):
        item = suite(session, key)
        source = session.scalar(
            select(SuiteDraft).where(SuiteDraft.suite_id == key, SuiteDraft.status == "saved")
        )
        if source:
            data = json.loads(source.data_json)
            data["name"] = item.name + " 副本"
            created = SuiteDraft(data_json=canonical_json(data))
            session.add(created)
            session.commit()
            return draft_payload(created)
        definition = suite_definition(item)
        # Preserve canonical checks by reconstructing portable per-dimension source packages.
        import base64

        from .services.catalog.designer import package_from_documents

        packages = {}
        for dimension in definition.get("dimensions", []):
            cases, assets = [], {}
            for original in definition["cases"]:
                own = [g for g in original["graders"] if g.get("dimension_id") == dimension["id"]]
                if not own:
                    continue
                case = deepcopy(original)
                case["files"] = {}
                case["graders"] = []
                for file in original.get("files", []):
                    source = f"{case['id']}/scene/{file['path']}"
                    assets[source] = base64.b64decode(file["content_base64"]).decode()
                    case["files"][file["path"]] = source
                for g in own:
                    if g["type"] == "llm_rubric":
                        continue
                    grader = {
                        name: g[name]
                        for name in (
                            "type",
                            "command",
                            "result_format",
                            "checkpoint_ids",
                            "setup_commands",
                            "timeout_seconds",
                        )
                        if name in g
                    }
                    grader["files"] = []
                    for file in g.get("files", []):
                        assets[file["path"]] = base64.b64decode(file["content_base64"]).decode()
                        grader["files"].append(file["path"])
                    case["graders"].append(grader)
                case["weight"] = original.get("dimension_weights", {}).get(dimension["id"], 1)
                case.pop("dimension_weights", None)
                cases.append(case)
            packages[dimension["id"]] = package_from_documents(
                dimension["id"], {"cases": cases}, assets
            )
        if not packages:
            raise EvalError(
                "LEGACY_COPY", "旧版自由评分套件请通过固定维度重新创建", status_code=422
            )
        data = {
            "name": item.name + " 副本",
            "project_path": item.project_path,
            "skill_path": item.skill.source_path,
            "requirement": "",
            "setup": definition.get("setup", {}),
            "dimensions": definition["dimensions"],
            "packages": packages,
            "generator_provider": "chrys",
            "generator_model": "",
        }
        created = SuiteDraft(data_json=canonical_json(data))
        session.add(created)
        session.commit()
        return draft_payload(created)

    @router.post("/package-documents")
    def package_documents(request: dict):
        try:
            return documents_from_package(request["package"], request["dimension_id"])
        except (ValueError, KeyError, UnicodeError) as exc:
            raise EvalError("INVALID_PACKAGE_DOCUMENTS", str(exc), status_code=422) from exc

    return router
