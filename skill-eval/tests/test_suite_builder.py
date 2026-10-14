from __future__ import annotations

import json

from test_detail_page_structure import _run_scenario

from aaw_skill_eval.services.catalog.packages import (
    PackageImportRequest,
    import_package,
)


def _cases(method):
    import base64

    from aaw_skill_eval.services.catalog.packages import standard_example_package

    dim_id = "correctness" if method == "code" else "maintainability"
    return import_package(
        PackageImportRequest(
            catalog_version=1,
            skill_type="development",
            dimension_id=dim_id,
            zip_base64=base64.b64encode(standard_example_package("development", dim_id)).decode(),
        ),
        require_standard=True,
    )["cases"]


def test_frontend_merges_shared_scenes_preserves_assets_and_independent_case_weights(tmp_path):
    result = _run_scenario(
        tmp_path,
        f"""
const codeCases = {json.dumps(_cases("code"), ensure_ascii=False)};
const llmCases = {json.dumps(_cases("llm"), ensure_ascii=False)};
const llmEditor = editableCases(llmCases);
llmEditor[0].weight = 3;
state.dimensions = [
  {{id:'correctness',name:'功能',method:'code',weight:1,hard_gate:false,pass_score:60,
    cases:codeCases,editor:JSON.stringify(editableCases(codeCases))}},
  {{id:'maintainability',name:'可维护性',method:'llm',weight:2,hard_gate:false,pass_score:60,
    cases:llmCases,editor:JSON.stringify(llmEditor)}}
];
const suite = buildDimensionSuite();
const cases = suite.cases;
console.log(JSON.stringify({{count:cases.length, checks:cases[0].graders.length,
  weights:cases[0].dimension_weights, visible:cases[0].files.map(file=>file.path),
  graderIds:cases[0].graders.map(grader=>grader.id),
  script:cases[0].graders[0].files[0].content_base64}}));
""",
    )
    assert result["count"] == 1
    assert result["checks"] == 2
    assert result["weights"] == {"correctness": 1, "maintainability": 3}
    assert result["visible"] == ["brief.md"]
    assert result["graderIds"] == ["correctness.code-1", "maintainability.llm"]
    assert result["script"]


def test_frontend_conflicting_scene_rejected_and_renaming_keeps_assets(tmp_path):
    result = _run_scenario(
        tmp_path,
        f"""
const cases = {json.dumps(_cases("code"), ensure_ascii=False)};
state.dimensions = ['one','two'].map(id=>({{id,name:id,method:'code',weight:1,
  cases:structuredClone(cases),editor:JSON.stringify(editableCases(cases))}}));
const edited = JSON.parse(state.dimensions[1].editor);
edited[0].input = 'A different task';
state.dimensions[1].editor = JSON.stringify(edited);
let error = '';
try {{ buildDimensionSuite(); }} catch (exc) {{ error = exc.message; }}
edited[0].id = 'independent-task';
state.dimensions[1].editor = JSON.stringify(edited);
const suite = buildDimensionSuite();
console.log(JSON.stringify({{error,count:suite.cases.length,
  assets:suite.cases[1].files[0].path,script:suite.cases[1].graders[0].files[0].path}}));
""",
    )
    assert "配置不一致" in result["error"]
    assert result["count"] == 2
    assert result["assets"] == "brief.md"
    assert result["script"] == "validate.py"
