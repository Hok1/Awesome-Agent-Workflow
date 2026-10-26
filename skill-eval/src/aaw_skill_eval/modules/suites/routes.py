from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from sqlalchemy import select

from aaw_skill_eval.contracts.entities import Experiment, Suite, SuiteDraft
from aaw_skill_eval.contracts.http import ArchiveInput, CaseEditInput, DraftInput, RevisionInput
from aaw_skill_eval.errors import EvalError
from aaw_skill_eval.infrastructure.storage.artifacts import canonical_json, content_hash
from aaw_skill_eval.modules.designer.packages import documents_from_package, package_from_documents
from aaw_skill_eval.modules.designer.views import compile_draft, draft_payload
from aaw_skill_eval.modules.results.suites import suite_view
from aaw_skill_eval.modules.results.views import _experiment_summary
from aaw_skill_eval.modules.suites.access import claim, draft, suite
from aaw_skill_eval.modules.suites.copying import draft_from_definition
from aaw_skill_eval.modules.suites.service import create_suite, suite_definition

BUSY = {"analyzing", "generating", "validating", "discussing"}
ACTIVE = {"queued", "preparing", "running"}


def build_router(settings, factory, dependency, orchestrator, jobs, designer):
    router = APIRouter(prefix="/api/v1/benchmark")

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
        old_data = json.loads(item.data_json)
        keys = ("project_path", "skill_path", "requirement", "case_mode", "dimensions", "packages")
        if any(old_data.get(k) != request.data.get(k) for k in keys):
            item.workflow_json = "{}"
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

    @router.patch("/drafts/{key}/cases/{case_id}")
    def edit_case(key: str, case_id: str, request: CaseEditInput, session=Depends(dependency)):
        item = draft(session, key, request.revision)
        data = json.loads(item.data_json)
        found = False
        for dimension_id, package in data.get("packages", {}).items():
            documents = documents_from_package(package, dimension_id)
            changed = False
            for case in documents["manifest"]["cases"]:
                if case["id"] == case_id:
                    case.update(request.model_dump(exclude={"revision"}))
                    changed = found = True
            if changed:
                data["packages"][dimension_id] = package_from_documents(
                    dimension_id, documents["manifest"], documents["assets"]
                )
        flow = json.loads(item.workflow_json)
        if flow.get("plan"):
            for case in flow["plan"]["cases"]:
                if case["id"] == case_id:
                    case.update(request.model_dump(exclude={"revision"}))
                    found = True
        if not found:
            raise EvalError("CASE_NOT_FOUND", "用例不存在", status_code=404)
        if not flow.get("plan"):
            compile_draft(data)
        if flow.get("plan"):
            for case in flow["plan"]["cases"]:
                if case["id"] == case_id:
                    case.update(request.model_dump(exclude={"revision"}))
            for state in flow.get("dimensions", {}).values():
                state.update(status="pending", detail="任务已修改，需要重新配置检查")
            flow.update(
                stage="evaluation", status="waiting", detail="任务已修改，请重新配置评价方式"
            )
            item.workflow_json = canonical_json(flow)
        claim(
            session,
            item,
            data_json=canonical_json(data),
            validation_json="{}",
            error=None,
            status="draft",
        )
        session.commit()
        return draft_payload(item)

    @router.post("/drafts/{key}/save", status_code=201)
    def save(key: str, request: RevisionInput, session=Depends(dependency)):
        item = draft(session, key, request.revision)
        data = json.loads(item.data_json)
        validation = json.loads(item.validation_json)
        if data.get("migration_review", {}).get("required") and not data["migration_review"].get(
            "confirmed"
        ):
            raise EvalError(
                "REVIEW_REQUIRED", "请先确认已审查通用任务和独立合规要求", status_code=422
            )
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
        data = draft_from_definition(suite_definition(item))
        data["name"] = item.name + " 副本"
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
