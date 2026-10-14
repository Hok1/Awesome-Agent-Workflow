import { useEffect, useMemo, useState } from "react";
import { Plus, Search, ArrowLeft, ArrowRight, RefreshCw } from "lucide-react";
import { api, type Json } from "../lib/api";
import { Button, Card, Empty, Modal } from "../components/ui";
import { TestSuiteCard } from "../components/TestSuiteCard";
import { ScoreRadar } from "../components/ScoreRadar";
import { PendingSuiteCard } from "../components/PendingSuiteCard";
import { draftDefaults } from "../lib/draft";
export function Dashboard({ notify }: { notify: (message: string) => void }) {
  const [suites, setSuites] = useState<Json[]>([]),
    [drafts, setDrafts] = useState<Json[]>([]),
    [loaded, setLoaded] = useState(false),
    [query, setQuery] = useState(""),
    [filter, setFilter] = useState("all"),
    [sort, setSort] = useState("new"),
    [archived, setArchived] = useState(false),
    [page, setPage] = useState(1),
    [radar, setRadar] = useState<Json | null>(null),
    [error, setError] = useState(""),
    [createOpen, setCreateOpen] = useState(false),
    [name, setName] = useState(""),
    [creating, setCreating] = useState(false),
    [createError, setCreateError] = useState("");
  async function create() {
    if (creating || !name.trim()) return;
    setCreating(true);
    setCreateError("");
    try {
      const created = await api("/benchmark/drafts", {
        data: draftDefaults({ name: name.trim() }),
      });
      setDrafts((old) => [
        created,
        ...old.filter((item) => item.id !== created.id),
      ]);
      setQuery("");
      setFilter("all");
      setArchived(false);
      setSort("new");
      setPage(1);
      setCreateOpen(false);
      setName("");
      notify("测试套已创建，可在卡片中进入配置");
      await load();
    } catch (e) {
      setCreateError(String(e));
    } finally {
      setCreating(false);
    }
  }
  async function load() {
    try {
      const [data, drafts] = await Promise.all([
        api("/benchmark/suites"),
        api("/benchmark/drafts"),
      ]);
      setSuites(data.items);
      setDrafts(drafts.items);
      setLoaded(true);
      setError("");
    } catch (e) {
      setError(String(e));
    }
  }
  useEffect(() => {
    load();
    const timer = setInterval(load, 5000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => setPage(1), [query, filter, sort, archived]);
  const filtered = useMemo(
    () =>
      [
        ...suites.map((s) => ({ ...s, kind: "suite" })),
        ...drafts.map((d) => ({
          ...d,
          kind: "draft",
          name: d.data.name || "未命名测试套",
          archived: false,
          created_at: d.created_at ?? d.updated_at,
        })),
      ] as Json[],
    [suites, drafts],
  );
  const filteredItems = useMemo(
    () =>
      filtered
        .filter(
          (s) =>
            s.archived === archived &&
            s.name.toLowerCase().includes(query.toLowerCase()) &&
            (filter === "all" ||
              (filter === "pending"
                ? s.kind === "draft"
                : s.kind === "suite" &&
                  (filter === "unrun"
                    ? !s.latest
                    : s.latest?.status === filter))),
        )
        .sort((a, b) =>
          sort === "new"
            ? b.created_at.localeCompare(a.created_at)
            : a.created_at.localeCompare(b.created_at),
        ),
    [filtered, query, filter, sort, archived],
  );
  const pages = Math.max(1, Math.ceil(filteredItems.length / 12)),
    safePage = Math.min(page, pages),
    visible = filteredItems.slice((safePage - 1) * 12, safePage * 12);
  async function archive(suite: Json) {
    try {
      await api(`/benchmark/suites/${suite.id}/archive`, {
        archived: !suite.archived,
      });
      notify(suite.archived ? "测试套已恢复" : "测试套已归档，历史结果保留");
      load();
    } catch (e) {
      notify(String(e));
    }
  }
  return (
    <main className="dashboard">
      <div className="page-heading">
        <div>
          <div className="eyebrow">BENCHMARK WORKSPACE</div>
          <h1>测试套管理</h1>
          <p>固定测试集，持续评价 Agent Skill 的能力变化。</p>
        </div>
        <Button
          onClick={() => {
            setCreateError("");
            setName("");
            setCreateOpen(true);
          }}
        >
          <Plus size={17} />
          创建测试套
        </Button>
      </div>
      <div className="stats-grid">
        <Card>
          <span>正式测试套</span>
          <strong>{suites.filter((s) => !s.archived).length}</strong>
        </Card>
        <Card>
          <span>累计执行</span>
          <strong>
            {suites.reduce((sum, s) => sum + s.execution_count, 0)}
          </strong>
        </Card>
        <Card>
          <span>正在执行</span>
          <strong>
            {
              suites.filter((s) =>
                ["queued", "preparing", "running"].includes(s.latest?.status),
              ).length
            }
          </strong>
        </Card>
        <Card>
          <span>待配置</span>
          <strong>{drafts.length}</strong>
        </Card>
      </div>
      <div className="toolbar">
        <div className="search">
          <Search size={16} />
          <input
            aria-label="搜索测试套名称"
            placeholder="搜索测试套名称…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="flex gap-3 items-center flex-wrap">
          <select
            aria-label="筛选测试状态"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          >
            <option value="all">全部状态</option>
            <option value="pending">待配置</option>
            <option value="unrun">未执行</option>
            <option value="completed">已完成</option>
            <option value="running">执行中</option>
            <option value="queued">等待执行</option>
            <option value="failed">失败</option>
          </select>
          <select
            aria-label="创建时间排序"
            value={sort}
            onChange={(e) => setSort(e.target.value)}
          >
            <option value="new">创建时间：最新优先</option>
            <option value="old">创建时间：最早优先</option>
          </select>
          <label className="flex gap-2 text-sm items-center">
            <input
              type="checkbox"
              checked={archived}
              onChange={(e) => setArchived(e.target.checked)}
            />
            已归档
          </label>
          <Button variant="ghost" aria-label="刷新列表" onClick={load}>
            <RefreshCw size={16} />
          </Button>
        </div>
      </div>
      {error && <div className="error-box">{error}</div>}
      {!loaded && !error ? (
        <Empty>加载测试套…</Empty>
      ) : visible.length ? (
        <div className="suite-grid">
          {visible.map((suite) =>
            suite.kind === "draft" ? (
              <PendingSuiteCard key={`draft/${suite.id}`} draft={suite} />
            ) : (
              <TestSuiteCard
                key={suite.id}
                suite={suite}
                onRadar={() => setRadar(suite)}
                onArchive={() => archive(suite)}
              />
            ),
          )}
        </div>
      ) : (
        <Empty>
          {query || filter !== "all"
            ? "没有匹配的测试套"
            : archived
              ? "暂无归档测试套"
              : "还没有测试套。创建测试套，开始设计你的固定测评集。"}
        </Empty>
      )}
      <div className="pagination">
        <span>共 {filteredItems.length} 个测试套</span>
        <div>
          <Button
            variant="ghost"
            disabled={safePage === 1}
            onClick={() => setPage(safePage - 1)}
            aria-label="上一页"
          >
            <ArrowLeft size={16} />
          </Button>
          <span>
            {safePage} / {pages}
          </span>
          <Button
            variant="ghost"
            disabled={safePage === pages}
            onClick={() => setPage(safePage + 1)}
            aria-label="下一页"
          >
            <ArrowRight size={16} />
          </Button>
        </div>
      </div>
      <Modal
        open={createOpen}
        onOpenChange={(open) => {
          if (!creating) setCreateOpen(open);
        }}
        title="创建测试套"
        className="modal-compact"
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            create();
          }}
          className="grid gap-4"
        >
          <label>
            测试套名称
            <input
              autoFocus
              required
              maxLength={160}
              value={name}
              disabled={creating}
              onChange={(event) => setName(event.target.value)}
              placeholder="请输入测试套名称"
            />
          </label>
          <p className="text-sm text-slate-500">
            创建后可从首页卡片进入用例配置。
          </p>
          {createError && (
            <div className="error-box" role="alert">
              {createError}
            </div>
          )}
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="ghost"
              disabled={creating}
              onClick={() => setCreateOpen(false)}
            >
              取消
            </Button>
            <Button type="submit" disabled={creating || !name.trim()}>
              {creating ? "创建中…" : "创建"}
            </Button>
          </div>
        </form>
      </Modal>
      <Modal
        open={!!radar}
        onOpenChange={() => setRadar(null)}
        title={radar?.name ?? "能力雷达图"}
      >
        {radar && (
          <>
            <ScoreRadar current={radar.latest} baseline={radar.baseline} />
            <p className="text-sm text-slate-500 mt-3">
              {radar.comparison.formal
                ? "相同条件下的历史比较"
                : radar.comparison.reasons.join(" · ")}
            </p>
          </>
        )}
      </Modal>
    </main>
  );
}
