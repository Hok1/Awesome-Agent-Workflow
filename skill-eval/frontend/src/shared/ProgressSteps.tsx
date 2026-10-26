import { Check, LoaderCircle } from "lucide-react";
export function ProgressSteps({
  steps,
  current,
  failed = false,
}: {
  steps: string[];
  current: number;
  failed?: boolean;
}) {
  return (
    <ol className="progress-steps" aria-label="任务进度">
      {steps.map((name, index) => (
        <li
          key={name}
          className={
            index < current ? "done" : index === current ? "active" : ""
          }
        >
          <span>
            {index < current ? (
              <Check size={12} />
            ) : index === current && !failed ? (
              <LoaderCircle size={12} className="animate-spin" />
            ) : (
              index + 1
            )}
          </span>
          {name}
        </li>
      ))}
    </ol>
  );
}
