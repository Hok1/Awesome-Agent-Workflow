/**
 * ACP 流量视图：读取 logStore 镜像（真相源是 core/logger 的 acpTraffic
 * 环形缓冲，由协议层逐条登记）。每条记录展示方向、类别、方法、id 与
 * 序列化 payload（可展开），支持方向过滤。
 */
import { useMemo, useState } from "react";
import { useLogStore } from "../stores/logStore";
import type { AcpTrafficEntry } from "../core/logger";
import { Listbox } from "./controls";

type DirectionFilter = "all" | "in" | "out";

const kindTone: Readonly<Record<AcpTrafficEntry["kind"], string>> = {
  request: "text-sky-300",
  response: "text-emerald-300",
  notification: "text-amber-300",
};

const kindLabel: Readonly<Record<AcpTrafficEntry["kind"], string>> = {
  request: "请求",
  response: "响应",
  notification: "通知",
};

function AcpTrafficView() {
  const traffic = useLogStore((state) => state.traffic);
  const clear = useLogStore((state) => state.clear);
  const [directionFilter, setDirectionFilter] =
    useState<DirectionFilter>("all");

  const filtered = useMemo(
    () =>
      directionFilter === "all"
        ? traffic
        : traffic.filter((entry) => entry.direction === directionFilter),
    [traffic, directionFilter],
  );

  return (
    <div className="rounded-lg border border-line bg-surface">
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
        <span className="flex items-center gap-2 text-xs text-ink-mute">
          方向
          <Listbox
            label="流量方向过滤"
            value={directionFilter}
            options={[
              { value: "all", label: "全部" },
              { value: "out", label: "发出（客户端 → agent）" },
              { value: "in", label: "收到（agent → 客户端）" },
            ]}
            onChange={(next) => {
              setDirectionFilter(next as DirectionFilter);
            }}
          />
        </span>
        <span className="ml-auto text-xs text-ink-faint">
          {`显示 ${filtered.length} / ${traffic.length} 条 · 单条正文上限 16KB`}
        </span>
        <button
          type="button"
          onClick={clear}
          className="rounded-md border border-line-strong px-2.5 py-1 text-xs text-ink-soft transition-colors hover:border-ink-faint hover:text-ink"
        >
          清空
        </button>
      </div>
      <div className="max-h-96 overflow-y-auto px-4 py-3 font-mono text-xs leading-relaxed">
        {filtered.length === 0 ? (
          <p className="text-ink-ghost">
            暂无 ACP 流量。建立 ACP 连接后，每条 JSON-RPC 消息都会在此登记。
          </p>
        ) : (
          <ul className="space-y-1.5" data-testid="traffic-list">
            {[...filtered].reverse().map((entry) => (
              <li
                key={entry.seq}
                className="rounded border border-line/60 bg-surface/60 px-2 py-1.5"
              >
                <details>
                  <summary className="flex cursor-pointer flex-wrap items-center gap-2 marker:content-none">
                    <span className="shrink-0 text-ink-ghost">
                      {entry.timestamp.slice(11, 23)}
                    </span>
                    <span
                      className="shrink-0"
                      title={
                        entry.direction === "in"
                          ? "从 agent 收到"
                          : "发给 agent"
                      }
                    >
                      {entry.direction === "in" ? "↓ 收到" : "↑ 发出"}
                    </span>
                    <span className={`shrink-0 ${kindTone[entry.kind] ?? ""}`}>
                      {kindLabel[entry.kind]}
                    </span>
                    <span className="min-w-0 break-all text-ink-soft">
                      {entry.method ?? `#${String(entry.requestId)}`}
                    </span>
                    {entry.serializeError !== undefined && (
                      <span className="shrink-0 text-danger-ink">
                        序列化失败
                      </span>
                    )}
                    <span className="ml-auto shrink-0 text-ink-ghost">
                      {`${entry.byteLength}B`}
                    </span>
                  </summary>
                  <pre className="mt-1.5 max-h-64 overflow-auto whitespace-pre-wrap break-all rounded bg-base p-2 text-ink-mute">
                    {entry.payload}
                  </pre>
                </details>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default AcpTrafficView;
