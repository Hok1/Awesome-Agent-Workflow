export type Json = Record<string, any>;
export async function api<T = Json>(
  path: string,
  data?: unknown,
  method?: string,
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method: method ?? (data ? "POST" : "GET"),
    headers: data ? { "Content-Type": "application/json" } : undefined,
    body: data ? JSON.stringify(data) : undefined,
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(
      result.message ?? result.detail ?? `请求失败 ${response.status}`,
    );
  return result;
}
export const score = (value: number | null | undefined) =>
  value == null ? "—" : value.toFixed(1);
export const date = (value: string) =>
  new Date(value).toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
export const active = (status: string) =>
  [
    "queued",
    "preparing",
    "running",
    "analyzing",
    "generating",
    "validating",
  ].includes(status);
export const statusName = (status: string) =>
  ({
    queued: "等待执行",
    preparing: "准备中",
    running: "执行中",
    completed: "已完成",
    completed_with_failures: "完成 · 存在失败",
    agent_error: "Agent 错误",
    infra_error: "环境错误",
    judge_error: "评分错误",
    timeout: "超时",
    failed: "失败",
    interrupted: "已中断",
    cancelled: "已取消",
    draft: "草稿",
    analyzing: "分析项目",
    generating: "生成用例",
    validating: "隔离校验",
    ready: "草稿就绪",
    saved: "已保存",
  })[status] ?? status;
export function navigate(path: string) {
  location.hash = path;
}
export function encode(text: string) {
  const bytes = new TextEncoder().encode(text);
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}
export function documentsPackage(doc: Json) {
  return {
    files: [
      {
        path: "suite.json",
        content_base64: encode(JSON.stringify(doc.manifest)),
      },
      ...Object.entries(doc.assets ?? {}).map(([path, text]) => ({
        path,
        content_base64: encode(String(text)),
      })),
    ],
  };
}
export function caseVerdict(
  runs: Json[],
  expected: number,
  dimensionId?: string,
): string {
  if (!runs.length) return "未执行";
  if (
    runs.some((run) => !["completed", "running", "queued"].includes(run.status))
  )
    return "Error";
  if (runs.length < expected || runs.some((run) => run.status !== "completed"))
    return "未完成";
  if (
    !dimensionId &&
    runs.some((run) => run.hard_gates?.passed < run.hard_gates?.total)
  )
    return "Failed";
  const dimensions = runs.flatMap((run) =>
    (run.scores?.dimensions ?? []).filter(
      (dim: Json) => !dimensionId || dim.id === dimensionId,
    ),
  );
  if (dimensions.some((dim) => dim.invalid)) return "Error";
  if (dimensionId && dimensions.length !== runs.length) return "未完成";
  if (!dimensionId && dimensions.length === 0)
    return runs.some((run) => run.scores?.invalid) ? "Error" : "Pass";
  return dimensions.some(
    (dim) => !dim.passed || dim.score == null || dim.score < dim.pass_score,
  )
    ? "Failed"
    : "Pass";
}

export function gateStatus(experiment: Json, group = "current"): string {
  const runs = experiment.runs.filter((run: Json) => run.group === group);
  const definition = experiment.suite_snapshot;
  const expected =
    definition.cases.reduce(
      (total: number, caseSpec: Json) =>
        total +
        caseSpec.graders.filter((grader: Json) => grader.hard_gate).length +
        (definition.dimensions ?? []).filter(
          (dim: Json) =>
            dim.hard_gate &&
            caseSpec.graders.some(
              (grader: Json) => grader.dimension_id === dim.id,
            ),
        ).length +
        (caseSpec.workflow && group !== "no_skill" ? 1 : 0),
      0,
    ) * experiment.trials;
  const total = runs.reduce(
    (sum: number, run: Json) => sum + (run.hard_gates?.total ?? 0),
    0,
  );
  if (
    runs.some(
      (run: Json) =>
        run.hard_gates?.passed < run.hard_gates?.total ||
        run.scores?.workflow_completion?.passed === false,
    )
  )
    return "未通过";
  if (!expected && !total) return "不适用";
  if (
    runs.some((run: Json) => ["running", "queued"].includes(run.status)) ||
    (!runs.length && active(experiment.status))
  )
    return "待检查";
  if (total < expected) return "缺少检查结果";
  return "通过";
}
