import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
} from "recharts";
import type { Json } from "../lib/api";
import { date } from "../lib/api";
import { Empty } from "./ui";
export function EvaluationChart({
  experiments,
  selected,
  onSelect,
}: {
  experiments: Json[];
  selected: string;
  onSelect: (id: string) => void;
}) {
  if (!experiments.length) return <Empty>暂无执行记录</Empty>;
  const data = [...experiments].reverse().map((exp, index) => ({
    id: exp.id,
    name: `Run ${index + 1}`,
    score: exp.scores.current,
    time: date(exp.created_at),
    status: exp.status,
  }));
  return (
    <>
      <div className="chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={data}
            margin={{ left: -20, right: 16, top: 20, bottom: 5 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              vertical={false}
              stroke="#e2e8f0"
            />
            <XAxis dataKey="name" tick={{ fontSize: 11 }} />
            <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
            <Tooltip
              labelFormatter={(_, payload) => payload?.[0]?.payload.time ?? ""}
            />
            <Bar
              name="当前 Skill 得分"
              dataKey="score"
              radius={[5, 5, 0, 0]}
              onClick={(entry) => onSelect(String(entry.id))}
            >
              {data.map((entry) => (
                <Cell
                  key={entry.id}
                  fill={entry.id === selected ? "#047857" : "#c4ded4"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className="history-buttons" aria-label="选择历史执行">
        {data.map((entry) => (
          <button
            key={entry.id}
            onClick={() => onSelect(entry.id)}
            aria-pressed={entry.id === selected}
          >
            {entry.name}
            {entry.score == null ? " · 无得分" : ""}
          </button>
        ))}
      </div>
    </>
  );
}
