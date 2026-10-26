from __future__ import annotations

import json

from fastapi import APIRouter, Depends

from aaw_skill_eval.contracts.http import ConversationInput, RevisionInput, SuggestionInput
from aaw_skill_eval.errors import EvalError
from aaw_skill_eval.infrastructure.storage.artifacts import canonical_json
from aaw_skill_eval.modules.designer.views import compile_draft, draft_payload
from aaw_skill_eval.modules.suites.access import claim, draft

BUSY = {"analyzing", "generating", "validating", "discussing"}
ACTIVE = {"queued", "preparing", "running"}


def build_router(settings, factory, dependency, orchestrator, jobs, designer):
    router = APIRouter(prefix="/api/v1/benchmark")

    @router.post("/drafts/{key}/messages", status_code=202)
    async def conversation(key: str, request: ConversationInput, session=Depends(dependency)):
        draft(session, key)
        designer.flow.submit(key, request.message, request.revision, request.mode)
        session.expire_all()
        return draft_payload(draft(session, key))

    @router.post("/drafts/{key}/suggestions/{suggestion_id}")
    async def suggestion(
        key: str, suggestion_id: str, request: SuggestionInput, session=Depends(dependency)
    ):
        item = draft(session, key)
        flow = json.loads(item.workflow_json)
        selected = next(
            (s for s in flow.get("plan", {}).get("suggestions", []) if s["id"] == suggestion_id),
            None,
        )
        if not selected:
            raise EvalError("SUGGESTION_NOT_FOUND", "建议不存在", status_code=404)
        if request.action == "adopt":
            with designer.flow.lock:
                designer.flow.submit(
                    key, f"请修改用例，明确采纳以下要求：{selected['text']}", request.revision
                )
                session.refresh(item)
                flow = json.loads(item.workflow_json)
                for entry in flow["plan"]["suggestions"]:
                    if entry["id"] == suggestion_id:
                        entry["status"] = "adopted"
                item.workflow_json = canonical_json(flow)
                session.commit()
            session.expire_all()
            return draft_payload(draft(session, key))
        with designer.flow.lock:
            session.refresh(item)
            if item.revision != request.revision or item.status == "saved":
                raise EvalError("DRAFT_CONFLICT", "草稿已更新，请刷新", status_code=409)
            flow = json.loads(item.workflow_json)
            for entry in flow["plan"]["suggestions"]:
                if entry["id"] == suggestion_id:
                    entry["status"] = "ignored"
            item.workflow_json = canonical_json(flow)
            item.revision += 1
            session.commit()
        return draft_payload(item)

    @router.post("/drafts/{key}/validate", status_code=202)
    async def validate(key: str, request: RevisionInput, session=Depends(dependency)):
        item = draft(session, key, request.revision)
        if json.loads(item.workflow_json).get("plan"):
            designer.flow.submit(key, "重新配置并校验未完成的评价方式", request.revision, "retry")
            session.expire_all()
            return draft_payload(draft(session, key))
        compile_draft(json.loads(item.data_json))
        claim(session, item, status="validating", error=None)
        session.commit()
        designer.enqueue(key, "validate")
        return draft_payload(item)

    @router.post("/drafts/{key}/cancel", status_code=202)
    async def cancel_draft(key: str, session=Depends(dependency)):
        item = draft(session, key)
        if key in designer.cancellations:
            designer.cancellations[key].set()
        if item.status == "saved":
            raise EvalError("DRAFT_CONFLICT", "已锁定的测试套不能停止", status_code=409)
        designer.flow.cancel(key)
        session.expire_all()
        item = draft(session, key)
        return {**draft_payload(item), "cancel_requested": True}

    return router
