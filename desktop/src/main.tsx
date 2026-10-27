import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";
// 应用启动即开始内存采样（诊断页「性能」折线图的数据源，见模块注释）
import "./ui/perf/memorySampler.ts";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
