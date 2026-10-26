import { useEffect, useState } from "react";
import { active, api, type Json } from "../../shared/api";
import { poll } from "../../shared/polling";
import { type CandidateKind, type SkillRevision } from "./CandidatePicker";
export function useSuite({
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
  const [suite, setSuite] = useState<Json | null>(null),
    [tab, setTab] = useState("data"),
    [configOpen, setConfigOpen] = useState(false),
    [selected, setSelected] = useState(initialExperiment ?? ""),
    [experiment, setExperiment] = useState<Json | null>(null),
    [baselineDetail, setBaselineDetail] = useState<Json | null>(null),
    [comparison, setComparison] = useState<Json | null>(null),
    [error, setError] = useState(""),
    [runner, setRunner] = useState(""),
    [judge, setJudge] = useState(""),
    [judgeBudget, setJudgeBudget] = useState(300),
    [mode, setMode] = useState("formal"),
    [candidate, setCandidate] = useState<CandidateKind>("no_skill"),
    [skillPath, setSkillPath] = useState(""),
    [skillRevision, setSkillRevision] = useState(""),
    [revisions, setRevisions] = useState<SkillRevision[]>([]),
    [assessmentId, setAssessmentId] = useState(""),
    [pending, setPending] = useState(false),
    [modal, setModal] = useState<Json | null>(null),
    [modalData, setModalData] = useState<Json | null>(null);
  const models = agents.find((a) => a.id === "chrys")?.models ?? [];
  useEffect(() => {
    api("/benchmark/skill-revisions")
      .then((data) => setRevisions(data.items))
      .catch(() => {});
  }, [suite?.execution_count]);
  useEffect(() => {
    setAssessmentId("");
  }, [selected]);
  useEffect(() => {
    if (models.length) {
      const model = models.find((item: Json) => item.active) ?? models[0];
      setRunner((old) => old || model.id);
      setJudge((old) => old || model.id);
    }
  }, [agents]);
  useEffect(() => {
    let alive = true;
    setBaselineDetail(null);
    if (suite?.baseline_experiment_id)
      api(
        `/experiments/${suite.baseline_experiment_id}?assessment_id=${suite.baseline_assessment_id}`,
      )
        .then((data) => {
          if (alive) setBaselineDetail(data);
        })
        .catch((error) => {
          if (alive) notify(String(error));
        });
    return () => {
      alive = false;
    };
  }, [suite?.baseline_experiment_id, suite?.baseline_assessment_id]);
  async function load() {
    try {
      const data = await api(`/benchmark/suites/${id}`);
      setSuite(data);
      setSelected((old) => old || data.experiments[0]?.id || "");
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }
  useEffect(() => {
    return poll(
      () => api(`/benchmark/suites/${id}`),
      (data) => {
        setSuite(data);
        setSelected((old) => old || data.experiments[0]?.id || "");
        setError("");
      },
      (e) => setError(String(e)),
      4000,
    );
  }, [id]);
  const latestAssessment = suite?.experiments?.find(
    (item: Json) => item.id === selected,
  )?.assessment_id;
  useEffect(() => {
    if (!selected) {
      setExperiment(null);
      return;
    }
    const query = assessmentId ? `?assessment_id=${assessmentId}` : "";
    return poll(
      () =>
        Promise.all([
          api(`/experiments/${selected}${query}`),
          api(`/benchmark/suites/${id}/comparison/${selected}${query}`),
        ]),
      ([exp, cmp]) => {
        setExperiment(exp);
        setComparison({
          ...cmp,
          experimentId: selected,
          baselineId: suite?.baseline_experiment_id ?? null,
          baselineGroup: "current",
        });
        setError("");
      },
      (e) => setError(String(e)),
      2500,
      ([exp]) => active(exp.status),
    );
  }, [
    selected,
    id,
    assessmentId,
    latestAssessment,
    suite?.baseline_experiment_id,
    suite?.baseline_assessment_id,
  ]);
  async function action(fn: () => Promise<void>) {
    setPending(true);
    try {
      await fn();
    } catch (e) {
      notify(String(e));
    } finally {
      setPending(false);
    }
  }
  async function run() {
    await action(async () => {
      const result = await api(`/benchmark/suites/${id}/execute`, {
        mode,
        candidate_kind: candidate,
        skill_path:
          candidate === "skill" && !skillRevision ? skillPath : undefined,
        skill_revision_id:
          candidate === "skill" && skillRevision ? skillRevision : undefined,
        profile: {
          name: "chrys-benchmark",
          runner_provider: "chrys",
          judge_provider: "chrys",
          runner_model: runner,
          judge_model: judge,
          timeout_seconds: 1800,
        },
      });
      setSelected(result.id);
      await load();
      notify("测评已启动");
    });
  }
  async function showRun(run: Json, kind: string) {
    setModal({ run, kind });
    setModalData(null);
    try {
      if (
        experiment?.assessment_id &&
        kind === "logs" &&
        run.execution_status === "completed"
      ) {
        setModalData(
          await api(
            `/benchmark/assessments/${experiment.assessment_id}/runs/${run.id}/logs?mode=raw`,
          ),
        );
        return;
      }
      if (experiment?.assessment_id && kind === "evidence") {
        const [executionFiles, assessmentFiles] = await Promise.all([
          api(`/runs/${run.id}/artifacts`),
          api(
            `/benchmark/assessments/${experiment.assessment_id}/runs/${run.id}/artifacts`,
          ),
        ]);
        setModalData({
          items: [...executionFiles.items, ...assessmentFiles.items],
        });
        return;
      }
      setModalData(
        await api(
          `/runs/${run.id}/${kind === "evidence" ? "artifacts" : kind === "logs" ? "logs?mode=raw" : "conversation"}`,
        ),
      );
    } catch (e) {
      setModalData({ error: String(e) });
    }
  }
  async function retry() {
    if (!experiment || pending) return;
    await action(async () => {
      const next = await api(
        `/benchmark/suites/${id}/experiments/${experiment.id}/retry`,
        {},
      );
      setSelected(next.id);
      setExperiment(null);
      await load();
      notify("已按当前运行环境重新执行，旧记录和证据已保留");
    });
  }
  async function rejudge() {
    if (!experiment || pending) return;
    await action(async () => {
      const next = await api(
        `/benchmark/suites/${id}/experiments/${experiment.id}/rejudge`,
        {
          judge_model: judge || experiment.profile.judge.model,
          judge_timeout_seconds: judgeBudget,
          judge_total_timeout_seconds: judgeBudget * 3,
        },
      );
      setSelected(next.id);
      setAssessmentId(next.assessment_id);
      setExperiment(null);
      await load();
      notify("仅评分重试已启动，执行产物与原评分记录已保留");
    });
  }

  return {
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
  };
}
