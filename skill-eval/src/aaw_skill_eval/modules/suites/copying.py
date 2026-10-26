from copy import deepcopy

from aaw_skill_eval.errors import EvalError


def draft_from_definition(definition):
    # Preserve canonical checks by reconstructing portable per-dimension source packages.
    import base64

    from aaw_skill_eval.modules.designer.packages import package_from_documents

    packages = {}
    for dimension in definition.get("dimensions", []):
        cases, assets = [], {}
        for original in definition["cases"]:
            own = [g for g in original["graders"] if g.get("dimension_id") == dimension["id"]]
            if not own:
                continue
            case = deepcopy(original)
            case["files"] = {}
            case["graders"] = []
            for file in original.get("files", []):
                source = f"{case['id']}/scene/{file['path']}"
                assets[source] = base64.b64decode(file["content_base64"]).decode()
                case["files"][file["path"]] = source
            for g in own:
                if g["type"] == "llm_rubric":
                    continue
                grader = {
                    name: g[name]
                    for name in (
                        "type",
                        "command",
                        "result_format",
                        "checkpoint_ids",
                        "setup_commands",
                        "timeout_seconds",
                    )
                    if name in g
                }
                grader["files"] = []
                for file in g.get("files", []):
                    assets[file["path"]] = base64.b64decode(file["content_base64"]).decode()
                    grader["files"].append(file["path"])
                case["graders"].append(grader)
            case["weight"] = original.get("dimension_weights", {}).get(dimension["id"], 1)
            case.pop("dimension_weights", None)
            cases.append(case)
        packages[dimension["id"]] = package_from_documents(
            dimension["id"], {"cases": cases}, assets
        )
    if not packages:
        raise EvalError("LEGACY_COPY", "旧版自由评分套件请通过固定维度重新创建", status_code=422)
    return {
        "name": definition["name"],
        "project_path": definition["project"]["path"],
        "skill_path": definition.get("reference_skill_path", ""),
        "requirement": definition.get("requirement", ""),
        "setup": definition.get("setup", {}),
        "dimensions": definition["dimensions"],
        "packages": packages,
        "generator_provider": "chrys",
        "generator_model": "",
    }
