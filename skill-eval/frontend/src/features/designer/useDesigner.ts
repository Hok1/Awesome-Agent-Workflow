import { useEffect, useRef, useState } from "react";
import {
  active,
  api,
  documentsPackage,
  navigate,
  type Json,
} from "../../shared/api";
import { poll } from "../../shared/polling";
import { draftDefaults } from "./draft";
const initial = draftDefaults();
export function useDesigner({
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
  const [configOpen, setConfigOpen] = useState<boolean | null>(null);
  const upload = useRef<HTMLInputElement>(null),
    folderUpload = useRef<HTMLInputElement>(null),
    importDimension = useRef("");
  const models = agents.find((a) => a.id === "chrys")?.models ?? [];
  const busy = pending || !!(draft && active(draft.status));
  const missingConfig = [
    !data.project_path?.trim() && "项目路径",
    !data.generator_model && "生成 Agent 模型",
  ].filter(Boolean);
  const dirty =
    !!draft &&
    JSON.stringify(data) !== JSON.stringify(draftDefaults(draft.data));
  const showConfigForm =
    configOpen ??
    (missingConfig.length > 0 ||
      (!data.requirement?.trim() && !draft?.preview));
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
    return poll(
      () => api(`/benchmark/drafts/${draft.id}`),
      (next) => {
        setDraft(next);
        setData(draftDefaults(next.data));
      },
      (e) => setError(String(e)),
      1500,
      (next) => active(next.status),
    );
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
  async function send(message: string, mode = "auto") {
    let sent = false;
    await action(async () => {
      const missing =
        mode === "auto"
          ? !data.generator_model
            ? ["生成 Agent 模型"]
            : []
          : missingConfig;
      if (missing.length)
        throw new Error(
          `请先补充${missing.join("、")}，再发送给 Agent。输入内容会保留。`,
        );
      const saved =
        !draft || (dirty && !active(draft.status)) ? await persist() : draft;
      let next;
      try {
        next = await api(`/benchmark/drafts/${saved!.id}/messages`, {
          message,
          mode,
          revision: saved!.revision,
        });
      } catch (e) {
        if ((e as { status?: number }).status !== 409 || !active(saved!.status))
          throw e;
        const latest = await api(`/benchmark/drafts/${saved!.id}`);
        next = await api(`/benchmark/drafts/${saved!.id}/messages`, {
          message,
          mode,
          revision: latest.revision,
        });
      }
      setDraft(next);
      setData(draftDefaults(next.data));
      sent = true;
    });
    return sent;
  }
  async function stopTask() {
    if (!draft) return;
    const result = await api(`/benchmark/drafts/${draft.id}/cancel`, {});
    setDraft(result);
    setData(draftDefaults(result.data));
    notify("已停止，已有产物保留");
  }
  async function suggestion(
    suggestionId: string,
    action: string,
    text?: string,
  ) {
    if (action === "edit") return send(`请修改用例，明确采用以下要求：${text}`);
    try {
      const latest = await api(`/benchmark/drafts/${draft!.id}`);
      const result = await api(
        `/benchmark/drafts/${draft!.id}/suggestions/${suggestionId}`,
        { action, revision: latest.revision },
      );
      setDraft(result);
      setData(draftDefaults(result.data));
      return true;
    } catch (e) {
      setError(String(e));
      return false;
    }
  }
  async function editCase(caseId: string, fields: Json) {
    setPending(true);
    setError("");
    try {
      const saved = dirty || !draft ? await persist() : draft;
      const next = await api(
        `/benchmark/drafts/${saved!.id}/cases/${caseId}`,
        { ...fields, revision: saved!.revision },
        "PATCH",
      );
      setDraft(next);
      setData(draftDefaults(next.data));
      notify("用例已同步到全部关联维度，请重新校验后确认使用");
      return true;
    } catch (e) {
      setError(String(e));
      return false;
    } finally {
      setPending(false);
    }
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

  return {
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
  };
}
