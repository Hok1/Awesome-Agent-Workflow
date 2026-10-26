import { FlaskConical, RefreshCw } from "lucide-react";
import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { DesignerPage } from "../features/designer/DesignerPage";
import { SuitePage } from "../features/executions/SuitePage";
import { Dashboard } from "../features/suites/Dashboard";
import { api, navigate, type Json } from "../shared/api";
import { Button } from "../shared/ui";
import "../styles.css";
class Boundary extends React.Component<
  { children: React.ReactNode },
  { error: string }
> {
  state = { error: "" };
  static getDerivedStateFromError(error: Error) {
    return { error: error.message };
  }
  render() {
    return this.state.error ? (
      <div className="error-box m-8">
        页面加载失败：{this.state.error}
        <Button onClick={() => location.reload()}>重新加载</Button>
      </div>
    ) : (
      this.props.children
    );
  }
}
function App() {
  const [path, setPath] = useState(location.hash.slice(1) || "/"),
    [agents, setAgents] = useState<Json[]>([]),
    [agentError, setAgentError] = useState(""),
    [toast, setToast] = useState(""),
    [legacy, setLegacy] = useState<Json | null>(null);
  function notify(message: string) {
    setToast(message);
  }
  async function loadAgents() {
    try {
      const result = await api("/benchmark/agents");
      setAgents(result.items);
      setAgentError(result.items[0]?.error ?? "");
    } catch (e) {
      setAgentError(String(e));
    }
  }
  useEffect(() => {
    const handler = () => setPath(location.hash.slice(1) || "/");
    window.addEventListener("hashchange", handler);
    loadAgents();
    return () => window.removeEventListener("hashchange", handler);
  }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 5000);
    return () => clearTimeout(timer);
  }, [toast]);
  const pieces = path.split("/").filter(Boolean);
  useEffect(() => {
    if (pieces[0] === "experiments" && pieces[1])
      api(`/experiments/${pieces[1]}`)
        .then(setLegacy)
        .catch((e) => notify(String(e)));
    else setLegacy(null);
  }, [path]);
  return (
    <>
      <header className="app-header">
        <button className="brand" onClick={() => navigate("/")}>
          <span className="brand-icon">
            <FlaskConical size={21} />
          </span>
          <span>
            <strong>AI Agent Skill Benchmark</strong>
            <small>固定测试集 · 多维度评价</small>
          </span>
        </button>
        <div className="runtime">
          <span
            className={`runtime-dot ${agents[0]?.available ? "ready" : ""}`}
          />
          <span>
            {agents[0]?.available
              ? `Chrys ${agents[0].version ?? ""}`
              : agentError
                ? "Chrys 未就绪"
                : "检查 Agent…"}
          </span>
          <Button
            variant="ghost"
            onClick={loadAgents}
            aria-label="刷新 Agent 状态"
          >
            <RefreshCw size={14} />
          </Button>
        </div>
      </header>
      {agentError && (
        <div className="runtime-error">
          {agentError} · 可查看与编辑测试套，生成和执行需要 Chrys 就绪。
        </div>
      )}
      <Boundary key={path}>
        {pieces[0] === "suites" && pieces[1] ? (
          <SuitePage
            key={pieces[1]}
            id={pieces[1]}
            agents={agents}
            notify={notify}
          />
        ) : pieces[0] === "create" || pieces[0] === "drafts" ? (
          <DesignerPage
            id={pieces[0] === "drafts" ? pieces[1] : undefined}
            agents={agents}
            notify={notify}
          />
        ) : pieces[0] === "experiments" ? (
          legacy ? (
            <SuitePage
              id={legacy.suite_id}
              initialExperiment={legacy.id}
              agents={agents}
              notify={notify}
            />
          ) : (
            <div className="empty">加载执行记录…</div>
          )
        ) : (
          <Dashboard notify={notify} />
        )}
      </Boundary>
      {toast && (
        <div className="toast" role="status" onClick={() => setToast("")}>
          {toast}
        </div>
      )}
      <footer className="app-footer">AI Agent Skill Benchmark Platform</footer>
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
