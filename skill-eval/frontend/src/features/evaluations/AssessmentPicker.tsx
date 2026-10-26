import { statusName } from "../../shared/api";
export interface AssessmentSummary {
  id: string;
  status: string;
  judge_model: string;
  created_at: string;
}
export function AssessmentPicker({
  value,
  onChange,
  assessments,
}: {
  value: string;
  onChange: (id: string) => void;
  assessments: AssessmentSummary[];
}) {
  return (
    <label>
      评分记录{" "}
      <select
        aria-label="评分记录"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">最新评分</option>
        {assessments.map((a, i) => (
          <option key={a.id} value={a.id}>
            评分 {i + 1} · {a.judge_model} · {statusName(a.status)}
          </option>
        ))}
      </select>
    </label>
  );
}
