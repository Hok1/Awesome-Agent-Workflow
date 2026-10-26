"""Revision-fenced staged designer jobs. Superseded workers cannot publish old results."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from datetime import UTC, datetime

from aaw_skill_eval.contracts.entities import SuiteDraft
from aaw_skill_eval.contracts.providers import DESIGNERS as FLOW_PROVIDERS
from aaw_skill_eval.errors import EvalError
from aaw_skill_eval.infrastructure.storage.artifacts import canonical_json
from aaw_skill_eval.modules.designer.packages import validate_draft
from aaw_skill_eval.modules.designer.planning import (
    DesignUnavailable,
    existing_plan,
    normalize_plan,
    package_for_dimension,
    project_summary,
)
from aaw_skill_eval.standards import get_dimension


def now():
    return datetime.now(UTC).isoformat()


class StagedDesignerJobs:
    def __init__(self, settings, factory):
        self.settings, self.factory = settings, factory
        self.lock = threading.RLock()
        self.tasks = set()
        self.interactions = {}
        self.operations = {}

    def _spawn(self, target, *args):
        task = asyncio.create_task(asyncio.to_thread(target, *args))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def stop(self):
        for event in [*self.interactions.values(), *self.operations.values()]:
            event.set()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)

    def submit(self, key, message, revision, mode="auto"):
        with self.lock, self.factory() as session:
            item = session.get(SuiteDraft, key)
            if not item or item.status == "saved":
                raise EvalError("DRAFT_CONFLICT", "草稿不存在或已锁定", status_code=409)
            if revision != item.revision:
                raise EvalError("DRAFT_CONFLICT", "配置已更新，请刷新后重试", status_code=409)
            data = json.loads(item.data_json)
            if not data.get("generator_model"):
                raise EvalError("MISSING_CONFIG", "请选择生成 Agent 模型", status_code=422)
            if mode in {"generate", "retry"} and not all(data.get(k) for k in ("project_path",)):
                raise EvalError("MISSING_CONFIG", "生成前请填写项目路径", status_code=422)
            event = threading.Event()
            if key in self.interactions:
                self.interactions[key].set()
            self.interactions[key] = event
            request_id = uuid.uuid4().hex
            flow = json.loads(item.workflow_json)
            flow["interaction"] = {
                "id": request_id,
                "status": "running",
                "started_at": now(),
                "mode": mode,
            }
            if (key not in self.operations or self.operations[key].is_set()) and mode in {
                "generate",
                "retry",
            }:
                flow.update(
                    stage="analysis",
                    status="running",
                    started_at=now(),
                    stage_started_at=now(),
                    ended_at=None,
                    detail="读取固定提交的项目摘要与 Skill 入口",
                    history=[{"stage": "analysis", "started_at": now(), "status": "running"}],
                )
            history = json.loads(item.messages_json)
            history.append({"role": "user", "content": message, "at": now()})
            item.messages_json = canonical_json(history)
            item.workflow_json = canonical_json(flow)
            if key not in self.operations or self.operations[key].is_set():
                item.status = "discussing"
            item.error = None
            item.revision += 1
            session.commit()
        self._spawn(self._conversation, key, request_id, event, mode)

    def cancel(self, key):
        with self.lock, self.factory() as session:
            for collection in (self.operations, self.interactions):
                if key in collection:
                    collection[key].set()
            item = session.get(SuiteDraft, key)
            if item and item.status != "saved":
                flow = json.loads(item.workflow_json)
                flow["operation_id"] = uuid.uuid4().hex
                flow["status"] = "cancelled"
                flow["detail"] = "任务已停止，已有草案和完成的检查已保留"
                flow["ended_at"] = now()
                if flow.get("history") and not flow["history"][-1].get("ended_at"):
                    flow["history"][-1].update(ended_at=now(), status="cancelled")
                if flow.get("interaction"):
                    flow["interaction"].update(status="cancelled", ended_at=now())
                item.workflow_json = canonical_json(flow)
                item.status = "draft"
                item.revision += 1
                session.commit()

    def _conversation(self, key, request_id, event, mode):
        # Keep nested Git checkouts within Windows' common path limit.
        root = self.settings.data_dir / "design-flow" / request_id[:12]
        root.mkdir(parents=True)
        started = now()
        try:
            with self.factory() as session:
                item = session.get(SuiteDraft, key)
                data = json.loads(item.data_json)
                flow = json.loads(item.workflow_json)
                messages = json.loads(item.messages_json)
            provider = FLOW_PROVIDERS[data.get("generator_provider", "chrys")]()
            previous = flow.get("plan") or existing_plan(data)
            summary = {}
            if data.get("project_path"):
                summary = project_summary(data)
                (root / "summary.json").write_text(canonical_json(summary), encoding="utf-8")
            analyzed = now()
            if mode in {"generate", "retry"}:
                with self.lock, self.factory() as session:
                    item = session.get(SuiteDraft, key)
                    current = json.loads(item.workflow_json)
                    if event.is_set() or current.get("interaction", {}).get("id") != request_id:
                        return
                    if current.get("stage") == "analysis":
                        current["history"][-1].update(ended_at=analyzed, status="completed")
                        current["history"].append(
                            {"stage": "design", "started_at": analyzed, "status": "running"}
                        )
                        current.update(
                            stage="design",
                            stage_started_at=analyzed,
                            detail="设计完整任务、预期结果与固定评价维度；不等待脚本",
                        )
                        item.workflow_json = canonical_json(current)
                        session.commit()
            if mode == "retry" and previous:
                decision = {**previous, "action": "update", "message": "重试未完成的评价方式"}
            else:
                decision = provider.plan(
                    self.settings,
                    data,
                    summary,
                    previous,
                    messages,
                    root / "design",
                    lambda stage, text: self._interaction_progress(key, request_id, text),
                    event.is_set,
                    mode=mode,
                )
            if event.is_set():
                return
            action = decision.get("action", "discuss")
            if action not in {"discuss", "generate", "update"}:
                raise ValueError("未知的对话操作")
            plan = normalize_plan(decision, data) if action != "discuss" else None
            with self.lock, self.factory() as session:
                item = session.get(SuiteDraft, key)
                flow = json.loads(item.workflow_json)
                if flow.get("interaction", {}).get("id") != request_id or event.is_set():
                    return
                flow["interaction"].update(status="completed", ended_at=now())
                history = json.loads(item.messages_json)
                history.append(
                    {
                        "role": "assistant",
                        "content": str(decision.get("message", ""))[:10000],
                        "at": now(),
                    }
                )
                item.messages_json = canonical_json(history)
                if action == "discuss":
                    if key not in self.operations or self.operations[key].is_set():
                        item.status = (
                            "ready"
                            if json.loads(item.validation_json).get("scripts_runnable")
                            else "draft"
                        )
                    item.workflow_json = canonical_json(flow)
                    item.revision += 1
                    session.commit()
                    return
                if not summary:
                    raise ValueError("生成前需要项目和 Skill 路径；讨论内容已保留")
                latest = json.loads(item.data_json)
                previous = flow.get("plan") or existing_plan(latest)
                same_tasks = previous and canonical_json(previous["cases"]) == canonical_json(
                    plan["cases"]
                )
                old_dims = {d["id"]: d for d in previous.get("dimensions", [])} if previous else {}
                requested = set(decision.get("affected_dimension_ids", []))
                selected = [d["id"] for d in plan["dimensions"]]
                confirmed = (
                    {
                        s["text"]: s["status"]
                        for s in previous.get("suggestions", [])
                        if s.get("status") in {"ignored", "adopted"}
                    }
                    if previous
                    else {}
                )
                for suggestion in plan["suggestions"]:
                    if suggestion["text"] in confirmed:
                        suggestion["status"] = confirmed[suggestion["text"]]
                packages = {d: p for d, p in latest.get("packages", {}).items() if d in selected}
                states = flow.get("dimensions", {})
                if same_tasks:
                    affected = requested | {
                        d["id"] for d in plan["dimensions"] if d != old_dims.get(d["id"])
                    }
                    affected |= {
                        d
                        for d in selected
                        if d not in packages or states.get(d, {}).get("status") != "ready"
                    }
                else:
                    affected = set(selected)
                for d in affected:
                    packages.pop(d, None)
                if key in self.operations:
                    self.operations[key].set()
                signal = threading.Event()
                self.operations[key] = signal
                op = uuid.uuid4().hex
                flow.update(
                    operation_id=op,
                    plan=plan,
                    stage="evaluation",
                    status="running",
                    started_at=started,
                    stage_started_at=now(),
                    last_activity_at=now(),
                    detail="草案已展示，正在逐项配置评价方式",
                    ended_at=None,
                    dimensions={
                        d: states.get(d, {}) if d not in affected else {"status": "pending"}
                        for d in selected
                    },
                    history=[
                        {
                            "stage": "analysis",
                            "started_at": started,
                            "ended_at": analyzed,
                            "status": "completed",
                        },
                        {
                            "stage": "design",
                            "started_at": analyzed,
                            "ended_at": now(),
                            "status": "completed",
                        },
                        {"stage": "evaluation", "started_at": now(), "status": "running"},
                    ],
                )
                latest["dimensions"] = [
                    {k: d[k] for k in ("id", "weight", "pass_score", "hard_gate")}
                    for d in plan["dimensions"]
                ]
                latest["dimension_reasons"] = {d["id"]: d["reason"] for d in plan["dimensions"]}
                latest["packages"] = packages
                item.data_json = canonical_json(latest)
                item.validation_json = "{}"
                item.workflow_json = canonical_json(flow)
                item.status = "generating"
                item.revision += 1
                session.commit()
            try:
                self._evaluate(key, op, signal, provider, summary, plan, root, affected)
            finally:
                signal.set()
        except Exception as exc:
            with self.lock, self.factory() as session:
                item = session.get(SuiteDraft, key)
                flow = json.loads(item.workflow_json)
                if flow.get("interaction", {}).get("id") != request_id or event.is_set():
                    return
                flow["interaction"].update(status="failed", ended_at=now(), detail=str(exc)[:2000])
                if key not in self.operations or self.operations[key].is_set():
                    item.status = "failed"
                    flow.update(status="failed", detail=str(exc)[:2000], ended_at=now())
                    if flow.get("history") and not flow["history"][-1].get("ended_at"):
                        flow["history"][-1].update(ended_at=now(), status="failed")
                item.error = str(exc)[:2000]
                item.workflow_json = canonical_json(flow)
                item.revision += 1
                session.commit()

    def _interaction_progress(self, key, request_id, text):
        with self.lock, self.factory() as session:
            item = session.get(SuiteDraft, key)
            flow = json.loads(item.workflow_json)
            if flow.get("interaction", {}).get("id") == request_id:
                flow["interaction"].update(detail=str(text)[:500], last_activity_at=now())
                if flow.get("stage") in {"analysis", "design"} and flow.get("status") == "running":
                    flow.update(detail=str(text)[:500], last_activity_at=now())
                item.workflow_json = canonical_json(flow)
                session.commit()

    def _dimension_progress(self, key, op, dimension_id, text):
        def progress(item, flow, data):
            flow["dimensions"][dimension_id].update(detail=str(text)[:500])
            flow.update(
                detail=f"{get_dimension('workflow', dimension_id)['name']}：{str(text)[:300]}",
                last_activity_at=now(),
            )

        self._publish(key, op, progress)

    def _publish(self, key, op, callback):
        with self.lock, self.factory() as session:
            item = session.get(SuiteDraft, key)
            flow = json.loads(item.workflow_json)
            if flow.get("operation_id") != op or self.operations[key].is_set():
                return False
            data = json.loads(item.data_json)
            callback(item, flow, data)
            item.workflow_json = canonical_json(flow)
            item.data_json = canonical_json(data)
            item.revision += 1
            session.commit()
            return True

    def _evaluate(self, key, op, signal, provider, summary, plan, root, affected):
        for dimension in sorted(
            plan["dimensions"], key=lambda d: get_dimension("workflow", d["id"])["method"] != "llm"
        ):
            dimension_id = dimension["id"]
            if dimension_id not in affected:
                continue
            standard = get_dimension("workflow", dimension_id)
            repair = None
            dimension_started = now()
            for attempt in range(3):
                if signal.is_set():
                    return

                def starting(
                    item,
                    flow,
                    data,
                    dimension_id=dimension_id,
                    attempt=attempt,
                    standard=standard,
                    dimension_started=dimension_started,
                ):
                    flow["dimensions"][dimension_id] = {
                        "status": "generating",
                        "started_at": dimension_started,
                        "attempt": attempt,
                        "detail": "采用平台固定标准"
                        if standard["method"] == "llm"
                        else "生成验证代码",
                    }
                    flow.update(detail=f"{standard['name']}：配置评价方式", last_activity_at=now())

                if not self._publish(key, op, starting):
                    return
                generated = None
                try:
                    with self.factory() as session:
                        data = json.loads(session.get(SuiteDraft, key).data_json)
                    generated = (
                        {}
                        if standard["method"] == "llm"
                        else provider.dimension(
                            self.settings,
                            data,
                            summary,
                            plan,
                            dimension_id,
                            root / dimension_id / str(attempt),
                            lambda stage, text, dimension_id=dimension_id: self._dimension_progress(
                                key, op, dimension_id, text
                            ),
                            signal.is_set,
                            repair=repair,
                        )
                    )
                    package = package_for_dimension(plan, dimension_id, generated)

                    def publishing(item, flow, data, dimension_id=dimension_id, package=package):
                        data.setdefault("packages", {})[dimension_id] = package
                        flow["dimensions"][dimension_id].update(
                            status="validating", detail="试运行验证代码"
                        )

                    if not self._publish(key, op, publishing):
                        return
                    candidate = {
                        **data,
                        "dimensions": [dimension],
                        "packages": {dimension_id: package},
                    }
                    validation = validate_draft(
                        self.settings,
                        candidate,
                        root / f"v-{dimension_id}-{attempt}",
                        run_scripts=True,
                        is_cancelled=signal.is_set,
                        command_timeout_seconds=30,
                    )
                    if not validation["scripts_runnable"]:
                        raise ValueError(canonical_json(validation["checks"])[:5000])

                    def completed(
                        item, flow, data, dimension_id=dimension_id, validation=validation
                    ):
                        flow["dimensions"][dimension_id].update(
                            status="ready",
                            detail="已就绪",
                            ended_at=now(),
                            checks=validation["checks"],
                        )

                    if not self._publish(key, op, completed):
                        return
                    break
                except Exception as exc:
                    if signal.is_set():
                        return
                    retry = attempt < 2 and not isinstance(exc, DesignUnavailable)

                    def failure(
                        item, flow, data, dimension_id=dimension_id, retry=retry, error=str(exc)
                    ):
                        flow["dimensions"][dimension_id].update(
                            status="repairing" if retry else "failed",
                            detail=error[:2000],
                            ended_at=None if retry else now(),
                        )

                    if not self._publish(key, op, failure):
                        return
                    if not retry:
                        break
                    repair = {
                        "error": str(exc)[:4000],
                        "previous": generated,
                    }

        def finish(item, flow, data):
            ready = all(state.get("status") == "ready" for state in flow["dimensions"].values())
            flow.update(
                status="ready" if ready else "failed",
                stage="confirm" if ready else "evaluation",
                ended_at=now(),
                detail="评价方式已就绪，请确认使用"
                if ready
                else "部分检查未完成，可重试失败项或切换模型",
            )
            flow["history"][-1].update(ended_at=now(), status="completed" if ready else "failed")
            item.status = (
                "discussing"
                if flow.get("interaction", {}).get("status") == "running"
                else "ready"
                if ready
                else "failed"
            )
            if ready:
                validation = validate_draft(
                    self.settings, data, root / "structure", run_scripts=False
                )
                validation.update(
                    scripts_checked=True,
                    scripts_runnable=True,
                    checks=[
                        check
                        for state in flow["dimensions"].values()
                        for check in state.get("checks", [])
                    ],
                )
                item.validation_json = canonical_json(validation)
            item.error = None if ready else flow["detail"]
            # Publish completion under the same lock as the final row update so
            # a simultaneous discussion cannot leave the draft marked busy.
            signal.set()

        self._publish(key, op, finish)
