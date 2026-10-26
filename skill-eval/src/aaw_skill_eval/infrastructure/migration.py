"""Import definitions once, retaining the old database and all historical artifacts."""

import json
import sqlite3

from sqlalchemy import text

from aaw_skill_eval.contracts.entities import SuiteDraft
from aaw_skill_eval.errors import EvalError
from aaw_skill_eval.infrastructure.storage.artifacts import canonical_json
from aaw_skill_eval.modules.suites.copying import draft_from_definition


def import_legacy_definitions(settings, factory):
    source = settings.data_dir / "skill-eval.db"
    with factory() as session:
        session.execute(
            text("CREATE TABLE IF NOT EXISTS migration_versions (version TEXT PRIMARY KEY)")
        )
        if session.execute(
            text("SELECT version FROM migration_versions WHERE version='definitions-v2'")
        ).first():
            return
        if source.is_file():
            with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True) as old:
                old.row_factory = sqlite3.Row
                names = {
                    row[0]
                    for row in old.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                drafts = (
                    [dict(d) for d in old.execute("SELECT * FROM suite_drafts")]
                    if "suite_drafts" in names
                    else []
                )
                suites = (
                    [dict(s) for s in old.execute("SELECT * FROM suites")]
                    if "suites" in names
                    else []
                )
            saved = {d["suite_id"]: d for d in drafts if d.get("suite_id")}
            inputs = []
            for suite in suites:
                definition = json.loads(suite["definition_json"])
                source_draft = saved.get(suite["id"])
                if source_draft:
                    data = json.loads(source_draft["data_json"])
                else:
                    try:
                        data = draft_from_definition(definition)
                    except (ValueError, KeyError, EvalError):
                        data = {
                            "name": suite["name"],
                            "project_path": suite["project_path"],
                            "requirement": definition.get("requirement", ""),
                            "packages": {},
                        }
                data["original_definition"] = definition
                inputs.append((source_draft["id"] if source_draft else suite["id"], data))
            for draft in drafts:
                if not draft.get("suite_id"):
                    inputs.append((draft["id"], json.loads(draft["data_json"])))
            for key, data in inputs:
                data["migration_review"] = {
                    "required": True,
                    "confirmed": False,
                    "notes": [
                        "原测试套与用例内容已保留，请检查业务诉求是否绑定某个 Skill。",
                        "公共判据仅评价交付结果；AAW 流程及 Reviewer 要求应放入独立合规检查。",
                        "确认通用任务和判据后，重新隔离校验并锁定。旧执行与评分保留在旧数据库中。",
                    ],
                }
                data.setdefault("generator_provider", "chrys")
                if not session.get(SuiteDraft, key):
                    session.add(SuiteDraft(id=key, data_json=canonical_json(data), status="draft"))
        session.execute(text("INSERT INTO migration_versions(version) VALUES ('definitions-v2')"))
        session.commit()
