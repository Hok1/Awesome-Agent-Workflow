from __future__ import annotations

import logging
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import ProjectRegistry
from ..services.ai_masters import AiMasterService
from ..services.queries import make_filters

logger = logging.getLogger(__name__)


class AiMasterCreate(BaseModel):
    name: str


class AiMasterRename(BaseModel):
    name: str


class AssignmentPayload(BaseModel):
    ai_master_id: uuid.UUID | None = None


def build_ai_masters_router(
    session_dependency,
    projects: ProjectRegistry,
    *,
    prefix: str = "/api/v1",
    workflow_kind: str = "aaw",
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["ai-masters"])

    def filters(
        request: Request,
        from_date: Annotated[date | None, Query(alias="from")] = None,
        to_date: Annotated[date | None, Query(alias="to")] = None,
        repository: Annotated[list[str] | None, Query()] = None,
        user_name: Annotated[list[str] | None, Query()] = None,
        aaw_version: Annotated[list[str] | None, Query()] = None,
        sr: Annotated[list[str] | None, Query()] = None,
        ar: Annotated[list[str] | None, Query()] = None,
    ):
        return make_filters(
            from_date,
            to_date,
            (repository or []) + request.query_params.getlist("project_key"),
            (user_name or []) + request.query_params.getlist("git_user_name"),
            aaw_version or [],
            sr or [],
            ar or [],
            workflow_kind,
        )

    def service(session: Session) -> AiMasterService:
        return AiMasterService(session, projects)

    # Static paths must be declared before the dynamic /{id} routes so FastAPI
    # does not capture "assignments" / "operations" as an id.

    @router.get("/ai-masters/assignments")
    def list_assignments(session: Session = Depends(session_dependency)):
        return service(session).list_assignments()

    @router.get("/ai-masters/operations")
    def operations(
        query=Depends(filters), session: Session = Depends(session_dependency)
    ):
        return service(session).operations(query)

    @router.get("/ai-masters")
    def list_ai_masters(session: Session = Depends(session_dependency)):
        return service(session).list_ai_masters()

    @router.post("/ai-masters", status_code=201)
    def create_ai_master(
        payload: AiMasterCreate, session: Session = Depends(session_dependency)
    ):
        return service(session).create_ai_master(payload.name)

    @router.patch("/ai-masters/{master_id}")
    def rename_ai_master(
        master_id: uuid.UUID,
        payload: AiMasterRename,
        session: Session = Depends(session_dependency),
    ):
        return service(session).rename_ai_master(master_id, payload.name)

    @router.delete("/ai-masters/{master_id}")
    def delete_ai_master(
        master_id: uuid.UUID, session: Session = Depends(session_dependency)
    ):
        return service(session).delete_ai_master(master_id)

    @router.put("/ai-masters/assignments/{component_id}")
    def assign_component(
        component_id: str,
        payload: AssignmentPayload,
        session: Session = Depends(session_dependency),
    ):
        return service(session).assign_component(component_id, payload.ai_master_id)

    @router.get("/ai-masters/{master_id}/components")
    def master_components(
        master_id: uuid.UUID,
        query=Depends(filters),
        session: Session = Depends(session_dependency),
    ):
        return service(session).master_components(master_id, query)

    return router
