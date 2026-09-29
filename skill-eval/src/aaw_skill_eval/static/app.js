const state = {
  suites: [], experiments: [], draft: null, poller: null,
  runtime: null, controlsInitialized: false, detail: null, detailPoller: null,
  experimentsRequestSeq: 0,
  runEvents: {}, eventCursors: {}, runLogs: {}, expandedRuns: {}, retryingExperiments: new Set(),
  logConsole: null, logPoller: null
};
const RUNTIME_CACHE_KEY = "aaw-skill-eval.runtime.v1";
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];

function escapeHtml(value = "") {
  return String(value).replace(/[&<>'"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"})[ch]);
}
function fmtScore(value) { return value == null ? "—" : Number(value).toFixed(1); }
function fmtDelta(value) {
  if (value == null) return '<span class="delta">—</span>';
  const cls = value > 0 ? "up" : value < 0 ? "down" : "";
  return `<span class="delta ${cls}">${value > 0 ? "+" : ""}${Number(value).toFixed(1)}</span>`;
}
function fmtTime(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("zh-CN", {month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"}).format(new Date(value));
}
function providerName(value) { return value === "chrys" ? "Chrys" : "Codex"; }
function modelName(role) { return role.model_name || role.model || "—"; }
function errorText(value) {
  if (!value) return value;
  let message = value;
  try { message = JSON.parse(value).error || value; } catch {}
  if (typeof message !== "string") message = String(value);
  if (message.includes("output token limit while reasoning")) {
    return "Chrys 在推理阶段耗尽 Max Output Tokens，未产生可见回答。请提高该 Model Profile 的 Max Output Tokens 后重试。";
  }
  if (message.includes("[WinError 3]") && message.includes("skill-snapshots") && message.includes(".aaw-eval")) {
    return "Skill 快照复制失败：Windows 工作区路径过长。新实验已改用较短的工作区路径。";
  }
  return message;
}
function toast(message) {
  const node = $("#toast"); node.textContent = message; node.classList.add("show");
  clearTimeout(node._timer); node._timer = setTimeout(() => node.classList.remove("show"), 2600);
}
async function api(path, options = {}) {
  const response = await fetch(path, {headers:{"Content-Type":"application/json",...(options.headers||{})},...options});
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.message || `HTTP ${response.status}`);
  return body;
}
function lines(value) { return value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean); }

function restoreRuntimeCache() {
  try {
    const cached = JSON.parse(localStorage.getItem(RUNTIME_CACHE_KEY) || "null");
    if (!cached?.value || Date.now() - cached.savedAt > 24 * 60 * 60 * 1000) return;
    state.runtime = cached.value;
    renderRuntime();
    renderProviderControls();
  } catch {
    localStorage.removeItem(RUNTIME_CACHE_KEY);
  }
}
function fmtDuration(seconds) {
  if (seconds == null) return "—";
  const value=Math.max(0,Math.floor(seconds));
  if(value<60)return `${value}s`;
  const minutes=Math.floor(value/60),remaining=value%60;
  return `${minutes}m ${remaining}s`;
}
function elapsedSince(value) { return value ? Math.max(0,(Date.now()-new Date(value).getTime())/1000) : null; }
function persistRuntimeCache(value) {
  try { localStorage.setItem(RUNTIME_CACHE_KEY, JSON.stringify({savedAt:Date.now(),value})); } catch {}
}

async function loadAll({refreshRuntime = false} = {}) {
  const runtimeRequest = api(`/api/v1/runtime${refreshRuntime ? "?refresh=true" : ""}`);
  const [suites] = await Promise.all([
    api("/api/v1/suites"), refreshExperiments()
  ]);
  state.suites = suites.items;
  renderSuites();

  try {
    state.runtime = await runtimeRequest;
    persistRuntimeCache(state.runtime);
    renderRuntime();
    renderProviderControls();
  } catch (error) {
    const badge = $("#runtimeBadge");
    badge.classList.remove("ok");
    badge.innerHTML = `<i></i>Runner 探测失败`;
    throw error;
  }
}
async function refreshExperiments() {
  const requestSeq = ++state.experimentsRequestSeq;
  const result = await api("/api/v1/experiments?limit=50");
  if (requestSeq !== state.experimentsRequestSeq) return;
  state.experiments = result.items;
  renderExperimentFilters(); renderExperiments(); updatePolling();
}
function upsertExperiment(item) {
  ++state.experimentsRequestSeq;
  state.experiments = [item, ...state.experiments.filter(existing => existing.id !== item.id)]
    .sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  $("#experimentStatusFilter").value = "";
  $("#experimentModeFilter").value = "";
  renderExperimentFilters(); renderExperiments(); updatePolling();
}
function renderRuntime() {
  const providers = state.runtime.providers || {};
  const ready = Object.entries(providers).filter(([,item])=>item.available);
  const badge = $("#runtimeBadge"); badge.classList.toggle("ok", ready.length > 0);
  badge.innerHTML = `<i></i>${ready.length ? ready.map(([name,item])=>`${providerName(name)} ${escapeHtml(item.version || "已就绪")}`).join(" · ") : "未找到可用 Agent"}`;
}
function optionMarkup(items, selected) {
  return items.map(item=>`<option value="${escapeHtml(item.value)}"${item.value===selected?' selected':''}>${escapeHtml(item.label)}</option>`).join("");
}
function availableProviders() {
  const providers = state.runtime?.providers || {};
  return ["chrys","codex"].filter(name=>providers[name]?.available);
}
function renderProviderControls() {
  const providers = availableProviders();
  const runner = $("#runnerProvider"), judge = $("#judgeProvider");
  const previousRunner = runner.value, previousJudge = judge.value;
  const options = providers.map(value=>({value,label:providerName(value)}));
  runner.innerHTML = optionMarkup(options, providers.includes(previousRunner) ? previousRunner : providers[0]);
  judge.innerHTML = optionMarkup(options, providers.includes(previousJudge) ? previousJudge : providers[0]);
  const models = state.runtime?.providers?.chrys?.models || [];
  const sortedModels = [...models].sort((a,b)=>Number(b.active)-Number(a.active)||String(a.name).localeCompare(String(b.name)));
  ["#runnerChrysModel","#judgeChrysModel"].forEach(selector=>{
    const select=$(selector), previous=select.value;
    select.innerHTML=optionMarkup(sortedModels.map(item=>({value:item.id,label:`${item.name}${item.active?" · active":""}`})),previous);
  });
  renderCodexModelOptions();
  if (!state.controlsInitialized) {
    const preferred = providers.includes("chrys") ? "chrys" : providers[0];
    if (preferred) { runner.value=preferred; judge.value=preferred; }
    state.controlsInitialized = true;
  }
  syncProviderControls();
}
function renderCodexModelOptions() {
  const models = state.runtime?.providers?.codex?.models || [];
  const datalist = $("#codexModelOptions");
  if (datalist) datalist.innerHTML = models.map(item=>`<option value="${escapeHtml(item.id)}">${escapeHtml(item.name || item.id)}</option>`).join("");
  const active = models.find(item=>item.active) || models[0];
  ["#runnerCodexModel","#judgeCodexModel"].forEach(selector=>{
    const input=$(selector);
    if (!input) return;
    if (active && !input.value.trim()) input.value = active.id;
    if (active && input.placeholder) input.placeholder = `请选择或输入模型 ID（如 ${active.id}）`;
  });
  const hint = $("#runnerCodexModelHint");
  if (hint) hint.textContent = models.length
    ? `候选模型读取自本机 Codex 配置（${models.map(item=>item.id).join("、")}），也可手动输入其他模型 ID。`
    : "本机 Codex 配置中未找到模型；可手动输入模型 ID（如 gpt-6-sol）。";
}
function syncProviderControls() {
  const runnerProvider=$("#runnerProvider").value, judgeProvider=$("#judgeProvider").value;
  $("#runnerCodexConfig").classList.toggle("hidden",runnerProvider!=="codex");
  $("#runnerChrysConfig").classList.toggle("hidden",runnerProvider!=="chrys");
  const same=$("#judgeSame").checked;
  $("#judgeConfig").classList.toggle("hidden",same);
  $("#judgeCodexConfig").classList.toggle("hidden",judgeProvider!=="codex");
  $("#judgeChrysConfig").classList.toggle("hidden",judgeProvider!=="chrys");
  const isolation=runnerProvider==="chrys"?"Chrys 软隔离 · 网络未强制隔离":"Codex workspace-write · 网络按 Profile 控制";
  $("#profileHint").textContent=`${isolation}。实验会固化 Runner、Judge、模型、版本与评分配置。`;
}
function setFilterOptions(selector, values, allLabel, labelFn=x=>x) {
  const select=$(selector), previous=select.value;
  const options=[{value:"",label:allLabel},...values.map(value=>({value,label:labelFn(value)}) )];
  select.innerHTML=optionMarkup(options,values.includes(previous)?previous:"");
}
function experimentStatusLabel(status) {
  return ({queued:"排队中",preparing:"准备中",running:"运行中",completed:"已完成",completed_with_failures:"完成但有失败",cancelled:"已取消",failed:"失败",invalid:"无效",grader_invalid:"评分无效",infra_error:"环境错误",agent_error:"Agent 错误",timeout:"超时"})[status] || status;
}
function stageLabel(stage) {
  return ({queued:"排队",creating_workspace:"创建工作区",installing_skill:"安装 Skill",runner:"Runner 执行",collecting_changes:"收集改动",validators:"执行验证器",judge:"Judge 评分",scoring:"汇总评分",persisting:"保存结果",completed:"完成",cancelled:"取消",infra_error:"环境错误",agent_error:"Agent 错误",timeout:"超时",grader_invalid:"评分无效"})[stage] || stage || "等待阶段信息";
}
function renderExperimentFilters() {
  const statuses=[...new Set(state.experiments.map(item=>item.status))];
  setFilterOptions("#experimentStatusFilter",statuses,"全部状态",experimentStatusLabel);
}
function filteredExperiments() {
  const status=$("#experimentStatusFilter").value, mode=$("#experimentModeFilter").value;
  return state.experiments.filter(item=>(!status||item.status===status)&&(!mode||item.mode===mode));
}
function renderSuites() {
  const select=$("#runSuite"),previous=select.value;
  select.innerHTML=state.suites.length?state.suites.map(s=>`<option value="${s.id}">${escapeHtml(s.name)} · ${escapeHtml(s.skill_name)}</option>`).join(""):'<option value="">请先创建测试套件</option>';
  if(state.suites.some(s=>s.id===previous))select.value=previous;
}
function experimentLineageMarkup(item) {
  const links=[];
  if(item.retry_of_experiment_id)links.push(`<button class="text-button retry-link" data-detail="${item.retry_of_experiment_id}">重试自 ${escapeHtml(item.retry_of_experiment_id.slice(0,8))}</button>`);
  (item.retry_experiment_ids||[]).forEach((id,index)=>links.push(`<button class="text-button retry-link" data-detail="${id}">后续重试 #${index+1}</button>`));
  return links.length?`<div class="experiment-lineage">${links.join("")}</div>`:"";
}
function renderExperiments() {
  const list=$("#experimentList"),items=filteredExperiments();
  if(!state.experiments.length){list.innerHTML='<div class="table-card empty">尚无实验记录。创建测试套件后，即可从右侧发起首次运行。</div>';return;}
  if(!items.length){list.innerHTML='<div class="table-card empty">当前筛选下尚无实验记录。</div>';return;}
  const stalled=items.filter(item=>item.progress?.stalled).length;document.title=stalled?`(${stalled}) AAW Skill Eval`:"AAW Skill Eval";
  list.innerHTML=items.map(item=>{const progress=item.progress||{},total=progress.total||0,done=progress.completed||0,percent=total?Math.round(done/total*100):0,retrying=state.retryingExperiments.has(item.id);return `<article class="experiment-item ${progress.stalled?"is-stalled":""}">
    <div><h3>${escapeHtml(item.suite_name)}</h3><div class="experiment-meta"><span class="pill ${item.status}">${escapeHtml(experimentStatusLabel(item.status))}</span><span>${providerName(item.profile.runner.provider)} → ${providerName(item.profile.judge.provider)}</span><span>${item.mode==="formal"?"正式":"快速"} · ${item.trials} trial</span><span>${fmtTime(item.created_at)}</span><span>${escapeHtml(item.project_commit.slice(0,8))}</span></div>${experimentLineageMarkup(item)}${total?`<div class="progress-row"><div class="progress-track"><i style="width:${percent}%"></i></div><span>${done}/${total} 完成${progress.running?` · ${progress.running} 运行中`:""}${progress.queued?` · ${progress.queued} 等待`:""}${progress.failed?` · ${progress.failed} 异常`:""}</span>${progress.active_stage?`<strong>${escapeHtml(stageLabel(progress.active_stage))}</strong>`:""}${progress.stalled?`<b class="stall-warning">${progress.active_heartbeat_age_seconds!=null&&progress.active_heartbeat_age_seconds<45?"静默等待":"心跳中断"} · ${fmtDuration(progress.active_activity_age_seconds)} 无新活动</b>`:""}</div>`:""}</div>
    <div class="experiment-result"><strong class="score">${fmtScore(item.scores.current)}</strong><button class="button button-ghost button-small" data-detail="${item.id}">详情</button><button class="button button-ghost button-small" data-retry-experiment="${item.id}" ${retrying?"disabled":""}>${retrying?"正在加入…":"重试"}</button></div>
  </article>`}).join("");
  $$('[data-detail]').forEach(button=>button.addEventListener("click",()=>showDetail(button.dataset.detail)));
  $$('[data-retry-experiment]').forEach(button=>button.addEventListener("click",()=>retryExperiment(button.dataset.retryExperiment)));
}
function updatePolling(){const active=state.experiments.some(x=>["queued","preparing","running"].includes(x.status));if(active&&!state.poller)state.poller=setInterval(()=>refreshExperiments().catch(()=>{}),2000);if(!active&&state.poller){clearInterval(state.poller);state.poller=null;}}

async function loadExpectedMarkdown(event){
  const input=event.currentTarget,file=input.files?.[0],status=$("#expectedFileStatus");
  status.classList.remove("loaded","error");
  if(!file){status.textContent="文件仅在浏览器本地读取，内容会填入上方文本框。";return;}
  if(!/\.(md|markdown)$/i.test(file.name)){input.value="";status.textContent="请选择 .md 或 .markdown 文件。";status.classList.add("error");toast("预期效果只支持 Markdown 文件");return;}
  if(file.size>2*1024*1024){input.value="";status.textContent="文件超过 2 MB，请精简后重试。";status.classList.add("error");toast("Markdown 文件不能超过 2 MB");return;}
  try{const content=await file.text();if(!content.trim())throw new Error("Markdown 文件内容为空");$("#expected").value=content;invalidateDraft();status.textContent=`已导入 ${file.name} · ${(file.size/1024).toFixed(1)} KB`;status.classList.add("loaded");}
  catch(error){input.value="";status.textContent=error.message||"无法读取 Markdown 文件。";status.classList.add("error");toast(status.textContent);}
}

async function generateDraft(){
  const required=[$("#projectPath"),$("#skillPath"),$("#skillInput"),$("#expected")],missing=required.find(field=>!field.value.trim());
  if(missing){showMessage("请先填写项目地址、Skill、输入和预期效果。",true);missing.focus();return;}
  const button=$("#draftButton");button.disabled=true;button.textContent="正在验证项目与 Skill…";
  try{const payload={project_path:$("#projectPath").value.trim(),skill_path:$("#skillPath").value.trim(),input:$("#skillInput").value.trim(),expected:$("#expected").value.trim()};state.draft=await api("/api/v1/rubric-drafts",{method:"POST",body:JSON.stringify(payload)});$("#verifiedContext").innerHTML=`<div><small>项目基线</small><strong>${escapeHtml(state.draft.project.name)} · ${state.draft.project.commit.slice(0,10)}</strong></div><div><small>Skill 修订</small><strong>${escapeHtml(state.draft.skill.name)} · ${state.draft.skill.content_hash.slice(0,10)}</strong></div>`;$("#suiteName").value=`${state.draft.skill.name} / ${state.draft.project.name}`;$("#caseJson").value=JSON.stringify(state.draft.case,null,2);$("#draftPanel").classList.remove("hidden");showMessage("评分草案已生成。请确认 Rubric、权重和验证命令。",false);}catch(error){showMessage(error.message,true);}finally{button.disabled=false;button.textContent="生成评分草案";}
}
function showMessage(message,error){const node=$("#suiteMessage");node.textContent=message;node.classList.remove("hidden","error");if(error)node.classList.add("error");}
async function saveSuite(){let saved;try{if(!state.draft)throw new Error("请先生成评分草案");const name=$("#suiteName").value.trim();if(!name){$("#suiteName").focus();throw new Error("请填写套件名称");}let caseData;try{caseData=JSON.parse($("#caseJson").value);}catch{throw new Error("评分用例 JSON 格式不正确");}const payload={name,project_path:$("#projectPath").value.trim(),skill_path:$("#skillPath").value.trim(),setup:{commands:lines($("#setupCommands").value),preflight:lines($("#preflightCommands").value),network:false,timeout_seconds:900},cases:[caseData]};saved=await api("/api/v1/suites",{method:"POST",body:JSON.stringify(payload)});}catch(error){showMessage(error.message,true);return;}$("#newSuite").close();resetSuiteForm();toast(`测试套件已保存：${saved.name}`);try{await loadAll();}catch{toast("套件已保存，但列表刷新失败，请手动刷新");}}
function invalidateDraft(){if(!state.draft)return;state.draft=null;$("#draftPanel").classList.add("hidden");showMessage("输入已变更，请重新生成评分草案。",false);}
function resetSuiteForm(){$("#suiteForm").reset();state.draft=null;$("#draftPanel").classList.add("hidden");$("#verifiedContext").innerHTML="";$("#suiteMessage").textContent="";$("#suiteMessage").classList.add("hidden");const status=$("#expectedFileStatus");status.textContent="文件仅在浏览器本地读取，内容会填入上方文本框。";status.classList.remove("loaded","error");}

function selectedModel(provider,role){return provider==="chrys"?$(`#${role}ChrysModel`).value:$(`#${role}CodexModel`).value.trim();}
function selectedTimeoutSeconds(){
  const raw=parseInt($("#timeoutSeconds")?.value,10);
  const value=Number.isFinite(raw)?raw:1800;
  return Math.min(14400,Math.max(30,value));
}
async function launchExperiment(){
  const suiteId=$("#runSuite").value;if(!suiteId)return toast("请先创建测试套件");
  const runnerProvider=$("#runnerProvider").value;if(!runnerProvider)return toast("没有可用的 Runner");
  const runnerModel=selectedModel(runnerProvider,"runner");if(!runnerModel)return toast("请选择或填写 Runner 模型");
  const same=$("#judgeSame").checked,judgeProvider=same?runnerProvider:$("#judgeProvider").value,judgeModel=same?runnerModel:selectedModel(judgeProvider,"judge");
  if(!judgeProvider||!judgeModel)return toast("请选择或填写 Judge 模型");
  const runnerEffort=$("#runnerEffort").value,judgeEffort=same?runnerEffort:$("#judgeEffort").value;
  const timeoutSeconds=selectedTimeoutSeconds();
  const profileName=`${runnerProvider}-${runnerModel}__${judgeProvider}-${judgeModel}`;
  const button=$("#runButton"),label=button.textContent;button.disabled=true;button.textContent="正在加入队列…";
  try{const body={suite_id:suiteId,mode:$("#runMode").value,profile:{schema_version:2,name:profileName,runner_provider:runnerProvider,runner_model:runnerModel,runner_reasoning_effort:runnerEffort,judge_provider:judgeProvider,judge_model:judgeModel,judge_reasoning_effort:judgeEffort,timeout_seconds:timeoutSeconds,network:false,allowed_mcp_servers:[]}};const result=await api("/api/v1/experiments",{method:"POST",body:JSON.stringify(body)});upsertExperiment(result.experiment);toast(`实验 ${result.id.slice(0,8)} 已加入队列（单轮无活动超时 ${timeoutSeconds}s）`);refreshExperiments().catch(()=>toast("实验已入队，后续状态刷新失败"));}catch(error){toast(error.message);}finally{button.disabled=false;button.textContent=label;}
}
function runActions(item,run){const actions=[];if(["queued","running"].includes(run.status))actions.push(`<button class="text-button danger" data-cancel-run="${run.id}">取消 run</button>`);if(["infra_error","timeout"].includes(run.error_kind)&&run.current_attempt<2)actions.push(`<button class="text-button" data-retry-run="${run.id}">正式重试</button>`);if(run.artifact_available)actions.push(`<button class="text-button" data-log="${run.id}">日志</button>`);if(!["queued","running"].includes(run.status)&&run.artifact_available)actions.push(`<button class="text-button" data-evidence="${run.id}">证据</button>`);if(!["queued","running"].includes(run.status))actions.push(`<button class="text-button" data-review="${run.id}">复核${run.reviews.length?` (${run.reviews.length})`:""}</button>`);return actions.join("");}
function renderTimeline(run){const events=state.runEvents[run.id]||[];if(!run.tracking_available&&!events.length)return '<p class="legacy-note">此 run 创建于阶段追踪功能之前，没有可用的阶段时间线。</p>';const lastHeartbeat=events.findLastIndex(event=>event.kind==="heartbeat");const visible=events.filter((event,index)=>event.kind!=="heartbeat"||index===lastHeartbeat);return `<ol class="timeline">${visible.map(event=>`<li class="${event.kind}"><time>${fmtTime(event.created_at)}</time><div><strong>${escapeHtml(stageLabel(event.stage))}</strong><span>${escapeHtml(event.message)}</span>${event.attempt>1?`<small>重试 #${event.attempt}</small>`:""}</div></li>`).join("")||'<li><div><span>正在等待首个阶段事件…</span></div></li>'}</ol>`;}
function stallDiagnosis(item,run){
  if(!run.stalled)return "";
  const provider=run.current_stage==="judge"?item.profile.judge.provider:item.profile.runner.provider;
  const alive=run.heartbeat_age_seconds!=null&&run.heartbeat_age_seconds<45;
  const output=run.output_bytes||{},stdout=output.stdout||0,stderr=output.stderr||0;
  const outputNote=stdout+stderr===0?"stdout/stderr 均为 0 字节":`stdout ${stdout} 字节 · stderr ${stderr} 字节`;
  const timeout=item.profile_config?.timeout_seconds;
  const limit=timeout&&["runner","judge"].includes(run.current_stage)?`当前阶段 ${fmtDuration(elapsedSince(run.stage_started_at))} · 单轮无活动超时上限 ${fmtDuration(timeout)}（持续有活动不会被中断）`:"";
  return `<div class="stall-diagnostic"><strong>${providerName(provider)} ${alive?"静默等待":"心跳已中断"}</strong><span>最近 ${fmtDuration(run.activity_age_seconds)} 没有新的输出或阶段进展；${outputNote}。</span>${limit?`<span>${limit}</span>`:""}<span>无法判断 CLI 内部阶段；可查看调用记录和原始流，必要时复制诊断或取消后重试。</span></div>`;
}
function renderScoreBreakdown(run){
  const components=run.scores?.components;
  if(!Array.isArray(components)||!components.length)return "";
  const rows=components.map(comp=>{
    const isRubric=comp.grader_type==="llm_rubric";
    const isGate=!!comp.hard_gate;
    const tag=isRubric?`LLM 评分 · 权重 ${comp.weight??"—"}`:isGate?"硬门禁（必须通过）":`命令验证器 · 权重 ${comp.weight??"—"}`;
    const value=isRubric?fmtScore(comp.score):(comp.passed?"通过":"未通过");
    const cls=comp.passed===false?"bad":comp.passed===true?"ok":"";
    return `<details class="score-component"><summary><span class="comp-name">${escapeHtml(comp.name||comp.grader_id)}</span><span class="comp-tag">${escapeHtml(tag)}</span><span class="comp-value ${cls}">${escapeHtml(String(value))}</span></summary><div class="comp-body">${comp.reasoning?`<p><strong>评分理由：</strong>${escapeHtml(comp.reasoning)}</p>`:""}${comp.evidence?`<pre>${escapeHtml(comp.evidence)}</pre>`:""}</div></details>`;
  }).join("");
  const gates=run.hard_gates||{};
  const loaded=Array.isArray(run.scores?.skills_loaded)?run.scores.skills_loaded.filter(Boolean):[];
  const isNoSkill=run.group==="no_skill";
  const loadedNote=loaded.length
    ?`<span class="skills-loaded ${isNoSkill?"warn":""}">${isNoSkill?"⚠ 对照组 Agent 加载了技能":"Agent 加载的技能"}：${escapeHtml(loaded.join("、"))}${isNoSkill?"——基线可能被全局技能污染，解读对比结论时请知悉":""}</span>`
    :"";
  return `<div class="score-breakdown"><div class="score-breakdown-head"><strong>评分构成（${components.length} 项）</strong><span class="comp-total">总分 ${fmtScore(run.quality_score)} · 硬门禁 ${gates.passed??0}/${gates.total??0}</span>${loadedNote}<span class="evidence-links"><button class="text-button" data-artifact-run="${run.id}" data-artifact="scores.json">scores.json</button><button class="text-button" data-artifact-run="${run.id}" data-artifact="changes.patch">改动 patch</button><button class="text-button" data-artifact-run="${run.id}" data-artifact="final-response.md">最终回复</button></span></div>${rows}</div>`;
}
function renderRun(item,run){
  run={...run,error_message:errorText(run.error_message)};
  const defaultOpen=run.status==="running"||run.stalled||!["queued","completed","cancelled"].includes(run.status),open=state.expandedRuns[run.id]??defaultOpen;
  const totalSeconds=run.completed_at&&run.started_at?(new Date(run.completed_at)-new Date(run.started_at))/1000:elapsedSince(run.started_at);
  const stageSeconds=run.status==="running"?elapsedSince(run.stage_started_at):null;
  const scoringSkipped=!["queued","running","completed"].includes(run.status)&&run.quality_score==null;
  const logs=state.runLogs[run.id];
  return `<article class="run-card ${run.stalled?"is-stalled":""}" data-run-card="${run.id}"><div class="run-summary"><div><span class="run-order">${escapeHtml(run.group)} · Trial ${run.trial}${run.current_attempt>1?` · 重试 #${run.current_attempt}`:""}</span><h3>${escapeHtml(run.case_id)}</h3></div><div class="run-stage"><span class="pill ${run.status}">${escapeHtml(experimentStatusLabel(run.status))}</span><strong>${escapeHtml(stageLabel(run.current_stage))}</strong>${scoringSkipped?'<span class="skip-badge" title="Runner 未完成，验证器与 Judge 未执行">评分已跳过</span>':""}</div><div class="run-clocks"><span>总耗时 ${fmtDuration(totalSeconds)}</span>${stageSeconds!=null?`<span>当前阶段 ${fmtDuration(stageSeconds)}</span>`:""}<span>心跳 ${fmtDuration(run.heartbeat_age_seconds)} 前</span><span class="${run.stalled?"warn":""}">有效活动 ${fmtDuration(run.activity_age_seconds)} 前</span></div><div class="run-actions">${runActions(item,run)}<button class="text-button" data-toggle-run="${run.id}">${open?"收起":"时间线"}</button></div></div><div class="run-detail ${open?"":"hidden"}" id="run-detail-${run.id}">${run.error_message?`<div class="message error"><strong>${escapeHtml(stageLabel(run.current_stage))}</strong> · ${escapeHtml(run.error_kind||"error")} · ${escapeHtml(run.error_message)}</div>`:""}${scoringSkipped?`<div class="skip-note">评分已跳过：Runner 未完成（${escapeHtml(experimentStatusLabel(run.status))}），确定性验证器、自动分与 Judge 盲评均未执行，因此分数显示为 “—”。如需评分请重试该 run。</div>`:""}${renderScoreBreakdown(run)}${stallDiagnosis(item,run)}${run.attempts.length?`<p class="attempt-history">历史尝试：${run.attempts.map(attempt=>`#${attempt.attempt} ${escapeHtml(experimentStatusLabel(attempt.status))}`).join(" · ")}</p>`:""}${renderTimeline(run)}${logs?`<div class="log-panel">${logs.items.map(log=>`<h4>${escapeHtml(log.name)}</h4><pre>${escapeHtml(log.content)}</pre>`).join("")||'<p>暂无日志输出。</p>'}</div>`:""}</div></article>`;
}
function bindDetailActions(item){const id=item.id;$$('[data-toggle-run]').forEach(button=>button.addEventListener("click",()=>{const runId=button.dataset.toggleRun;state.expandedRuns[runId]=!(state.expandedRuns[runId]??false);renderDetail(state.detail);if(state.expandedRuns[runId])loadRunEvents(runId);}));$$('[data-evidence]').forEach(button=>button.addEventListener("click",()=>showEvidence(button.dataset.evidence)));$$('[data-artifact]').forEach(button=>button.addEventListener("click",()=>openArtifact(button.dataset.artifactRun,button.dataset.artifact)));$$('[data-review]').forEach(button=>button.addEventListener("click",()=>addReview(id,button.dataset.review)));$$('[data-cancel-run]').forEach(button=>button.addEventListener("click",()=>cancelRun(button.dataset.cancelRun)));$$('[data-retry-run]').forEach(button=>button.addEventListener("click",()=>retryRun(button.dataset.retryRun)));$$('[data-log]').forEach(button=>button.addEventListener("click",()=>loadRunLogs(button.dataset.log)));const cancel=$("#cancelExperimentButton");if(cancel)cancel.addEventListener("click",()=>cancelExperiment(id));const baseline=$("#setBaselineButton");if(baseline)baseline.addEventListener("click",()=>setBaseline(item));}
function renderDetail(item){state.detail=item;$("#detailTitle").textContent=item.suite_name;const p=item.profile,active=["queued","preparing","running"].includes(item.status);$("#detailBody").innerHTML=`<div class="detail-toolbar"><div class="experiment-meta"><span class="pill ${item.status}">${escapeHtml(experimentStatusLabel(item.status))}</span><span>commit ${escapeHtml(item.project_commit.slice(0,10))}</span><span>${providerName(p.runner.provider)} ${escapeHtml(modelName(p.runner))} → ${providerName(p.judge.provider)} ${escapeHtml(modelName(p.judge))}</span>${p.self_judge?'<span class="self-judge">Self-judge</span>':""}</div>${active?'<button class="button button-ghost button-small danger" id="cancelExperimentButton">取消整个实验</button>':""}</div><div class="profile-strip"><span>Runner 隔离：${escapeHtml(p.runner.isolation)}</span><span>网络：${escapeHtml(p.runner.network_policy)}</span><span>Profile ${escapeHtml(p.hash.slice(0,10))}</span></div><div class="detail-scores"><div class="detail-score"><small>无 Skill</small><strong>${fmtScore(item.scores.no_skill)}</strong></div><div class="detail-score"><small>上一基准</small><strong>${fmtScore(item.scores.baseline)}</strong></div><div class="detail-score"><small>当前候选</small><strong>${fmtScore(item.scores.current)}</strong></div></div><p>当前 vs 无 Skill：${fmtDelta(item.delta_no_skill)}　 当前 vs 基准：${fmtDelta(item.delta_baseline)}</p>${item.error_message?`<div class="message error">${escapeHtml(item.error_message)}</div>`:""}<div class="run-grid">${item.runs.map(run=>renderRun(item,run)).join("")||'<div class="empty">正在准备运行列表…</div>'}</div>${item.status==="completed"?'<button class="button button-ghost" id="setBaselineButton">将当前修订设为基准版本</button>':""}`;bindDetailActions(item);}
async function loadRunEvents(runId){try{const after=state.eventCursors[runId]||0,result=await api(`/api/v1/runs/${runId}/events?after=${after}`);state.runEvents[runId]=[...(state.runEvents[runId]||[]),...result.items];if(result.items.length)state.eventCursors[runId]=result.items.at(-1).id;if(state.detail)renderDetail(state.detail);}catch(error){toast(error.message);}}
async function refreshDetail(){if(!state.detail)return;try{const item=await api(`/api/v1/experiments/${state.detail.id}`);state.detail=item;await Promise.all(item.runs.filter(run=>run.status==="running"||run.stalled||!["queued","completed","cancelled"].includes(run.status)).map(run=>loadRunEvents(run.id)));renderDetail(item);if(!["queued","preparing","running"].includes(item.status)){clearInterval(state.detailPoller);state.detailPoller=null;}}catch(error){toast(error.message);}}
async function showDetail(id){try{const item=await api(`/api/v1/experiments/${id}`);state.runEvents={};state.eventCursors={};state.runLogs={};state.expandedRuns={};item.runs.forEach(run=>{if(run.status==="running"||run.stalled||!["queued","completed","cancelled"].includes(run.status))state.expandedRuns[run.id]=true;});renderDetail(item);if(!$("#detailModal").open)$("#detailModal").showModal();await Promise.all(item.runs.filter(run=>state.expandedRuns[run.id]).map(run=>loadRunEvents(run.id)));if(state.detailPoller)clearInterval(state.detailPoller);if(["queued","preparing","running"].includes(item.status))state.detailPoller=setInterval(refreshDetail,2000);}catch(error){toast(error.message);}}
async function cancelRun(runId){if(!window.confirm("取消当前 run，并继续执行其余 run？"))return;try{await api(`/api/v1/runs/${runId}/cancel`,{method:"POST"});toast("已请求取消 run");await refreshDetail();}catch(error){toast(error.message);}}
async function cancelExperiment(id){if(!window.confirm("取消整个实验及所有未运行的 run？"))return;try{await api(`/api/v1/experiments/${id}/cancel`,{method:"POST"});toast("已请求取消实验");await refreshDetail();}catch(error){toast(error.message);}}
async function retryRun(runId){if(!window.confirm("对这个基础设施失败执行一次正式重试？原失败记录会保留。"))return;try{await api(`/api/v1/runs/${runId}/retry`,{method:"POST"});toast("正式重试已加入队列");await refreshDetail();}catch(error){toast(error.message);}}
async function retryExperiment(experimentId) {
  if (state.retryingExperiments.has(experimentId)) return;
  if (!window.confirm("将使用这条实验记录的固定版本和配置创建一次完整重跑；如果原实验仍在运行，会先请求取消。继续？")) return;
  state.retryingExperiments.add(experimentId);
  renderExperiments();
  if (state.detail?.id === experimentId) renderDetail(state.detail);
  try {
    const result = await api(`/api/v1/experiments/${experimentId}/retry`, {method:"POST"});
    upsertExperiment(result.experiment);
    toast(`重试实验 ${result.id.slice(0,8)} 已加入队列`);
    refreshExperiments().catch(() => toast("实验已入队，列表刷新失败"));
    if (state.detail?.id === experimentId) await refreshDetail();
  } catch (error) {
    toast(error.message);
  } finally {
    state.retryingExperiments.delete(experimentId);
    renderExperiments();
    if (state.detail?.id === experimentId) renderDetail(state.detail);
  }
}
async function loadRunLogs(runId){try{state.runLogs[runId]=await api(`/api/v1/runs/${runId}/logs?tail=300`);if(state.detail)renderDetail(state.detail);}catch(error){toast(error.message);}}
async function setBaseline(item){try{await api(`/api/v1/skills/${item.skill_id}/baseline`,{method:"POST",body:JSON.stringify({revision_id:item.current_revision_id})});toast("已设为基准版本");try{await loadAll();}catch{toast("基准已保存，但页面刷新失败");}}catch(error){toast(error.message);}}
async function showEvidence(runId){try{const result=await api(`/api/v1/runs/${runId}/artifacts`);if(!result.items.length)return toast("这个 run 暂无证据文件");const preferred=result.items.find(item=>item.name==="scores.json")||result.items[0];window.open(preferred.url,"_blank","noopener");}catch(error){toast(error.message);}}
async function openArtifact(runId,name){try{const result=await api(`/api/v1/runs/${runId}/artifacts`);const item=result.items.find(entry=>entry.name===name);if(!item)return toast(`该 run 没有 ${name}（可能未产生该证据文件）`);window.open(item.url,"_blank","noopener");}catch(error){toast(error.message);}}

const LOG_CURSOR_CACHE_KEY = "aaw-skill-eval.log-cursors.v1";
const MAX_BROWSER_LOG_RECORDS = 5000;

function activeRun(item) {
  const activeId = item.progress?.active_run_id;
  return item.runs.find(run => run.id === activeId)
    || item.runs.find(run => run.status === "running")
    || null;
}

function readLogCursors() {
  try { return JSON.parse(sessionStorage.getItem(LOG_CURSOR_CACHE_KEY) || "{}"); } catch { return {}; }
}

function persistLogCursors() {
  if (!state.logConsole) return;
  const cursors = readLogCursors();
  Object.entries(state.logConsole.streams).forEach(([key, stream]) => {
    if (stream.cursor) cursors[key] = stream.cursor;
  });
  try { sessionStorage.setItem(LOG_CURSOR_CACHE_KEY, JSON.stringify(cursors)); } catch {}
}

function logStreamKey(consoleState = state.logConsole) {
  if (!consoleState) return "";
  return consoleState.scope === "experiment"
    ? `experiment:${consoleState.experimentId}`
    : `run:${consoleState.runId}:attempt:${consoleState.attempt}`;
}

function currentLogStream() {
  const consoleState = state.logConsole;
  if (!consoleState) return null;
  const key = logStreamKey(consoleState);
  if (!consoleState.streams[key]) {
    consoleState.streams[key] = {
      cursor: null,
      records: [],
      invocationRecords: [],
      files: [],
      selectedFile: "",
      preview: null,
      previewLoading: false,
      previewError: "",
      lastPreviewAt: 0,
      lastFilesCheck: 0,
      historical: false,
      pending: false,
      resetNotice: "",
      promptPreview: null,
      promptPreviewId: null,
    };
  }
  return consoleState.streams[key];
}

function ensureLogConsole(item, {fresh = false} = {}) {
  if (fresh || !state.logConsole || state.logConsole.experimentId !== item.id) {
    state.logConsole = {
      experimentId: item.id,
      scope: "experiment",
      runId: null,
      attempt: null,
      pinned: false,
      mode: "raw",
      unmasked: false,
      channel: "",
      keyword: "",
      paused: false,
      atBottom: true,
      scrollTop: 0,
      newLines: 0,
      loading: false,
      streams: {},
    };
  }
  syncLogSelection(item);
}

function syncLogSelection(item) {
  const consoleState = state.logConsole;
  if (!consoleState || consoleState.pinned) return;
  const run = activeRun(item);
  if (run) {
    consoleState.scope = "run";
    consoleState.runId = run.id;
    consoleState.attempt = run.current_attempt;
  } else {
    consoleState.scope = "experiment";
    consoleState.runId = null;
    consoleState.attempt = null;
  }
}

function selectedRun(item = state.detail) {
  if (!item || state.logConsole?.scope !== "run") return null;
  return item.runs.find(run => run.id === state.logConsole.runId) || null;
}

function selectedAttempts(run) {
  if (!run) return [];
  return [...new Set([...(run.attempts || []).map(item => item.attempt), run.current_attempt])].sort((a, b) => a - b);
}

function selectExperimentLog({pin = true} = {}) {
  const consoleState = state.logConsole;
  if (!consoleState) return;
  consoleState.scope = "experiment";
  consoleState.runId = null;
  consoleState.attempt = null;
  consoleState.pinned = pin;
  consoleState.newLines = 0;
  renderLogConsoleOnly();
  loadSelectedLogFiles();
  fetchSelectedLog();
}

function selectRunLog(runId, {attempt = null, pin = true} = {}) {
  const item = state.detail;
  const run = item?.runs.find(candidate => candidate.id === runId);
  if (!run || !state.logConsole) return;
  state.logConsole.scope = "run";
  state.logConsole.runId = runId;
  state.logConsole.attempt = attempt || run.current_attempt;
  state.logConsole.pinned = pin;
  state.logConsole.newLines = 0;
  renderLogConsoleOnly();
  loadSelectedLogFiles();
  fetchSelectedLog();
}

function followCurrentLog() {
  if (!state.detail || !state.logConsole) return;
  state.logConsole.pinned = false;
  syncLogSelection(state.detail);
  state.logConsole.newLines = 0;
  renderLogConsoleOnly();
  loadSelectedLogFiles();
  fetchSelectedLog();
}

function resetSelectedLog() {
  const stream = currentLogStream();
  if (!stream) return;
  stream.cursor = null;
  stream.records = [];
  stream.invocationRecords = [];
  stream.historical = false;
  stream.pending = false;
  stream.resetNotice = "";
}

function selectedLogUrl() {
  const consoleState = state.logConsole;
  if (consoleState.scope === "experiment") return `/api/v1/experiments/${consoleState.experimentId}/logs`;
  return `/api/v1/runs/${consoleState.runId}/logs?attempt=${consoleState.attempt}`;
}

function selectedLogFilesUrl() {
  const consoleState = state.logConsole;
  if (consoleState.scope === "experiment") return `/api/v1/experiments/${consoleState.experimentId}/log-files`;
  return `/api/v1/runs/${consoleState.runId}/log-files?attempt=${consoleState.attempt}`;
}

function appendLogRecords(stream, records) {
  const known = new Set(stream.records.map(record => `${record.sequence}:${record.timestamp}`));
  const additions = records.filter(record => {
    const key = `${record.sequence}:${record.timestamp}`;
    if (known.has(key)) return false;
    known.add(key);
    return true;
  });
  stream.records.push(...additions);
  stream.invocationRecords.push(...additions.filter(record => record.channel === "invocation"));
  if (stream.records.length > MAX_BROWSER_LOG_RECORDS) {
    stream.records.splice(0, stream.records.length - MAX_BROWSER_LOG_RECORDS);
  }
  return additions.length;
}

async function fetchSelectedLog({reset = false} = {}) {
  const consoleState = state.logConsole;
  if (!consoleState || consoleState.paused || consoleState.loading) return;
  const stream = currentLogStream();
  if (!stream) return;
  if (reset) resetSelectedLog();
  consoleState.loading = true;
  try {
    const separator = selectedLogUrl().includes("?") ? "&" : "?";
    const parameters = new URLSearchParams({mode: consoleState.mode, limit_bytes: "262144"});
    if (stream.cursor) parameters.set("cursor", stream.cursor);
    if (consoleState.mode === "raw" && consoleState.unmasked) parameters.set("unmasked", "true");
    const result = await api(`${selectedLogUrl()}${separator}${parameters.toString()}`);
    const wasAtBottom = consoleState.atBottom;
    if (result.reset_required) {
      stream.records = [];
      stream.invocationRecords = [];
      stream.resetNotice = "日志源已重新打开，已从安全位置继续读取。";
    }
    const added = appendLogRecords(stream, result.records || []);
    stream.cursor = result.next_cursor || stream.cursor;
    stream.historical = Boolean(result.historical);
    stream.pending = Boolean(result.pending);
    persistLogCursors();
    if (!wasAtBottom && added) consoleState.newLines += added;
    if (state.logConsole === consoleState && currentLogStream() === stream) {
      updateLogOutput();
      if (Date.now() - stream.lastFilesCheck > 5000) loadSelectedLogFiles();
      if (stream.selectedFile && Date.now() - stream.lastPreviewAt > 3000) fetchFilePreview();
    }
  } catch (error) {
    toast(`日志读取失败：${error.message}`);
  } finally {
    if (state.logConsole) state.logConsole.loading = false;
  }
}

async function loadSelectedLogFiles() {
  const consoleState = state.logConsole;
  if (!consoleState) return;
  const stream = currentLogStream();
  if (!stream) return;
  try {
    const result = await api(selectedLogFilesUrl());
    const files = result.items || [];
    const changed = files.map(file => file.url).join("\n") !== stream.files.map(file => file.url).join("\n");
    stream.files = files;
    stream.lastFilesCheck = Date.now();
    if (stream.selectedFile && !files.some(file => file.url === stream.selectedFile)) {
      stream.selectedFile = "";
      stream.preview = null;
    }
    if (changed && state.logConsole === consoleState && currentLogStream() === stream) renderLogConsoleOnly();
  } catch (error) {
    toast(`日志文件读取失败：${error.message}`);
  }
}

async function fetchFilePreview() {
  const consoleState = state.logConsole, stream = currentLogStream();
  if (!consoleState || !stream?.selectedFile || stream.previewLoading) return;
  const fileUrl = stream.selectedFile;
  stream.previewLoading = true;
  stream.previewError = "";
  stream.lastPreviewAt = Date.now();
  updateLogOutput();
  try {
    const url = new URL(fileUrl, window.location.origin);
    url.searchParams.set("preview", "true");
    if (consoleState.unmasked) url.searchParams.set("unmasked", "true");
    const preview = await api(`${url.pathname}${url.search}`);
    if (state.logConsole === consoleState && currentLogStream() === stream && stream.selectedFile === fileUrl) {
      stream.preview = preview;
      updateLogOutput();
    }
  } catch (error) {
    stream.previewError = error.message;
    updateLogOutput();
    toast(`文件预览失败：${error.message}`);
  } finally {
    stream.previewLoading = false;
  }
}

function visibleLogRecords() {
  const consoleState = state.logConsole;
  const stream = currentLogStream();
  if (!consoleState || !stream) return [];
  const keyword = consoleState.keyword.trim().toLocaleLowerCase();
  return stream.records.filter(record => {
    if (consoleState.channel && record.channel !== consoleState.channel) return false;
    return !keyword || `${record.source} ${record.channel} ${record.text}`.toLocaleLowerCase().includes(keyword);
  });
}

function logLine(record) {
  const tag = `${record.source || "system"}/${record.channel || "event"}`;
  const partial = record.partial ? " · partial" : "";
  return `[${fmtTime(record.timestamp)}] [${tag}${partial}] ${record.text}`;
}

function responseText(value) {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map(responseText).filter(Boolean).join("\n");
  if (!value || typeof value !== "object") return "";
  if (value.type === "agent_message" || value.role === "assistant") return responseText(value.content || value.text);
  for (const key of ["item", "delta", "final_response", "response", "output", "result", "message", "content", "text"]) {
    const found = responseText(value[key]);
    if (found) return found;
  }
  return "";
}

function readableLogText(records) {
  const lines = [], pending = {};
  const add = (record, value) => {
    if (!value.trim()) return;
    let readable = value;
    try {
      const parsed = JSON.parse(value);
      readable = responseText(parsed) || [parsed.type, parsed.item?.type].filter(Boolean).join(" · ") || value;
    } catch {
      if (/^\s*[\[{]/.test(value)) return;
    }
    lines.push(`[${fmtTime(record.timestamp)}] [${record.source || "system"}] ${readable}`);
  };
  records.forEach(record => {
    if (record.channel === "invocation") {
      const event = record.details;
      if (event) lines.push(`[${fmtTime(record.timestamp)}] [${event.source}] ${event.phase === "start" ? `启动 PID ${event.pid}` : event.phase === "end" ? `退出码 ${event.exit_code} · ${fmtDuration(event.duration_ms / 1000)}` : `启动失败：${event.error}`}`);
      if (event?.phase === "end") {
        Object.entries(pending).forEach(([key, value]) => {
          add({source: key, timestamp: record.timestamp}, value);
          delete pending[key];
        });
      }
    } else if (record.channel === "stdout") {
      const key = record.source || "agent";
      pending[key] = (pending[key] || "") + record.text;
      const parts = pending[key].split("\n");
      pending[key] = parts.pop();
      parts.forEach(part => add(record, part));
    } else if (record.channel === "stderr" || record.channel === "event" || record.channel === "acp") {
      add(record, record.text);
    }
  });
  Object.entries(pending).forEach(([source, value]) => {
    if (!value.trim()) return;
    add({source, timestamp: new Date().toISOString()}, value);
  });
  return lines.join("\n") || "尚无 Agent 响应。";
}

function logInvocations() {
  const events = currentLogStream()?.invocationRecords.filter(record => record.details) || [];
  const byId = new Map();
  events.forEach(record => {
    const value = record.details;
    byId.set(value.id, {...(byId.get(value.id) || {}), ...value});
  });
  return [...byId.values()];
}

function invocationStatus() {
  const run = selectedRun();
  const invocations = logInvocations();
  const last = invocations.at(-1);
  if (!run || !last) return "尚无 Agent 调用记录。";
  if (last.phase === "spawn_error") return `启动失败 · ${last.error || "未知错误"}`;
  if (last.phase !== "start") return `${last.source} 已退出 · PID ${last.pid || "—"} · 退出码 ${last.exit_code ?? "—"} · 用时 ${fmtDuration((last.duration_ms || 0) / 1000)}`;
  if (run.status !== "running") return `调用记录未收到结束事件 · run 状态 ${experimentStatusLabel(run.status)} · 进程状态未知`;
  const age = Math.max(0, Math.floor((Date.now() - new Date(last.started_at).getTime()) / 1000));
  const recentOutput = currentLogStream().records.filter(record => ["stdout", "stderr", "acp"].includes(record.channel)).at(-1);
  const silent = Math.max(0, Math.floor((Date.now() - new Date(recentOutput?.timestamp || last.started_at).getTime()) / 1000));
  const heartbeat = run.heartbeat_age_seconds;
  const stateLabel = heartbeat == null ? "心跳未知" : heartbeat >= 45 ? "心跳中断" : silent >= 120 ? "静默等待" : "运行中";
  return `${stateLabel} · PID ${last.pid} · 已运行 ${fmtDuration(age)} · ${fmtDuration(silent)} 无输出 · 心跳 ${heartbeat == null ? "未知" : `${fmtDuration(heartbeat)} 前`} · 无活动超时 ${fmtDuration(last.timeout_seconds)}${stateLabel === "静默等待" ? " · 无法判断 CLI 内部阶段" : ""}`;
}

function invocationMarkup() {
  const stream = currentLogStream();
  const invocations = logInvocations();
  return invocations.map((entry, index) => `<div class="log-invocation">
    <div class="log-invocation-head"><strong>${escapeHtml(entry.source)} · 调用 ${index + 1} · ${entry.phase === "start" ? "运行中" : entry.phase === "end" ? `退出码 ${entry.exit_code ?? "—"}` : "启动失败"}</strong><span>PID ${escapeHtml(entry.pid ?? "—")} · ${escapeHtml(entry.started_at || "")} ${entry.ended_at ? `→ ${escapeHtml(entry.ended_at)}` : ""}</span></div>
    <div class="log-invocation-path">目录：${escapeHtml(entry.cwd || "")}</div>
    <pre class="log-command">${escapeHtml(entry.command || "")}</pre>
    <div class="log-invocation-actions"><button class="text-button" data-copy-command="${escapeHtml(entry.id)}">复制命令</button>${entry.prompt_file ? `<button class="text-button" data-preview-prompt="${escapeHtml(entry.id)}">${stream.promptPreviewId === entry.id ? "收起提示词" : "预览提示词"}</button>` : ""}</div>
    ${stream.promptPreviewId === entry.id ? `<pre class="log-prompt-preview">${escapeHtml(stream.promptPreview?.content || "正在读取提示词…")}</pre>` : ""}
  </div>`).join("") || '<p class="log-note">新测评启动后，这里会显示每次 Agent 调用。</p>';
}

function logPresentation() {
  const stream = currentLogStream(), consoleState = state.logConsole;
  if (!stream || !consoleState) return {content: "", count: "", note: ""};
  if (stream.selectedFile) {
    const preview = stream.preview;
    return {
      content: preview ? (preview.content || "文件为空。") : stream.previewError || "正在读取文件…",
      count: preview ? `${(preview.size / 1024).toFixed(1)} KiB` : "文件",
      note: preview?.truncated ? "文件较大，当前显示末尾 256 KiB。" : "",
    };
  }
  const visible = visibleLogRecords();
  return {
    content: visible.length ? visible.map(logLine).join("\n") : "暂无可显示的日志。",
    count: `${visible.length}/${stream.records.length} 条`,
    note: stream.pending
      ? "该 run 尚未开始，日志会在启动后自动出现。"
      : stream.historical
        ? "历史实验没有统一实时日志索引；可查看仍可用的原始输出文件。"
        : stream.resetNotice,
  };
}

function updateLogOutput() {
  const output = $("#liveLogOutput"), readable = $("#readableLogOutput"), count = $("#logCount"), note = $("#logNote");
  if (!output || !count || !note) return;
  const presentation = logPresentation();
  const visible = visibleLogRecords();
  const newLines = $("#logNewLines");
  count.textContent = presentation.count;
  note.textContent = presentation.note;
  note.classList.toggle("hidden", !presentation.note);
  if (newLines) {
    newLines.textContent = `有 ${state.logConsole.newLines} 条新日志，回到底部`;
    newLines.classList.toggle("hidden", !state.logConsole.newLines);
  }
  if (output.textContent !== presentation.content) {
    output.textContent = presentation.content;
    restoreLogScroll();
  }
  if (readable) {
    const content = currentLogStream()?.selectedFile ? presentation.content : readableLogText(visible);
    if (readable.textContent !== content) readable.textContent = content;
  }
  const status = $("#logProcessStatus");
  if (status) status.textContent = invocationStatus();
  const calls = $("#logInvocations");
  if (calls) {
    const markup = invocationMarkup();
    if (calls.innerHTML !== markup) {
      calls.innerHTML = markup;
      bindInvocationActions();
    }
  }
}

function renderLogConsole(item) {
  const consoleState = state.logConsole;
  const stream = currentLogStream();
  if (!consoleState || !stream) return "";
  const run = selectedRun(item);
  const attempts = selectedAttempts(run);
  const files = stream.files || [];
  const presentation = logPresentation();
  const runTabs = item.runs.map(candidate => {
    const selected = consoleState.scope === "run" && candidate.id === consoleState.runId;
    return `<button class="log-tab ${selected ? "active" : ""}" data-log-run="${candidate.id}">${escapeHtml(candidate.group)} · T${candidate.trial}${candidate.current_attempt > 1 ? ` · #${candidate.current_attempt}` : ""}</button>`;
  }).join("");
  return `<section class="live-log-console" id="liveLogConsole">
    <div class="live-log-head"><div><p class="eyebrow">LIVE LOGS</p><h3>实时日志控制台</h3></div><span class="log-count" id="logCount">${escapeHtml(presentation.count)}</span></div>
    <div class="log-tabs"><button class="log-tab ${consoleState.scope === "experiment" ? "active" : ""}" data-log-scope="experiment">实验日志</button>${runTabs}</div>
    <div class="log-controls">
      ${run ? `<label>尝试<select id="logAttempt">${attempts.map(value => `<option value="${value}"${value === consoleState.attempt ? " selected" : ""}>尝试 #${value}</option>`).join("")}</select></label>` : ""}
      <label>通道<select id="logChannel"${stream.selectedFile ? " disabled" : ""}><option value="">全部通道</option><option value="event"${consoleState.channel === "event" ? " selected" : ""}>系统事件</option><option value="invocation"${consoleState.channel === "invocation" ? " selected" : ""}>调用</option><option value="acp"${consoleState.channel === "acp" ? " selected" : ""}>Agent 流（ACP）</option><option value="stdout"${consoleState.channel === "stdout" ? " selected" : ""}>stdout</option><option value="stderr"${consoleState.channel === "stderr" ? " selected" : ""}>stderr</option></select></label>
      <label class="log-search">搜索<input id="logSearch" value="${escapeHtml(consoleState.keyword)}" placeholder="关键词"${stream.selectedFile ? " disabled" : ""}></label>
      <button class="text-button" id="logPause">${consoleState.paused ? "继续" : "暂停"}</button>
      <button class="text-button" id="logFollow">跟随当前 run</button>
      <button class="text-button" id="logCopy">复制可见内容</button>
      ${run ? '<button class="text-button" id="logCopyDiagnostics">复制诊断</button>' : ""}
      ${run?.status === "running" ? '<button class="text-button danger" id="logCancelRun">取消当前 run</button>' : ""}
      ${run && item.status !== "running" ? `<button class="text-button" data-retry-experiment="${item.id}">重试实验</button>` : ""}
      ${stream.selectedFile ? "" : '<button class="text-button" id="logClear">清空显示</button>'}
      ${files.length ? `<label class="log-file-select">查看文件<select id="logFile"><option value="">实时日志</option>${files.map(file => `<option value="${escapeHtml(file.url)}"${file.url === stream.selectedFile ? " selected" : ""}>${escapeHtml(file.name)}</option>`).join("")}</select></label>${stream.selectedFile ? '<button class="text-button" id="logDownloadButton">下载</button>' : ""}` : ""}
    </div>
    <label class="log-sensitive"><input type="checkbox" id="logUnmasked"${consoleState.unmasked ? " checked" : ""}> 显示未遮盖内容（可能包含敏感信息）</label>
    ${run ? `<p class="log-process-status" id="logProcessStatus">${escapeHtml(invocationStatus())}</p>` : ""}
    ${run ? `<details class="log-invocations"${run.status === "running" ? " open" : ""}><summary>Agent 调用记录 · ${logInvocations().length}</summary><div id="logInvocations">${invocationMarkup()}</div></details>` : ""}
    <p class="legacy-note log-note ${presentation.note ? "" : "hidden"}" id="logNote">${escapeHtml(presentation.note)}</p>
    ${stream.selectedFile ? "" : `<button class="log-new-lines ${consoleState.newLines ? "" : "hidden"}" id="logNewLines">有 ${consoleState.newLines} 条新日志，回到底部</button>`}
    <div class="log-output-grid"><div><h4>可读响应</h4><pre class="live-log-output" id="readableLogOutput" tabindex="0">${escapeHtml(stream.selectedFile ? presentation.content : readableLogText(visibleLogRecords()))}</pre></div><div><h4>原始流</h4><pre class="live-log-output" id="liveLogOutput" tabindex="0">${escapeHtml(presentation.content)}</pre></div></div>
  </section>`;
}

function restoreLogScroll() {
  const output = $("#liveLogOutput");
  const readable = $("#readableLogOutput");
  const consoleState = state.logConsole;
  if (!output || !consoleState) return;
  requestAnimationFrame(() => {
    output.scrollTop = consoleState.atBottom ? output.scrollHeight : consoleState.scrollTop;
    if (readable && consoleState.atBottom) readable.scrollTop = readable.scrollHeight;
  });
}

function renderLogConsoleOnly() {
  const node = $("#liveLogConsole");
  if (!node || !state.detail) return;
  node.outerHTML = renderLogConsole(state.detail);
  bindLogConsole();
  restoreLogScroll();
}

async function copyVisibleLogs() {
  const text = currentLogStream()?.selectedFile
    ? currentLogStream().preview?.content || ""
    : visibleLogRecords().map(logLine).join("\n");
  if (!text) return toast("没有可复制的日志");
  try {
    await navigator.clipboard.writeText(text);
    toast("已复制可见日志");
  } catch {
    toast("浏览器未允许复制，请手动选择日志内容");
  }
}

async function copyDiagnostics() {
  const consoleState = state.logConsole;
  if (!consoleState?.runId) return;
  try {
    const result = await api(`/api/v1/runs/${consoleState.runId}/diagnostics?attempt=${consoleState.attempt}`);
    await navigator.clipboard.writeText(JSON.stringify(result, null, 2));
    toast("已复制遮盖敏感值的诊断信息");
  } catch (error) { toast(`复制诊断失败：${error.message}`); }
}

async function previewInvocationPrompt(id) {
  const stream = currentLogStream();
  const entry = logInvocations().find(item => item.id === id);
  if (!stream || !entry?.prompt_file) return;
  if (stream.promptPreviewId === id) {
    stream.promptPreviewId = null;
    stream.promptPreview = null;
    updateLogOutput();
    return;
  }
  stream.promptPreviewId = id;
  stream.promptPreview = null;
  updateLogOutput();
  try {
    const base = selectedLogFilesUrl().split("?")[0];
    const path = entry.prompt_file.split("/").map(encodeURIComponent).join("/");
    const url = new URL(`${base}/${path}`, window.location.origin);
    url.searchParams.set("preview", "true");
    if (state.logConsole.attempt != null) url.searchParams.set("attempt", state.logConsole.attempt);
    if (state.logConsole.unmasked) url.searchParams.set("unmasked", "true");
    const result = await api(`${url.pathname}${url.search}`);
    if (stream.promptPreviewId === id) {
      stream.promptPreview = result;
      updateLogOutput();
    }
  } catch (error) {
    stream.promptPreview = {content: `提示词读取失败：${error.message}`};
    updateLogOutput();
  }
}

function bindInvocationActions() {
  $$('[data-copy-command]').forEach(button => button.addEventListener("click", async () => {
    const entry = logInvocations().find(item => item.id === button.dataset.copyCommand);
    if (!entry) return;
    try { await navigator.clipboard.writeText(entry.command); toast("已复制命令"); }
    catch { toast("浏览器未允许复制"); }
  }));
  $$('[data-preview-prompt]').forEach(button => button.addEventListener("click", () => previewInvocationPrompt(button.dataset.previewPrompt)));
}

function bindLogConsole() {
  const consoleState = state.logConsole;
  if (!consoleState) return;
  $$('[data-log-scope="experiment"]').forEach(button => button.addEventListener("click", () => selectExperimentLog()));
  $$('[data-log-run]').forEach(button => button.addEventListener("click", () => selectRunLog(button.dataset.logRun)));
  $("#logAttempt")?.addEventListener("change", event => selectRunLog(consoleState.runId, {attempt: Number(event.target.value)}));
  $("#logChannel")?.addEventListener("change", event => {
    consoleState.channel = event.target.value;
    updateLogOutput();
  });
  $("#logSearch")?.addEventListener("input", event => {
    consoleState.keyword = event.target.value;
    updateLogOutput();
  });
  $("#logPause")?.addEventListener("click", () => {
    consoleState.paused = !consoleState.paused;
    renderLogConsoleOnly();
    if (!consoleState.paused) fetchSelectedLog();
  });
  $("#logFollow")?.addEventListener("click", followCurrentLog);
  $("#logCopy")?.addEventListener("click", copyVisibleLogs);
  $("#logCopyDiagnostics")?.addEventListener("click", copyDiagnostics);
  $("#logCancelRun")?.addEventListener("click", () => cancelRun(consoleState.runId));
  $("#liveLogConsole [data-retry-experiment]")?.addEventListener("click", () => retryExperiment(state.detail.id));
  bindInvocationActions();
  $("#logClear")?.addEventListener("click", () => {
    const stream = currentLogStream();
    if (stream) stream.records = [];
    consoleState.newLines = 0;
    renderLogConsoleOnly();
  });
  $("#logFile")?.addEventListener("change", event => {
    const stream = currentLogStream();
    stream.selectedFile = event.target.value;
    stream.preview = null;
    stream.previewError = "";
    stream.lastPreviewAt = 0;
    renderLogConsoleOnly();
    if (stream.selectedFile) fetchFilePreview();
  });
  $("#logDownloadButton")?.addEventListener("click", () => {
    const url = currentLogStream()?.selectedFile;
    if (url) window.open(url, "_blank", "noopener");
  });
  $("#logUnmasked")?.addEventListener("change", event => {
    consoleState.unmasked = event.target.checked;
    resetSelectedLog();
    const stream = currentLogStream();
    if (stream) { stream.preview = null; stream.promptPreview = null; stream.promptPreviewId = null; }
    updateLogOutput();
    fetchSelectedLog();
    if (stream?.selectedFile) fetchFilePreview();
  });
  $("#logNewLines")?.addEventListener("click", () => {
    consoleState.atBottom = true;
    consoleState.newLines = 0;
    renderLogConsoleOnly();
  });
  const output = $("#liveLogOutput");
  output?.addEventListener("scroll", () => {
    consoleState.scrollTop = output.scrollTop;
    consoleState.atBottom = output.scrollHeight - output.scrollTop - output.clientHeight < 12;
    if (consoleState.atBottom && consoleState.newLines) {
      consoleState.newLines = 0;
      renderLogConsoleOnly();
    }
  });
}

function startLogPolling() {
  if (state.logPoller) clearInterval(state.logPoller);
  state.logPoller = setInterval(() => fetchSelectedLog(), 1000);
}

function stopLogPolling() {
  if (state.logPoller) clearInterval(state.logPoller);
  state.logPoller = null;
}

function renderDetail(item, {fresh = false} = {}) {
  state.detail = item;
  const previousLogKey = logStreamKey();
  ensureLogConsole(item);
  $("#detailTitle").textContent = item.suite_name;
  const p = item.profile, active = ["queued", "preparing", "running"].includes(item.status);
  const retrying = state.retryingExperiments.has(item.id);
  const body = $("#detailBody");
  const rebuild = fresh || body.dataset.experimentId !== item.id || !$("#detailSummary");
  const summary = `<div class="detail-toolbar"><div class="experiment-meta"><span class="pill ${item.status}">${escapeHtml(experimentStatusLabel(item.status))}</span><span>commit ${escapeHtml(item.project_commit.slice(0,10))}</span><span>${providerName(p.runner.provider)} ${escapeHtml(modelName(p.runner))} → ${providerName(p.judge.provider)} ${escapeHtml(modelName(p.judge))}</span>${p.self_judge?'<span class="self-judge">Self-judge</span>':""}</div><div class="detail-actions"><button class="button button-ghost button-small" data-retry-experiment="${item.id}" ${retrying?"disabled":""}>${retrying?"正在加入…":"重试实验"}</button>${active?'<button class="button button-ghost button-small danger" id="cancelExperimentButton">取消整个实验</button>':""}</div></div>${experimentLineageMarkup(item)}<div class="profile-strip"><span>Runner 隔离：${escapeHtml(p.runner.isolation)}</span><span>网络：${escapeHtml(p.runner.network_policy)}</span><span>Profile ${escapeHtml(p.hash.slice(0,10))}</span></div><div class="detail-scores"><div class="detail-score"><small>无 Skill</small><strong>${fmtScore(item.scores.no_skill)}</strong></div><div class="detail-score"><small>上一基准</small><strong>${fmtScore(item.scores.baseline)}</strong></div><div class="detail-score"><small>当前候选</small><strong>${fmtScore(item.scores.current)}</strong></div></div><p>当前 vs 无 Skill：${fmtDelta(item.delta_no_skill)}　 当前 vs 基准：${fmtDelta(item.delta_baseline)}</p>${item.error_message?`<div class="message error">${escapeHtml(item.error_message)}</div>`:""}`;
  const runs = item.runs.map(run => renderRun(item, run)).join("") || '<div class="empty">正在准备运行列表…</div>';
  const footer = item.status === "completed" ? '<button class="button button-ghost" id="setBaselineButton">将当前修订设为基准版本</button>' : "";
  if (rebuild) {
    body.innerHTML = `<div id="detailSummary">${summary}</div>${renderLogConsole(item)}<div class="run-grid" id="detailRunGrid">${runs}</div><div id="detailFooter">${footer}</div>`;
    body.dataset.experimentId = item.id;
    bindLogConsole();
    restoreLogScroll();
  } else {
    $("#detailSummary").innerHTML = summary;
    $("#detailRunGrid").innerHTML = runs;
    $("#detailFooter").innerHTML = footer;
  }
  bindDetailActions(item);
  if (!rebuild && previousLogKey !== logStreamKey()) {
    renderLogConsoleOnly();
    loadSelectedLogFiles();
    fetchSelectedLog();
  }
}

function bindDetailActions(item) {
  const id = item.id;
  $$('[data-toggle-run]').forEach(button => button.addEventListener("click", () => {
    const runId = button.dataset.toggleRun;
    state.expandedRuns[runId] = !(state.expandedRuns[runId] ?? false);
    renderDetail(state.detail);
    if (state.expandedRuns[runId]) loadRunEvents(runId);
  }));
  $$('[data-evidence]').forEach(button => button.addEventListener("click", () => showEvidence(button.dataset.evidence)));
  $$('[data-review]').forEach(button => button.addEventListener("click", () => addReview(id, button.dataset.review)));
  $$('[data-cancel-run]').forEach(button => button.addEventListener("click", () => cancelRun(button.dataset.cancelRun)));
  $$('[data-retry-run]').forEach(button => button.addEventListener("click", () => retryRun(button.dataset.retryRun)));
  $("#detailSummary")?.querySelectorAll("[data-retry-experiment]").forEach(button => button.addEventListener("click", () => retryExperiment(button.dataset.retryExperiment)));
  $$('[data-log]').forEach(button => button.addEventListener("click", () => selectRunLog(button.dataset.log)));
  $("#detailSummary")?.querySelectorAll("[data-detail]").forEach(button => button.addEventListener("click", () => showDetail(button.dataset.detail)));
  const cancel = $("#cancelExperimentButton");
  if (cancel) cancel.addEventListener("click", () => cancelExperiment(id));
  const baseline = $("#setBaselineButton");
  if (baseline) baseline.addEventListener("click", () => setBaseline(item));
}

async function loadRunEvents(runId) {
  try {
    const after = state.eventCursors[runId] || 0;
    const result = await api(`/api/v1/runs/${runId}/events?after=${after}`);
    state.runEvents[runId] = [...(state.runEvents[runId] || []), ...result.items];
    if (result.items.length) state.eventCursors[runId] = result.items.at(-1).id;
  } catch (error) { toast(error.message); }
}

async function refreshDetail() {
  if (!state.detail) return;
  try {
    const item = await api(`/api/v1/experiments/${state.detail.id}`);
    state.detail = item;
    await Promise.all(item.runs.filter(run => run.status === "running" || run.stalled || !["queued", "completed", "cancelled"].includes(run.status)).map(run => loadRunEvents(run.id)));
    renderDetail(item);
    fetchSelectedLog();
    if (!["queued", "preparing", "running"].includes(item.status)) {
      clearInterval(state.detailPoller);
      state.detailPoller = null;
    }
  } catch (error) { toast(error.message); }
}

async function showDetail(id) {
  try {
    const item = await api(`/api/v1/experiments/${id}`);
    state.runEvents = {};
    state.eventCursors = {};
    state.runLogs = {};
    state.expandedRuns = {};
    item.runs.forEach(run => { if (run.status === "running" || run.stalled || !["queued", "completed", "cancelled"].includes(run.status)) state.expandedRuns[run.id] = true; });
    ensureLogConsole(item, {fresh: true});
    renderDetail(item, {fresh: true});
    if (!$("#detailModal").open) $("#detailModal").showModal();
    await Promise.all(item.runs.filter(run => state.expandedRuns[run.id]).map(run => loadRunEvents(run.id)));
    renderDetail(item);
    await loadSelectedLogFiles();
    await fetchSelectedLog();
    startLogPolling();
    if (state.detailPoller) clearInterval(state.detailPoller);
    if (["queued", "preparing", "running"].includes(item.status)) state.detailPoller = setInterval(refreshDetail, 2000);
  } catch (error) { toast(error.message); }
}

async function loadRunLogs(runId) { selectRunLog(runId); }

document.addEventListener("DOMContentLoaded", () => {
  $("#detailModal").addEventListener("close", stopLogPolling);
});
async function addReview(experimentId,runId){const scoreText=window.prompt("人工复核分（0–100）");if(scoreText===null)return;const score=Number(scoreText);if(!Number.isFinite(score)||score<0||score>100)return toast("请输入 0–100 的分数");const note=window.prompt("复核说明（可留空）")??"";try{await api(`/api/v1/runs/${runId}/reviews`,{method:"POST",body:JSON.stringify({score,note,reviewer:"local-user"})});toast("人工复核已保存");await showDetail(experimentId);}catch(error){toast(error.message);}}

document.addEventListener("DOMContentLoaded",()=>{
  restoreRuntimeCache();
  $$('[data-open]').forEach(button=>button.addEventListener("click",()=>$("#"+button.dataset.open).showModal()));$$('[data-close]').forEach(button=>button.addEventListener("click",()=>{const modal=$("#"+button.dataset.close);modal.close();if(modal.id==="detailModal"){clearInterval(state.detailPoller);state.detailPoller=null;state.detail=null;}}));
  $("#draftButton").addEventListener("click",generateDraft);$("#saveSuiteButton").addEventListener("click",saveSuite);$("#runButton").addEventListener("click",launchExperiment);$("#refreshButton").addEventListener("click",()=>loadAll({refreshRuntime:true}).then(()=>toast("已刷新")));
  $("#expectedFile").addEventListener("change",loadExpectedMarkdown);
  $("#suiteForm").addEventListener("submit",event=>event.preventDefault());["#projectPath","#skillPath","#skillInput","#expected"].forEach(selector=>$(selector).addEventListener("input",invalidateDraft));
  ["#runnerProvider","#judgeProvider","#judgeSame"].forEach(selector=>$(selector).addEventListener("change",syncProviderControls));
  ["#experimentStatusFilter","#experimentModeFilter"].forEach(selector=>$(selector).addEventListener("change",renderExperiments));
  loadAll().catch(error=>toast(error.message));
});
