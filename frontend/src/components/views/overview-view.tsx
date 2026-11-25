"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowUpRight,
  FilePlus2,
  RefreshCw,
  ServerCrash,
} from "lucide-react";
import { MetricCard } from "@/components/metric-card";
import { PageHeading } from "@/components/page-heading";
import { StatusPill } from "@/components/status-pill";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type RunRecord } from "@/lib/api";
import { formatDate, formatDuration } from "@/lib/format";

type RunSnapshot = {
  runs: RunRecord[];
  total: number;
};

const metricDefinitions = [
  { key: "runs", label: "Total runs", detail: "All submitted runs", tone: "lime", icon: "runs" },
  { key: "completed", label: "Successful executions", detail: "Runs marked completed", tone: "teal", icon: "completed" },
  { key: "failed", label: "Failed executions", detail: "Runs marked failed", tone: "rose", icon: "failed" },
  { key: "active", label: "In progress", detail: "Queued or running now", tone: "violet", icon: "active" },
  { key: "runtime", label: "Average runtime", detail: "Completed and failed runs", tone: "amber", icon: "runtime" },
] as const;

export function OverviewView({
  onNewRun,
  onSelectRun,
}: {
  onNewRun: () => void;
  onSelectRun?: (runId: string) => void;
}) {
  const [snapshot, setSnapshot] = useState<RunSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const result = await api.allRuns();
      setSnapshot({ runs: result.items, total: result.total });
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load run history.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => void refresh(), 0);
    const interval = window.setInterval(() => void refresh(), 5000);
    return () => {
      window.clearTimeout(initialLoad);
      window.clearInterval(interval);
    };
  }, [refresh]);

  const counts = useMemo(() => {
    if (!snapshot) return null;
    const completed = snapshot.runs.filter((run) => run.status === "completed").length;
    const failed = snapshot.runs.filter((run) => run.status === "failed").length;
    const active = snapshot.runs.filter(
      (run) => run.status === "queued" || run.status === "running",
    ).length;
    const durations = snapshot.runs
      .filter((run) => run.status === "completed" || run.status === "failed")
      .map((run) => run.execution_time_seconds)
      .filter((value): value is number => value !== null);
    const averageRuntime = durations.length
      ? formatDuration(durations.reduce((sum, value) => sum + value, 0) / durations.length)
      : snapshot.total === 0
        ? "0s"
        : "—";
    return { completed, failed, active, averageRuntime };
  }, [snapshot]);

  const metrics = metricDefinitions.map((metric) => ({
    ...metric,
    value: !snapshot
      ? "—"
      : metric.key === "runs"
        ? String(snapshot.total)
        : metric.key === "completed"
          ? String(counts?.completed ?? 0)
          : metric.key === "failed"
            ? String(counts?.failed ?? 0)
            : metric.key === "active"
              ? String(counts?.active ?? 0)
              : counts?.averageRuntime ?? "—",
  }));
  const recentRuns = snapshot?.runs.slice(0, 8) ?? [];

  return (
    <div className="space-y-6">
      <PageHeading
        eyebrow="Workspace"
        title="Execution overview"
        description="Live run totals and recent executions from the PRD pipeline."
        action={
          <>
            <span className="hidden items-center gap-1.5 text-[10px] text-slate-500 sm:inline-flex">
              <span className="size-1.5 rounded-full bg-emerald-300" />
              Refreshes every 5 seconds
            </span>
            <Button
              variant="outline"
              onClick={() => void refresh()}
              disabled={refreshing}
              className="border-white/[0.09] bg-white/[0.02] text-slate-300"
            >
              <RefreshCw className={`size-3.5 ${refreshing ? "animate-spin" : ""}`} />
              Refresh
            </Button>
            <Button onClick={onNewRun} className="gap-2 bg-lime-300 text-slate-950 hover:bg-lime-200">
              <FilePlus2 className="size-4" />
              New PRD run
            </Button>
          </>
        }
      />

      {error && (
        <div role="alert" className="flex flex-col gap-3 rounded-xl border border-rose-300/15 bg-rose-300/[0.045] p-4 sm:flex-row sm:items-center">
          <ServerCrash className="size-4 shrink-0 text-rose-300" />
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium text-rose-200">Could not load execution data</p>
            <p className="mt-1 break-words text-[11px] text-slate-400">{error}</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void refresh()} className="border-rose-200/15 bg-transparent text-rose-100">
            Retry
          </Button>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {loading && !snapshot
          ? metricDefinitions.map((metric) => (
              <Card key={metric.key} className="dashboard-card">
                <CardContent className="space-y-4 p-5">
                  <Skeleton className="h-3 w-28 bg-white/[0.07]" />
                  <Skeleton className="h-8 w-20 bg-white/[0.07]" />
                  <Skeleton className="h-2 w-32 bg-white/[0.045]" />
                </CardContent>
              </Card>
            ))
          : metrics.map(({ key, ...metric }) => (
              <MetricCard key={key} {...metric} />
            ))}
      </div>

      <Card className="dashboard-card overflow-hidden">
        <CardHeader className="flex flex-row items-center justify-between px-5 pb-4 pt-5 sm:px-6">
          <div>
            <CardTitle className="text-sm font-semibold text-slate-100">Recent executions</CardTitle>
            <p className="mt-1 text-xs text-slate-500">
              {snapshot ? `${snapshot.total} run${snapshot.total === 1 ? "" : "s"} recorded by the API` : "Loading run history…"}
            </p>
          </div>
          <Button variant="ghost" size="sm" onClick={() => void refresh()} className="gap-1.5 text-xs text-slate-400 hover:text-lime-200">
            Refresh list <RefreshCw className="size-3.5" />
          </Button>
        </CardHeader>
        <CardContent className="px-0 pb-1">
          {loading && !snapshot ? (
            <div className="space-y-3 px-6 pb-5">
              {Array.from({ length: 4 }, (_, index) => (
                <Skeleton key={index} className="h-12 w-full bg-white/[0.04]" />
              ))}
            </div>
          ) : recentRuns.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left text-xs">
                <thead>
                  <tr className="border-y border-white/[0.06] text-[10px] uppercase tracking-[0.12em] text-slate-500">
                    <th className="px-6 py-3 font-medium">PRD</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium">Submitted</th>
                    <th className="px-4 py-3 font-medium">Runtime</th>
                    <th className="px-5 py-3 font-medium">Run ID</th>
                  </tr>
                </thead>
                <tbody>
                  {recentRuns.map((run) => (
                    <tr
                      key={run.run_id}
                      onClick={() => onSelectRun?.(run.run_id)}
                      className={`border-b border-white/[0.045] transition hover:bg-white/[0.03] last:border-0 ${onSelectRun ? "cursor-pointer" : ""}`}
                    >
                      <td className="px-6 py-3.5">
                        <div className="min-w-0">
                          <p className="truncate font-medium text-slate-200">{run.filename}</p>
                          <p className="mt-0.5 truncate font-mono text-[10px] text-slate-600">{run.run_id}</p>
                        </div>
                      </td>
                      <td className="px-4 py-3.5"><StatusPill status={run.status} /></td>
                      <td className="px-4 py-3.5 text-slate-400">{formatDate(run.created_at)}</td>
                      <td className="px-4 py-3.5 tabular-nums text-slate-400">
                        {run.execution_time_seconds === null ? "—" : formatDuration(run.execution_time_seconds)}
                      </td>
                      <td className="px-5 py-3.5 font-mono text-[10px] text-slate-500">
                        {run.run_id.slice(0, 12)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : snapshot ? (
            <div className="flex flex-col items-center px-6 py-12 text-center">
              <span className="grid size-11 place-items-center rounded-2xl border border-white/[0.07] bg-white/[0.025] text-slate-500">
                <FilePlus2 className="size-5" />
              </span>
              <h2 className="mt-4 text-sm font-medium text-slate-200">No executions yet</h2>
              <p className="mt-1 max-w-sm text-xs leading-5 text-slate-500">
                Start from an existing PRD or upload one. Completed and failed runs will appear here.
              </p>
              <Button onClick={onNewRun} className="mt-4 gap-2 bg-lime-300 text-slate-950 hover:bg-lime-200">
                Create a run <ArrowUpRight className="size-3.5" />
              </Button>
            </div>
          ) : !error ? (
            <div className="px-6 py-10 text-center text-xs text-slate-500">Connecting to the API…</div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}

