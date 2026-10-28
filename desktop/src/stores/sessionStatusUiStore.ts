import { create } from "zustand";

export type StatusCardMode = "auto" | "panel" | "mini";
/** 同客户端会话共享展示偏好，不写入持久化存储；重启恢复自动。 */
export const useSessionStatusUiStore = create<{
  mode: StatusCardMode;
  setMode: (mode: StatusCardMode) => void;
}>((set) => ({ mode: "auto", setMode: (mode) => set({ mode }) }));
