/**
 * 「添加项目」流程（workbench 组装层）：系统目录对话框（pickDirectory）
 * → 选中该项目 → 内容区切到项目总览。
 *
 * 返回选中的路径；取消或环境不支持返回 null（调用方提示重试或从列表
 * 选择）。项目总览空态与【+】面板的「添加项目」tab 共用本流程。
 *
 * 「进项目」与「进会话」是两类入口，行为分别统一（见 ProjectTree 顶部
 * 说明）：本流程属于「进项目」——只选中并落到总览，连接是总览里显式的
 * 一步（先看到健康检查结论，再决定连不连）。自动连接留给会话入口
 * （sessionEntry 的 openSessionFromEntry、向导发送时的 wizardSubmit）。
 */
import { useWorkspaceStore } from "../../stores/workspaceStore.ts";
import { useWorkbenchUiStore } from "../../stores/workbenchUiStore.ts";
import { pickDirectory } from "../workspaces/pickDirectory.ts";

/** 打开系统目录对话框添加项目；成功即选中并进总览，返回路径或 null。 */
export async function addProjectViaDialog(): Promise<string | null> {
  const path = await pickDirectory();
  if (path === null) {
    return null;
  }
  useWorkspaceStore.getState().selectWorkspace(path);
  useWorkbenchUiStore.getState().openProjectOverview(path);
  return path;
}
