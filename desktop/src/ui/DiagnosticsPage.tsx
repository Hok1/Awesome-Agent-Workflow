/**
 * 诊断页：运行日志查看 + ACP 流量记录查看。
 *
 * 数据全部来自 logStore（镜像自 core/logger 的两个环形缓冲——应用日志
 * appLogSink 与协议层逐条登记的 acpTraffic），本页不做任何数据累积，
 * 只做过滤与展示（架构约定：诊断页只读 ring 快照）。协议自检已随多
 * agent 管理整体移入设置页「Agent」分片（见 ui/AgentsSettings.tsx）。
 */
import { useState } from "react";
import { useLogStore } from "../stores/logStore";
import { tabActiveClass, tabInactiveClass } from "./controls";
import LogView from "./LogView";
import AcpTrafficView from "./AcpTrafficView";
import { PerfHud } from "./PerfHud.tsx";

type DiagnosticsTab = "logs" | "traffic" | "perf";

// 页签状态放模块级：性能自检会临时收起诊断覆盖层（回会话视图采样），
// 覆盖层重挂载时不能把用户丢回日志页——否则自检结果看不见
let diagnosticsTab: DiagnosticsTab = "logs";

/** 测试专用：页签状态是模块级，用例间复位回默认日志页。 */
export function resetDiagnosticsTabForTests(): void {
  diagnosticsTab = "logs";
}

function DiagnosticsPage() {
  const [tab, setTab] = useState<DiagnosticsTab>(diagnosticsTab);
  const logCount = useLogStore((state) => state.entries.length);
  const trafficCount = useLogStore((state) => state.traffic.length);

  // 「性能」不带计数徽标：内存 / 存储是读数不是条目数（日志与流量页签
  // 的计数是「有多少条可查看」，性能页没有对应语义）
  const tabs: ReadonlyArray<{
    id: DiagnosticsTab;
    label: string;
    count: number | null;
  }> = [
    { id: "logs", label: "运行日志", count: logCount },
    { id: "traffic", label: "ACP 流量", count: trafficCount },
    { id: "perf", label: "性能", count: null },
  ];

  return (
    <section aria-label="诊断" className="space-y-4">
      <header>
        <h2 className="text-lg font-medium text-ink">诊断</h2>
        <p className="mt-1 text-sm text-ink-faint">
          运行日志与 ACP wire 流量的环形缓冲快照（日志 2000 条 / 流量 1000
          条，写满覆盖最旧）。
        </p>
      </header>
      <div
        role="tablist"
        aria-label="诊断视图"
        className="flex w-fit gap-1 rounded-lg border border-line bg-surface p-1"
      >
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            onClick={() => {
              diagnosticsTab = item.id;
              setTab(item.id);
            }}
            className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
              tab === item.id ? tabActiveClass : tabInactiveClass
            }`}
          >
            {item.count === null
              ? item.label
              : `${item.label}（${item.count}）`}
          </button>
        ))}
      </div>
      {tab === "logs" ? (
        <LogView />
      ) : tab === "traffic" ? (
        <AcpTrafficView />
      ) : (
        <PerfHud />
      )}
    </section>
  );
}

export default DiagnosticsPage;
