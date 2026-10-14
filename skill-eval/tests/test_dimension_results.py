"""Dimension summaries drive the main radar; graders remain inspectable scene details."""

from test_detail_page_structure import _js, _run_scenario


def experiment():
    dimensions = [
        {"id": key, "name": name, "method": "llm", "weight": weight, "hard_gate": False}
        for key, name, weight in (
            ("correctness", "功能正确性", 3),
            ("accuracy", "事实与证据质量", 1),
            ("clarity", "表达清晰度", 1),
        )
    ] + [{"id": "gate", "name": "维度门禁", "hard_gate": True, "weight": 1}]
    graders = [
        {
            "id": f"{dimension['id']}.{index}",
            "name": f"评分项 {index}",
            "dimension_id": dimension["id"],
            "type": "llm_rubric",
            "weight": 0.5,
        }
        for dimension in dimensions[:3]
        for index in (1, 2)
    ]
    cases = [{"id": case_id, "name": case_id, "graders": graders} for case_id in ("a", "b")]
    runs = [
        {
            "id": f"run-{case_id}",
            "case_id": case_id,
            "group": "current",
            "trial": 1,
            "status": "completed",
            "quality_score": 99,
            "reviews": [],
            "scores": {"components": [{"grader_id": g["id"], "score": 99} for g in graders]},
        }
        for case_id in ("a", "b")
    ]
    return {
        "id": "exp",
        "trials": 1,
        "catalog_version": 1,
        "suite_snapshot": {"dimensions": dimensions, "cases": cases},
        "runs": runs,
        "scores": {"current": 48},
        "dimension_scores": {
            "current": [
                {
                    "id": d["id"],
                    "score": value,
                    "completed": 2,
                    "expected": 2,
                    "incomplete": False,
                    "passed": True,
                }
                for d, value in zip(dimensions, [20, 80, 100, 100], strict=True)
            ]
        },
    }


def test_radar_uses_suite_dimension_results_and_preserves_grouped_score_items(tmp_path):
    result = _run_scenario(
        tmp_path,
        f"""
const item = {_js(experiment())};
state.detailCaseFor = item.id; state.detailCaseId = 'a';
const grouped = runsByCaseAndGroup(item);
const dataA = caseComparisonData(item, item.suite_snapshot.cases[0], grouped.get('a'));
const dataB = caseComparisonData(item, item.suite_snapshot.cases[1], grouped.get('b'));
state.expandedResultNodes.clear();
for (const dimension of ['correctness','accuracy','clarity']) {{
  state.expandedResultNodes.add('dimension/'+dimension);
  state.expandedResultNodes.add('scene/'+dimension+'/a');
}}
const markup = comparisonViewParts(item);
console.log(JSON.stringify({{
  axes:dataA.axes.map(d=>d.id), values:dataA.series[0].values,
  quality:dataA.series[0].quality, caseSwitchStable:JSON.stringify(dataA)===JSON.stringify(dataB),
  scoreRows:(markup.body.match(/data-result-grader=/g)||[]).length,
  grouped:markup.body.includes('data-result-dimension="accuracy"'),
  radarLabel:markup.chart.includes('评价维度雷达图'),
  scope:markup.chart.includes('全部场景汇总'),
  oldLabel:markup.body.includes('评分维度'),
  snapshotLabel:caseSnapshotMarkup(item,item.suite_snapshot.cases[0]).includes('评分项')
}}));
""",
    )
    assert result["axes"] == ["correctness", "accuracy", "clarity"]
    assert result["values"] == [20, 80, 100]  # Server's case-weighted scores, not raw grader 99.
    assert result["quality"] == 48
    assert result["caseSwitchStable"]
    assert result["scoreRows"] == 6
    assert result["grouped"] and result["radarLabel"] and result["scope"]
    assert result["snapshotLabel"] and not result["oldLabel"]


def test_missing_dimension_results_stay_missing_and_partial_results_are_provisional(tmp_path):
    item = experiment()
    item["dimension_scores"]["current"][0].update(score=0, incomplete=True)
    item["dimension_scores"]["current"].pop(1)
    result = _run_scenario(
        tmp_path,
        f"""
const item={_js(item)};
const data=dimensionComparisonData(item);
const chart=radarChartMarkup(data);
console.log(JSON.stringify({{values:data.series[0].values,
  provisional:data.series[0].provisional,
  partial:chart.includes('临时结果'), missingAxisPresent:data.axes.some(d=>d.id==='accuracy')}}));
""",
    )
    assert result["values"] == [0, None, 100]
    assert result["provisional"] and result["partial"] and result["missingAxisPresent"]


def test_failed_workflow_gate_is_visible_even_when_run_is_not_completed(tmp_path):
    item = experiment()
    case = item["suite_snapshot"]["cases"][0]
    case["workflow"] = {"entry": "sr", "sr": "SR-TEST"}
    run = item["runs"][0]
    run.update(status="agent_error", quality_score=None)
    run["scores"]["workflow_completion"] = {
        "passed": False,
        "state_path": ".sdd/SR-TEST/workflow.yaml",
        "errors": ["设计门禁未通过", "<script>injected</script>"],
    }
    result = _run_scenario(
        tmp_path,
        f"""
const item={_js(item)};
state.detailCaseFor=item.id; state.detailCaseId='a';
const parts=comparisonViewParts(item);
const markup=workflowGatesMarkup(item.suite_snapshot.cases[0],
  {{current:[item.runs[0]], no_skill:[{{status:'completed'}}]}},1);
console.log(JSON.stringify({{gate:parts.gates.includes('AAW 流程完成检查'),
  failed:markup.includes('未通过 · 0/1'), error:markup.includes('设计门禁未通过'),
  notApplicable:markup.includes('不适用'), escaped:markup.includes('&lt;script&gt;'),
  noFakeAxis:!dimensionComparisonData(item).axes.some(d=>d.id==='system.workflow-completion')}}));
""",
    )
    assert all(result.values())


def test_workflow_without_evidence_does_not_report_pass(tmp_path):
    result = _run_scenario(
        tmp_path,
        """
const spec={workflow:{entry:'dev',sr:'SR-TEST'}};
const queued=workflowGatesMarkup(spec,{current:[{status:'queued'}]},3);
const failed=workflowGatesMarkup(spec,{current:[{status:'timeout'}]},3);
console.log(JSON.stringify({pending:queued.includes('待检查 · 0/3'),
  missing:failed.includes('缺少完成证据 · 0/3'), noPassed:!failed.includes('radar-gate passed')}));
""",
    )
    assert all(result.values())


def test_score_item_toggle_binds_once_when_detail_rerenders(tmp_path):
    result = _run_scenario(
        tmp_path,
        """
const button={dataset:{dimensionOpen:'accuracy.factual-consistency'}};
document.querySelectorAll=selector=>selector==='[data-dimension-open]' ? [button] : [];
state.detail=null; state.expandedDimensions.clear();
bindDetailActions({id:'fixture'}); bindDetailActions({id:'fixture'});
button.onclick();
const expanded=state.expandedDimensions.has(button.dataset.dimensionOpen);
button.onclick();
console.log(JSON.stringify({expanded,collapsed:!state.expandedDimensions.has(button.dataset.dimensionOpen)}));
""",
    )
    assert result == {"expanded": True, "collapsed": True}
