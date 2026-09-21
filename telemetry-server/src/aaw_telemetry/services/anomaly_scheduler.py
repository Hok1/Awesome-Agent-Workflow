from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from ..config import ProjectRegistry, Settings
from .anomalies import AnomalyService

logger = logging.getLogger("aaw_telemetry.anomalies")


class AnomalyScheduler:
    def __init__(self, session_factory, settings: Settings, projects: ProjectRegistry):
        self.session_factory = session_factory
        self.settings = settings
        self.projects = projects
        self._stop = asyncio.Event()
        self.task: asyncio.Task | None = None

    def start(self) -> asyncio.Task:
        self.task = asyncio.create_task(self.run(), name="anomaly-scheduler")
        return self.task

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(self._scan)
            except Exception:
                logger.exception("异常规则定时检测失败", extra={"event": "anomaly.scan_failed"})
            with suppress(TimeoutError):
                await asyncio.wait_for(
                    self._stop.wait(), timeout=self.settings.anomaly_scan_interval_seconds
                )

    def _scan(self) -> None:
        with self.session_factory() as session:
            result = AnomalyService(session, self.projects).evaluate()
        if result["rules"]:
            logger.info(
                "异常规则检测完成",
                extra={
                    "event": "anomaly.scan_completed",
                    "rule_count": result["rules"],
                    "match_count": result["matches"],
                },
            )
