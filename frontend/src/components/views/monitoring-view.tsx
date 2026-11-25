"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  FilePlus2,
  RefreshCw,
  ServerCrash,
  TerminalSquare,
} from "lucide-react";
import { PageHeading } from "@/components/page-heading";
import { RunResultsPanel } from "@/components/run-results-panel";
import { StatusPill } from "@/components/status-pill";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  api,
  type MonitoringEvent,
  type RunRecord,
  type RunResultsResponse,
} from "@/lib/api";
import { formatDate, formatDuration } from "@/lib/format";

export function MonitoringView({
  onNewRun,
  trackedRunId = null,
  onSelectRun,
}: {
  onNewRun: () => void;
  trackedRunId?: string | null;
  onSelectRun?: (runId: string) => void;
}) {
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(trackedRunId);
  const [events, setEvents] = useState<MonitoringEvent[]>([]);
  const [results, setResults] = useState<RunResultsResponse | null>(null);
  const [resultsLoading, setResultsLoading] = useState(false);
  const [resultsError, setResultsError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(0);
  const loadedResultsRunIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (trackedRunId) {
      setSelectedRunId(trackedRunId);
    }
  }, [trackedRunId]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      const { items } = await api.allRuns();
      setNow(Date.now());
      setRuns(items);
      const activeRuns = items.filter(
        (run) => run.status === "queued" || run.status === "running",
      );
      const selected =
        items.find((run) => run.run_id === selectedRunId) ??
        activeRuns[0] ??
        items[0];
      if (selected && selected.run_id !== selectedRunId) {
        setSelectedRunId(selected.run_id);
      }
      if (selected) {
        const eventResponse = await api.events(selected.run_id);
        setEvents(eventResponse.events);
        if (selected.status === "completed") {
          if (loadedResultsRunIdRef.current !== selected.run_id) {
            setResultsLoading(true);
            setResultsError(null);
            try {
              const runResults = await api.results(selected.run_id);
              loadedResultsRunIdRef.current = selected.run_id;
              setResults(runResults);
            } catch (reason) {
              setResultsError(
                reason instanceof Error ? reason.message : "Could not load run results.",
              );
            } finally {
              setResultsLoading(false);
            }
          }
        } else {
          loadedResultsRunIdRef.current = null;
          setResults(null);
          setResultsError(null);
        }
      } else {
        loadedResultsRunIdRef.current = null;
        setEvents([]);
        setResults(null);
        setResultsError(null);
      }
      setError(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load active runs.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [selectedRunId]);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => void refresh(), 0);
    const interval = window.setInterval(() => void refresh(), 3000);
    return () => {
      window.clearTimeout(initialLoad);
      window.clearInterval(interval);
    };
  }, [refresh]);

  const selectedRun = runs.find((run) => run.run_id === selectedRunId) ?? runs[0];
  const recentRuns = runs.slice(0, 6);
  const recentEvents = [...events].reverse().slice(0, 30);
  const isRunning = selectedRun?.status === "queued" || selectedRun?.status === "running";

  return (
    <div className="space-y-6">
      <PageHeading
        eyebrow="Observability"
        title="Live agent monitoring"
        description="Live execution state and monitoring events from the API."
        action={
          <>
            <span className="hidden items-center gap-1.5 text-[10px] text-slate-500 sm:inline-flex">
              <span className="size-1.5 animate-pulse rounded-full bg-emerald-300" />
              Polling every 3 seconds
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
          </>
        }
      />

      {error && (
        <div role="alert" className="flex flex-col gap-3 rounded-xl border border-rose-300/15 bg-rose-300/[0.045] p-4 sm:flex-row sm:items-center">
          <ServerCrash className="size-4 shrink-0 text-rose-300" />
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium text-rose-200">Could not load monitoring data</p>
            <p className="mt-1 break-words text-[11px] text-slate-400">{error}</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void refresh()} className="border-rose-200/15 bg-transparent text-rose-100">
            Retry
          </Button>
        </div>
      )}

      {!loading && !error && !selectedRun ? (
        <Card className="dashboard-card">
          <CardContent className="flex min-h-[340px] flex-col items-center justify-center px-6 py-12 text-center">
            <span className="grid size-14 place-items-center rounded-2xl border border-white/[0.07] bg-white/[0.025] text-slate-500">
              <Activity className="size-6" />
            </span>
            <h2 className="mt-5 text-base font-medium text-slate-100">
              No PRD runs recorded yet
            </h2>
            <p className="mt-2 max-w-md text-xs leading-5 text-slate-500">
              Start a PRD run to watch live monitoring events and inspect the generated requirements, test cases, and Selenium scripts.
            </p>
            <Button onClick={onNewRun} className="mt-5 gap-2 bg-lime-300 text-slate-950 hover:bg-lime-200">
              <FilePlus2 className="size-4" /> Start a PRD run
            </Button>
          </CardContent>
        </Card>
      ) : loading ? (
        <Card className="dashboard-card">
          <CardContent className="flex min-h-[300px] items-center justify-center gap-3 text-xs text-slate-500">
            <RefreshCw className="size-4 animate-spin text-lime-200" />
            Loading PRD runs…
          </CardContent>
        </Card>
      ) : error ? null : (
        <>
          {recentRuns.length > 1 && (
            <div className="flex flex-wrap gap-2">
              {recentRuns.map((run) => (
                <Button
                  key={run.run_id}
                  variant={run.run_id === selectedRun?.run_id ? "secondary" : "outline"}
                  onClick={() => {
                    setSelectedRunId(run.run_id);
                    onSelectRun?.(run.run_id);
                  }}
                  className="max-w-full border-white/[0.08] bg-white/[0.025] text-xs text-slate-300"
                >
                  <span className="max-w-40 truncate">{run.filename}</span>
                  <StatusPill status={run.status} />
                </Button>
              ))}
            </div>
          )}

          {selectedRun && (
            <Card className="dashboard-card">
              <CardHeader className="flex flex-row items-start justify-between gap-4 px-5 pb-4 pt-5 sm:px-6">
                <div className="min-w-0">
                  <CardTitle className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                    <Activity className="size-4 text-lime-200" /> {isRunning ? "Current execution" : "Execution summary"}
                  </CardTitle>
                  <p className="mt-1 truncate text-xs text-slate-500">{selectedRun.filename}</p>
                </div>
                <StatusPill status={selectedRun.status} />
              </CardHeader>
              <CardContent className="grid gap-3 px-5 pb-5 sm:grid-cols-2 lg:grid-cols-4 sm:px-6">
                <ContextStat label="Run ID" value={selectedRun.run_id} mono />
                <ContextStat label="Submitted" value={formatDate(selectedRun.created_at)} />
                <ContextStat
                  label="Started"
                  value={selectedRun.started_at ? formatDate(selectedRun.started_at) : "Waiting to start"}
                />
                <ContextStat
                  label={isRunning ? "Elapsed" : "Runtime"}
                  value={
                    selectedRun.execution_time_seconds !== null
                      ? formatDuration(selectedRun.execution_time_seconds)
                      : selectedRun.started_at
                        ? formatDuration(Math.max(0, (now - new Date(selectedRun.started_at).getTime()) / 1000))
                        : "Queued"
                  }
                />
                <ContextStat label="Architecture" value={selectedRun.architecture} />
                <ContextStat label="Orchestration" value={selectedRun.orchestration_pattern} />
              </CardContent>
            </Card>
          )}

          {selectedRun?.status === "failed" && (
            <div role="alert" className="flex items-start gap-3 rounded-xl border border-rose-300/20 bg-rose-300/[0.05] p-4">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-rose-300" />
              <div className="min-w-0">
                <p className="text-xs font-medium text-rose-200">
                  Execution failed{selectedRun.error_type ? ` (${selectedRun.error_type})` : ""}
                </p>
                <p className="mt-1 break-words text-[11px] text-slate-300">
                  {selectedRun.error_message || "No error message was recorded."}
                </p>
              </div>
            </div>
          )}

          {selectedRun?.status === "completed" && (
            resultsLoading ? (
              <Card className="dashboard-card">
                <CardContent className="flex min-h-32 items-center justify-center gap-3 text-xs text-slate-400">
                  <RefreshCw className="size-4 animate-spin text-lime-200" />
                  Loading pipeline results…
                </CardContent>
              </Card>
            ) : resultsError ? (
              <div role="alert" className="rounded-xl border border-rose-300/15 bg-rose-300/[0.045] p-4 text-xs text-rose-200">
                {resultsError}
              </div>
            ) : results ? (
              <RunResultsPanel results={results} />
            ) : null
          )}

          <Card className="dashboard-card overflow-hidden">
            <CardHeader className="px-5 pb-4 pt-5 sm:px-6">
              <CardTitle className="flex items-center gap-2 text-sm font-semibold text-slate-100">
                <TerminalSquare className="size-4 text-slate-400" /> Monitoring events
              </CardTitle>
              <p className="mt-1 text-xs text-slate-500">
                {selectedRun ? `Run ${selectedRun.run_id}` : "Active run event stream"}
              </p>
            </CardHeader>
            <CardContent className="px-5 pb-5 sm:px-6">
              {recentEvents.length ? (
                <div className="overflow-hidden rounded-xl border border-white/[0.06]">
                  {recentEvents.map((event) => (
                    <EventRow key={event.event_id} event={event} />
                  ))}
                </div>
              ) : (
                <div className="flex min-h-28 items-center justify-center rounded-xl border border-dashed border-white/[0.08] px-4 text-center text-xs text-slate-500">
                  No monitoring events are available for this run yet.
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function ContextStat({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0 rounded-lg border border-white/[0.055] bg-white/[0.018] px-3 py-2.5">
      <p className="text-[9px] uppercase tracking-[0.12em] text-slate-600">{label}</p>
      <p className={`mt-1 truncate text-xs font-medium text-slate-200 ${mono ? "font-mono" : ""}`}>{value}</p>
    </div>
  );
}

function EventRow({ event }: { event: MonitoringEvent }) {
  return (
    <div className="grid grid-cols-[90px_1fr_auto] items-center gap-3 border-b border-white/[0.045] bg-[#0b1117]/70 px-3 py-3 last:border-0 sm:grid-cols-[150px_130px_1fr_auto] sm:px-4">
      <span className="font-mono text-[10px] tabular-nums text-slate-600">{formatDate(event.timestamp)}</span>
      <span className="hidden truncate text-[11px] font-medium text-slate-400 sm:block">{event.agent_name || "Pipeline"}</span>
      <div className="flex min-w-0 items-center gap-2">
        <span className={`size-1.5 shrink-0 rounded-full ${event.status === "failed" ? "bg-rose-300" : event.status === "started" ? "bg-lime-200" : "bg-emerald-300"}`} />
        <span className="truncate text-[11px] text-slate-300">
          {event.event_type.replaceAll("_", " ")}
          {event.output_summary ? ` · ${event.output_summary}` : ""}
          {event.error_message ? ` · ${event.error_message}` : ""}
        </span>
      </div>
      <span className="hidden text-[10px] text-slate-600 md:block">
        {event.duration_ms === null ? event.status : `${Math.round(event.duration_ms)} ms`}
      </span>
    </div>
  );
}
