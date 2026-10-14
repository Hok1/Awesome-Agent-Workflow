from test_detail_page_structure import _js, _run_scenario
from test_dimension_results import experiment


def item_with_scenes():
    item = experiment()
    for index, case in enumerate(item["suite_snapshot"]["cases"]):
        case.update(
            input=f"Task for {case['id']}",
            expected="Expected output",
            max_turns=6,
            dimension_weights={"correctness": 3 if index == 0 else 1},
        )
        item["runs"][index]["scores"]["dimensions"] = [
            {
                "id": "correctness",
                "score": 10 if index == 0 else 50,
                "passed": True,
                "invalid": False,
            }
        ]
    return item


def test_default_view_only_shows_dimension_results_not_duplicate_sections(tmp_path):
    result = _run_scenario(
        tmp_path,
        f"""
const item={_js(item_with_scenes())};
state.expandedResultNodes.clear();
const body=comparisonViewParts(item).body;
console.log(JSON.stringify({{dimensions:(body.match(/data-result-dimension=/g)||[]).length,
  items:body.includes('data-result-grader'), cases:body.includes('data-result-case'),
  splitSummary:body.includes('dimension-summary'), splitDetails:body.includes('检查点与评分明细'),
  parentScore:body.includes('20.0'), scope:body.includes('全套件结果')}}));
""",
    )
    assert result["dimensions"] == 4
    assert result["parentScore"] and result["scope"]
    assert not any(result[key] for key in ("items", "cases", "splitSummary", "splitDetails"))


def test_multiple_scenes_show_own_dimension_scores_and_weights(tmp_path):
    result = _run_scenario(
        tmp_path,
        f"""
const item={_js(item_with_scenes())};
state.expandedResultNodes=new Set(['dimension/correctness']);
const body=comparisonViewParts(item).body;
console.log(JSON.stringify({{scenes:(body.match(/data-result-case=/g)||[]).length,
  sceneA:body.includes('10.0'), sceneB:body.includes('50.0'),
  weightA:body.includes('用例权重 3'), weightB:body.includes('用例权重 1'),
  hiddenItems:!body.includes('data-result-grader'), globalPreserved:body.includes('20.0')}}));
""",
    )
    assert result["scenes"] == 2
    assert all(value for key, value in result.items() if key != "scenes")


def test_single_scene_skips_extra_fold_and_keeps_definition_and_config_hidden(tmp_path):
    item = item_with_scenes()
    item["suite_snapshot"]["cases"] = item["suite_snapshot"]["cases"][:1]
    item["runs"] = item["runs"][:1]
    result = _run_scenario(
        tmp_path,
        f"""
const item={_js(item)};
state.expandedResultNodes=new Set(['dimension/correctness']);
const collapsed=comparisonViewParts(item).body;
state.expandedResultNodes.add('definition/correctness/a');
const definition=comparisonViewParts(item).body;
state.expandedResultNodes.add('configuration/correctness/a');
const configuration=comparisonViewParts(item).body;
console.log(JSON.stringify({{single:collapsed.includes('result-single-scene'),
  noExtraFold:!collapsed.includes('data-result-toggle="scene/correctness/a"'),
  itemCount:(collapsed.match(/data-result-grader=/g)||[]).length,
  hiddenInput:!collapsed.includes('Task for a'), input:definition.includes('Task for a'),
  configHidden:!definition.includes('grader-snapshot-head'),
  configVisible:configuration.includes('grader-snapshot-head')}}));
""",
    )
    assert result["itemCount"] == 2
    assert all(value for key, value in result.items() if key != "itemCount")


def test_trial_expansion_is_scoped_to_case_and_persists_when_parent_is_closed(tmp_path):
    result = _run_scenario(
        tmp_path,
        f"""
const item={_js(item_with_scenes())};
state.expandedResultNodes=new Set(['dimension/correctness','scene/correctness/a',
  'scene/correctness/b','score/a/correctness.1']);
const open=comparisonViewParts(item).body;
state.expandedResultNodes.delete('dimension/correctness');
const closed=comparisonViewParts(item).body;
state.expandedResultNodes.add('dimension/correctness');
const reopened=comparisonViewParts(item).body;
console.log(JSON.stringify({{trialCount:(open.match(/data-trial-comparison="correctness.1"/g)||[]).length,
  closed:!closed.includes('data-trial-comparison'), stable:open===reopened}}));
""",
    )
    assert result == {"trialCount": 1, "closed": True, "stable": True}


def test_tree_button_binding_is_idempotent_and_workflow_checks_include_all_cases(tmp_path):
    item = item_with_scenes()
    for case in item["suite_snapshot"]["cases"]:
        case["workflow"] = {"entry": "dev", "sr": f"SR-{case['id']}"}
    result = _run_scenario(
        tmp_path,
        f"""
const item={_js(item)};
const button={{dataset:{{resultToggle:'dimension/correctness'}}}};
document.querySelectorAll=selector=>selector==='[data-result-toggle]' ? [button] : [];
state.detail=null; state.expandedResultNodes.clear();
bindDetailActions(item); bindDetailActions(item); button.onclick();
console.log(JSON.stringify({{expanded:state.expandedResultNodes.has('dimension/correctness'),
  checks:(comparisonViewParts(item).gates.match(/aria-label="流程完成检查"/g)||[]).length}}));
""",
    )
    assert result == {"expanded": True, "checks": 2}
