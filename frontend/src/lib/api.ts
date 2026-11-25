import type { AgentRole, Provider, RunStatus } from "./types";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type RunRecord = {
  run_id: string;
  filename: string;
  status: RunStatus;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  execution_time_seconds: number | null;
  error_type: string | null;
  error_message: string | null;
  architecture: "blackboard";
  orchestration_pattern: "sequential";
};

export type SampleItem = {
  id: string;
  name: string;
  filename: string;
};

export type ModelRoleSetting = {
  provider: Provider;
  model: string;
  credential_configured: boolean;
  credential_ref_masked: string | null;
};

export type ModelsConfigResponse = {
  roles: Record<AgentRole, ModelRoleSetting>;
};

export type ModelsConfigRequest = {
  roles: Record<
    AgentRole,
    { provider: Provider; model: string; credential_ref?: string | null }
  >;
};

export type ProviderTestResponse = {
  role: AgentRole;
  provider: Provider;
  model: string;
  configured: boolean;
  reachable: boolean;
  model_available: boolean | null;
  error_type: string | null;
  message: string;
  credential_ref_masked: string | null;
};

export type MonitoringEvent = {
  run_id: string;
  trace_id: string;
  event_id: string;
  timestamp: string;
  agent_name: string;
  orchestration_pattern: string;
  event_type: string;
  status: string;
  duration_ms: number | null;
  parent_agent: string;
  parent_task_id: string;
  input_summary: string;
  output_summary: string;
  error_type: string;
  error_message: string;
  retry_count: number;
  metadata: Record<string, unknown>;
};

export type RequirementPoint = {
  id: string;
  text: string;
  source_chunk_id: string;
  acceptance_criteria: string[];
  source_section?: string;
};

export type TestCaseItem = {
  id: string;
  req_ids: string[];
  title: string;
  preconditions: string[];
  steps: string[];
  expected_result: string;
  type: "positive" | "negative" | "edge";
  priority: "high" | "medium" | "low";
};

export type CoverageReport = {
  covered_requirement_ids: string[];
  uncovered_requirement_ids: string[];
  missing_positive_requirement_ids?: string[];
  missing_negative_requirement_ids?: string[];
  missing_edge_requirement_ids?: string[];
  invalid_requirement_ids?: string[];
  behaviorally_verified_requirement_ids?: string[];
  score: number;
};

export type SeleniumScript = {
  test_case_id: string;
  filename: string;
  code: string;
  locators: Array<{ strategy: string; value: string }>;
};

export type ValidationReport = {
  valid: boolean;
  script_results?: Record<string, string[]>;
  errors: string[];
  validated_count: number;
  rejected_count?: number;
};

export type RunReport = {
  run_id?: string | null;
  source_path: string;
  iterations: number;
  final_quality_score: number;
  final_coverage_score: number;
  deterministic_coverage_percent: number;
  remaining_gaps: Record<string, string[]>;
  requirement_count: number;
  test_case_count: number;
  script_count?: number;
  elapsed_seconds: number;
  estimated_token_counts: Record<string, number>;
  estimated_api_cost_usd?: number | null;
  scripts_validated: number;
  scripts_rejected?: number;
  execution_mode?: string;
  models_used?: Record<string, string>;
  diagnostics?: string[];
};

export type RunResultsResponse = {
  run: RunRecord;
  requirements: RequirementPoint[];
  test_cases: TestCaseItem[];
  coverage: CoverageReport | null;
  selenium_scripts: SeleniumScript[];
  validation_report: ValidationReport | null;
  run_report: RunReport | null;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        ...(init?.body instanceof FormData
          ? {}
          : { "Content-Type": "application/json" }),
        ...init?.headers,
      },
      cache: "no-store",
    });
  } catch (reason) {
    if (reason instanceof TypeError) {
      throw new Error(
        `Cannot reach the API at ${API_BASE_URL}. Start FastAPI and ensure CORS_ORIGINS includes this frontend origin.`,
      );
    }
    throw reason;
  }
  const bodyText = await response.text();
  if (!response.ok) {
    let body: unknown;
    try {
      body = JSON.parse(bodyText);
    } catch {
      throw new Error(bodyText || `Request failed with status ${response.status}`);
    }
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? String(body.detail)
        : `Request failed with status ${response.status}`;
    throw new Error(detail);
  }
  return JSON.parse(bodyText) as T;
}

export const api = {
  health: () =>
    request<{
      status: "ok";
      service: string;
      architecture: "blackboard";
      orchestration_pattern: "sequential";
    }>("/health"),
  samples: () => request<{ items: SampleItem[] }>("/api/samples"),
  uploadPrd: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<{ upload_id: string; filename: string; size_bytes: number }>(
      "/api/upload-prd",
      { method: "POST", body: form },
    );
  },
  startRun: (source: { upload_id: string } | { sample_id: string }) =>
    request<RunRecord>("/api/run", {
      method: "POST",
      body: JSON.stringify(source),
    }),
  runs: (limit = 50, offset = 0) =>
    request<{ items: RunRecord[]; total: number }>(
      `/api/runs?limit=${limit}&offset=${offset}`,
    ),
  async allRuns() {
    const fetchPage = (offset: number) =>
      request<{ items: RunRecord[]; total: number }>(
        `/api/runs?limit=100&offset=${offset}`,
      );
    const firstPage = await fetchPage(0);
    const items = [...firstPage.items];
    let total = firstPage.total;
    while (items.length < total) {
      const nextPage = await fetchPage(items.length);
      if (nextPage.items.length === 0) break;
      items.push(...nextPage.items);
      total = nextPage.total;
    }
    return { items, total };
  },
  run: (runId: string) => request<RunRecord>(`/api/runs/${runId}`),
  results: (runId: string) =>
    request<RunResultsResponse>(`/api/runs/${runId}/results`),
  events: (runId: string) =>
    request<{ run_id: string; events: MonitoringEvent[] }>(
      `/api/runs/${runId}/events`,
    ),
  modelConfig: () => request<ModelsConfigResponse>("/api/models/config"),
  saveModelConfig: (config: ModelsConfigRequest) =>
    request<ModelsConfigResponse>("/api/models/config", {
      method: "PUT",
      body: JSON.stringify(config),
    }),
  testModel: (role: AgentRole) =>
    request<ProviderTestResponse>("/api/models/test", {
      method: "POST",
      body: JSON.stringify({ role }),
    }),
};
