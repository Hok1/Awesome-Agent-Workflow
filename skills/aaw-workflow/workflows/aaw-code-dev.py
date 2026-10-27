# /// script
# requires-python = ">=3.9"
# ///
"""AAW · ③ 代码开发 — AAW 工作流的 chrys 驱动器。

覆盖所有入口的编码段：task-split → task-dev（dev 轻量入口使用 dev-task-split / dev-task-dev，由相同节点承接）。task-dev 内部按阶段机多轮推进，多个任务会循环经过相同节点。

用法：
    1. 在 TUI 的 Workflows 里选择本工作流，输入文本可留空（或写 SR 编号 / 一句话意图）；
    2. run 启动后先由协商 Agent 与你确认本次目标：继续哪个 SR / 新建（sr / ar / dev）/
       回退 / 取消——新建与回退都在 run 内完成，不需要聊天模式配合；
    3. 确认后进入推进循环：每个阶段节点执行一个 aaw 工作单，需要决策时会弹窗询问；
    4. run 结束后随时可以重新启动，路由器会从 .sdd/ 的当前进度继续。

环境：驱动器通过 ``aaw next/done`` 调用 AAW CLI。它会依次尝试
``uv run --with typer --with pyyaml``、当前解释器和 PATH 上的 python；
CLI 路径依次探测工作区与用户目录下的 skills 安装位置，也可用环境变量
``AAW_SCRIPT`` 直接指定 aaw.py 的绝对路径。

兼容性：需要 chrys >= 0.25.2（workflow agent 节点加载 skills）。结构化提问
（单选弹窗）在 chrys >= 0.26.1 可用；旧版本自动退化为纯文本提问。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

try:
    from chrys.workflows import Option, Question, WorkflowBuilder, WorkflowValue
except ImportError:  # chrys < 0.26.1 ships no structured questions yet
    from chrys.workflows import WorkflowBuilder, WorkflowValue

    Option = Question = None

WORKFLOW_TITLE = "AAW · ③ 代码开发"
STAGES = [
    ('task-split', ('task-split', 'dev-task-split'), '本节点承接任务拆分工作单。'),
    ('task-dev', ('task-dev', 'dev-task-dev'), '本节点承接任务实现工作单，内部按 task-dev 阶段机推进。'),
]

_AGENT_ROLE = (
    "你是 AAW 研发工作流中的一个阶段执行 Agent。工作单的完整指令在输入文本中："
    "先加载它点名的 skill，严格按指令执行，完成后执行它给出的完成命令。"
    "需要用户决策时用 ask_user 提问，不要臆测。"
)

_NEGOTIATE_ROLE = (
    "你是本次 run 的启动协商 Agent。读输入文本中的仓库状态与规则，用 ask_user 与用户对话弄清目标，"
    "然后输出一行严格格式的决策（decision:continue / create / rollback / cancel，具体格式见输入说明），"
    "需要附带的收集信息按输入说明的标记格式给出。除 ask_user 外不得调用任何工具，"
    "不得执行命令、不得读写文件。用户意图不明就继续追问，不要猜；无法向用户提问时"
    "（没有 ask_user 工具），启动输入中含 SR 编号就输出 decision:continue <该编号>，"
    "否则输出 decision:cancel。"
)

_STATE = {"sr": None, "script": None, "runner": None, "decision_done": False}


# ---------- locate and call the aaw CLI ----------


def _script_candidates():
    env = os.environ.get("AAW_SCRIPT")
    if env:
        yield env
    script = os.path.join("aaw-workflow", "scripts", "aaw.py")
    yield os.path.join(os.getcwd(), ".agents", "skills", script)
    home = os.path.expanduser("~")
    yield os.path.join(home, ".agents", "skills", script)
    yield os.path.join(home, ".chrys", "skills", script)
    appdata = os.environ.get("APPDATA")
    if appdata:
        yield os.path.join(appdata, "chrys", "skills", script)
    yield os.path.join(home, ".claude", "skills", script)


def _runner_candidates():
    uv = shutil.which("uv")
    if uv:
        yield [uv, "run", "--with", "typer", "--with", "pyyaml"]
    if sys.executable:
        yield [sys.executable]
    for exe in ("python3", "python"):
        found = shutil.which(exe)
        if found:
            yield [found]


def _run(argv, timeout):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return subprocess.run(
        argv, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, env=env,
    )


def _ensure_env():
    if _STATE["script"] and _STATE["runner"]:
        return
    script = next((p for p in _script_candidates() if os.path.isfile(p)), None)
    if not script:
        tried = "\n  ".join(_script_candidates())
        raise RuntimeError(
            "找不到 AAW CLI（aaw.py）。已尝试:\n  " + tried +
            "\n可用环境变量 AAW_SCRIPT 指定其绝对路径。"
        )
    for runner in _runner_candidates():
        try:
            probe = _run(runner + [script, "status", "--json"], timeout=120)
        except Exception:
            continue
        if probe.returncode != 0:
            continue
        try:
            if json.loads(probe.stdout).get("ok"):
                _STATE["script"] = script
                _STATE["runner"] = runner
                return
        except Exception:
            continue
    raise RuntimeError(
        "没有可用的 Python 运行器能执行 AAW CLI（需要 typer 与 pyyaml）。"
        "请安装 uv，或在一个装有这两个包的解释器环境下运行 chrys。"
    )


def _cli(args, timeout=180):
    _ensure_env()
    proc = _run(_STATE["runner"] + [_STATE["script"]] + list(args), timeout=timeout)
    try:
        return json.loads(proc.stdout)
    except Exception:
        tail = (proc.stderr or "")[-400:]
        raise RuntimeError(
            "aaw CLI 输出无法解析（rc=%s）：%s %s" % (proc.returncode, proc.stdout[:200], tail)
        )


def _cli_argv(argv, timeout=180):
    """Run a done/next/user-confirm argv from a work order, runner-corrected."""
    _ensure_env()
    proc = _run(_fix_argv(argv), timeout=timeout)
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {"ok": False, "error": {"message": (proc.stderr or proc.stdout)[-400:]}}


def _fix_argv(argv):
    # Work orders hardcode ["python", "<script>", ...]; swap in the probed runner.
    return _STATE["runner"] + list(argv)[1:]


def _argv_lines(argv):
    fixed = _fix_argv(argv)
    return json.dumps(fixed, ensure_ascii=False) + "\n    " + shlex.join(fixed)


def _control(kind, message):
    return "control:" + kind + "\n" + message


async def _ask_choice(ctx, question, options, safe=None):
    """Ask one single-select question; returns the matched option label.

    An answer that matches no option is re-asked once with a stricter prompt;
    a second miss returns *safe* — which must be the non-acting side (pause /
    cancel), never an action. Returns None when *safe* is None.

    Uses the structured dialog on chrys >= 0.26.1 and falls back to plain-text
    ctx.ask on older versions, where the answer may be an index or a prefix.
    """
    prompt = question
    for _attempt in (0, 1):
        if Question is not None:
            answer = await ctx.ask(Question(prompt, options=[Option(o) for o in options]))
            picked = (answer.selected or [answer.text.strip()])[0].strip()
        else:
            listing = " / ".join("%d.%s" % (i + 1, o) for i, o in enumerate(options))
            raw = (await ctx.ask(prompt + "\n（输入序号或选项文字）：" + listing) or "").strip()
            picked = ""
            if raw.isdigit():
                index = int(raw) - 1
                if 0 <= index < len(options):
                    picked = options[index]
            if not picked:
                for option in options:
                    if raw and (raw in option or option.startswith(raw)):
                        picked = option
                        break
        for option in options:
            if picked == option or (picked and option.startswith(picked)):
                return option
        prompt = "未理解上一条回答。请从以下选项中选择：" + " / ".join(options)
    return safe


async def _ask_text(ctx, prompt):
    return ((await ctx.ask(prompt)) or "").strip()


# ---------- router ----------


def _startup_brief(run_text, status_payload):
    srs = status_payload.get("srs") or []
    lines = []
    lines.append("你是 AAW 工作流的启动协商 Agent，负责在 run 开始时与用户确认本次目标。")
    lines.append("【可用决策】你的输出中必须有且仅有一行以 decision: 开头（可以放在开头或结尾），格式为以下之一：")
    lines.append("  decision:continue <SR>")
    lines.append("  decision:create sr <SR>")
    lines.append("  decision:create ar <SR> <AR>")
    lines.append("  decision:create dev <SR>")
    lines.append("  decision:rollback <SR>")
    lines.append("  decision:cancel")
    lines.append("【仓库状态】进行中的 SR：" + ("、".join(srs) if srs else "（无，只能新建）"))
    lines.append(
        "【入口须知】"
        "sr：必须完整收集用户提供的原始需求文本（保持原文、不总结、不改写，普通讨论和你的解释不得混入），"
        "放在 ---requirement--- 与 ---end--- 两行标记之间；"
        "ar：本仓库需已执行过 repo-init，需收集 AR 编号与一句话描述（描述放在第二行，格式 title: <描述>）；"
        "dev：最轻量入口，SR 编号即可，可选附需求原文（同样标记）。"
    )
    lines.append(
        "【规则】新建时向用户提议一个未占用的 SR 编号并确认；用户意图不明就追问，不要猜。"
        "只允许通过 ask_user 对话，不得调用其他工具、不得执行命令、不得读写文件。"
    )
    lines.append("【本次启动输入】" + ((run_text or "").strip() or "（空）"))
    return "\n".join(lines)


def prep(value, ctx):
    payload = _cli(["status", "--json"])
    return _startup_brief(getattr(value, "text", "") or "", payload)


def _write_temp_requirement(text):
    fd, path = tempfile.mkstemp(prefix="aaw-req-", suffix=".md")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def _read_head(path, limit=30):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return "（读取失败：%s）" % path
    shown = "".join(lines[:limit]).rstrip("\n")
    return shown + ("\n…（共 %d 行）" % len(lines) if len(lines) > limit else "")


def _requirement_block(text):
    if "---requirement---" not in text:
        return ""
    segment = text.split("---requirement---", 1)[1]
    if "---end---" in segment:
        segment = segment.split("---end---", 1)[0]
    return segment.strip("\n")


def _extract_decision(text):
    """Find the decision line anywhere in the negotiate agent's output.

    Agents sometimes explain first and put the decision last, so scan every
    line instead of trusting position. Exactly one decision line is required;
    ambiguity is an error, never a guess.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith("decision:")]
    if len(lines) == 1:
        return lines[0] + "\n" + text
    return None


