import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { Json } from "../../shared/api";
import { Empty } from "../../shared/ui";
export function ScoreRadar({
  current,
  baseline,
}: {
  current?: Json | null;
  baseline?: Json | null;
}) {
  const currentDims = current?.dimension_scores?.current ?? [],
    baseDims =
      baseline?.dimension_scores?.[baseline.selected_group ?? "current"] ?? [];
  const axes = [
    ...new Map(
      [...currentDims, ...baseDims].map((dim: Json) => [dim.id, dim]),
    ).values(),
  ] as Json[];
  if (!axes.length) return <Empty>执行完成后展示固定评价维度得分</Empty>;
  const data = axes.map((dim) => ({
    name: dim.name,
    current: currentDims.find((x: Json) => x.id === dim.id)?.score ?? undefined,
    baseline: baseDims.find((x: Json) => x.id === dim.id)?.score ?? undefined,
  }));
  if (axes.length < 3)
    return (
      <div
        className="chart"
        role="img"
        aria-label="少于三个维度时用得分条比较能力"
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            layout="vertical"
            data={data}
            margin={{ left: 5, right: 20, top: 35, bottom: 5 }}
            barSize={20}
          >
            <CartesianGrid
              horizontal={false}
              strokeDasharray="3 3"
              stroke="#e2e8f0"
            />
            <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 10 }} />
            <YAxis
              type="category"
              dataKey="name"
              width={110}
              tick={{ fontSize: 11 }}
            />
            {baseline && (
              <Bar
                name="所选基线"
                dataKey="baseline"
                fill="#94a3b8"
                radius={[0, 4, 4, 0]}
              />
            )}
            <Bar
              name="当前执行"
              dataKey="current"
              fill="#047857"
              radius={[0, 4, 4, 0]}
            />
            <Tooltip />
            <Legend iconType="circle" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  return (
    <div
      className="chart"
      role="img"
      aria-label="本次执行与所选基线的评价维度雷达图"
    >
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} outerRadius="65%">
          <PolarGrid stroke="#e2e8f0" />
          <PolarAngleAxis
            dataKey="name"
            tick={{ fontSize: 11, fill: "#64748b" }}
          />
          <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 10 }} />
          {baseline && (
            <Radar
              name="所选基线"
              dataKey="baseline"
              stroke="#94a3b8"
              fill="#94a3b8"
              fillOpacity={0.13}
            />
          )}
          <Radar
            name="当前执行"
            dataKey="current"
            stroke="#047857"
            fill="#10b981"
            fillOpacity={0.18}
          />
          <Tooltip />
          <Legend iconType="circle" />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
