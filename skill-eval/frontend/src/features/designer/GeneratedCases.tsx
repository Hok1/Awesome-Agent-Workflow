import { useState } from "react";
import type { Json } from "../../shared/api";
import { Badge, Button, Card } from "../../shared/ui";

export function GeneratedCases({
  draft,
  dirty,
  busy,
  onSave,
  onSuggestion,
  interactionPending,
}: {
  draft: Json;
  dirty: boolean;
  busy: boolean;
  onSave: (id: string, fields: Json) => Promise<boolean>;
  onSuggestion: (id: string, action: string, text?: string) => Promise<boolean>;
  interactionPending: boolean;
}) {
  const [editing, setEditing] = useState<Json | null>(null);
  const [suggestionEdit, setSuggestionEdit] = useState<Json | null>(null);
  const preview = draft.preview;
  if (!preview)
    return (
      <Card className="generated-cases">
        <h2>生成的测评用例</h2>
        <p className="text-sm text-slate-500 mt-2">
          {draft.preview_error ||
            "描述测评目标，让 Agent 生成完整任务、推荐评价维度和检查规则，结果会直接呈现在这里。"}
        </p>
      </Card>
    );
  return (
    <Card className="generated-cases">
      <div className="section-heading">
        <h2>生成的测评用例</h2>
        <Badge>{preview.cases.length} 个完整任务</Badge>
      </div>
      {dirty && (
        <p className="text-sm text-amber-700 mb-3">
          配置已修改，以下为上次生成结果；请重新生成或校验后确认使用。
        </p>
      )}
      {preview.cases.map((item: Json) => (
        <article className="generated-case" key={item.id}>
          <div className="flex gap-3 items-center justify-between">
            <strong>{item.name}</strong>
            <Button
              variant="ghost"
              disabled={busy}
              onClick={() =>
                setEditing({
                  id: item.id,
                  name: item.name,
                  input: item.input,
                  expected: item.expected,
                })
              }
            >
              编辑任务与预期
            </Button>
          </div>
          {editing && editing.id === item.id ? (
            <div className="grid gap-3 mt-3">
              <label>
                用例名称
                <input
                  value={editing.name}
                  disabled={busy}
                  onChange={(e) =>
                    setEditing({ ...editing, name: e.target.value })
                  }
                />
              </label>
              <label>
                任务描述
                <textarea
                  rows={5}
                  value={editing.input}
                  disabled={busy}
                  onChange={(e) =>
                    setEditing({ ...editing, input: e.target.value })
                  }
                />
              </label>
              <label>
                预期结果
                <textarea
                  rows={5}
                  value={editing.expected}
                  disabled={busy}
                  onChange={(e) =>
                    setEditing({ ...editing, expected: e.target.value })
                  }
                />
              </label>
              <div className="flex gap-2 justify-end">
                <Button
                  variant="ghost"
                  disabled={busy}
                  onClick={() => setEditing(null)}
                >
                  取消编辑
                </Button>
                <Button
                  disabled={
                    busy ||
                    !editing.name.trim() ||
                    !editing.input.trim() ||
                    !editing.expected.trim()
                  }
                  onClick={async () => {
                    if (
                      await onSave(item.id, {
                        name: editing.name,
                        input: editing.input,
                        expected: editing.expected,
                      })
                    )
                      setEditing(null);
                  }}
                >
                  保存用例
                </Button>
              </div>
            </div>
          ) : (
            <div className="generated-case-text">
              <div>
                <label>任务描述</label>
                <p>{item.input}</p>
              </div>
              <div>
                <label>预期结果</label>
                <p>{item.expected}</p>
              </div>
            </div>
          )}
          {!!item.files?.length && (
            <details className="definition">
              <summary>参考材料 · {item.files.length} 个文件</summary>
              {item.files.map((file: Json) => (
                <details key={file.path} className="p-3">
                  <summary>{file.path}</summary>
                  <pre>
                    {new TextDecoder().decode(
                      Uint8Array.from(atob(file.content_base64), (c) =>
                        c.charCodeAt(0),
                      ),
                    )}
                  </pre>
                </details>
              ))}
            </details>
          )}
          <div className="generated-evaluations">
            {preview.dimensions
              .filter((dim: Json) =>
                item.graders.some((g: Json) => g.dimension_id === dim.id),
              )
              .map((dim: Json) => (
                <details key={dim.id} className="definition">
                  <summary>
                    <strong>{dim.name}</strong>
                    <Badge>
                      {dim.method === "code"
                        ? "代码检查"
                        : dim.method === "llm"
                          ? "Agent 评价"
                          : "代码 + Agent 评价"}
                    </Badge>
                    <Badge>
                      {(
                        {
                          pending: "等待配置",
                          generating: "生成检查",
                          validating: "试运行",
                          repairing: "局部修复",
                          ready: "已就绪",
                          failed: "未完成",
                        } as Record<string, string>
                      )[draft.workflow?.dimensions?.[dim.id]?.status] ||
                        "已配置"}
                    </Badge>
                    <span>
                      阈值 {dim.pass_score} · 权重 {dim.weight}
                    </span>
                  </summary>
                  <div className="p-3">
                    <p className="text-sm text-slate-500">
                      {draft.data.dimension_reasons?.[dim.id] ||
                        dim.description}
                    </p>
                    {draft.workflow?.dimensions?.[dim.id]?.detail && (
                      <p className="text-sm my-2">
                        {draft.workflow.dimensions[dim.id].detail}
                        {draft.workflow.dimensions[dim.id].attempt > 0 &&
                          ` · 局部修复 ${draft.workflow.dimensions[dim.id].attempt}/2`}
                      </p>
                    )}
                    {(dim.checkpoints ?? []).map((point: Json) => (
                      <p className="text-sm my-2" key={point.id}>
                        {point.name}：{point.description}
                      </p>
                    ))}
                  </div>
                </details>
              ))}
          </div>
          <details className="definition">
            <summary>高级：验证代码与运行配置</summary>
            {item.graders.map((grader: Json) => (
              <div className="p-3" key={grader.id}>
                <strong>{grader.name}</strong>
                <p>
                  {grader.pending
                    ? "评价方式准备中，草案已可查看"
                    : grader.command || "按平台固定标准评价"}
                </p>
                {grader.files?.map((file: Json) => (
                  <details key={file.path}>
                    <summary>{file.path}</summary>
                    <pre>
                      {new TextDecoder().decode(
                        Uint8Array.from(atob(file.content_base64), (c) =>
                          c.charCodeAt(0),
                        ),
                      )}
                    </pre>
                  </details>
                ))}
              </div>
            ))}
          </details>
        </article>
      ))}
      {!!draft.workflow?.plan?.suggestions?.some(
        (s: Json) => s.status === "pending",
      ) && (
        <section className="designer-suggestions">
          <h3>待确认建议</h3>
          <p>以下内容尚未加入任务或评分要求。</p>
          {draft.workflow.plan.suggestions
            .filter((s: Json) => s.status === "pending")
            .map((s: Json) => (
              <div key={s.id}>
                {suggestionEdit?.id === s.id ? (
                  <textarea
                    aria-label="修改建议"
                    value={suggestionEdit!.text}
                    onChange={(e) =>
                      setSuggestionEdit({
                        ...suggestionEdit,
                        text: e.target.value,
                      })
                    }
                  />
                ) : (
                  <p>{s.text}</p>
                )}
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    disabled={interactionPending}
                    onClick={() => onSuggestion(s.id, "adopt")}
                  >
                    采纳
                  </Button>
                  <Button
                    variant="ghost"
                    disabled={interactionPending}
                    onClick={async () => {
                      if (suggestionEdit?.id === s.id) {
                        if (
                          await onSuggestion(s.id, "edit", suggestionEdit!.text)
                        )
                          setSuggestionEdit(null);
                      } else setSuggestionEdit(s);
                    }}
                  >
                    {suggestionEdit?.id === s.id ? "按修改内容采纳" : "修改"}
                  </Button>
                  <Button
                    variant="ghost"
                    disabled={interactionPending}
                    onClick={() => onSuggestion(s.id, "ignore")}
                  >
                    忽略
                  </Button>
                </div>
              </div>
            ))}
        </section>
      )}
    </Card>
  );
}
