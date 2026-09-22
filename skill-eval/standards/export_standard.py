"""把一个已提交到 skill-eval 的 suite，逐字导出为标准归档。

用法：
    python export_standard.py <suite_id> <skill-name> [--source-standard <path>]

产出 <repo>/skill-eval/standards/<skill-name>/ 下的 6 个文件。
本脚本只读平台的 suite 定义，不读也不重新生成 rubric——保证"测的是什么就存什么"。
"""

import argparse
import json
import os
import urllib.request

import yaml

API = "http://127.0.0.1:18110/api/v1"
STANDARDS_ROOT = os.path.join(
    r"C:\code\workspace\Awesome-Agent-Workflow", "skill-eval", "standards"
)


def fetch_suite(suite_id: str) -> dict:
    """优先读平台持久化的 yaml（就是平台自己在用的那份）。"""
    path = os.path.join(
        r"C:\code\workspace\Awesome-Agent-Workflow\skill-eval\.skill-eval-data\suites",
        f"{suite_id}.yaml",
    )
    if os.path.exists(path):
        return yaml.safe_load(open(path, encoding="utf-8"))
    with urllib.request.urlopen(f"{API}/suites/{suite_id}", timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))["definition"]


def fetch_experiment(exp_id: str) -> dict:
    try:
        with urllib.request.urlopen(f"{API}/experiments/{exp_id}", timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return {}


def write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("suite_id")
    ap.add_argument("skill_name")
    ap.add_argument("--source-standard", default=None,
                    help="手写源头标准 .md 的路径，可选")
    ap.add_argument("--experiment", default=None, help="实测实验 id，可选")
    ap.add_argument("--results", default=None,
                    help="实测结果的 JSON 文本或 .json 文件路径，写入 meta.results")
    args = ap.parse_args()

    d = fetch_suite(args.suite_id)
    case = d["cases"][0]
    out = os.path.join(STANDARDS_ROOT, args.skill_name)
    os.makedirs(out, exist_ok=True)

    if args.source_standard:
        write(os.path.join(out, "00-source-standard.md"),
              open(args.source_standard, encoding="utf-8").read())
    write(os.path.join(out, "01-case-input.md"), case["input"])
    write(os.path.join(out, "02-case-expected.md"), case["expected"])

    rows = ["| id | 类型 | 权重 | 硬门槛 | rubric 字数 |", "|---|---|---|---|---|"]
    for g in case["graders"]:
        rows.append(
            f"| `{g['id']}` | {g['type']} | {g['weight']} | "
            f"{bool(g.get('hard_gate'))} | {len(g.get('rubric') or '')} |"
        )
    body = [
        f"# {args.skill_name} 评测标准（判据正文）",
        "",
        f"来源套件：`{d['name']}`",
        f"套件 id：{args.suite_id}",
        f"skill：{(d.get('skill') or {}).get('name')}  "
        f"project：{(d.get('project') or {}).get('path')}",
        "",
        *rows,
        "",
    ]
    for g in case["graders"]:
        body += [
            "---", "", f"## {g['id']}", "",
            f"- 名称：{g['name']}",
            f"- 类型：`{g['type']}`",
            f"- 权重：{g['weight']}",
            f"- 硬门槛：{bool(g.get('hard_gate'))}",
            "", "### rubric", "", "```text", g.get("rubric") or "", "```", "",
        ]
    write(os.path.join(out, "03-graders.md"), "\n".join(body))

    write(os.path.join(out, "04-suite.definition.yaml"),
          yaml.safe_dump(d, allow_unicode=True, sort_keys=False, width=10 ** 6))

    meta = {
        "skill": args.skill_name,
        "skill_id": (d.get("skill") or {}).get("id"),
        "suite_id": args.suite_id,
        "suite_name": d["name"],
        "definition_hash": (d.get("skill") or {}).get("definition_hash"),
        "project_path": (d.get("project") or {}).get("path"),
        "project_commit": (d.get("project") or {}).get("commit"),
        "setup": d.get("setup"),
        "max_turns": case.get("max_turns"),
        "followups": case.get("followups"),
        "graders": [
            {"id": g["id"], "type": g["type"], "weight": g["weight"],
             "hard_gate": bool(g.get("hard_gate"))}
            for g in case["graders"]
        ],
    }
    if args.experiment:
        exp = fetch_experiment(args.experiment)
        meta["experiment"] = {
            "id": args.experiment,
            "mode": exp.get("mode"),
            "status": exp.get("status"),
        }
        if exp.get("project_commit"):
            meta["project_commit"] = exp["project_commit"]
    if args.results:
        raw = args.results
        if os.path.exists(raw):
            raw = open(raw, encoding="utf-8").read()
        meta["results"] = json.loads(raw)
    write(os.path.join(out, "05-meta.json"),
          json.dumps(meta, ensure_ascii=False, indent=2))

    for f in sorted(os.listdir(out)):
        print(f"{f:<28} {os.path.getsize(os.path.join(out, f)):>8} B")


if __name__ == "__main__":
    main()