async def _handle_decision(text, ctx):
    """Execute the negotiate agent's decision line; None means proceed to the loop."""
    decision_line = text.splitlines()[0]
    rest = decision_line[len("decision:"):].strip().split()
    kind = rest[0] if rest else ""
    if kind == "cancel":
        return _control("paused", "已按用户要求取消，未做任何变更。")
    if kind == "continue" and len(rest) >= 2:
        _STATE["sr"] = rest[1]
        ctx.emit("[router] 继续 " + rest[1])
        return None
    if kind == "create" and len(rest) >= 3:
        entry, sr = rest[1], rest[2]
        requirement = _requirement_block(text)
        temp_path = ""
        args = ["start", "--entry", entry, "--sr", sr, "--json"]
        if entry == "sr":
            if not requirement:
                return _control("error", "decision:create sr 缺少 ---requirement--- 原文块，无法启动。")
            temp_path = _write_temp_requirement(requirement)
            args = ["start", "--entry", "sr", "--sr", sr, "--requirement-file", temp_path, "--json"]
        elif entry == "ar":
            ar = rest[3] if len(rest) > 3 else "AR-001"
            title = ""
            for line in text.splitlines():
                if line.startswith("title:"):
                    title = line[len("title:"):].strip()
                    break
            args = ["start", "--entry", "ar", "--sr", sr, "--ar", ar, "--title", title or "AR", "--json"]
        elif entry != "dev":
            return _control("error", "未知的 create 入口：" + str(entry))
        result = await asyncio.to_thread(_cli, args)
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
        if not result.get("ok"):
            return _control("error", "aaw start 失败：" + json.dumps(result.get("error", {}), ensure_ascii=False))
        _STATE["sr"] = sr
        ctx.emit("[router] 已创建 %s 入口工作流 %s" % (entry, sr))
        if entry == "sr":
            saved = os.path.join(".sdd", sr, "original-requirement.md")
            for _round in range(3):
                head = _read_head(saved)
                verdict = await _ask_choice(
                    ctx,
                    "已保存需求原文（开头 %s）。与你向用户收集的原文一致吗？" % ("如下\n" + head if head else "读取失败"),
                    ["一致，继续", "不一致，重新提供"],
                    safe="不一致，重新提供",
                )
                if verdict == "一致，继续":
                    break
                corrected = await _ask_text(ctx, "请提供正确的需求原文（可多行，保持原文不加工）：")
                if not corrected:
                    return _control("paused", "未提供修正原文，已暂停。")
                with open(saved, "w", encoding="utf-8", newline="\n") as handle:
                    handle.write(corrected + "\n")
            else:
                return _control("paused", "需求原文核对未通过，已暂停。处理后可重新启动。")
        elif requirement:
            target = os.path.join(".sdd", sr, "requirement.md")
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(requirement + "\n")
            ctx.emit("[router] 已落盘可选需求原文 " + target)
        return None
    if kind == "rollback" and len(rest) >= 2:
        sr = rest[1]
        detail = await asyncio.to_thread(_cli, ["status", "--sr", sr, "--json"])
        if not detail.get("ok"):
            return _control("error", "查询 %s 状态失败：%s" % (sr, json.dumps(detail.get("error", {}), ensure_ascii=False)))
        steps_detail = detail.get("steps") or []
        finished = [s for s in steps_detail if s.get("finished")]
        if not finished:
            return _control("error", sr + " 没有可回退的已完成步骤。")
        labels = ["%s·%s" % (s.get("id"), s.get("name")) for s in finished[:8]] + ["取消回退"]
        picked = await _ask_choice(ctx, "回退 %s 到哪个步骤？（其下游将失效）" % sr, labels, safe="取消回退")
        if picked == "取消回退":
            return _control("paused", "已取消回退，未做任何变更。")
        step_id = picked.split("·", 1)[0]
        preview = await asyncio.to_thread(_cli, ["rollback", "--sr", sr, step_id, "--json"])
        if not preview.get("ok"):
            return _control("error", "回退预览失败：" + json.dumps(preview.get("error", {}), ensure_ascii=False))
        artifacts = ", ".join(a.get("path", "?") for a in (preview.get("managed_artifacts") or [])[:6])
        summary = "目标步骤 %s（%s）；将失效步骤 %s；受影响成果物：%s" % (
            step_id, (preview.get("target_step") or {}).get("name", "?"),
            preview.get("invalidated_step_ids"), artifacts or "（无）",
        )
        choices = preview.get("choices") or []
        labels2 = [c.get("label") or c.get("id") for c in choices] + ["取消回退"]
        picked2 = await _ask_choice(ctx, "确认回退。\n" + summary + "\n选择成果物处理策略：", labels2, safe="取消回退")
        if picked2 == "取消回退":
            return _control("paused", "已取消回退，未做任何变更。")
        for choice in choices:
            if picked2 in (choice.get("label"), choice.get("id")):
                result = await asyncio.to_thread(_cli_argv, choice["command_argv"])
                if not result.get("ok"):
                    return _control("error", "回退执行失败：" + json.dumps(result.get("error", {}), ensure_ascii=False))
                break
        _STATE["sr"] = sr
        ctx.emit("[router] 已回退 %s 到步骤 %s" % (sr, step_id))
        return None
    return _control("error", "无法理解的决策行：" + lines[0][:200])


