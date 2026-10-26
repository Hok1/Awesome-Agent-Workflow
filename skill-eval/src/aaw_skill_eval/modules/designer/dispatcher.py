from __future__ import annotations

import asyncio
import json
import threading
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from aaw_skill_eval.contracts.entities import SuiteDraft
from aaw_skill_eval.infrastructure.storage.artifacts import canonical_json
from aaw_skill_eval.modules.designer.jobs import StagedDesignerJobs
from aaw_skill_eval.modules.designer.packages import validate_draft

BUSY = {"analyzing", "generating", "validating", "discussing"}
ACTIVE = {"queued", "preparing", "running"}


class DraftJobs:
    def __init__(self, settings, factory):
        self.settings, self.factory = settings, factory
        self.tasks = set()
        self.cancellations = {}
        self.flow = StagedDesignerJobs(settings, factory)

    def recover(self):
        with self.factory() as session:
            for item in session.scalars(select(SuiteDraft).where(SuiteDraft.status.in_(BUSY))):
                item.status = "failed"
                item.error = "服务重启，任务已中断；草稿保留，可重试"
                flow = json.loads(item.workflow_json)
                if flow:
                    ended = datetime.now(UTC).isoformat()
                    flow.update(status="failed", detail=item.error, ended_at=ended)
                    if flow.get("interaction"):
                        flow["interaction"].update(status="failed", ended_at=ended)
                    if flow.get("history") and not flow["history"][-1].get("ended_at"):
                        flow["history"][-1].update(status="failed", ended_at=ended)
                    item.workflow_json = canonical_json(flow)
            session.commit()

    async def stop(self):
        await self.flow.stop()
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
            root = self.settings.data_dir / "designer" / draft_id[:8] / uuid.uuid4().hex[:8]
            root.mkdir(parents=True)

            def progress(stage, message):
                with self.factory() as session:
                    item = session.get(SuiteDraft, draft_id)
                    history = json.loads(item.messages_json)
                    if len(history) < 500:
                        history.append({"role": "status", "content": str(message)[:2000]})
                    item.messages_json = canonical_json(history)
                    item.status = "validating" if stage == "validating" else "generating"
                    session.commit()

            validation = validate_draft(
                self.settings,
                data,
                root / "validation",
                run_scripts=True,
                is_cancelled=signal.is_set,
            )
            reply = "隔离校验完成，请检查任务和判据后确认锁定。"
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
