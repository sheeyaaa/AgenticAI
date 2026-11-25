import { cn } from "@/lib/utils";
import type { RunStatus } from "@/lib/types";

const statusLabel: Record<RunStatus, string> = {
  completed: "Completed",
  failed: "Failed",
  running: "Running",
  queued: "Queued",
};

const statusStyle: Record<RunStatus, string> = {
  completed: "border-emerald-400/20 bg-emerald-400/10 text-emerald-300",
  failed: "border-rose-400/20 bg-rose-400/10 text-rose-300",
  running: "border-lime-300/20 bg-lime-300/10 text-lime-200",
  queued: "border-slate-400/20 bg-slate-400/10 text-slate-300",
};

export function StatusPill({ status }: { status: RunStatus }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium",
        statusStyle[status],
      )}
    >
      <span
        className={cn(
          "size-1.5 rounded-full bg-current",
          status === "running" && "animate-pulse",
        )}
      />
      {statusLabel[status]}
    </span>
  );
}
