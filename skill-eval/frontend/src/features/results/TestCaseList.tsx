import { ChevronRight } from "lucide-react";
import { score, statusName, type Json } from "../../shared/api";
import { Badge, Button, Card, Empty } from "../../shared/ui";
export function TestCaseList({
  experiment,
  baseline,
  baselineGroup = "current",
  currentLabel = "本次执行",
  baselineLabel = "所选基线",
  onRun,
}: {
  experiment: Json;
  baseline?: Json | null;
  baselineGroup?: string;
  currentLabel?: string;
  baselineLabel?: string;
  onRun: (run: Json, kind: string) => void;
}) {
  const definition = experiment.suite_snapshot,
    dimensions = definition.dimensions ?? [],
    groups = baseline ? ["current", "history"] : ["current"];
  const names: Json = {
    current: "本次执行",
    history: "所选基线",
  };
  const runsFor = (id: string, group = "current") =>
    (group === "history" ? baseline!.runs : experiment.runs).filter(
      (run: Json) =>
        run.case_id === id &&
        run.group === (group === "history" ? baselineGroup : group),
    );
  function scene(caseSpec: Json, dim?: Json) {
    return (
      <div className="case-scores">
        <div className="grader-list">
          {caseSpec.graders
            .filter((g: Json) => !dim || g.dimension_id === dim.id)
            .map((grader: Json) => (
              <details key={grader.id}>
                <summary>
                  <span>{grader.name}</span>
                  <span className="flex gap-4">
                    {groups.map((group) => {
                      const avg = (group === "history" ? baseline : experiment)
                        ?.presentation?.component_scores?.[caseSpec.id]?.[
                        grader.id
                      ];
                      return (
                        <span key={group} title={names[group]}>
                          {names[group]} {score(avg)}
                        </span>
                      );
                    })}
                  </span>
                </summary>
                <div className="trial-evidence">
                  {groups.flatMap((group) =>
                    runsFor(caseSpec.id, group).map((run: Json) => {
                      const result = run.scores?.components?.find(
                        (s: Json) => s.grader_id === grader.id,
                      );
                      const verdict = result?.invalid
                        ? "Error"
                        : run.status !== "completed" &&
                            !(
                              run.execution_status === "completed" &&
                              result &&
                              !result.invalid
                            )
                          ? statusName(run.status)
                          : !result
                            ? "缺少结果"
                            : result.passed
                              ? "Pass"
                              : "Failed";
                      return (
                        <details
                          className="trial-row"
                          key={`${group}/${run.id}`}
                        >
                          <summary>
                            <strong>
                              {names[group]} · Trial {run.trial}
                            </strong>
                            <Badge>
                              {result?.invalid ? "Error" : score(result?.score)}
                            </Badge>
                            <Badge
                              tone={
                                verdict === "Pass"
                                  ? "green"
                                  : verdict === "Failed" || verdict === "Error"
                                    ? "red"
                                    : "neutral"
                              }
                            >
                              {verdict}
                            </Badge>
                            <span className="trial-preview">
                              {result?.evidence ??
                                run.error_message ??
                                "等待评分"}
                            </span>
                            <span className="trial-expand">详情</span>
                          </summary>
                          <div className="trial-details">
                            <p>
                              {result?.evidence ??
                                run.error_message ??
                                "等待评分"}
                            </p>
                            {result?.reasoning &&
                              result.reasoning !== result.evidence && (
                                <p className="text-slate-500">
                                  {result.reasoning}
                                </p>
                              )}
                            {result?.checks?.map((check: Json) => (
                              <p key={check.id}>
                                {check.id} · {score(check.score)} ·{" "}
                                {check.evidence !== result.evidence &&
                                check.evidence !== result.reasoning
                                  ? check.evidence
                                  : ""}
                              </p>
                            ))}
                            <Button
                              variant="ghost"
                              onClick={() => onRun(run, "conversation")}
                            >
                              查看对话
                            </Button>
                            <Button
                              variant="ghost"
                              onClick={() => onRun(run, "logs")}
                            >
                              运行日志
                            </Button>
                            <Button
                              variant="ghost"
                              onClick={() => onRun(run, "evidence")}
                            >
                              产出证据
                            </Button>
                          </div>
                        </details>
                      );
                    }),
                  )}
                </div>
              </details>
            ))}
        </div>
      </div>
    );
  }
  const gates = [
    ...experiment.runs.filter((run: Json) => run.group === "current"),
    ...(baseline?.runs ?? [])
      .filter((run: Json) => run.group === baselineGroup)
      .map((run: Json) => ({ ...run, group: "history" })),
  ].filter((run: Json) => run.hard_gates?.total > 0);
  const caseStates = experiment.presentation?.cases ?? [];
  const counts = experiment.presentation?.counts ?? {};
  return (
    <Card className="result-panel">
      <div className="section-heading">
        <div>
          <h2>执行结果对照</h2>
          <p>
            {currentLabel} · 对比基线：{baseline ? baselineLabel : "未选择"}
          </p>
        </div>
        <Badge>{experiment.trials} Trial / 用例</Badge>
      </div>
      <details className="result-case-status">
        <summary>
          用例整体状态
          <span className="case-verdict-counts">
            {Object.entries(counts).map(([verdict, count]) => (
              <Badge
                key={verdict}
                tone={
                  verdict === "Pass"
                    ? "green"
                    : verdict === "Failed" || verdict === "Error"
                      ? "red"
                      : "neutral"
                }
              >
                {verdict} {String(count)}
              </Badge>
            ))}
          </span>
          <span className="text-slate-400">共 {caseStates.length} 个用例</span>
        </summary>
        <div>
          {caseStates.map((item: Json) => (
            <span key={item.id} title={item.name}>
              <span>{item.name}</span>
              <Badge
                tone={
                  item.verdict === "Pass"
                    ? "green"
                    : item.verdict === "Failed" || item.verdict === "Error"
                      ? "red"
                      : "neutral"
                }
              >
                {item.verdict}
              </Badge>
            </span>
          ))}
        </div>
      </details>
      {experiment.runs.some(
        (r: Json) => r.scores?.workflow_completion?.required,
      ) && (
        <details className="gates">
          <summary>AAW 流程合规（独立记录，不计入公共评分）</summary>
          {experiment.runs
            .filter((r: Json) => r.scores?.workflow_completion?.required)
            .map((r: Json) => (
              <div key={r.id}>
                Trial {r.trial} ·{" "}
                {r.scores.workflow_completion.passed ? "通过" : "未通过"}
                <pre>
                  {JSON.stringify(r.scores.workflow_completion, null, 2)}
                </pre>
              </div>
            ))}
        </details>
      )}
      <details className="gates">
        <summary>
          <span>硬门禁状态</span>
          <div className="flex gap-3">
            {groups.map((group) => {
              const status = (group === "history" ? baseline : experiment)
                ?.presentation?.gate_status;
              return (
                <Badge
                  key={group}
                  tone={
                    status === "通过"
                      ? "green"
                      : status === "未通过"
                        ? "red"
                        : "neutral"
                  }
                >
                  {names[group]} · {status}
                </Badge>
              );
            })}
          </div>
        </summary>
        <div className="p-4 grid gap-3">
          {gates.length ? (
            gates.map((run: Json) => (
              <details key={`${run.group}/${run.id}`}>
                <summary>
                  {
                    definition.cases.find((c: Json) => c.id === run.case_id)
                      ?.name
                  }{" "}
                  · {names[run.group]} · Trial {run.trial} ·{" "}
                  {run.hard_gates?.passed ?? 0}/{run.hard_gates?.total ?? 0}
                </summary>
                <pre>
                  {JSON.stringify(
                    {
                      gates: run.scores?.components?.filter(
                        (c: Json) => c.hard_gate,
                      ),
                      dimensions: run.scores?.dimensions?.filter(
                        (dim: Json) => dim.hard_gate,
                      ),
                      error: run.error_message,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
            ))
          ) : (
            <p>当前测试套没有门禁检查结果。</p>
          )}
        </div>
      </details>
      {!dimensions.length && (
        <p className="text-sm text-slate-500 my-4">
          旧版套件 · 保留原评分项和历史结果
        </p>
      )}
      {dimensions.map((dim: Json) => {
        const cases = definition.cases.filter((c: Json) =>
          c.graders.some((g: Json) => g.dimension_id === dim.id),
        );
        return (
          <details className="dimension" key={`${experiment.id}/${dim.id}`}>
            <summary>
              <span className="dimension-name">
                <ChevronRight size={16} />
                <span>
                  <strong>{dim.name}</strong>
                  <small>
                    {dim.method === "code"
                      ? "代码"
                      : dim.method === "llm"
                        ? "LLM"
                        : "混合"}
                    评价 · 权重 {dim.weight}
                  </small>
                </span>
              </span>
              <div className="dimension-values">
                <Badge
                  tone={
                    experiment.presentation?.dimensions?.[dim.id] === "Pass"
                      ? "green"
                      : "neutral"
                  }
                >
                  {experiment.presentation?.dimensions?.[dim.id]}
                </Badge>
                {groups.map((group) => {
                  const value = (
                    group === "history"
                      ? baseline?.dimension_scores?.[baselineGroup]
                      : experiment.dimension_scores?.[group]
                  )?.find((d: Json) => d.id === dim.id);
                  return (
                    <span key={group}>
                      <small>{names[group]}</small>
                      <strong>{score(value?.score)}</strong>
                      <small>
                        {value?.completed ?? 0}/
                        {value?.expected ??
                          cases.length *
                            (group === "history"
                              ? baseline!.trials
                              : experiment.trials)}
                      </small>
                    </span>
                  );
                })}
              </div>
            </summary>
            <div className="dimension-body">
              {cases.length === 1
                ? scene(cases[0], dim)
                : cases.map((c: Json) => (
                    <details className="scene" key={c.id}>
                      <summary>
                        <span>{c.name}</span>
                        <Badge>
                          {
                            experiment.presentation?.cases?.find(
                              (item: Json) => item.id === c.id,
                            )?.dimensions?.[dim.id]
                          }
                        </Badge>
                      </summary>
                      {scene(c, dim)}
                    </details>
                  ))}
            </div>
          </details>
        );
      })}
      {!dimensions.length &&
        definition.cases.map((c: Json) => (
          <details className="scene" key={c.id}>
            <summary>{c.name}</summary>
            {scene(c)}
          </details>
        ))}
      {!definition.cases.length && <Empty>暂无用例</Empty>}
    </Card>
  );
}
