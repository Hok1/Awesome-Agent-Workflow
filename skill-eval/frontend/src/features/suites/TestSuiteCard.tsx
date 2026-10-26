import { Archive, ArrowUpRight, Radar, RotateCcw } from "lucide-react";
import { date, navigate, score, statusName, type Json } from "../../shared/api";
import { Badge, Button, Card } from "../../shared/ui";
export function TestSuiteCard({
  suite,
  onRadar,
  onArchive,
}: {
  suite: Json;
  onRadar: () => void;
  onArchive: () => void;
}) {
  return (
    <Card className="suite-card" title={suite.project_path}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 title={suite.name}>{suite.name}</h2>
          <p className="suite-skill truncate">{suite.skill_name}</p>
        </div>
        <Badge
          tone={suite.latest?.status === "completed" ? "green" : "neutral"}
        >
          {suite.archived
            ? "已归档"
            : suite.latest
              ? statusName(suite.latest.status)
              : "未执行"}
        </Badge>
      </div>
      <div className="suite-scores">
        <div>
          <span>对比基线</span>
          <strong>
            {score(suite.baseline?.scores[suite.baseline_group ?? "current"])}
          </strong>
        </div>
        <div>
          <span>最新评分</span>
          <strong className="text-emerald-700">
            {score(suite.latest?.scores.current)}
          </strong>
        </div>
      </div>
      <p className="suite-condition">
        {suite.latest?.conclusion.verdict === "provisional"
          ? "最新分数为暂定结果"
          : suite.comparison.formal
            ? `正式比较 · ${suite.comparison.delta >= 0 ? "+" : ""}${score(suite.comparison.delta)}`
            : suite.comparison.reasons.join(" · ")}
      </p>
      <div className="suite-footer">
        <span title={suite.project_path}>
          {date(suite.created_at)} · {suite.execution_count} 次执行
        </span>
        <div className="suite-actions">
          <Button
            variant="ghost"
            onClick={onRadar}
            aria-label="查看雷达图"
            title="查看雷达图"
          >
            <Radar size={13} />
            雷达
          </Button>
          <Button
            variant="ghost"
            onClick={() => navigate(`/suites/${suite.id}`)}
          >
            详情
            <ArrowUpRight size={12} />
          </Button>
          <Button
            variant="ghost"
            onClick={onArchive}
            aria-label={
              suite.archived ? `恢复 ${suite.name}` : `归档 ${suite.name}`
            }
          >
            {suite.archived ? <RotateCcw size={13} /> : <Archive size={13} />}
          </Button>
        </div>
      </div>
    </Card>
  );
}