def _brief(sr, order):
    lines = []
    lines.append(
        "你是 AAW 研发工作流的阶段执行 Agent，在当前项目仓库中执行下面的工作单。"
    )
    lines.append(
        "SR：%s｜步骤 %s：%s（type=%s，execution=%s）"
        % (sr, order.get("id"), order.get("name"), order.get("type"), order.get("execution"))
    )
    if order.get("existing_output_reusable"):
        lines.append(
            "注意：本步骤已有可复用的既有产出。先按 skill 的复用检查判断能否复用，"
            "能复用则只补充缺失部分，不要推倒重来。"
        )
    if order.get("skill"):
        lines.append("【第一步】用 load_skill 逐个加载并完整遵循以下 skill：" + "、".join(order["skill"]))
    if order.get("prompt"):
        lines.append("【工作单指令】\n" + order["prompt"])
    if order.get("input"):
        rows = "\n".join(
            "- %s（required=%s，exists=%s）" % (i.get("path"), i.get("required"), i.get("exists"))
            for i in order["input"]
        )
        lines.append("【输入文件】\n" + rows)
    if order.get("output"):
        rows = "\n".join(
            "- %s（required=%s，exists=%s）" % (o.get("path"), o.get("required"), o.get("exists"))
            for o in order["output"]
        )
        lines.append("【交付物】\n" + rows)
    guidance = order.get("task_dev")
    if guidance:
        lines.append(
            "【task-dev 阶段机】严格按下面 JSON 的 objective 与 required 逐项执行，"
            "forbidden 是硬约束；每个阶段把阶段报告写入 commands.data_file 指定的文件，"
            "然后执行 commands.next_argv 提交；当 JSON 中出现 commands.done_argv 时执行它完成本工作单。"
            "指令与报告 schema 参照 instruction_refs 与 report_schema_ref。"
        )
        lines.append("```json\n" + json.dumps(guidance, ensure_ascii=False, indent=2) + "\n```")
        commands = guidance.get("commands") or {}
        if commands.get("next_argv"):
            lines.append("- next 命令（argv 与可粘贴命令行）：\n    " + _argv_lines(commands["next_argv"]))
        if commands.get("done_argv"):
            lines.append("- done 命令（argv 与可粘贴命令行）：\n    " + _argv_lines(commands["done_argv"]))
    else:
        commands = order.get("commands") or {}
        if order.get("data") or order.get("data_file"):
            data_file = (order.get("data_file") or {}).get("path")
            lines.append(
                "【完成后提交数据】按下述 schema 构造 JSON（字段说明见 data.fields），"
                "以 UTF-8 写入：\n" + str(data_file)
            )
            if order.get("data"):
                lines.append("```json\n" + json.dumps(order["data"], ensure_ascii=False, indent=2) + "\n```")
            if order.get("data_prompt"):
                lines.append("说明：" + json.dumps(order["data_prompt"], ensure_ascii=False))
            if commands.get("done_argv"):
                lines.append("然后执行完成命令：\n    " + _argv_lines(commands["done_argv"]))
            lines.append("若命令返回校验错误（ok=false），按 error 修正数据或产出后重试，直到成功。")
        elif commands.get("done_argv"):
            lines.append("【完成】交付物就绪后执行完成命令：\n    " + _argv_lines(commands["done_argv"]))
    if str(order.get("type", "")).endswith("-gate"):
        lines.append(
            "【门禁特别约定】门禁结论为不通过或阻塞时，done 命令会被 CLI 拒绝，"
            "这是协议的预期行为，不是错误。被拒后的默认动作：按门禁报告的整改建议修正"
            "上游成果物，然后重新执行门禁检查（可多轮循环，直到通过）。整改方向需要用户"
            "决策时用 ask_user 询问。禁止因为门禁不通过而输出 AAW_STOP。"
        )
    lines.append("【通用约束】")
    lines.append("- 需要用户决策或补充信息时，直接使用 ask_user 工具提问，不要自行臆测。")
    lines.append(
        "- 只执行本工作单；不要运行 start/rollback/status/migrate 等 aaw 命令，"
        "不要改写 .sdd/ 下的 workflow.yaml。"
    )
    lines.append("- 完成后用中文简要汇报（不超过 200 字）：做了什么、产出文件、done 是否成功。")
    lines.append(
        "- 只有当用户在对话中明确要求停止时，才在最后一行单独输出 AAW_STOP；"
        "自认无法继续时必须先用 ask_user 向用户说明情况并征求意见"
        "（继续修正 / 调整方向 / 停止），不得自行停止 run。"
    )
    return "\n\n".join(lines)


