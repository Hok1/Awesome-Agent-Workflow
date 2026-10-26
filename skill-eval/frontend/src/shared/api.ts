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
    throw Object.assign(
      new Error(
        result.message ?? result.detail ?? `请求失败 ${response.status}`,
      ),
      { status: response.status },
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
    "discussing",
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
    discussing: "讨论与设计中",
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
