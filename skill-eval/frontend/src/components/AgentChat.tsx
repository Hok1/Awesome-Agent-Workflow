import { useEffect, useRef, useState } from "react";
import { Send, Bot } from "lucide-react";
import { Button, Card, Badge } from "./ui";
import { active, statusName, type Json } from "../lib/api";
import { ProgressSteps } from "./ProgressSteps";
export function AgentChat({
  draft,
  onSend,
  disabled,
}: {
  draft: Json;
  onSend: (message: string) => Promise<void>;
  disabled: boolean;
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
            <p>Chrys · 项目分析与用例生成</p>
          </div>
        </div>
        <Badge tone={active(draft.status) ? "green" : "neutral"}>
          {statusName(draft.status)}
        </Badge>
      </div>
      <ProgressSteps
        steps={["分析项目", "生成用例", "隔离校验", "草稿就绪"]}
        current={
          draft.status === "analyzing"
            ? 0
            : draft.status === "generating"
              ? 1
              : draft.status === "validating"
                ? 2
                : draft.validation?.scripts_checked
                  ? 4
                  : draft.status === "ready"
                    ? 2
                    : -1
        }
        failed={draft.status === "failed"}
      />
      <div className="chat-messages">
        {!draft.messages?.length && (
          <div className="chat-welcome">
            <Bot size={30} />
            <strong>将需求转成可执行的测评用例</strong>
            <p>
              选择固定评价维度，描述想检验的 Skill 行为。Agent 将读取项目与
              Skill，生成场景、参考材料和验证代码。
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
      <form
        className="chat-input"
        onSubmit={async (e) => {
          e.preventDefault();
          if (message.trim()) {
            await onSend(message);
            setMessage("");
          }
        }}
      >
        <textarea
          aria-label="与生成 Agent 对话"
          placeholder="例如：覆盖异常输入，并同时检查实现代码与设计文档…"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          disabled={disabled}
        />
        <Button
          type="submit"
          disabled={disabled || !message.trim()}
          aria-label="发送并生成用例"
        >
          <Send size={17} />
        </Button>
      </form>
    </Card>
  );
}