async def router(value, ctx):
    await asyncio.to_thread(_ensure_env)
    if not _STATE["decision_done"]:
        _STATE["decision_done"] = True
        text = (getattr(value, "text", "") or "").strip()
        normalized = _extract_decision(text)
        if normalized is not None:
            outcome = await _handle_decision(normalized, ctx)
            if outcome is not None:
                return outcome
        elif text:
            return _control(
                "error",
                "协商 Agent 的输出中没有恰好一行 decision: 决策。其原样输出：\n" + text[:500],
            )
    sr = _STATE["sr"]
    if not sr:
        return _control("error", "协商未确定要推进的 SR，无法继续。")
    while True:
        payload = await asyncio.to_thread(_cli, ["next", "--sr", sr, "--json"])
        if not payload.get("ok"):
            return _control("error", "aaw next 失败：" + json.dumps(payload.get("error", {}), ensure_ascii=False))
        if payload.get("definition_drift"):
            ctx.emit("[router] 提示：" + str(payload["definition_drift"].get("message", "定义版本漂移")))
        status = payload.get("status")
        if status == "awaiting_user_confirm":
            pending = payload.get("pending_user_confirm") or {}
            planned = pending.get("planned_next") or pending.get("to_step") or "下一步"
            choice = await _ask_choice(
                ctx, "步骤已完成，是否放行进入 %s？" % planned,
                ["放行", "暂停"], safe="暂停",
            )
            if choice == "放行":
                await asyncio.to_thread(_cli_argv, payload["commands"]["user_confirm_argv"])
                continue
            return _control("paused", "已按你的选择暂停。再次启动本工作流会从当前进度继续。")
        if payload.get("done"):
            return _control("finished", "SR %s 的工作流已全部完成。" % sr)
        ready = payload.get("ready") or []
        if not ready:
            return _control(
                "blocked",
                "没有可执行的工作单（status=%s）。请处理后重新启动本工作流。" % status,
            )
        order = ready[0]
        if len(ready) > 1:
            labels = ["%s·%s" % (r.get("id"), r.get("name")) for r in ready[:8]] + ["暂停本次运行"]
            picked = await _ask_choice(
                ctx, "当前有多个可执行步骤，先执行哪个？", labels, safe="暂停本次运行",
            )
            if picked == "暂停本次运行":
                return _control("paused", "已暂停。再次启动本工作流会从当前进度继续。")
            for candidate in ready:
                if picked.startswith(str(candidate.get("id")) + "·") or picked == candidate.get("name"):
                    order = candidate
                    break
        inputs = order.get("inputs") or {}
        if inputs.get("blocked"):
            return _control(
                "blocked",
                "步骤 %s 缺少必需输入 %s；请补齐或回退后再启动本工作流。"
                % (order.get("name"), inputs.get("missing_required")),
            )
        execution = order.get("execution")
        if execution in ("noop", "manual") and not order.get("data") and not order.get("data_file"):
            if execution == "manual":
                confirmed = await _ask_choice(
                    ctx,
                    "manual 步骤【%s】完成后继续：\n%s" % (order.get("name"), (order.get("prompt") or "")[:500]),
                    ["已完成，继续"], safe=None,
                )
                if confirmed != "已完成，继续":
                    return _control("paused", "manual 步骤未确认，已暂停。")
            await asyncio.to_thread(_cli_argv, order["commands"]["done_argv"])
            ctx.emit("[router] %s 步骤 %s 完成" % (execution, order.get("name")))
            continue
        ctx.emit("[router] 分派步骤 %s：%s" % (order.get("id"), order.get("name")))
        return "step:%s\n\n%s" % (order.get("type"), _brief(sr, order))


