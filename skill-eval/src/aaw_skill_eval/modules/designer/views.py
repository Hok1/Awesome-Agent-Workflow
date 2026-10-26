from __future__ import annotations

import base64
import json

from aaw_skill_eval.errors import EvalError
from aaw_skill_eval.modules.designer.packages import compile_draft as _compile_draft
from aaw_skill_eval.modules.results.views import _iso
from aaw_skill_eval.standards import get_dimension


def compile_draft(data):
    try:
        return _compile_draft(data)
    except (ValueError, KeyError, TypeError) as exc:
        raise EvalError("INVALID_DRAFT", str(exc), status_code=422) from exc


def draft_payload(item):
    data = json.loads(item.data_json)
    workflow = json.loads(item.workflow_json)
    preview, preview_error = None, None
    if data.get("packages") and data.get("dimensions"):
        try:
            definition = _compile_draft(data).model_dump(mode="json")
            preview = {
                "dimensions": [
                    {**get_dimension("workflow", dim["id"]), **dim}
                    for dim in definition["dimensions"]
                ],
                "cases": definition["cases"],
            }
        except (ValueError, KeyError, TypeError, EvalError) as exc:
            preview_error = str(exc)[:2000]
    if not preview and workflow.get("plan"):
        plan = workflow["plan"]
        preview = {
            "dimensions": [
                {**get_dimension("workflow", dim["id"]), **dim} for dim in plan["dimensions"]
            ],
            "cases": [
                {
                    **case,
                    "files": [
                        {"path": path, "content_base64": base64.b64encode(text.encode()).decode()}
                        for path, text in case.get("references", {}).items()
                    ],
                    "graders": [
                        {
                            "id": f"pending-{dim['id']}",
                            "dimension_id": dim["id"],
                            "name": get_dimension("workflow", dim["id"])["name"],
                            "pending": True,
                        }
                        for dim in plan["dimensions"]
                    ],
                }
                for case in plan["cases"]
            ],
        }
        preview_error = None
    return {
        "id": item.id,
        "data": data,
        "preview": preview,
        "preview_error": preview_error,
        "workflow": workflow,
        "messages": json.loads(item.messages_json),
        "validation": json.loads(item.validation_json),
        "revision": item.revision,
        "status": item.status,
        "error": item.error,
        "suite_id": item.suite_id,
        "created_at": _iso(item.created_at),
        "updated_at": _iso(item.updated_at),
    }
