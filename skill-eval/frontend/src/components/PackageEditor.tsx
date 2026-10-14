import { useState } from "react";
import { Button } from "./ui";
import type { Json } from "../lib/api";
export function PackageEditor({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  const [tab, setTab] = useState("cases"),
    [asset, setAsset] = useState("");
  let document: Json | null = null;
  try {
    document = JSON.parse(value);
  } catch {
    /* Advanced edits may temporarily be incomplete. */
  }
  const assets = Object.keys(document?.assets ?? {}),
    selected = assets.includes(asset) ? asset : assets[0];
  function scene(index: number, key: string, text: string) {
    if (!document) return;
    const next = structuredClone(document);
    next.manifest.cases[index][key] = text;
    onChange(JSON.stringify(next, null, 2));
  }
  return (
    <>
      <div className="flex gap-2 mb-4">
        <Button
          variant={tab === "cases" ? "default" : "ghost"}
          onClick={() => setTab("cases")}
        >
          场景与参考
        </Button>
        <Button
          variant={tab === "files" ? "default" : "ghost"}
          onClick={() => setTab("files")}
        >
          代码与材料
        </Button>
        <Button
          variant={tab === "advanced" ? "default" : "ghost"}
          onClick={() => setTab("advanced")}
        >
          高级配置
        </Button>
      </div>
      {tab === "advanced" || !document ? (
        <textarea
          className="code-editor"
          aria-label="用例包内容"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : tab === "cases" ? (
        <div className="package-scenes">
          {document.manifest.cases.map((caseSpec: Json, index: number) => (
            <div
              key={index}
              className="grid gap-3 mb-5 p-4 rounded-lg border border-slate-200"
            >
              <label>
                场景名称
                <input
                  value={caseSpec.name}
                  onChange={(e) => scene(index, "name", e.target.value)}
                />
              </label>
              <label>
                任务描述
                <textarea
                  rows={4}
                  value={caseSpec.input}
                  onChange={(e) => scene(index, "input", e.target.value)}
                />
              </label>
              <label>
                预期与评分端参考
                <textarea
                  rows={4}
                  value={caseSpec.expected}
                  onChange={(e) => scene(index, "expected", e.target.value)}
                />
              </label>
              <p className="text-xs text-slate-400">
                场景 ID：{caseSpec.id}
                。共用场景的任务与参考材料需在各维度保持一致。
              </p>
            </div>
          ))}
        </div>
      ) : assets.length ? (
        <>
          <select
            aria-label="选择验证代码或参考文件"
            className="w-full mb-3"
            value={selected}
            onChange={(e) => setAsset(e.target.value)}
          >
            {assets.map((path) => (
              <option key={path} value={path}>
                {path}
              </option>
            ))}
          </select>
          <textarea
            className="code-editor"
            aria-label="文件内容"
            value={document.assets[selected]}
            onChange={(e) => {
              const next = {
                ...document,
                assets: { ...document!.assets, [selected]: e.target.value },
              };
              onChange(JSON.stringify(next, null, 2));
            }}
          />
        </>
      ) : (
        <p className="text-sm text-slate-500">
          此维度没有额外代码或文件，按平台固定 LLM 标准评价。
        </p>
      )}
    </>
  );
}
