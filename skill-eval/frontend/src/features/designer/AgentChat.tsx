import { Bot, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { active, statusName, type Json } from "../../shared/api";
import { Badge, Button, Card } from "../../shared/ui";
export function AgentChat({
  draft,
  onSend,
  disabled,
  onGenerate,
  canGenerate,
  configHint,
  sendError,
}: {
  draft: Json;
  onSend: (message: string) => Promise<boolean>;
  disabled: boolean;
  onGenerate: () => Promise<boolean>;
  canGenerate: boolean;
  configHint?: string;
  sendError?: string;
}) {
  const [message, setMessage] = useState(""),
    bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const container = bottom.current?.parentElement;
    if (container) container.scrollTop = container.scrollHeight;
  }, [draft.messages?.length]);
  return (
    <Card className="agent-chat">
      <div className="section-heading p-5 border-b">
        <div className="flex items-center gap-3">
          <div className="agent-icon">
            <Bot size={20} />
          </div>
          <div>
            <h2>Agent Test Designer</h2>
            <p>讨论需求、修改草案；生成进度见上方流程</p>
          </div>
        </div>
        <div className="flex gap-3 items-center">
          <Button disabled={disabled || !canGenerate} onClick={onGenerate}>
            生成用例草案
          </Button>
          <Badge tone={active(draft.status) ? "green" : "neutral"}>
            {statusName(draft.status)}
          </Badge>
        </div>
      </div>
      <div className="chat-messages">
        {!draft.messages?.length && (
          <div className="chat-welcome">
            <Bot size={30} />
            <strong>将需求转成可执行的测评用例</strong>
            <p>
              描述想检验的 Skill 行为。Agent 将分析项目与
              Skill，先展示完整任务、预期和推荐维度，再逐项准备评价方式。普通提问只讨论，不会重新生成。
            </p>
          </div>
        )}
        {draft.messages?.map((entry: Json, index: number) => (
          <div key={index} className={`chat-message ${entry.role}`}>
            <small>
              {entry.role === "user"
                ? "你"
                : entry.role === "assistant"
                  ? "Chrys"
                  : "进度"}
            </small>
            <p>{entry.content}</p>
          </div>
        ))}
        {draft.error && <div className="error-box">{draft.error}</div>}
        <div ref={bottom} />
      </div>
      {configHint && (
        <p className="chat-config-hint" id="agent-config-hint">
          {configHint}
        </p>
      )}
      {sendError && (
        <p className="error-box m-3" role="alert">
          {sendError}
        </p>
      )}
      <form
        className="chat-input"
        onSubmit={async (e) => {
          e.preventDefault();
          if (message.trim()) {
            if (await onSend(message)) setMessage("");
          }
        }}
      >
        <textarea
          aria-label="与生成 Agent 对话"
          aria-describedby={configHint ? "agent-config-hint" : undefined}
          placeholder="例如：覆盖异常输入，并同时检查实现代码与设计文档…"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
        />
        <Button
          type="submit"
          disabled={disabled || !message.trim()}
          aria-label="发送消息"
        >
          <Send size={17} />
        </Button>
      </form>
    </Card>
  );
}
