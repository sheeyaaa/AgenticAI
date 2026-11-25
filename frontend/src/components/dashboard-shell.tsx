"use client";

import { useEffect, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  Bot,
  ChevronRight,
  FilePlus2,
  LayoutDashboard,
  Menu,
  PanelLeftClose,
  Settings2,
  Workflow,
  X,
} from "lucide-react";
import { ModelsView } from "@/components/views/models-view";
import { MonitoringView } from "@/components/views/monitoring-view";
import { NewRunView } from "@/components/views/new-run-view";
import { OverviewView } from "@/components/views/overview-view";
import { SettingsView } from "@/components/views/settings-view";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";

type ViewId = "overview" | "new-run" | "monitoring" | "models" | "settings";
const navigation: { id: ViewId; label: string; icon: LucideIcon }[] = [
  { id: "overview", label: "Overview", icon: LayoutDashboard },
  { id: "new-run", label: "New PRD Run", icon: FilePlus2 },
  { id: "monitoring", label: "Live Agent Monitoring", icon: Activity },
  { id: "models", label: "Model Configuration", icon: Bot },
  { id: "settings", label: "Settings", icon: Settings2 },
];
const viewTitles: Record<ViewId, string> = {
  overview: "Overview",
  "new-run": "New PRD Run",
  monitoring: "Live Agent Monitoring",
  models: "Model Configuration",
  settings: "Settings",
};

