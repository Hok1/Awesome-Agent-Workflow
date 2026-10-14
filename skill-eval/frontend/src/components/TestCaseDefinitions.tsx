import { Badge, Card, Empty } from "./ui";
import { caseVerdict, type Json } from "../lib/api";

export function TestCaseDefinitions({
  definition,
  experiment,
}: {
  definition: Json;
  experiment?: Json | null;
}) {
  return (
    <Card className="case-definitions">
      <div className="section-heading">
        <h2>测评用例</h2>
        <Badge>{definition.cases.length} 个完整诉求</Badge>
      </div>
      {definition.cases.map((item: Json) => (
        <details className="definition" key={item.id} id={`case-${item.id}`}>
          <summary>
            <strong>{item.name}</strong>
            {experiment && (
              <Badge>
                {caseVerdict(
                  experiment.runs.filter(
                    (run: Json) =>
                      run.group === "current" && run.case_id === item.id,
                  ),
                  experiment.trials,
                )}
              </Badge>
            )}
            <span className="text-slate-400">需求、参考材料与预期结果</span>
          </summary>
          <div className="case-definition-content">
            <div>
              <label>需求描述</label>
              <p className="whitespace-pre-wrap">{item.input}</p>
            </div>
            <div>
              <label>预期与评分端参考</label>
              <p className="whitespace-pre-wrap">{item.expected}</p>
            </div>
            <details>
              <summary>配置、场景文件与验证脚本</summary>
              <pre>{JSON.stringify(item, null, 2)}</pre>
            </details>
          </div>
        </details>
      ))}
      {!definition.cases.length && <Empty>暂无用例</Empty>}
    </Card>
  );
}
