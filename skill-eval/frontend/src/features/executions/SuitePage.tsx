import {
  ArrowLeft,
  BarChart3,
  Copy,
  Lock,
  Play,
  RotateCcw,
  Settings2,
  Square,
} from "lucide-react";
import {
  active,
  api,
  date,
  navigate,
  score,
  statusName,
  type Json,
} from "../../shared/api";
import { ProgressSteps } from "../../shared/ProgressSteps";
import { Badge, Button, Card, Empty, Modal } from "../../shared/ui";
import { AssessmentPicker } from "../evaluations/AssessmentPicker";
import { EvaluationChart } from "../results/EvaluationChart";
import { ScoreRadar } from "../results/ScoreRadar";
import { TestCaseList } from "../results/TestCaseList";
import { TestCaseDefinitions } from "../suites/TestCaseDefinitions";
import { CandidatePicker } from "./CandidatePicker";
import { ExecutionLog } from "./ExecutionLog";
import { useSuite } from "./useSuite";
export function SuitePage({
  id,
  agents,
  notify,
  initialExperiment,
}: {
  id: string;
  agents: Json[];
  notify: (message: string) => void;
  initialExperiment?: string;
}) {
  const {
    suite,
    setSuite,
    tab,
    setTab,
    configOpen,
    setConfigOpen,
    selected,
    setSelected,
    experiment,
    setExperiment,
    baselineDetail,
    setBaselineDetail,
    comparison,
    setComparison,
    error,
    setError,
    runner,
    setRunner,
    judge,
    setJudge,
    judgeBudget,
    setJudgeBudget,
    mode,
    setMode,
    candidate,
    setCandidate,
    skillPath,
    setSkillPath,
    skillRevision,
    setSkillRevision,
    revisions,
    setRevisions,
    assessmentId,
    setAssessmentId,
    pending,
    setPending,
    modal,
    setModal,
    modalData,
    setModalData,
    models,
    load,
    action,
    run,
    showRun,
    retry,
    rejudge,
  } = useSuite({ id, agents, notify, initialExperiment });
  if (!suite)
    return (
      <main className="dashboard">
        <Empty>{error || "加载测试套…"}</Empty>
      </main>
    );
  const running = suite.experiments.some((exp: Json) => active(exp.status)),
    baseline = suite.baseline,
    baselineGroup = suite.baseline_group ?? "current";
  const runLabel = (expId: string) => {
    const index = [...suite.experiments]
      .reverse()
      .findIndex((exp: Json) => exp.id === expId);
    return index < 0 ? expId.slice(0, 8) : `Run ${index + 1}`;
  };
  const baselineLabel = baseline
    ? `${runLabel(baseline.id)} · ${baseline.candidate_label} · 评分 ${baseline.assessment_id?.slice(0, 8)}`
    : "未选择";
  const comparisonView =
    comparison?.experimentId === experiment?.id &&
    comparison?.baselineId === (suite.baseline_experiment_id ?? null) &&
    comparison?.baselineGroup === baselineGroup
      ? comparison
      : null;
  const canRejudge =
    !!experiment?.runs?.length &&
    experiment.profile.judge.provider === "chrys" &&
    experiment.runs.every(
      (run: Json) =>
        run.execution_status === "completed" && run.artifact_available,
    );
  return (
    <div className="suite-workspace suite-detail">
      <aside className="sidebar">
        <Button variant="ghost" onClick={() => navigate("/")}>
          <ArrowLeft size={15} />
          测试套管理
        </Button>
        <div className="sidebar-suite">
          <span className="eyebrow">TEST SUITE</span>
          <h2>{suite.name}</h2>
          <Badge>
            <Lock size={11} />
            固定测试集
          </Badge>
        </div>
        <nav>
          <button
            className={tab === "data" ? "selected" : ""}
            onClick={() => setTab("data")}
          >
            <BarChart3 size={17} />
            测评数据
          </button>
          <button
            className={tab === "cases" ? "selected" : ""}
            onClick={() => setTab("cases")}
          >
            <Settings2 size={17} />
            用例设置
          </button>
        </nav>
        <div className="sidebar-note">
          用例与项目地址已锁定。修改内容请复制为新测试套。
        </div>
      </aside>
      <main className="suite-main">
        <div className="page-heading">
          <div>
            <div className="eyebrow">
              {tab === "data" ? "EVALUATION EXECUTION" : "FIXED TEST CASES"}
            </div>
            <h1>{tab === "data" ? "测评数据" : "用例设置"}</h1>
            <p>
              {suite.skill_name} · {suite.name}
            </p>
          </div>
          <Button
            variant="outline"
            disabled={pending}
            onClick={() =>
              action(async () => {
                const draft = await api(`/benchmark/suites/${id}/copy`, {});
                navigate(`/drafts/${draft.id}`);
              })
            }
          >
            <Copy size={15} />
            复制并修改
          </Button>
        </div>
        {error && <div className="error-box">{error}</div>}
        <Card className="execution-controls">
          <div className="project-bar">
            <div className="min-w-0 flex-1">
              <label>项目仓库</label>
              <div className="project-path" title={suite.project_path}>
                <Lock size={13} />
                {suite.project_path}
              </div>
            </div>
            {tab === "data" && (
              <>
                <Button
                  variant="ghost"
                  onClick={() => setConfigOpen(!configOpen)}
                  aria-expanded={configOpen}
                  aria-controls="executionConfig"
                >
                  <Settings2 size={14} />
                  运行配置
                </Button>
                <CandidatePicker
                  candidate={candidate}
                  onCandidate={setCandidate}
                  path={skillPath}
                  onPath={setSkillPath}
                  revision={skillRevision}
                  onRevision={setSkillRevision}
                  revisions={revisions}
                />
                <select
                  aria-label="执行模式"
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                >
                  <option value="formal">正式 · 3 Trial</option>
                  <option value="quick">快速 · 1 Trial</option>
                </select>
                <Button
                  disabled={
                    pending ||
                    running ||
                    suite.archived ||
                    !runner ||
                    !judge ||
                    (candidate === "skill" && !skillPath && !skillRevision)
                  }
                  onClick={run}
                >
                  <Play size={15} />
                  执行
                </Button>
              </>
            )}
          </div>
          {tab === "data" && configOpen && (
            <div id="executionConfig" className="execution-config">
              <div className="grid md:grid-cols-2 gap-4 p-4">
                <label>
                  执行 Agent
                  <select
                    value={runner}
                    onChange={(e) => setRunner(e.target.value)}
                  >
                    <option value="">请选择模型</option>
                    {models.map((m: Json) => (
                      <option key={m.id} value={m.id}>
                        {m.name || m.id}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  评分 Agent
                  <select
                    value={judge}
                    onChange={(e) => setJudge(e.target.value)}
                  >
                    <option value="">请选择模型</option>
                    {models.map((m: Json) => (
                      <option key={m.id} value={m.id}>
                        {m.name || m.id}
                      </option>
                    ))}
                  </select>
                </label>
                <p className="text-xs text-slate-500 md:col-span-2">
                  每次仅运行一个候选。no_skill 与 Skill
                  共用任务、项目提交和评分规则；AAW 合规检查单独展示。
                </p>
              </div>
            </div>
          )}
        </Card>
        {tab === "cases" ? (
          <>
            <div className="info-box">
              正式测试套不可修改。每个场景可以关联多个固定评价维度，执行一次、分别评分。
            </div>
            <Card className="p-6">
              <h2 className="font-semibold mb-4">评价维度与检查标准</h2>
              {suite.definition.dimensions?.map((dim: Json) => (
                <details className="scene" key={dim.id}>
                  <summary>
                    <strong>{dim.name}</strong>
                    <Badge>{dim.method}</Badge>
                  </summary>
                  <div className="p-4">
                    <p className="text-sm text-slate-500 mb-3">
                      {dim.description} · 通过阈值 {dim.pass_score} · 权重{" "}
                      {dim.weight}
                    </p>
                    {dim.checkpoints?.map((point: Json) => (
                      <p className="text-sm my-2" key={point.id}>
                        {point.name}：{point.description}
                      </p>
                    ))}
                  </div>
                </details>
              ))}
              {!suite.definition.dimensions?.length && (
                <pre>{JSON.stringify(suite.definition, null, 2)}</pre>
              )}
            </Card>
            <TestCaseDefinitions definition={suite.definition} />
          </>
        ) : (
          <>
            <div className="chart-grid">
              <Card className="p-5">
                <div className="section-heading">
                  <div>
                    <h2>能力维度</h2>
                    <p>本次执行 / {baselineLabel}</p>
                  </div>
                  <Badge>{baseline ? "已设基线" : "未设基线"}</Badge>
                </div>
                <ScoreRadar current={experiment} baseline={baseline} />
              </Card>
              <Card className="p-5">
                <div className="section-heading">
                  <div>
                    <h2>运行评分趋势</h2>
                    <p>点击柱子或运行编号查看该次结果</p>
                  </div>
                  <Badge>{suite.experiments.length} 次执行</Badge>
                </div>
                <EvaluationChart
                  experiments={suite.experiments}
                  selected={selected}
                  onSelect={setSelected}
                />
              </Card>
            </div>
            {experiment ? (
              <>
                <Card className="execution-panel">
                  <div className="execution-summary">
                    <div>
                      <Badge
                        tone={
                          experiment.status === "completed"
                            ? "green"
                            : "neutral"
                        }
                      >
                        {statusName(experiment.status)}
                      </Badge>
                      <span>
                        {date(experiment.created_at)} ·{" "}
                        {experiment.mode === "formal" ? "正式" : "快速"} ·{" "}
                        {experiment.trials} Trial
                      </span>
                    </div>
                    <div>
                      <label>本次评分</label>
                      <strong>{score(experiment.scores.current)}</strong>
                    </div>
                    <div>
                      <label>所选基线</label>
                      <strong>{score(baseline?.scores[baselineGroup])}</strong>
                    </div>
                    <div>
                      <label>
                        {comparisonView?.formal ? "正式分差" : "参考分差"}
                      </label>
                      <strong>
                        {comparisonView?.delta == null
                          ? "—"
                          : `${comparisonView.delta >= 0 ? "+" : ""}${score(comparisonView.delta)}`}
                      </strong>
                    </div>
                    <div className="flex gap-2">
                      <select
                        aria-label="对比基线"
                        disabled={pending}
                        value={
                          baseline
                            ? `${baseline.id}/${suite.baseline_assessment_id}`
                            : ""
                        }
                        onChange={(e) => {
                          const [experimentId, baselineAssessmentId] =
                            e.target.value.split("/");
                          action(async () => {
                            await api(`/benchmark/suites/${id}/baseline`, {
                              experiment_id: experimentId || null,
                              assessment_id: baselineAssessmentId || null,
                            });
                            await load();
                            notify(
                              experimentId
                                ? "对比基线已更新"
                                : "已清除对比基线",
                            );
                          });
                        }}
                      >
                        <option value="">未选择对比基线</option>
                        {[...suite.experiments].reverse().flatMap((exp: Json) =>
                          (exp.assessments ?? [])
                            .filter((a: Json) => a.status === "completed")
                            .map((a: Json, i: number) => (
                              <option key={a.id} value={`${exp.id}/${a.id}`}>
                                {runLabel(exp.id)} · {exp.candidate_label} ·
                                评分 {i + 1}
                              </option>
                            )),
                        )}
                      </select>
                      {active(experiment.status) && (
                        <Button
                          variant="danger"
                          onClick={() =>
                            action(async () => {
                              await api(`/experiments/${selected}/cancel`, {});
                              notify("已请求停止");
                            })
                          }
                        >
                          <Square size={14} />
                          停止
                        </Button>
                      )}
                    </div>
                  </div>
                  <div className="execution-meta">
                    {" "}
                    <ProgressSteps
                      steps={
                        experiment.execution_kind === "judge_only"
                          ? ["复用已完成产物", "按维度评分", "合并结果", "完成"]
                          : ["准备环境", "执行任务", "评价结果", "完成"]
                      }
                      current={
                        experiment.status === "completed"
                          ? 4
                          : experiment.status === "queued" ||
                              experiment.status === "preparing"
                            ? 0
                            : ["validator", "judge", "collect"].includes(
                                  experiment.progress.active_stage,
                                )
                              ? 2
                              : experiment.status === "running"
                                ? 1
                                : -1
                      }
                      failed={
                        !active(experiment.status) &&
                        experiment.status !== "completed"
                      }
                    />
                    <AssessmentPicker
                      value={assessmentId}
                      onChange={setAssessmentId}
                      assessments={experiment.assessments ?? []}
                    />
                    {canRejudge && !running && (
                      <Button
                        variant="outline"
                        disabled={pending}
                        onClick={rejudge}
                      >
                        重新评分
                      </Button>
                    )}
                    <small>
                      项目 {experiment.project_commit.slice(0, 10)} · Skill{" "}
                      {experiment.current_revision.slice(0, 10)} ·{" "}
                      {experiment.profile.runner.model_name ||
                        experiment.profile.runner.model}
                    </small>
                  </div>{" "}
                  {comparisonView && !comparisonView.formal && (
                    <div className="comparison-note">
                      {comparisonView.reasons.join(" · ")}
                      。分数保留供分析，不作为正式提升结论。
                    </div>
                  )}
                </Card>
                {experiment.retry_of_experiment_id && (
                  <p className="comparison-note">
                    {experiment.execution_kind === "judge_only"
                      ? "仅重新评分，复用"
                      : "重新执行自"}{" "}
                    {runLabel(experiment.retry_of_experiment_id)} ·
                    原项目提交、用例和 Skill
                    版本保持固定；采用本次记录中的运行环境配置。旧记录和证据保留。
                  </p>
                )}
                {(experiment.error_message ||
                  [
                    "failed",
                    "cancelled",
                    "interrupted",
                    "completed_with_failures",
                  ].includes(experiment.status)) && (
                  <Card className="execution-failure p-4">
                    <div className="section-heading">
                      <div>
                        <h2>
                          {canRejudge
                            ? "Agent 执行已完成，评分未完成"
                            : "执行未完成"}
                        </h2>
                        <p>
                          {canRejudge
                            ? "可复用本次固定产物，仅重试评分。新模型重新评分全部 LLM 维度；同一模型复用已完成维度。"
                            : "重新执行会使用当前运行环境，从原项目提交开始，保留本次记录。"}
                        </p>
                      </div>
                      <div className="flex gap-2 items-center flex-wrap">
                        {canRejudge && (
                          <>
                            <label>
                              评分重试模型
                              <select
                                aria-label="评分重试模型"
                                value={judge || experiment.profile.judge.model}
                                onChange={(e) => setJudge(e.target.value)}
                                disabled={pending || running}
                              >
                                {!models.some(
                                  (m: Json) =>
                                    m.id ===
                                    (judge || experiment.profile.judge.model),
                                ) && (
                                  <option
                                    value={
                                      judge || experiment.profile.judge.model
                                    }
                                  >
                                    {judge || experiment.profile.judge.model}
                                  </option>
                                )}
                                {models.map((m: Json) => (
                                  <option key={m.id} value={m.id}>
                                    {m.name || m.id}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label>
                              单维度评分预算
                              <select
                                aria-label="单维度评分预算"
                                value={judgeBudget}
                                onChange={(e) =>
                                  setJudgeBudget(Number(e.target.value))
                                }
                                disabled={pending || running}
                              >
                                <option value={300}>5 分钟</option>
                                <option value={600}>10 分钟</option>
                                <option value={900}>15 分钟</option>
                              </select>
                            </label>
                            <Button
                              disabled={pending || running}
                              onClick={rejudge}
                            >
                              仅重试评分
                            </Button>
                          </>
                        )}
                        <Button
                          variant="outline"
                          disabled={pending || running}
                          onClick={retry}
                        >
                          <RotateCcw size={15} />
                          重新执行
                        </Button>
                      </div>
                    </div>
                    {(experiment.runs ?? [])
                      .filter((run: Json) => run.error_message)
                      .map((run: Json) => (
                        <div className="run-failure" key={run.id}>
                          <div className="flex gap-2 items-center">
                            <Badge tone="red">
                              {run.error_kind === "workflow_incomplete"
                                ? "AAW 流程未完成"
                                : run.error_kind === "judge_error" ||
                                    run.error_kind === "grader_invalid"
                                  ? "评价结果异常"
                                  : run.status === "infra_error"
                                    ? "运行环境错误"
                                    : statusName(run.status)}
                            </Badge>
                            <strong>
                              {run.case_id} · Trial {run.trial}
                            </strong>
                            <Button
                              variant="ghost"
                              onClick={() => showRun(run, "logs")}
                            >
                              查看日志
                            </Button>
                          </div>
                          <p>{run.error_message}</p>
                        </div>
                      ))}
                    {!(experiment.runs ?? []).some(
                      (run: Json) => run.error_message,
                    ) && (
                      <p>
                        {experiment.error_message ||
                          "本次执行已中断，可修复问题后重新执行。"}
                      </p>
                    )}
                  </Card>
                )}
                {experiment.runs?.some(
                  (run: Json) => run.execution_status === "completed",
                ) && (
                  <Card className="p-4 judge-status-panel">
                    <div className="section-heading">
                      <h2>执行与评分状态</h2>
                      <small>
                        Judge：
                        {experiment.profile.judge.model_name ||
                          experiment.profile.judge.model}
                      </small>
                    </div>
                    {experiment.runs.map((run: Json) => (
                      <div key={run.id}>
                        <p>
                          {run.case_id} · Agent：
                          {run.execution_status === "completed"
                            ? "已完成"
                            : "未完成"}{" "}
                          · 评分：
                          {run.status === "completed"
                            ? "已完成"
                            : active(run.status)
                              ? "进行中"
                              : "未完成"}
                        </p>
                        {Object.entries(
                          run.judge_progress?.dimensions ?? {},
                        ).map(([key, state]) => (
                          <div className="judge-dimension-state" key={key}>
                            <strong>
                              {suite.definition.dimensions.find(
                                (d: Json) => d.id === key,
                              )?.name || key}
                            </strong>
                            <Badge
                              tone={
                                (state as Json).status === "failed"
                                  ? "red"
                                  : (state as Json).status === "completed" ||
                                      (state as Json).status === "cached"
                                    ? "green"
                                    : "neutral"
                              }
                            >
                              {
                                (
                                  {
                                    pending: "等待",
                                    running: "评分中",
                                    completed: "已完成",
                                    cached: "复用已完成评分",
                                    failed: "失败",
                                  } as Json
                                )[(state as Json).status]
                              }
                            </Badge>
                            <span>
                              {(state as Json).elapsed_seconds != null
                                ? `${(state as Json).elapsed_seconds}秒`
                                : ""}
                            </span>
                            {(state as Json).error && (
                              <p>{(state as Json).error}</p>
                            )}
                          </div>
                        ))}
                      </div>
                    ))}
                  </Card>
                )}
                <TestCaseDefinitions
                  definition={experiment.suite_snapshot}
                  experiment={experiment}
                />
                <TestCaseList
                  experiment={experiment}
                  baseline={baselineDetail}
                  baselineGroup={baselineGroup}
                  currentLabel={`本次执行：${runLabel(experiment.id)}`}
                  baselineLabel={baselineLabel}
                  onRun={showRun}
                />

                <ExecutionLog
                  key={selected}
                  experimentId={selected}
                  assessmentId={experiment.assessment_id}
                  runs={experiment.runs}
                />
              </>
            ) : (
              <>
                <TestCaseDefinitions definition={suite.definition} />
                <Empty>测试套已准备就绪，选择模型并点击执行。</Empty>
              </>
            )}
          </>
        )}
        <Modal
          open={!!modal}
          onOpenChange={() => setModal(null)}
          title={
            modal
              ? `${modal.run.case_id} · Trial ${modal.run.trial} · ${modal.kind === "logs" ? "日志" : modal.kind === "evidence" ? "证据" : "对话"}`
              : ""
          }
        >
          {modal?.kind === "evidence" &&
            modalData?.items?.map((item: Json) => (
              <a
                key={item.name}
                href={item.url}
                target="_blank"
                rel="noreferrer"
                className="block text-emerald-700 text-sm mb-3"
              >
                {item.name} · {item.size} bytes
              </a>
            ))}
          <pre className="modal-json">
            {modalData ? JSON.stringify(modalData, null, 2) : "加载中…"}
          </pre>
        </Modal>
      </main>
    </div>
  );
}
