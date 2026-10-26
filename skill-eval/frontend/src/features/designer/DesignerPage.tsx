import {
  ArrowLeft,
  Check,
  Download,
  FolderOpen,
  Lock,
  Save,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { navigate, type Json } from "../../shared/api";
import { PackageEditor } from "./PackageEditor";
import { Badge, Button, Card, Empty, Modal } from "../../shared/ui";
import { AgentChat } from "./AgentChat";
import { DesignerWorkflow } from "./DesignerWorkflow";
import { draftDefaults } from "./draft";
import { GeneratedCases } from "./GeneratedCases";
import { useDesigner } from "./useDesigner";
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
  const {
    draft,
    setDraft,
    data,
    setData,
    catalog,
    setCatalog,
    pending,
    setPending,
    editor,
    setEditor,
    editorText,
    setEditorText,
    error,
    setError,
    pathModal,
    setPathModal,
    pathData,
    setPathData,
    pathInput,
    setPathInput,
    configOpen,
    setConfigOpen,
    upload,
    folderUpload,
    importDimension,
    models,
    busy,
    missingConfig,
    dirty,
    showConfigForm,
    action,
    persist,
    send,
    stopTask,
    suggestion,
    editCase,
    validate,
    save,
    change,
    selectDimension,
    importFiles,
    editPackage,
    applyEditor,
    browse,
    checked,
  } = useDesigner({ id, agents, notify });
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
          分析项目 → 设计用例 → 配置评价方式 → 确认使用
        </div>
      </aside>
      <main className="suite-main designer-page">
        <div className="page-heading">
          <div>
            <div className="eyebrow">AGENT TEST DESIGNER</div>
            <h1>用例配置</h1>
          </div>
          <div className="heading-actions">
            <Button
              variant="outline"
              disabled={busy || !data.dimensions.length}
              onClick={validate}
            >
              <ShieldCheck size={16} />
              {draft?.workflow?.plan ? "重新配置评价方式" : "校验已导入用例"}
            </Button>
            <Button disabled={busy || !checked || !draft} onClick={save}>
              <Lock size={15} />
              确认使用并锁定
            </Button>
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
        </div>
        {error && <div className="error-box">{error}</div>}
        {data.migration_review?.required && (
          <div className="info-box">
            <strong>旧测试套已转为待确认草稿</strong>
            {data.migration_review.notes.map((note: string) => (
              <p key={note}>{note}</p>
            ))}
            <label>
              <input
                type="checkbox"
                checked={!!data.migration_review.confirmed}
                disabled={busy}
                onChange={(e) =>
                  change("migration_review", {
                    ...data.migration_review,
                    confirmed: e.target.checked,
                  })
                }
              />{" "}
              我已检查并分离通用任务、公共评分与 Skill 合规要求
            </label>
            {data.original_definition && (
              <details>
                <summary>查看保留的原用例定义</summary>
                <pre>{JSON.stringify(data.original_definition, null, 2)}</pre>
              </details>
            )}
          </div>
        )}
        <DesignerWorkflow
          draft={draft ?? { status: "draft" }}
          onStop={() => action(stopTask)}
          onRetry={() =>
            send(
              "继续未完成的步骤",
              draft?.workflow?.plan ? "retry" : "generate",
            )
          }
        />
        <div className="config-strip">
          <span className="cf-field">
            <label>名称</label>
            <input
              value={data.name}
              disabled={busy}
              onChange={(e) => change("name", e.target.value)}
            />
          </span>
          <span className="cf-field">
            <label>模型</label>
            <select
              value={data.generator_model}
              disabled={busy}
              onChange={(e) => change("generator_model", e.target.value)}
            >
              <option value="">选择</option>
              {data.generator_model &&
                !models.some((m: Json) => m.id === data.generator_model) && (
                  <option value={data.generator_model}>
                    {data.generator_model}（已配置）
                  </option>
                )}
              {models.map((model: Json) => (
                <option key={model.id} value={model.id}>
                  {model.name || model.id}
                </option>
              ))}
            </select>
          </span>
          <span className="cf-field">
            <label>项目</label>
            <input
              value={data.project_path}
              disabled={busy}
              onChange={(e) => change("project_path", e.target.value)}
            />
          </span>
          <span className="cf-field">
            <label>参考 Skill（可选）</label>
            <input
              value={data.skill_path}
              disabled={busy}
              onChange={(e) => change("skill_path", e.target.value)}
            />
          </span>
          <span
            className={missingConfig.length ? "cf-status warn" : "cf-status ok"}
          >
            {missingConfig.length
              ? `需补充：${missingConfig.join("、")}`
              : "✓ 配置完整"}
          </span>
          <button
            className="cf-toggle"
            onClick={() => setConfigOpen(!showConfigForm)}
          >
            {showConfigForm ? "收起完整配置 ▴" : "展开完整配置 ▾"}
          </button>
        </div>
        {showConfigForm && (
          <>
            <Card className="p-6 config-form">
              <div className="section-heading">
                <div>
                  <h2>完整配置</h2>
                  <p>
                    需求描述是 Agent
                    生成用例的核心输入；正式保存后项目地址与用例不可修改
                  </p>
                </div>
                <Lock size={16} className="text-slate-400" />
              </div>
              <div className="form-grid">
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
                <label>
                  任务组织
                  <select
                    disabled={busy}
                    value={data.case_mode ?? "single"}
                    onChange={(e) => change("case_mode", e.target.value)}
                  >
                    <option value="single">一个完整任务（默认）</option>
                    <option value="multiple">多个独立场景</option>
                  </select>
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
                {[
                  ["project_path", "浏览选择项目目录"],
                  ["skill_path", "浏览选择 Skill 目录"],
                ].map(([key, label]) => (
                  <div className="path-browse" key={key}>
                    <span>{label}</span>
                    <Button
                      variant="ghost"
                      disabled={busy}
                      onClick={() => {
                        setPathModal(key);
                        setPathInput(data[key]);
                        browse(data[key]);
                      }}
                    >
                      <FolderOpen size={15} />
                      {data[key] || "未设置"}
                    </Button>
                  </div>
                ))}
              </div>
            </Card>
            <details className="designer-advanced" open>
              <summary>调整评价维度与高级配置（导入、验证代码）</summary>
              <Card className="p-4">
                <div className="section-heading">
                  <div>
                    <h2>评价维度</h2>
                    <p>
                      未选择时由 Agent
                      推荐；调整后重新生成，同一完整任务关联多个维度
                    </p>
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
                                                    weight: Number(
                                                      e.target.value,
                                                    ),
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
                                        data.packages[dim.id]
                                          ? "green"
                                          : "neutral"
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
            </details>
          </>
        )}
        <div className="designer-workbench chat-primary">
          <AgentChat
            draft={draft ?? { status: "draft", messages: [] }}
            onSend={send}
            onGenerate={() =>
              send(
                "请根据测评目标生成完整用例，推荐适用的固定评价维度，并自动校验。",
                "generate",
              )
            }
            canGenerate={!!data.requirement.trim()}
            disabled={pending}
            configHint={
              missingConfig.length
                ? `可以先输入测评目标；调用 Agent 前还需补充：${missingConfig.join("、")}。`
                : undefined
            }
            sendError={error}
          />
          <div className="cases-rail">
            <GeneratedCases
              draft={draft ?? { data }}
              dirty={dirty}
              busy={busy}
              onSave={editCase}
              onSuggestion={suggestion}
              interactionPending={pending}
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
          </div>
        </div>
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
