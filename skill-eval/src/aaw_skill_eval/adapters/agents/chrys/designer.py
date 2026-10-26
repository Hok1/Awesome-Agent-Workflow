"""Bounded, tool-free design turns and independently executable dimension packages."""

from __future__ import annotations

import json
import threading
import time

from aaw_skill_eval.adapters.agents.chrys.runner import (
    _acp_error_text,
    _build_session,
    _start_session,
)
from aaw_skill_eval.adapters.agents.chrys.runtime import JUDGE_PROFILE_NAME, prepare_isolated_home
from aaw_skill_eval.modules.designer.planning import DesignFlow, DesignUnavailable


class ChrysDesignFlow(DesignFlow):
    def request(self, settings, data, root, prompt, *, budget, cancelled, progress):
        root.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        expired = threading.Event()
        timer = threading.Timer(budget, expired.set)
        timer.daemon = True
        timer.start()
        home = prepare_isolated_home(settings, root=root / "home")
        workspace = root / "context"
        workspace.mkdir()
        session = _build_session(
            settings,
            agent_profile=JUDGE_PROFILE_NAME,
            cwd=workspace,
            artifact_dir=root / "events",
            on_log=None,
            log_source="designer",
            chrys_home_root=home,
        )
        try:
            progress("connection", "启动 Chrys 并连接会话")
            _start_session(session, settings)
            session.initialize()
            progress("session", "建立无工具会话，固定所选模型")
            session.new_session(workspace)
            session.ensure_model(data["generator_model"])
            if expired.is_set() or cancelled():
                raise DesignUnavailable("连接已超时或任务已停止，可重试或切换模型")
            progress("response", "等待所选模型返回结构化结果")
            result = session.prompt(
                prompt,
                timeout_seconds=max(1, budget - int(time.monotonic() - started)),
                on_progress=progress,
                is_cancelled=lambda: cancelled() or expired.is_set(),
                turn=1,
            )
            if expired.is_set() or result.timed_out:
                raise DesignUnavailable(
                    f"本阶段超过 {budget} 秒预算，已保留已有内容；可重试或切换模型"
                )
            if cancelled() or result.cancelled:
                raise DesignUnavailable("任务已停止")
            if result.error:
                raise DesignUnavailable(_acp_error_text(result.error))
            text = result.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            return json.loads(text)
        except (ValueError, DesignUnavailable):
            raise
        except Exception as exc:
            raise DesignUnavailable(str(exc)[:2000]) from exc
        finally:
            timer.cancel()
            session.close()