# ---------- reporter ----------


def reporter(value, ctx):
    text = getattr(value, "text", "") or ""
    if text.startswith("control:"):
        kind = text.splitlines()[0][len("control:"):]
        ctx.emit("[reporter] run 结束：%s" % kind)
        return WorkflowValue(text=text.split("\n", 1)[-1], data={"finished": True})
    if "AAW_STOP" in text:
        tail = text[-800:].strip()
        return WorkflowValue(
            text="Agent 停止了 run（应为用户要求）。其最终汇报（末尾）：\n" + tail,
            data={"finished": True},
        )
    sr = _STATE.get("sr")
    if not sr:
        return WorkflowValue(text="缺少 SR 状态，run 结束。", data={"finished": True})
    payload = _cli(["next", "--sr", sr, "--json"])
    if payload.get("done"):
        ctx.emit("[reporter] 工作流已全部完成")
        return WorkflowValue(text="SR %s 工作流已全部完成。" % sr, data={"finished": True})
    ready = payload.get("ready") or []
    if ready:
        ctx.emit("[reporter] 下一步：%s（%s）" % (ready[0].get("name"), ready[0].get("type")))
    return WorkflowValue(text="继续推进。", data={"finished": False})


def end(value, ctx):
    return value


def _finished(v):
    data = getattr(v, "data", None)
    return bool(data and data.get("finished"))


