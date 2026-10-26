import { useEffect, useState } from "react";
import { active, type Json } from "../../shared/api";
import { Button, Card } from "../../shared/ui";

const stages = [
  { id: "analysis", name: "分析项目" },
  { id: "design", name: "设计用例" },
  { id: "evaluation", name: "配置评价方式" },
  { id: "confirm", name: "确认使用" },
];
function elapsed(start?: string, end?: string, clock = Date.now()) {
  if (!start) return "—";
  const seconds = Math.max(
    0,
    Math.floor(((end ? Date.parse(end) : clock) - Date.parse(start)) / 1000),
  );
  return seconds < 60
    ? `${seconds}秒`
    : `${Math.floor(seconds / 60)}分${seconds % 60}秒`;
}
export function DesignerWorkflow({
  draft,
  onStop,
  onRetry,
}: {
  draft: Json;
  onStop: () => void;
  onRetry: () => void;
}) {
  const [clock, setClock] = useState(Date.now()),
    [expanded, setExpanded] = useState("");
  useEffect(() => {
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const flow = draft.workflow ?? {},
    interaction = flow.interaction ?? {},
    history = flow.history ?? [];
  const talking =
    interaction.status === "running" &&
    interaction.mode !== "generate" &&
    flow.status !== "running";
  const running = active(draft.status),
    ready = !!draft.validation?.scripts_runnable;
  const start = talking ? interaction.started_at : flow.stage_started_at;
  const slow = running && start && clock - Date.parse(start) > 60000;
  return (
    <Card className="designer-flow" aria-label="用例创建流程">
      <div className="designer-flow-stages">
        {stages.map((stage, index) => {
          const entry = history.find((h: Json) => h.stage === stage.id);
          const done = entry?.status === "completed" || (ready && index < 3);
          const selected =
            !talking && stage.id === (flow.stage || (ready ? "confirm" : ""));
          return (
            <button
              key={stage.id}
              className={done ? "done" : selected ? "selected" : ""}
              onClick={() => setExpanded(expanded === stage.id ? "" : stage.id)}
            >
              <span>{done ? "✓" : index + 1}</span>
              <strong>{stage.name}</strong>
              <small>
                {done
                  ? "已完成"
                  : selected
                    ? flow.status === "failed"
                      ? "失败"
                      : flow.status === "cancelled"
                        ? "已停止"
                        : index === 3
                          ? "待确认"
                          : "进行中"
                    : "等待"}
              </small>
              {entry && (
                <small>
                  {elapsed(entry.started_at, entry.ended_at, clock)}
                </small>
              )}
            </button>
          );
        })}
      </div>
      <div className="designer-flow-current">
        <div>
          <strong>
            {talking
              ? "正在讨论，未启动新的生成"
              : flow.detail ||
                (ready
                  ? "评价方式已就绪，可确认使用"
                  : "先描述目标，与 Agent 讨论或生成用例")}
          </strong>
          <p>
            {flow.started_at && (
              <>总用时 {elapsed(flow.started_at, flow.ended_at, clock)} · </>
            )}
            {start && <>当前阶段 {elapsed(start, flow.ended_at, clock)} · </>}
            首稿目标：1分钟内展示；验证代码随后逐项准备
          </p>
          {interaction.status === "running" &&
            interaction.mode === "auto" &&
            flow.status === "running" && (
              <p>
                正在理解新消息；已有工作暂时继续，需要修改时只调整受影响部分。
              </p>
            )}
        </div>
        <div className="flex gap-2">
          {running && (
            <Button variant="danger" onClick={onStop}>
              停止任务
            </Button>
          )}
          {!running && ["failed", "cancelled"].includes(flow.status) && (
            <Button variant="outline" onClick={onRetry}>
              重试未完成步骤
            </Button>
          )}
        </div>
      </div>
      {slow && (
        <p className="designer-flow-warning" role="status">
          本阶段已超过1分钟。已有内容会保留，可停止后重试，或在基础配置切换模型；系统不会静默更换模型或全量重来。
        </p>
      )}
      {expanded && (
        <div className="designer-flow-history">
          <strong>{stages.find((s) => s.id === expanded)?.name}</strong>
          {history
            .filter((h: Json) => h.stage === expanded)
            .map((h: Json, i: number) => (
              <p key={i}>
                开始：{new Date(h.started_at).toLocaleTimeString("zh-CN")} ·{" "}
                {h.ended_at
                  ? `结束：${new Date(h.ended_at).toLocaleTimeString("zh-CN")}`
                  : "尚未结束"}{" "}
                · 耗时 {elapsed(h.started_at, h.ended_at, clock)}
              </p>
            ))}
          {expanded === "evaluation" &&
            Object.entries(flow.dimensions ?? {}).map(([id, value]) => (
              <p key={id}>
                {id} · {(value as Json).detail} ·{" "}
                {elapsed(
                  (value as Json).started_at,
                  (value as Json).ended_at,
                  clock,
                )}
              </p>
            ))}
          {expanded === "confirm" && (
            <p>任务和判据核对后再锁定；未确认的补充建议不作为扣分条件。</p>
          )}
          {expanded === "design" && (
            <p>完整任务、预期与固定维度推荐显示在右侧；首稿不等待验证代码。</p>
          )}
        </div>
      )}
    </Card>
  );
}
