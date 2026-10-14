import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  Save,
  ShieldCheck,
  FolderOpen,
  Upload,
  Download,
  Lock,
  Check,
} from "lucide-react";
import { api, active, documentsPackage, navigate, type Json } from "../lib/api";
import { AgentChat } from "../components/AgentChat";
import { PackageEditor } from "../components/PackageEditor";
import { Badge, Button, Card, Empty, Modal } from "../components/ui";
import { draftDefaults } from "../lib/draft";
const initial = draftDefaults();
export function DesignerPage({
  id,
  agents,
  notify,
}: {
  id?: string;
  agents: Json[];
  notify: (message: string) => void;
}) {
  const [draft, setDraft] = useState<Json | null>(null),
    [data, setData] = useState<Json>(initial),
    [catalog, setCatalog] = useState<Json | null>(null),
    [pending, setPending] = useState(false),
    [editor, setEditor] = useState<Json | null>(null),
    [editorText, setEditorText] = useState(""),
    [error, setError] = useState(""),
    [pathModal, setPathModal] = useState<string | null>(null),
    [pathData, setPathData] = useState<Json | null>(null),
    [pathInput, setPathInput] = useState("");
  const upload = useRef<HTMLInputElement>(null),
    folderUpload = useRef<HTMLInputElement>(null),
    importDimension = useRef("");
  const models = agents.find((a) => a.id === "chrys")?.models ?? [];
  const busy = pending || !!(draft && active(draft.status));
  const dirty =
    !!draft &&
    JSON.stringify(data) !== JSON.stringify(draftDefaults(draft.data));
  useEffect(() => {
    api("/dimension-templates")
      .then(setCatalog)
      .catch((e) => setError(String(e)));
  }, []);
  useEffect(() => {
    if (id) {
      let alive = true;
      api(`/benchmark/drafts/${id}`)
        .then((result) => {
          if (alive) {
            setDraft(result);
            setData(draftDefaults(result.data));
          }
        })
        .catch((e) => setError(String(e)));
      return () => {
        alive = false;
      };
    }
    setDraft(null);
    setData(initial);
  }, [id]);
  useEffect(() => {
    if (!draft || !active(draft.status)) return;
    let alive = true;
    const timer = setInterval(async () => {
      try {
        const next = await api(`/benchmark/drafts/${draft.id}`);
        if (alive) {
          setDraft(next);
          if (!active(next.status)) setData(draftDefaults(next.data));
        }
      } catch (e) {
        if (alive) setError(String(e));
      }
    }, 1500);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [draft?.id, draft?.status]);
  useEffect(() => {
    if (models.length)
      setData((old) => ({
        ...old,
        generator_model:
          old.generator_model ||
          (models.find((item: Json) => item.active) ?? models[0]).id,
      }));
  }, [agents, draft?.id]);
  async function action(fn: () => Promise<void>) {
    setPending(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(String(e));
      notify(String(e));
    } finally {
      setPending(false);
    }
  }
  async function persist() {
    const next = await api(
      draft ? `/benchmark/drafts/${draft.id}` : "/benchmark/drafts",
      { data, revision: draft?.revision },
      draft ? "PUT" : "POST",
    );
    setDraft(next);
    setData(draftDefaults(next.data));
    if (!id) navigate(`/drafts/${next.id}`);
    return next;
  }
  async function send(message: string) {
    await action(async () => {
      const saved = dirty || !draft ? await persist() : draft;
      const next = await api(`/benchmark/drafts/${saved!.id}/generate`, {
        message,
        revision: saved!.revision,
      });
      setDraft(next);
    });
  }
  async function validate() {
    await action(async () => {
      const saved = dirty || !draft ? await persist() : draft;
      const next = await api(`/benchmark/drafts/${saved!.id}/validate`, {
        revision: saved!.revision,
      });
      setDraft(next);
    });
  }
  async function save() {
    await action(async () => {
      if (dirty) throw new Error("草稿已修改，请重新隔离校验");
      const suite = await api(`/benchmark/drafts/${draft!.id}/save`, {
        revision: draft!.revision,
      });
      notify("测试套已保存，用例与项目地址已锁定");
      navigate(`/suites/${suite.id}`);
    });
  }
  function change(key: string, value: unknown) {
    setData((old) => ({ ...old, [key]: value }));
  }
  function selectDimension(dim: Json, enabled: boolean) {
    change(
      "dimensions",
      enabled
        ? [
            ...data.dimensions,
            { id: dim.id, weight: 1, hard_gate: false, pass_score: 60 },
          ]
        : data.dimensions.filter((d: Json) => d.id !== dim.id),
    );
  }
  async function importFiles(files: FileList | null, folder = false) {
    if (!files?.length) return;
    await action(async () => {
      const key = importDimension.current;
      let pack: Json;
      if (folder) {
        const items = await Promise.all(
          [...files].map(async (file) => {
            const bytes = new Uint8Array(await file.arrayBuffer());
            let binary = "";
            for (const byte of bytes) binary += String.fromCharCode(byte);
            return {
              path: file.webkitRelativePath || file.name,
              content_base64: btoa(binary),
            };
          }),
        );
        pack = { files: items };
      } else {
        const file = files[0];
        if (file.size > 20 * 1024 * 1024) throw new Error("用例包超过20MB");
        const bytes = new Uint8Array(await file.arrayBuffer());
        let binary = "";
        for (const byte of bytes) binary += String.fromCharCode(byte);
        pack = { zip_base64: btoa(binary) };
      }
      await api("/suite-packages/preview", {
        ...pack,
        catalog_version: catalog!.catalog_version,
        skill_type: "workflow",
        dimension_id: key,
      });
      change("packages", { ...data.packages, [key]: pack });
      notify("用例包已导入，保存前请隔离校验");
    });
  }
  async function editPackage(dim: Json) {
    await action(async () => {
      const doc = await api("/benchmark/package-documents", {
        dimension_id: dim.id,
        package: data.packages[dim.id],
      });
      setEditor(dim);
      setEditorText(JSON.stringify(doc, null, 2));
    });
  }
  async function applyEditor() {
    await action(async () => {
      const doc = JSON.parse(editorText),
        pack = documentsPackage(doc);
      await api("/suite-packages/preview", {
        ...pack,
        catalog_version: catalog!.catalog_version,
        skill_type: "workflow",
        dimension_id: editor!.id,
      });
      change("packages", { ...data.packages, [editor!.id]: pack });
      setEditor(null);
    });
  }
  async function browse(path: string) {
    try {
      setPathData(
        await api(`/benchmark/directories?path=${encodeURIComponent(path)}`),
      );
    } catch (e) {
      notify(String(e));
    }
  }
  const checked =
    !dirty &&
    draft?.validation?.scripts_checked &&
    draft?.validation?.scripts_runnable;
  if (id && !draft)
    return (
      <main className="dashboard">
        <Empty>{error || "加载草稿…"}</Empty>
      </main>
    );
  if (draft?.status === "saved")
    return (
      <main className="dashboard">
        <Empty>
          此草稿已保存并锁定。
          <Button onClick={() => navigate(`/suites/${draft.suite_id}`)}>
            查看测试套
          </Button>
        </Empty>
      </main>
    );
  return (
    <div className="suite-workspace">
      <aside className="sidebar">
        <Button variant="ghost" onClick={() => navigate("/")}>
          <ArrowLeft size={15} />
          测试套管理
        </Button>
        <div className="sidebar-suite">
          <span className="eyebrow">TEST DESIGNER</span>
          <h2>{data.name || "测试套"}</h2>
          <Badge>待配置</Badge>
        </div>
        <nav>
          <button disabled>测评数据</button>
          <button className="selected">用例设置</button>
        </nav>
        <div className="sidebar-note">
          选择固定标准 → 生成或导入用例 → 隔离校验 → 保存并锁定
        </div>
      </aside>
      <main className="suite-main">
        <div className="page-heading">
          <div>
            <div className="eyebrow">AGENT TEST DESIGNER</div>
            <h1>用例配置</h1>
            <p>为代码、文档与分析设计建立可复用的固定测试集。</p>
          </div>
          <Button
            variant="outline"
            disabled={busy}
            onClick={() =>
              action(async () => {
                await persist();
                notify("草稿已保存");
              })
            }
          >
            <Save size={15} />
            保存草稿
          </Button>
        </div>
        {error && <div className="error-box">{error}</div>}
        <Card className="p-6">
          <div className="section-heading">
            <div>
              <h2>基础配置</h2>
              <p>正式保存后，项目地址与测试用例不可修改</p>
            </div>
            <Lock size={16} className="text-slate-400" />
          </div>
          <div className="form-grid">
            <label>
              测试套名称
              <input
                placeholder="例如：AAW 开发与文档联合测评"
                value={data.name}
                disabled={busy}
                onChange={(e) => change("name", e.target.value)}
              />
            </label>
            <label>
              生成 Agent 模型
              <select
                value={data.generator_model}
                disabled={busy}
                onChange={(e) => change("generator_model", e.target.value)}
              >
                <option value="">请选择 Chrys 模型</option>
                {models.map((model: Json) => (
                  <option key={model.id} value={model.id}>
                    {model.name || model.id}
                  </option>
                ))}
              </select>
            </label>
            {[
              ["project_path", "项目路径"],
              ["skill_path", "目标 Skill 路径"],
            ].map(([key, label]) => (
              <label key={key}>
                {label}
                <div className="path-input">
                  <input
                    placeholder={
                      key === "project_path"
                        ? "干净的本地 Git 仓库"
                        : "包含 SKILL.md 的目录"
                    }
                    value={data[key]}
                    disabled={busy}
                    onChange={(e) => change(key, e.target.value)}
                  />
                  <Button
                    variant="ghost"
                    disabled={busy}
                    aria-label={`选择${label}`}
                    onClick={() => {
                      setPathModal(key);
                      setPathInput(data[key]);
                      browse(data[key]);
                    }}
                  >
                    <FolderOpen size={16} />
                  </Button>
                </div>
              </label>
            ))}
            <label className="col-span-full">
              需求描述
              <textarea
                rows={4}
                placeholder="描述想测评的 Skill 能力、项目任务、交付物和边界条件…"
                value={data.requirement}
                disabled={busy}
                onChange={(e) => change("requirement", e.target.value)}
              />
            </label>
            <label className="col-span-full">
              环境准备命令（每行一条，可选）
              <textarea
                rows={2}
                placeholder="例如：python -m pip install -e ."
                value={(data.setup?.commands ?? []).join("\n")}
                disabled={busy}
                onChange={(e) =>
                  change("setup", {
                    ...data.setup,
                    commands: e.target.value.split("\n").filter(Boolean),
                  })
                }
              />
            </label>
          </div>
        </Card>
        <Card className="p-6">
          <div className="section-heading">
            <div>
              <h2>评价维度</h2>
              <p>固定标准 · 分别生成或导入用例 · 同一场景可关联多个维度</p>
            </div>
            <Badge>{data.dimensions.length} 已选择</Badge>
          </div>
          <div className="dimensions-grid">
            {catalog &&
              Object.entries(catalog.items).map(([group, dimensions]) => (
                <div key={group}>
                  <h3 className="dimension-group-label">
                    {catalog.labels[group]}
                  </h3>
                  {(dimensions as Json[]).map((dim) => {
                    const selection = data.dimensions.find(
                      (d: Json) => d.id === dim.id,
                    );
                    return (
                      <div
                        className={`dimension-option ${selection ? "enabled" : ""}`}
                        key={dim.id}
                      >
                        <label className="dimension-checkbox">
                          <input
                            type="checkbox"
                            disabled={busy}
                            checked={!!selection}
                            onChange={(e) =>
                              selectDimension(dim, e.target.checked)
                            }
                          />
                          <strong>{dim.name}</strong>
                          <Badge>
                            {dim.method === "code"
                              ? "代码"
                              : dim.method === "llm"
                                ? "LLM"
                                : "混合"}
                          </Badge>
                        </label>
                        <p>{dim.description}</p>
                        <details className="standard-details">
                          <summary>查看固定检查点</summary>
                          {dim.checkpoints.map((point: Json) => (
                            <p key={point.id}>
                              {point.name}：{point.description}
                            </p>
                          ))}
                        </details>
                        {selection && (
                          <>
                            <div className="dimension-controls">
                              <label>
                                权重
                                <input
                                  type="number"
                                  min=".1"
                                  max="1000"
                                  step=".1"
                                  disabled={busy}
                                  value={selection.weight}
                                  onChange={(e) =>
                                    change(
                                      "dimensions",
                                      data.dimensions.map((d: Json) =>
                                        d.id === dim.id
                                          ? {
                                              ...d,
                                              weight: Number(e.target.value),
                                            }
                                          : d,
                                      ),
                                    )
                                  }
                                />
                              </label>
                              <label>
                                通过阈值
                                <input
                                  type="number"
                                  min="0"
                                  max="100"
                                  disabled={busy}
                                  value={selection.pass_score}
                                  onChange={(e) =>
                                    change(
                                      "dimensions",
                                      data.dimensions.map((d: Json) =>
                                        d.id === dim.id
                                          ? {
                                              ...d,
                                              pass_score: Number(
                                                e.target.value,
                                              ),
                                            }
                                          : d,
                                      ),
                                    )
                                  }
                                />
                              </label>
                              <label className="gate-choice">
                                <input
                                  type="checkbox"
                                  disabled={busy}
                                  checked={selection.hard_gate}
                                  onChange={(e) =>
                                    change(
                                      "dimensions",
                                      data.dimensions.map((d: Json) =>
                                        d.id === dim.id
                                          ? {
                                              ...d,
                                              hard_gate: e.target.checked,
                                            }
                                          : d,
                                      ),
                                    )
                                  }
                                />
                                硬门禁
                              </label>
                            </div>
                            <div className="flex gap-2 flex-wrap items-center">
                              <Badge
                                tone={
                                  data.packages[dim.id] ? "green" : "neutral"
                                }
                              >
                                {data.packages[dim.id] ? (
                                  <>
                                    <Check size={12} />
                                    已有用例
                                  </>
                                ) : (
                                  "待生成 / 导入"
                                )}
                              </Badge>
                              <Button
                                variant="ghost"
                                disabled={busy}
                                onClick={() => {
                                  importDimension.current = dim.id;
                                  upload.current?.click();
                                }}
                              >
                                <Upload size={13} />
                                ZIP
                              </Button>
                              <Button
                                variant="ghost"
                                disabled={busy}
                                onClick={() => {
                                  importDimension.current = dim.id;
                                  folderUpload.current?.click();
                                }}
                              >
                                目录
                              </Button>
                              {data.packages[dim.id] && (
                                <Button
                                  variant="ghost"
                                  disabled={busy}
                                  onClick={() => editPackage(dim)}
                                >
                                  编辑用例
                                </Button>
                              )}
                              <a
                                className="template-link"
                                href={`/api/v1/suite-packages/example/workflow/${dim.id}`}
                                download
                              >
                                <Download size={13} />
                                模板
                              </a>
                            </div>
                          </>
                        )}
                      </div>
                    );
                  })}
                </div>
              ))}
          </div>
        </Card>
        <input
          ref={upload}
          type="file"
          accept=".zip"
          className="hidden"
          onChange={(e) => {
            importFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <input
          ref={folderUpload}
          type="file"
          multiple
          {...({ webkitdirectory: "" } as any)}
          className="hidden"
          onChange={(e) => {
            importFiles(e.target.files, true);
            e.target.value = "";
          }}
        />
        <AgentChat
          draft={draft ?? { status: "draft", messages: [] }}
          onSend={send}
          disabled={busy || !data.generator_model || !data.dimensions.length}
        />
        {!!draft?.validation?.structure_passed && (
          <Card className="p-5">
            <div className="section-heading">
              <div>
                <h2>用例校验</h2>
                <p>
                  {dirty
                    ? "草稿已修改，需要重新校验"
                    : `结构校验通过 · ${draft.validation.case_count} 个场景`}
                </p>
              </div>
              <Badge tone={checked ? "green" : "neutral"}>
                {checked
                  ? draft.validation.checks?.length
                    ? "脚本可运行"
                    : "校验完成 · 无代码脚本"
                  : draft.validation.scripts_checked
                    ? "脚本存在问题"
                    : "尚未试验证"}
              </Badge>
            </div>
            <p className="text-sm text-slate-500">
              断言有效性待人工确认。未修改项目上的质量得分不作为正式测评结果。
            </p>
            <details className="definition mt-3">
              <summary>校验明细</summary>
              <pre>{JSON.stringify(draft.validation, null, 2)}</pre>
            </details>
          </Card>
        )}
        <div className="save-bar">
          <span>保存测试套后锁定内容，执行需单独发起。</span>
          <div className="flex gap-3">
            {draft && active(draft.status) && (
              <Button
                variant="danger"
                onClick={() =>
                  action(async () => {
                    await api(`/benchmark/drafts/${draft.id}/cancel`, {});
                    notify("已请求停止任务");
                  })
                }
              >
                停止任务
              </Button>
            )}
            <Button
              variant="outline"
              disabled={busy || !data.dimensions.length}
              onClick={validate}
            >
              <ShieldCheck size={16} />
              隔离校验
            </Button>
            <Button disabled={busy || !checked || !draft} onClick={save}>
              <Lock size={15} />
              完成配置并锁定
            </Button>
          </div>
        </div>
        <Modal
          open={!!editor}
          onOpenChange={() => setEditor(null)}
          title={`编辑 ${editor?.name ?? ""} 用例包`}
        >
          <p className="text-sm text-slate-500 mb-4">
            检查任务、预期与验证代码。修改后需重新校验，固定评分标准不可覆盖。
          </p>
          <PackageEditor value={editorText} onChange={setEditorText} />
          <div className="flex justify-end mt-4">
            <Button disabled={pending} onClick={applyEditor}>
              应用修改
            </Button>
          </div>
        </Modal>
        <Modal
          open={!!pathModal}
          onOpenChange={() => setPathModal(null)}
          title="选择本地目录"
        >
          <form
            className="flex gap-2 mb-4"
            onSubmit={(e) => {
              e.preventDefault();
              browse(pathInput);
            }}
          >
            <input
              aria-label="目录路径"
              value={pathInput}
              onChange={(e) => setPathInput(e.target.value)}
              className="flex-1"
            />
            <Button variant="outline" type="submit">
              打开
            </Button>
          </form>
          {pathData && (
            <>
              <p className="text-sm break-all mb-3">
                {pathData.path || "选择磁盘"}
              </p>
              {pathData.parent && (
                <Button
                  variant="ghost"
                  onClick={() => {
                    setPathInput(pathData.parent);
                    browse(pathData.parent);
                  }}
                >
                  上级目录
                </Button>
              )}
              <div className="directory-list">
                {pathData.items.map((entry: Json) => (
                  <button
                    key={entry.path}
                    onClick={() => {
                      setPathInput(entry.path);
                      browse(entry.path);
                    }}
                  >
                    <FolderOpen size={15} />
                    {entry.name}
                  </button>
                ))}
              </div>
              <Button
                className="mt-4"
                disabled={!pathData.path}
                onClick={() => {
                  change(pathModal!, pathData.path);
                  setPathModal(null);
                }}
              >
                选择此目录
              </Button>
            </>
          )}
        </Modal>
      </main>
    </div>
  );
}
