/**
 * 诊断页：运行日志查看 + ACP 流量记录查看。
 *
 * 数据全部来自 logStore（镜像自 core/logger 的两个环形缓冲——应用日志
 * appLogSink 与协议层逐条登记的 acpTraffic），本页不做任何数据累积，
 * 只做过滤与展示（架构约定：诊断页只读 ring 快照）。
 */
import { useState } from "react";
import { useLogStore } from "../stores/logStore";
import { tabActiveClass, tabInactiveClass } from "./controls";
import LogView from "./LogView";
import AcpTrafficView from "./AcpTrafficView";

type DiagnosticsTab = "logs" | "traffic";

function DiagnosticsPage() {
  const [tab, setTab] = useState<DiagnosticsTab>("logs");
  const logCount = useLogStore((state) => state.entries.length);
  const trafficCount = useLogStore((state) => state.traffic.length);

  const tabs: ReadonlyArray<{
    id: DiagnosticsTab;
    label: string;
    count: number;
  }> = [
    { id: "logs", label: "运行日志", count: logCount },
    { id: "traffic", label: "ACP 流量", count: trafficCount },
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
              setTab(item.id);
            }}
            className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
              tab === item.id ? tabActiveClass : tabInactiveClass
            }`}
          >
            {`${item.label}（${item.count}）`}
          </button>
        ))}
      </div>
      {tab === "logs" ? <LogView /> : <AcpTrafficView />}
    </section>
  );
}

export default DiagnosticsPage;
