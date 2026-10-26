"""HTTP composition only; business routes belong to their modules."""

from fastapi import APIRouter

from aaw_skill_eval.app import runtime_routes
from aaw_skill_eval.modules.designer import routes as designer_routes
from aaw_skill_eval.modules.evaluations import routes as evaluations
from aaw_skill_eval.modules.executions import commands as execution_commands
from aaw_skill_eval.modules.executions import routes as executions
from aaw_skill_eval.modules.results import commands as result_commands
from aaw_skill_eval.modules.results import routes as results
from aaw_skill_eval.modules.suites import catalog_routes
from aaw_skill_eval.modules.suites import routes as suites


def build_router(*, settings, session_factory, get_session, orchestrator, jobs, designer):
    router = APIRouter()
    router.include_router(execution_commands.build_creation_router(orchestrator, jobs))
    for module in (catalog_routes, executions, results):
        router.include_router(
            module.build_router(
                settings=settings,
                session_factory=session_factory,
                get_session=get_session,
                orchestrator=orchestrator,
                jobs=jobs,
            )
        )
    for module in (
        suites,
        designer_routes,
        execution_commands,
        evaluations,
        result_commands,
        runtime_routes,
    ):
        router.include_router(
            module.build_router(
                settings, session_factory, get_session, orchestrator, jobs, designer
            )
        )
    return router
