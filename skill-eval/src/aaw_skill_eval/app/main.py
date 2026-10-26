from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from aaw_skill_eval.app.api import build_router
from aaw_skill_eval.config import Settings, get_settings
from aaw_skill_eval.errors import EvalError
from aaw_skill_eval.infrastructure.database import (
    Base,
    build_engine,
    build_session_factory,
    session_dependency,
)
from aaw_skill_eval.infrastructure.jobs import JobManager
from aaw_skill_eval.modules.designer.dispatcher import DraftJobs
from aaw_skill_eval.modules.executions.service import ExperimentOrchestrator


def create_app(settings: Settings | None = None, *, engine=None) -> FastAPI:
    from aaw_skill_eval.app.composition import register_defaults

    register_defaults()
    settings = settings or get_settings()
    settings.ensure_directories()
    engine = engine or build_engine(settings)
    Base.metadata.create_all(engine)
    session_factory = build_session_factory(engine)
    from aaw_skill_eval.infrastructure.migration import import_legacy_definitions

    import_legacy_definitions(settings, session_factory)
    get_session = session_dependency(session_factory)
    orchestrator = ExperimentOrchestrator(settings, session_factory)
    jobs = JobManager(session_factory, orchestrator)
    designer = DraftJobs(settings, session_factory)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        designer.recover()
        await jobs.start()
        try:
            yield
        finally:
            await designer.stop()
            await jobs.stop()

    app = FastAPI(
        title="AAW Skill Eval",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.orchestrator = orchestrator
    app.state.jobs = jobs
    app.state.designer = designer
    app.include_router(
        build_router(
            settings=settings,
            session_factory=session_factory,
            get_session=get_session,
            orchestrator=orchestrator,
            jobs=jobs,
            designer=designer,
        )
    )

    static_dir = Path(__file__).resolve().parents[1] / "static"
    app.mount("/assets", StaticFiles(directory=static_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def index():
        built = static_dir / "benchmark" / "index.html"
        return FileResponse(
            built,
            media_type="text/html; charset=utf-8",
        )

    @app.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok"}

    @app.exception_handler(EvalError)
    async def eval_error_handler(_: Request, exc: EvalError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "kind": exc.kind},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=400,
            content={
                "code": "INVALID_REQUEST",
                "message": "; ".join(
                    f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                    for item in exc.errors()
                )[:3000],
                "kind": "invalid",
            },
        )

    return app
