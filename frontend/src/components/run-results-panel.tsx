"use client";

import { useState } from "react";
import {
  Check,
  CheckCircle2,
  Code2,
  Copy,
  FileCheck2,
  ListChecks,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { RunResultsResponse } from "@/lib/api";
import { formatDuration } from "@/lib/format";

type ResultsTab = "test_cases" | "requirements" | "scripts" | "coverage";

export function RunResultsPanel({ results }: { results: RunResultsResponse }) {
  const [activeTab, setActiveTab] = useState<ResultsTab>("test_cases");
  const [copiedScript, setCopiedScript] = useState<string | null>(null);

  const report = results.run_report;
  const coverage = results.coverage;
  const validation = results.validation_report;

  const coveragePercent = report
    ? Math.round(report.deterministic_coverage_percent)
    : coverage
      ? Math.round(coverage.score * 100)
      : 0;
  const qualityPercent = report ? Math.round(report.final_quality_score * 100) : null;

  async function copyCode(filename: string, code: string) {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedScript(filename);
      window.setTimeout(() => setCopiedScript(null), 2000);
    } catch {
      // Clipboard API may be unavailable in non-secure contexts.
    }
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryStat
          label="Requirements"
          value={String(results.requirements.length)}
          subtext={report ? `${report.iterations} critic iteration${report.iterations === 1 ? "" : "s"}` : "Extracted from PRD"}
        />
        <SummaryStat
          label="Test cases"
          value={String(results.test_cases.length)}
          subtext={qualityPercent !== null ? `Quality score ${qualityPercent}%` : "Generated"}
        />
        <SummaryStat
          label="Coverage"
          value={`${coveragePercent}%`}
          subtext={
            coverage
              ? `${coverage.covered_requirement_ids.length} covered · ${coverage.uncovered_requirement_ids.length} uncovered`
              : "Requirement coverage"
          }
        />
        <SummaryStat
          label="Selenium scripts"
          value={String(results.selenium_scripts.length)}
          subtext={
            validation
              ? `${validation.validated_count} validated${validation.rejected_count ? ` · ${validation.rejected_count} rejected` : ""}`
              : report
                ? `Completed in ${formatDuration(report.elapsed_seconds)}`
                : "Generated"
          }
        />
      </div>

      <Card className="dashboard-card overflow-hidden">
        <CardHeader className="flex flex-col gap-3 border-b border-white/[0.06] px-5 pb-4 pt-5 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <div>
            <CardTitle className="flex items-center gap-2 text-sm font-semibold text-slate-100">
              <FileCheck2 className="size-4 text-lime-200" /> Pipeline results
            </CardTitle>
            <p className="mt-1 text-xs text-slate-500">
              Generated artifacts for {results.run.filename}
              {report?.elapsed_seconds !== undefined ? ` · ${formatDuration(report.elapsed_seconds)}` : ""}
            </p>
          </div>
          <div className="flex flex-wrap gap-1 rounded-lg border border-white/[0.07] bg-black/20 p-1">
            {(
              [
                { id: "test_cases", label: `Test cases (${results.test_cases.length})`, icon: ListChecks },
                { id: "requirements", label: `Requirements (${results.requirements.length})`, icon: CheckCircle2 },
                { id: "scripts", label: `Selenium (${results.selenium_scripts.length})`, icon: Code2 },
                { id: "coverage", label: "Coverage & report", icon: ShieldCheck },
              ] as const
            ).map((tab) => {
              const Icon = tab.icon;
              const active = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                  className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[11px] transition ${
                    active
                      ? "bg-lime-300/[0.12] font-medium text-lime-100"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  <Icon className="size-3.5" />
                  {tab.label}
                </button>
              );
            })}
          </div>
        </CardHeader>

        <CardContent className="p-5 sm:p-6">
          {activeTab === "test_cases" && (
            <div className="space-y-3">
              {results.test_cases.length === 0 ? (
                <EmptyState message="No test cases were generated for this run." />
              ) : (
                results.test_cases.map((tc) => (
                  <div
                    key={tc.id}
                    className="rounded-xl border border-white/[0.06] bg-[#0b1117]/75 p-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-[11px] font-semibold text-lime-200">{tc.id}</span>
                          <Badge
                            variant="outline"
                            className={`border-white/[0.08] text-[10px] capitalize ${
                              tc.type === "positive"
                                ? "bg-emerald-300/[0.08] text-emerald-200"
                                : tc.type === "negative"
                                  ? "bg-rose-300/[0.08] text-rose-200"
                                  : "bg-amber-300/[0.08] text-amber-200"
                            }`}
                          >
                            {tc.type}
                          </Badge>
                          <Badge variant="outline" className="border-white/[0.08] bg-white/[0.03] text-[10px] capitalize text-slate-400">
                            {tc.priority}
                          </Badge>
                        </div>
                        <p className="mt-1.5 text-xs font-medium text-slate-100">{tc.title}</p>
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {tc.req_ids.map((reqId) => (
                          <span
                            key={reqId}
                            className="rounded border border-white/[0.07] bg-white/[0.03] px-1.5 py-0.5 font-mono text-[10px] text-slate-400"
                          >
                            {reqId}
                          </span>
                        ))}
                      </div>
                    </div>
                    {tc.preconditions.length > 0 && (
                      <p className="mt-2.5 text-[11px] text-slate-400">
                        <span className="font-medium text-slate-300">Preconditions:</span> {tc.preconditions.join("; ")}
                      </p>
                    )}
                    {tc.steps.length > 0 && (
                      <ol className="mt-2.5 list-inside list-decimal space-y-1 text-[11px] text-slate-300">
                        {tc.steps.map((step, index) => (
                          <li key={index}>{step}</li>
                        ))}
                      </ol>
                    )}
                    <p className="mt-2.5 rounded-lg border border-white/[0.05] bg-white/[0.02] px-3 py-2 text-[11px] text-slate-300">
                      <span className="font-medium text-slate-200">Expected:</span> {tc.expected_result}
                    </p>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === "requirements" && (
            <div className="space-y-3">
              {results.requirements.length === 0 ? (
                <EmptyState message="No requirements were extracted." />
              ) : (
                results.requirements.map((req) => (
                  <div
                    key={req.id}
                    className="rounded-xl border border-white/[0.06] bg-[#0b1117]/75 p-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-mono text-[11px] font-semibold text-lime-200">{req.id}</span>
                      <span className="font-mono text-[10px] text-slate-500">
                        {req.source_section || req.source_chunk_id}
                      </span>
                    </div>
                    <p className="mt-1.5 text-xs leading-5 text-slate-200">{req.text}</p>
                    {req.acceptance_criteria.length > 0 && (
                      <ul className="mt-2.5 list-inside list-disc space-y-1 text-[11px] text-slate-400">
                        {req.acceptance_criteria.map((criterion, index) => (
                          <li key={index}>{criterion}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === "scripts" && (
            <div className="space-y-4">
              {results.selenium_scripts.length === 0 ? (
                <EmptyState message="No Selenium scripts were generated for this run." />
              ) : (
                results.selenium_scripts.map((script) => (
                  <div
                    key={`${script.test_case_id}-${script.filename}`}
                    className="overflow-hidden rounded-xl border border-white/[0.07] bg-[#080d12]"
                  >
                    <div className="flex items-center justify-between gap-3 border-b border-white/[0.06] bg-white/[0.02] px-4 py-2.5">
                      <div className="flex min-w-0 items-center gap-2">
                        <Code2 className="size-3.5 shrink-0 text-lime-200" />
                        <span className="truncate font-mono text-xs font-medium text-slate-200">{script.filename}</span>
                        <span className="rounded border border-white/[0.08] bg-white/[0.03] px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
                          {script.test_case_id}
                        </span>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => void copyCode(script.filename, script.code)}
                        className="h-7 gap-1.5 px-2 text-[11px] text-slate-400 hover:text-slate-100"
                      >
                        {copiedScript === script.filename ? (
                          <>
                            <Check className="size-3 text-emerald-300" /> Copied
                          </>
                        ) : (
                          <>
                            <Copy className="size-3" /> Copy
                          </>
                        )}
                      </Button>
                    </div>
                    <pre className="max-h-80 overflow-auto p-4 font-mono text-[11px] leading-5 text-slate-300">
                      <code>{script.code}</code>
                    </pre>
                  </div>
                ))
              )}
            </div>
          )}

          {activeTab === "coverage" && (
            <div className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="rounded-xl border border-white/[0.06] bg-[#0b1117]/75 p-4">
                  <div className="flex items-center gap-2 text-xs font-semibold text-slate-100">
                    {validation?.valid ? (
                      <ShieldCheck className="size-4 text-emerald-300" />
                    ) : (
                      <ShieldAlert className="size-4 text-amber-300" />
                    )}
                    Script validation
                  </div>
                  {validation ? (
                    <div className="mt-3 space-y-2 text-xs text-slate-300">
                      <p>
                        Status:{" "}
                        <span className={validation.valid ? "text-emerald-300" : "text-amber-300"}>
                          {validation.valid ? "All scripts valid" : "Validation issues found"}
                        </span>
                      </p>
                      <p className="text-[11px] text-slate-400">
                        Validated: {validation.validated_count} · Rejected: {validation.rejected_count ?? 0}
                      </p>
                      {validation.errors.length > 0 && (
                        <ul className="mt-2 list-inside list-disc space-y-1 text-[11px] text-rose-300">
                          {validation.errors.map((err, index) => (
                            <li key={index}>{err}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ) : (
                    <p className="mt-2 text-xs text-slate-500">No validation report recorded.</p>
                  )}
                </div>

                <div className="rounded-xl border border-white/[0.06] bg-[#0b1117]/75 p-4">
                  <p className="text-xs font-semibold text-slate-100">Requirement coverage</p>
                  {coverage ? (
                    <div className="mt-3 space-y-2 text-[11px]">
                      <p className="text-slate-300">
                        Covered ({coverage.covered_requirement_ids.length}):{" "}
                        <span className="font-mono text-emerald-300">
                          {coverage.covered_requirement_ids.join(", ") || "None"}
                        </span>
                      </p>
                      <p className="text-slate-300">
                        Uncovered ({coverage.uncovered_requirement_ids.length}):{" "}
                        <span className="font-mono text-amber-300">
                          {coverage.uncovered_requirement_ids.join(", ") || "None"}
                        </span>
                      </p>
                    </div>
                  ) : (
                    <p className="mt-2 text-xs text-slate-500">No coverage report recorded.</p>
                  )}
                </div>
              </div>

              {report && (
                <div className="rounded-xl border border-white/[0.06] bg-[#0b1117]/75 p-4 text-xs">
                  <p className="font-semibold text-slate-100">Run summary</p>
                  <div className="mt-3 grid gap-2 text-[11px] text-slate-400 sm:grid-cols-3">
                    <p>Mode: <span className="text-slate-200">{report.execution_mode ?? "—"}</span></p>
                    <p>
                      Tokens:{" "}
                      <span className="text-slate-200">
                        {(report.estimated_token_counts.input_tokens ?? 0) + (report.estimated_token_counts.output_tokens ?? 0)}
                      </span>
                    </p>
                    <p>
                      Estimated cost:{" "}
                      <span className="text-slate-200">
                        {report.estimated_api_cost_usd != null ? `$${report.estimated_api_cost_usd.toFixed(4)}` : "N/A"}
                      </span>
                    </p>
                  </div>
                  {report.diagnostics && report.diagnostics.length > 0 && (
                    <ul className="mt-3 list-inside list-disc space-y-1 text-[11px] text-slate-400">
                      {report.diagnostics.map((diag, index) => (
                        <li key={index}>{diag}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function SummaryStat({ label, value, subtext }: { label: string; value: string; subtext: string }) {
  return (
    <Card className="dashboard-card">
      <CardContent className="p-4">
        <p className="text-[10px] uppercase tracking-[0.12em] text-slate-500">{label}</p>
        <p className="mt-1.5 text-2xl font-semibold tabular-nums text-slate-100">{value}</p>
        <p className="mt-1 truncate text-[11px] text-slate-500">{subtext}</p>
      </CardContent>
    </Card>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex min-h-28 items-center justify-center rounded-xl border border-dashed border-white/[0.08] px-4 text-center text-xs text-slate-500">
      {message}
    </div>
  );
}
