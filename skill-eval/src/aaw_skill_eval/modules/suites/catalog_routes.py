from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from aaw_skill_eval.contracts.schemas import SuiteCreateRequest
from aaw_skill_eval.errors import EvalError
from aaw_skill_eval.modules.results.views import _suite_payload
from aaw_skill_eval.modules.suites.access import suite
from aaw_skill_eval.modules.suites.packages import (
    PackageImportRequest,
    import_package,
    standard_example_package,
)
from aaw_skill_eval.modules.suites.service import create_suite, suite_definition
from aaw_skill_eval.standards import catalog_payload


def build_router(*, settings, session_factory, get_session, orchestrator, jobs):
    router = APIRouter(prefix="/api/v1")

    @router.post("/suites", status_code=201)
    def import_suite(request: SuiteCreateRequest, session=Depends(get_session)):
        return _suite_payload(create_suite(session, settings, request))

    @router.get("/suites/{suite_id}")
    def definition(suite_id: str, session=Depends(get_session)):
        item = suite(session, suite_id)
        return {**_suite_payload(item), "definition": suite_definition(item)}

    @router.get("/dimension-templates")
    def dimension_templates():
        return catalog_payload()

    @router.post("/suite-packages/preview")
    def preview_package(request: PackageImportRequest):
        return import_package(request, require_standard=True)

    @router.get("/suite-packages/example/{skill_type}/{dimension_id}")
    def download_example(skill_type: str, dimension_id: str, entry: str | None = None):
        try:
            content = standard_example_package(skill_type, dimension_id, entry)
        except ValueError as exc:
            raise EvalError("INVALID_DIMENSION", str(exc), status_code=422) from exc
        return Response(
            content,
            media_type="application/zip",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="skill-eval-{dimension_id}-example.zip"'
                )
            },
        )

    return router
