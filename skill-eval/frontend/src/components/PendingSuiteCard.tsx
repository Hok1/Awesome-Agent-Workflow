import { ArrowUpRight } from "lucide-react";
import { active, date, navigate, statusName, type Json } from "../lib/api";
import { Badge, Button, Card } from "./ui";

export function PendingSuiteCard({ draft }: { draft: Json }) {
  return (
    <Card className="suite-card pending-suite-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 title={draft.data.name}>{draft.data.name || "未命名测试套"}</h2>
          <p className="suite-skill truncate" title={draft.data.project_path}>
            {draft.data.project_path || "项目尚未配置"}
          </p>
        </div>
        <Badge>待配置</Badge>
      </div>
      <p className="pending-suite-description">
        {active(draft.status)
          ? statusName(draft.status)
          : draft.status === "failed"
            ? "配置任务失败，可进入查看并重试"
            : "补全项目、评价维度与测评用例后，校验并锁定即可执行。"}
      </p>
      <div className="suite-footer">
        <span>{date(draft.created_at ?? draft.updated_at)}</span>
        <Button variant="ghost" onClick={() => navigate(`/drafts/${draft.id}`)}>
          去配置
          <ArrowUpRight size={12} />
        </Button>
      </div>
    </Card>
  );
}