export function DashboardShell() {
  const [activeView, setActiveView] = useState<ViewId>("overview");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [toast, setToast] = useState("");
  const [apiStatus, setApiStatus] = useState<"checking" | "connected" | "offline">("checking");
  const sidebarCollapsed = collapsed && !mobileOpen;

  useEffect(() => {
    let active = true;
    const checkApi = async () => {
      try {
        await api.health();
        if (active) setApiStatus("connected");
      } catch {
        if (active) setApiStatus("offline");
      }
    };
    void checkApi();
    const interval = window.setInterval(() => void checkApi(), 15000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  function showToast(message: string) {
    setToast(message);
    window.setTimeout(() => setToast(""), 3200);
  }

  function navigate(view: ViewId) {
    setActiveView(view);
    setMobileOpen(false);
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="app-backdrop pointer-events-none fixed inset-0 -z-10" />
      {mobileOpen && (
        <button
          aria-label="Close navigation"
          onClick={() => setMobileOpen(false)}
          className="fixed inset-0 z-40 bg-black/65 backdrop-blur-[2px] lg:hidden"
        />
      )}
      <aside
        className={`sidebar-shell fixed inset-y-0 left-0 z-50 flex flex-col border-r border-white/[0.065] transition-[width,transform] duration-200 ${
          sidebarCollapsed ? "w-[76px]" : "w-[252px]"
        } ${mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"}`}
      >
        <div className={`flex h-[68px] shrink-0 items-center border-b border-white/[0.055] ${sidebarCollapsed ? "justify-center px-3" : "justify-between px-5"}`}>
          <button onClick={() => navigate("overview")} className="flex items-center gap-3 text-left" aria-label="Go to overview">
            <span className="relative grid size-9 place-items-center rounded-xl bg-lime-300 text-slate-950 shadow-[0_0_22px_rgba(184,243,107,.14)]">
              <Workflow className="size-[19px]" strokeWidth={2.2} />
              <span className="absolute -bottom-0.5 -right-0.5 size-2.5 rounded-full border-2 border-[#0b1117] bg-[#71d9c0]" />
            </span>
            {!sidebarCollapsed && (
              <span className="min-w-0">
                <span className="block text-[13px] font-semibold tracking-tight text-slate-100">TCgen</span>
                <span className="mt-0.5 block text-[9px] uppercase tracking-[0.16em] text-slate-600">Test case generation</span>
              </span>
            )}
          </button>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => {
              setCollapsed((value) => !value);
              setMobileOpen(false);
            }}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={`hidden text-slate-500 hover:text-slate-200 lg:inline-flex ${collapsed ? "absolute -right-3 top-6 size-6 rounded-full border border-white/10 bg-[#0b1117]" : ""}`}
          >
            {collapsed ? <ChevronRight className="size-3.5" /> : <PanelLeftClose className="size-4" />}
          </Button>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
            className="text-slate-500 lg:hidden"
          >
            <X className="size-4" />
          </Button>
        </div>

        <div className={`mb-2 mt-6 px-3 text-[9px] font-semibold uppercase tracking-[0.19em] text-slate-600 ${sidebarCollapsed ? "text-center" : "pl-5"}`}>
          {sidebarCollapsed ? "•••" : "Workspace"}
        </div>
        <nav className="flex-1 space-y-1 px-2.5" aria-label="Main navigation">
          {navigation.map((item) => {
            const Icon = item.icon;
            const active = activeView === item.id;
            const control = (
              <button
                key={item.id}
                onClick={() => navigate(item.id)}
                aria-current={active ? "page" : undefined}
                aria-label={item.label}
                className={`group relative flex h-10 w-full items-center gap-3 rounded-lg px-3 text-left text-xs transition ${
                  active
                    ? "bg-lime-300/[0.1] font-medium text-lime-100"
                    : "text-slate-500 hover:bg-white/[0.035] hover:text-slate-200"
                } ${sidebarCollapsed ? "justify-center px-0" : ""}`}
              >
                {active && <span className="absolute -left-2.5 top-2.5 h-5 w-[2px] rounded-r bg-lime-300" />}
                <Icon className={`size-[17px] shrink-0 ${active ? "text-lime-200" : "text-slate-500 group-hover:text-slate-300"}`} strokeWidth={1.8} />
                {!sidebarCollapsed && <span className="truncate">{item.label}</span>}
              </button>
            );
            return sidebarCollapsed ? (
              <Tooltip key={item.id}>
                <TooltipTrigger render={control} />
                <TooltipContent side="right" className="border-white/10 bg-[#111a22] text-xs text-slate-200">
                  {item.label}
                </TooltipContent>
              </Tooltip>
            ) : control;
          })}
        </nav>

        <div className="mt-auto space-y-3 p-3">
          <Separator className="bg-white/[0.06]" />
          <div className={`flex items-center gap-2.5 ${sidebarCollapsed ? "justify-center" : "px-1"}`}>
            <Avatar className="size-8 border border-white/[0.08]">
              <AvatarFallback className="bg-slate-700/70 text-[10px] font-semibold text-slate-200">TC</AvatarFallback>
            </Avatar>
            {!sidebarCollapsed && (
              <>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[11px] font-medium text-slate-300">TCgen workspace</p>
                  <p className="truncate text-[9px] text-slate-600">Local instance</p>
                </div>
                <Button variant="ghost" size="icon-xs" aria-label="Open settings" onClick={() => navigate("settings")} className="text-slate-500">
                  <Settings2 />
                </Button>
              </>
            )}
          </div>
        </div>
      </aside>

      <div className={`min-h-screen transition-[padding] duration-200 ${collapsed ? "lg:pl-[76px]" : "lg:pl-[252px]"}`}>
        <header className="sticky top-0 z-30 flex h-[68px] items-center justify-between border-b border-white/[0.055] bg-[#090e13]/85 px-4 backdrop-blur-xl sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <Button
              variant="ghost"
              size="icon-sm"
              className="shrink-0 text-slate-400 lg:hidden"
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation"
            >
              <Menu className="size-5" />
            </Button>
            <div className="hidden items-center gap-2 text-[11px] text-slate-600 sm:flex">
              <span>TCgen</span>
              <span className="text-slate-700">/</span>
              <span className="truncate text-slate-300">{viewTitles[activeView]}</span>
            </div>
            <span className="truncate text-xs font-medium text-slate-300 sm:hidden">{viewTitles[activeView]}</span>
          </div>
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[9px] font-medium uppercase tracking-[0.1em] ${
              apiStatus === "connected"
                ? "border-emerald-200/10 bg-emerald-300/[0.045] text-emerald-100"
                : apiStatus === "offline"
                  ? "border-rose-200/10 bg-rose-300/[0.045] text-rose-100"
                  : "border-white/[0.08] bg-white/[0.025] text-slate-400"
            }`}
          >
            <span className={`size-1.5 rounded-full ${apiStatus === "connected" ? "bg-emerald-300" : apiStatus === "offline" ? "bg-rose-300" : "animate-pulse bg-slate-400"}`} />
            {apiStatus === "connected" ? "API connected" : apiStatus === "offline" ? "API unavailable" : "Connecting"}
          </span>
        </header>

        <main className="mx-auto w-full max-w-[1580px] px-4 py-6 sm:px-6 sm:py-7 lg:px-8 lg:py-8">
          {activeView === "overview" && (
            <OverviewView
              onNewRun={() => navigate("new-run")}
              onSelectRun={(runId) => {
                setSelectedRunId(runId);
                navigate("monitoring");
              }}
            />
          )}
          {activeView === "new-run" && (
            <NewRunView
              onManageModels={() => navigate("models")}
              onRunStarted={(runId) => {
                setSelectedRunId(runId);
                showToast(`Run ${runId.slice(0, 8)} queued.`);
                navigate("monitoring");
              }}
            />
          )}
          {activeView === "monitoring" && (
            <MonitoringView
              onNewRun={() => navigate("new-run")}
              trackedRunId={selectedRunId}
              onSelectRun={setSelectedRunId}
            />
          )}
          {activeView === "models" && <ModelsView onToast={showToast} />}
          {activeView === "settings" && <SettingsView />}
        </main>
      </div>

      {toast && (
        <div role="status" aria-live="polite" className="fixed bottom-5 left-1/2 z-[80] flex -translate-x-1/2 items-center gap-2.5 rounded-xl border border-white/10 bg-[#151e26] px-4 py-3 text-xs text-slate-200 shadow-2xl">
          <span className="grid size-5 place-items-center rounded-full bg-lime-300/10 text-lime-200"><CheckIcon /></span>
          {toast}
        </div>
      )}
    </div>
  );
}

function CheckIcon() {
  return <span aria-hidden="true" className="text-[11px] font-bold">✓</span>;
}
