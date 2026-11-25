import {
  Activity,
  CheckCircle2,
  Clock3,
  FileText,
  XCircle,
} from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

const iconMap = {
  runs: FileText,
  completed: CheckCircle2,
  failed: XCircle,
  active: Activity,
  runtime: Clock3,
} as const;

const toneMap = {
  lime: "bg-lime-300/10 text-lime-200 ring-lime-200/10",
  teal: "bg-teal-300/10 text-teal-200 ring-teal-200/10",
  rose: "bg-rose-300/10 text-rose-200 ring-rose-200/10",
  violet: "bg-violet-300/10 text-violet-200 ring-violet-200/10",
  amber: "bg-amber-300/10 text-amber-200 ring-amber-200/10",
} as const;

export function MetricCard({
  label,
  value,
  detail,
  tone,
  icon,
}: {
  label: string;
  value: string;
  detail: string;
  tone: keyof typeof toneMap;
  icon: keyof typeof iconMap;
}) {
  const Icon = iconMap[icon];
  return (
    <Card className="dashboard-card overflow-hidden">
      <CardContent className="relative p-4 sm:p-5">
        <div className="flex items-start justify-between gap-2">
          <p className="text-xs font-medium text-slate-400">{label}</p>
          <span className={`grid size-8 shrink-0 place-items-center rounded-lg ring-1 ${toneMap[tone]}`}>
            <Icon className="size-4" strokeWidth={1.8} />
          </span>
        </div>
        <p className="mt-4 text-2xl font-semibold tracking-tight text-slate-50 sm:text-[27px]">
          {value}
        </p>
        <p className="mt-1 text-[11px] text-slate-500">{detail}</p>
      </CardContent>
    </Card>
  );
}