def _is_control(v):
    lines = (getattr(v, "text", "") or "").splitlines()
    return bool(lines) and lines[0].startswith("control:")


def _step_pred(types):
    def predicate(v):
        lines = (getattr(v, "text", "") or "").splitlines()
        return bool(lines) and lines[0] in tuple("step:%s" % t for t in types)
    return predicate


# ---------- graph ----------

wf = WorkflowBuilder(WORKFLOW_TITLE, description='覆盖所有入口的编码段：task-split → task-dev（dev 轻量入口使用 dev-task-split / dev-task-dev，由相同节点承接）。task-dev 内部按阶段机多轮推进，多个任务会循环经过相同节点。\n\n本工作流属于 AAW 流程的最后一段（代码开发），要求设计门禁已通过。')

_STAGE_ROLE = '本工作流属于 AAW 流程的最后一段（代码开发），要求设计门禁已通过。'


def _pipeline(scope):
    router_node = scope.python("router", router, timeout=None)
    cases = []
    stage_nodes = []
    for node_name, types, role in STAGES:
        node = scope.agent(
            node_name, profile="Code",
            instructions_suffix=_AGENT_ROLE + (role or ""), timeout=None,
        )
        stage_nodes.append(node)
        cases.append((_step_pred(types), node))
    end_node = scope.python("end", end)
    cases.insert(0, (_is_control, end_node))
    fallback = scope.agent("fallback", profile="Code", instructions_suffix=_AGENT_ROLE, timeout=None)
    scope.switch(router_node, cases=cases, default=fallback)
    reporter_node = scope.python("reporter", reporter, timeout=600)
    scope.join(stage_nodes + [fallback, end_node], reporter_node)
    return router_node, reporter_node


pipeline = wf.loop(
    "pipeline", body=_pipeline, until=_finished,
    max_iterations=300, on_exhausted="fail",
)

prep_node = wf.python("prep", prep)
negotiate_node = wf.agent("negotiate", profile="Code", instructions_suffix=_NEGOTIATE_ROLE, timeout=None)
wf.edge(prep_node, negotiate_node)
wf.edge(negotiate_node, pipeline)
wf.start(prep_node)
wf.output(pipeline)

workflow = wf.build()
