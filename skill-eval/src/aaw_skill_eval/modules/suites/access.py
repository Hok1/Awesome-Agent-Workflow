from __future__ import annotations

from sqlalchemy import update

from aaw_skill_eval.contracts.entities import Suite, SuiteDraft
from aaw_skill_eval.errors import EvalError

BUSY = {"analyzing", "generating", "validating", "discussing"}
ACTIVE = {"queued", "preparing", "running"}


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
        raise EvalError("DRAFT_CONFLICT", "草稿正在处理、已保存或已更新，请刷新", status_code=409)
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
