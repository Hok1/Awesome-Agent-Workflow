export type CandidateKind = "no_skill" | "skill";
export interface SkillRevision {
  id: string;
  name: string;
  content_hash: string;
  source_path: string;
}

export function CandidatePicker({
  candidate,
  onCandidate,
  path,
  onPath,
  revision,
  onRevision,
  revisions,
}: {
  candidate: CandidateKind;
  onCandidate: (kind: CandidateKind) => void;
  path: string;
  onPath: (path: string) => void;
  revision: string;
  onRevision: (id: string) => void;
  revisions: SkillRevision[];
}) {
  return (
    <>
      <select
        aria-label="执行候选"
        value={candidate}
        onChange={(e) => onCandidate(e.target.value as CandidateKind)}
      >
        <option value="no_skill">no_skill · 不加载任何 Skill</option>
        <option value="skill">指定 Skill</option>
      </select>
      {candidate === "skill" && (
        <>
          <select
            aria-label="Skill 版本"
            value={revision}
            onChange={(e) => onRevision(e.target.value)}
          >
            <option value="">从路径创建新快照</option>
            {revisions.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name} · {r.content_hash.slice(0, 10)}
              </option>
            ))}
          </select>
          {!revision && (
            <input
              aria-label="Skill 路径"
              placeholder="Skill 目录"
              value={path}
              onChange={(e) => onPath(e.target.value)}
            />
          )}
        </>
      )}
    </>
  );
}
