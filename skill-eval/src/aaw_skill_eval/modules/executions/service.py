"""单候选执行的创建、准备、Trial 调度与停止。评分由独立模块负责。"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from aaw_skill_eval.config import Settings
from aaw_skill_eval.contracts.entities import Experiment, Run
from aaw_skill_eval.contracts.schemas import ExperimentCreateRequest
from aaw_skill_eval.modules.executions import execution, prepare


class ExperimentOrchestrator:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        *,
        runner=None,
        judge=None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.runner = runner
        self.judge = judge

    def create(self, request: ExperimentCreateRequest) -> Experiment:
        return prepare.create(self.settings, self.session_factory, request)

    def create_retry(self, experiment_id: str, *, refresh_runtime: bool = False) -> Experiment:
        return prepare.create_retry(
            self.session_factory,
            experiment_id,
            settings=self.settings,
            refresh_runtime=refresh_runtime,
        )

    def execute(self, experiment_id: str) -> None:
        return execution.execute(
            self.settings, self.session_factory, self.runner, self.judge, experiment_id
        )

    def request_run_cancel(self, run_id: str) -> Run:
        return execution.request_run_cancel(self.session_factory, run_id)

    def request_experiment_cancel(self, experiment_id: str) -> Experiment:
        return execution.request_experiment_cancel(self.session_factory, experiment_id)
