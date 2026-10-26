import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, type Json } from "../../shared/api";
import { Button, Card } from "../../shared/ui";
export function ExecutionLog({
  experimentId,
  assessmentId,
  runs,
}: {
  experimentId: string;
  assessmentId?: string;
  runs: Json[];
}) {
  const [source, setSource] = useState("experiment"),
    [text, setText] = useState(""),
    [error, setError] = useState(""),
    [follow, setFollow] = useState(true),
    [copied, setCopied] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let alive = true,
      busy = false,
      cursor: string | undefined;
    setText("");
    setError("");
    async function poll() {
      if (busy) return;
      busy = true;
      try {
        const data = await api(
          `${source.startsWith("judge:") ? `/benchmark/assessments/${assessmentId}/runs/${source.slice(6)}` : source === "experiment" ? `/experiments/${experimentId}` : `/runs/${source}`}/logs?mode=raw${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
        );
        if (alive) {
          cursor = data.next_cursor ?? data.cursor;
          const chunk =
            data.records
              ?.map(
                (record: Json) =>
                  record.text ?? record.message ?? JSON.stringify(record),
              )
              .join("\n") ??
            data.text ??
            "";
          setText((old) =>
            (old + (old && chunk ? "\n" : "") + chunk).slice(-200000),
          );
          setError("");
        }
      } catch (e) {
        if (alive) setError(String(e));
      } finally {
        busy = false;
      }
    }
    poll();
    const timer = setInterval(poll, 2000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [experimentId, assessmentId, source]);
  useEffect(() => {
    const container = bottom.current?.parentElement;
    if (follow && container) container.scrollTop = container.scrollHeight;
  }, [text, follow]);
  return (
    <Card className="execution-log">
      <div className="section-heading log-toolbar">
        <div>
          <h2>运行日志</h2>
        </div>
        <div className="flex gap-3 items-center flex-wrap">
          <select
            aria-label="日志来源"
            value={source}
            onChange={(e) => setSource(e.target.value)}
          >
            <option value="experiment">整体执行</option>
            {assessmentId &&
              runs.map((run) => (
                <option key={`judge:${run.id}`} value={`judge:${run.id}`}>
                  {run.case_id} · T{run.trial} · 评分日志
                </option>
              ))}
            {runs.map((run) => (
              <option key={run.id} value={run.id}>
                {run.case_id} · {run.group} · T{run.trial}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={follow}
              onChange={(e) => setFollow(e.target.checked)}
            />
            追尾
          </label>
          <Button
            variant="ghost"
            onClick={async () => {
              await navigator.clipboard.writeText(text);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
          >
            {copied ? <Check size={15} /> : <Copy size={15} />}复制
          </Button>
        </div>
      </div>
      <div className={`log-view ${!text && !error ? "log-empty" : ""}`}>
        <pre>{error || text || "等待运行日志…"}</pre>
        <div ref={bottom} />
      </div>
    </Card>
  );
}
