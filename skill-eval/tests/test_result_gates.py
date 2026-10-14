from test_detail_page_structure import _js, _run_scenario
from test_unified_results import item_with_scenes


def workflow_item():
    item = item_with_scenes()
    item["suite_snapshot"]["dimensions"] = [
        d for d in item["suite_snapshot"]["dimensions"] if not d["hard_gate"]
    ]
    for case, run in zip(item["suite_snapshot"]["cases"], item["runs"], strict=True):
        case["workflow"] = {"entry": "dev", "sr": "SR-TEST"}
        run["hard_gates"] = {"passed": 1, "total": 1}
        run["scores"]["workflow_completion"] = {"passed": True, "errors": []}
    return item


def test_gate_summary_is_in_results_and_details_are_collapsed_without_mutating_scores(tmp_path):
    result = _run_scenario(
        tmp_path,
        f"""
const item={_js(workflow_item())};
const before=JSON.stringify(item);
state.expandedResultNodes.clear();
const parts=comparisonViewParts(item);
const collapsed=parts.body;
state.expandedResultNodes.add('gates/summary');
const expanded=comparisonViewParts(item).body;
console.log(JSON.stringify({{inResults:collapsed.includes('硬门禁状态'),
  beforeDimensions:collapsed.indexOf('result-gates')<collapsed.indexOf('result-tree'),
  summaryPassed:collapsed.includes('通过')&&collapsed.includes('2/2'),
  hidden:!collapsed.includes('AAW 流程完成检查'),
  expanded:(expanded.match(/aria-label="流程完成检查"/g)||[]).length,
  unchanged:JSON.stringify(item)===before}}));
""",
    )
    assert result["expanded"] == 2
    assert all(value for key, value in result.items() if key != "expanded")


def test_failed_workflow_run_is_failed_in_collapsed_summary(tmp_path):
    item = workflow_item()
    run = item["runs"][0]
    run.update(status="agent_error", quality_score=None, hard_gates={"passed": 0, "total": 1})
    run["scores"]["workflow_completion"] = {"passed": False, "errors": ["Missing report"]}
    result = _run_scenario(
        tmp_path,
        f"""
const item={_js(item)};
state.expandedResultNodes.clear();
const value=resultGateStatus(item,item.suite_snapshot.cases,'current');
const body=comparisonViewParts(item).body;
console.log(JSON.stringify({{text:value.text,note:value.note,
  visible:body.includes('未通过'), evidenceHidden:!body.includes('Missing report')}}));
""",
    )
    assert result == {"text": "未通过", "note": "1/2", "visible": True, "evidenceHidden": True}


def test_pending_workflow_and_no_skill_are_not_falsely_marked_passed(tmp_path):
    item = workflow_item()
    item["trials"] = 3
    item["runs"][0].update(status="queued", hard_gates={"passed": 0, "total": 0}, scores={})
    result = _run_scenario(
        tmp_path,
        f"""
const item={_js(item)};
const current=resultGateStatus(item,item.suite_snapshot.cases,'current');
const control=resultGateStatus(item,item.suite_snapshot.cases,'no_skill');
console.log(JSON.stringify({{current:current.text,note:current.note,control:control.text}}));
""",
    )
    assert result == {"current": "待检查", "note": "1/6", "control": "不适用"}
