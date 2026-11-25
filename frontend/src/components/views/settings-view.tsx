"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CircleAlert,
  Database,
  Globe2,
  LockKeyhole,
  RefreshCw,
  Server,
  ShieldCheck,
} from "lucide-react";
import { PageHeading } from "@/components/page-heading";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API_BASE_URL, api } from "@/lib/api";

type HealthStatus = Awaited<ReturnType<typeof api.health>>;

export function SettingsView() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const checkHealth = useCallback(async () => {
    setLoading(true);
    try {
      setHealth(await api.health());
      setError(null);
    } catch (reason) {
      setHealth(null);
      setError(reason instanceof Error ? reason.message : "The API health check failed.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialCheck = window.setTimeout(() => void checkHealth(), 0);
    return () => window.clearTimeout(initialCheck);
  }, [checkHealth]);

  return (
    <div className="space-y-6">
      <PageHeading
        eyebrow="Workspace"
        title="Settings"
        description="API connection and deployment information for this TCgen instance."
        action={
          <Button
            variant="outline"
            onClick={() => void checkHealth()}
            disabled={loading}
            className="border-white/[0.09] bg-white/[0.02] text-slate-300"
          >
            <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
            Check API
          </Button>
        }
      />

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(300px,0.75fr)]">
        <Card className="dashboard-card">
          <CardHeader className="px-5 pb-3 pt-5 sm:px-6">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold text-slate-100">
              <Globe2 className="size-4 text-slate-400" /> API connection
            </CardTitle>
            <p className="mt-1 text-xs text-slate-500">The dashboard reads execution and model settings from FastAPI.</p>
          </CardHeader>
          <CardContent className="space-y-4 px-5 pb-5 sm:px-6">
            <div className={`flex items-center gap-3 rounded-xl border p-3.5 ${
              error
                ? "border-rose-300/10 bg-rose-300/[0.035]"
                : health
                  ? "border-emerald-300/10 bg-emerald-300/[0.035]"
                  : "border-white/[0.07] bg-white/[0.02]"
            }`}>
              <span className={`grid size-8 place-items-center rounded-lg ${
                error ? "bg-rose-300/10 text-rose-200" : health ? "bg-emerald-300/10 text-emerald-200" : "bg-white/[0.04] text-slate-400"
              }`}>
                {error ? <CircleAlert className="size-4" /> : <Server className="size-4" />}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium text-slate-200">
                  {loading ? "Checking connection…" : error ? "API unavailable" : "API connected"}
                </p>
                <p className="mt-0.5 break-words text-[10px] text-slate-500">
                  {error ?? (health ? `${health.service} · ${health.architecture} · ${health.orchestration_pattern}` : "Waiting for health check")}
                </p>
              </div>
            </div>
            <InfoRow label="FastAPI base URL" value={API_BASE_URL} mono />
            {error && (
              <p role="alert" className="text-[11px] leading-5 text-rose-200">
                Verify that the API is running and that its CORS_ORIGINS includes this frontend origin.
              </p>
            )}
          </CardContent>
        </Card>

        <Card className="dashboard-card">
          <CardHeader className="px-5 pb-3 pt-5">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold text-slate-100">
              <LockKeyhole className="size-4 text-lime-200" /> Security & deployment
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 px-5 pb-5">
            <InfoRow label="Provider credentials" value="Server-side environment variables" />
            <InfoRow label="Frontend secret keys" value="None" />
            <InfoRow label="Run storage" value="Configured on the API server" />
            <div className="flex items-start gap-2 rounded-lg border border-white/[0.06] bg-[#0b1117] p-3 text-[10px] leading-5 text-slate-500">
              <ShieldCheck className="mt-0.5 size-3.5 shrink-0 text-emerald-300" />
              Set NEXT_PUBLIC_API_BASE_URL when building the frontend and CORS_ORIGINS on the API server.
              Do not place provider keys in NEXT_PUBLIC_* variables.
            </div>
          </CardContent>
        </Card>

        <Card className="dashboard-card xl:col-span-2">
          <CardHeader className="px-5 pb-3 pt-5 sm:px-6">
            <CardTitle className="flex items-center gap-2 text-sm font-semibold text-slate-100">
              <Database className="size-4 text-slate-400" /> Pipeline and run data
            </CardTitle>
          </CardHeader>
          <CardContent className="grid gap-3 px-5 pb-5 sm:grid-cols-3 sm:px-6">
            <InfoTile title="Orchestration" value={health?.orchestration_pattern ?? "Sequential"} detail="No parallel agent execution" />
            <InfoTile title="Architecture" value={health?.architecture ?? "Blackboard"} detail="Shared pipeline state" />
            <InfoTile title="Execution history" value="API-backed" detail="Overview and monitoring use live run records" />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function InfoRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-1 border-b border-white/[0.045] pb-3 last:border-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between sm:gap-4">
      <p className="text-[11px] text-slate-500">{label}</p>
      <p className={`break-all text-[11px] text-slate-300 ${mono ? "font-mono" : ""}`}>{value}</p>
    </div>
  );
}

function InfoTile({ title, value, detail }: { title: string; value: string; detail: string }) {
  return (
    <div className="rounded-xl border border-white/[0.055] bg-white/[0.018] p-3.5">
      <p className="text-[9px] uppercase tracking-[0.12em] text-slate-600">{title}</p>
      <p className="mt-2 text-sm font-medium text-slate-200">{value}</p>
      <p className="mt-1 text-[10px] text-slate-500">{detail}</p>
    </div>
  );
}
