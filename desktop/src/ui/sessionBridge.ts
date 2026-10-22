/**
 * 会话视图装配桥（ui 层组装模块）：把一条 AcpSession 的事件流同时接到
 * 两个消费方——
 *
 * - 会话视图（sessionStore.handleEvent，经 stores/sessionStore 的
 *   attachSession）；
 * - 工作流状态面板的会话事件自动刷新（aawStatusStore.handleSessionEvent，
 *   内部节流）。store 之间不互相 import（约定 §2.4），这条桥因此放在
 *   组装层：真实运行经此完成全部接线。
 *
 * 返回的解挂函数同时撤销两路订阅与下行通道绑定。
 */
import type { AcpSession } from "../acp/session.ts";
import { attachSession } from "../stores/sessionStore.ts";
import { useAawStatusStore } from "../stores/aawStatusStore.ts";

export function attachSessionViews(acp: AcpSession): () => void {
  const detachSessionView = attachSession(acp);
  const unsubscribeAaw = acp.onEvent((event) => {
    useAawStatusStore.getState().handleSessionEvent(event);
  });
  return () => {
    unsubscribeAaw();
    detachSessionView();
  };
}
