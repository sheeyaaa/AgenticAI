"use client";

import { useCallback, useEffect, useState } from "react";
import {
  CircleAlert,
  KeyRound,
  LockKeyhole,
  RefreshCw,
  Save,
  Signal,
  SignalHigh,
  Sparkles,
} from "lucide-react";
import { PageHeading } from "@/components/page-heading";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, type ModelRoleSetting, type ModelsConfigRequest } from "@/lib/api";
import {
  agentRoles,
  providerLabels,
  providerModels,
  providers,
  roleDetails,
  type AgentRole,
  type Provider,
} from "@/lib/types";

type ConnectionState = "connected" | "missing" | "failed" | "checking" | "not-tested";
type CredentialEdits = Partial<Record<AgentRole, string | null>>;
type ConnectionStates = Record<AgentRole, ConnectionState>;

const initialConnections: ConnectionStates = {
  extractor: "not-tested",
  generator: "not-tested",
  critic: "not-tested",
  selenium: "not-tested",
};

function isProvider(value: string): value is Provider {
  return providers.includes(value as Provider);
}

export function ModelsView({ onToast }: { onToast: (message: string) => void }) {
  const [settings, setSettings] = useState<Record<AgentRole, ModelRoleSetting> | null>(null);
  const [credentialEdits, setCredentialEdits] = useState<CredentialEdits>({});
  const [dirty, setDirty] = useState(false);
  const [connections, setConnections] = useState<ConnectionStates>(initialConnections);
  const [connectionMessages, setConnectionMessages] = useState<Partial<Record<AgentRole, string>>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const loadSettings = useCallback(async () => {
    setLoading(true);
    api.modelConfig()
      .then((response) => {
        setSettings(response.roles);
        setError(null);
      })
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "Could not load model settings.");
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => void loadSettings(), 0);
    return () => {
      window.clearTimeout(initialLoad);
    };
  }, [loadSettings]);

  function updateProvider(role: AgentRole, provider: Provider) {
    if (!settings) return;
    setSettings((current) => current && ({
      ...current,
      [role]: { ...current[role], provider, model: providerModels[provider][0] },
    }));
    setCredentialEdits((current) => ({ ...current, [role]: null }));
    setDirty(true);
    setConnections((current) => ({ ...current, [role]: "not-tested" }));
    setConnectionMessages((current) => ({ ...current, [role]: undefined }));
  }

  function updateModel(role: AgentRole, model: string) {
    setSettings((current) => current && ({
      ...current,
      [role]: { ...current[role], model },
    }));
    setDirty(true);
    setConnections((current) => ({ ...current, [role]: "not-tested" }));
    setConnectionMessages((current) => ({ ...current, [role]: undefined }));
  }

  async function saveSettings() {
    if (!settings || saving) return;
    setSaving(true);
    setSaveError(null);
    try {
      const roleRequest = (role: AgentRole) => ({
        provider: settings[role].provider,
        model: settings[role].model,
        ...(Object.prototype.hasOwnProperty.call(credentialEdits, role)
          ? { credential_ref: credentialEdits[role] }
          : {}),
      });
      const roles: ModelsConfigRequest["roles"] = {
        extractor: roleRequest("extractor"),
        generator: roleRequest("generator"),
        critic: roleRequest("critic"),
        selenium: roleRequest("selenium"),
      };
      const response = await api.saveModelConfig({ roles });
      setSettings(response.roles);
      setCredentialEdits({});
      setDirty(false);
      setConnections(initialConnections);
      setConnectionMessages({});
      onToast("Model settings saved.");
    } catch (reason) {
      setSaveError(reason instanceof Error ? reason.message : "Could not save model settings.");
    } finally {
      setSaving(false);
    }
  }

  async function testConnections() {
    if (testing) return;
    setTesting(true);
    setConnectionMessages({});
    for (const role of agentRoles) {
      setConnections((current) => ({ ...current, [role]: "checking" }));
      try {
        const result = await api.testModel(role);
        setConnections((current) => ({
          ...current,
          [role]: !result.configured ? "missing" : result.reachable ? "connected" : "failed",
        }));
        setConnectionMessages((current) => ({ ...current, [role]: result.message }));
      } catch (reason) {
        setConnections((current) => ({ ...current, [role]: "failed" }));
        setConnectionMessages((current) => ({
          ...current,
          [role]: reason instanceof Error ? reason.message : "Provider test failed.",
        }));
      }
    }
    setTesting(false);
  }

  return (
    <div className="space-y-6">
      <PageHeading
        eyebrow="Runtime"
        title="Model configuration"
        description="Choose a provider and model for each pipeline role. Credentials stay on the server."
        action={
          <Button
            variant="outline"
            onClick={() => void testConnections()}
            disabled={testing || loading || dirty || !settings}
            className="border-white/[0.09] bg-white/[0.02] text-slate-300"
          >
            <RefreshCw className={`size-3.5 ${testing ? "animate-spin" : ""}`} />
            {testing ? "Testing…" : "Test configured providers"}
          </Button>
        }
      />

      <div className="flex items-start gap-3 rounded-xl border border-sky-300/10 bg-sky-300/[0.04] px-4 py-3.5">
        <LockKeyhole className="mt-0.5 size-4 shrink-0 text-sky-200" />
        <div className="min-w-0">
          <p className="text-xs font-medium text-sky-100">Server-side credentials</p>
          <p className="mt-1 text-[11px] leading-5 text-slate-400">
            Enter environment variable names such as GEMINI_API_KEY or GROQ1, not API key values.
            The backend resolves these references; key values are never sent to or returned by this page.
          </p>
        </div>
      </div>

      {error && (
        <div role="alert" className="flex flex-col gap-3 rounded-xl border border-rose-300/15 bg-rose-300/[0.045] p-4 sm:flex-row sm:items-center">
          <CircleAlert className="size-4 shrink-0 text-rose-300" />
          <p className="min-w-0 flex-1 break-words text-xs text-rose-100">{error}</p>
          <Button variant="outline" size="sm" onClick={() => void loadSettings()} className="border-rose-200/15 bg-transparent text-rose-100">
            Retry
          </Button>
        </div>
      )}

      {loading ? (
        <div className="flex min-h-56 items-center justify-center gap-2 text-xs text-slate-500">
          <RefreshCw className="size-4 animate-spin text-lime-200" /> Loading model settings…
        </div>
      ) : settings ? (
        <>
          <div className="grid gap-4 xl:grid-cols-2">
            {agentRoles.map((role, index) => (
              <ModelCard
                key={role}
                role={role}
                index={index + 1}
                setting={settings[role]}
                credentialEdit={credentialEdits[role]}
                connection={connections[role]}
                connectionMessage={connectionMessages[role]}
                onProviderChange={(provider) => updateProvider(role, provider)}
                onModelChange={(model) => updateModel(role, model)}
                onCredentialEdit={(value) => {
                  setCredentialEdits((current) => ({ ...current, [role]: value }));
                  setDirty(true);
                }}
                onClearCredential={() => {
                  setCredentialEdits((current) => ({ ...current, [role]: null }));
                  setDirty(true);
                }}
              />
            ))}
          </div>

          {saveError && (
            <p role="alert" className="rounded-lg border border-rose-300/15 bg-rose-300/[0.04] px-3.5 py-3 text-xs text-rose-200">
              Could not save settings: {saveError}
            </p>
          )}

          <div className="flex flex-col-reverse gap-3 border-t border-white/[0.06] pt-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-[11px] text-slate-600">Credential references are stored server-side; raw keys are not accepted here.</p>
            <Button onClick={() => void saveSettings()} disabled={saving || !dirty} className="gap-2 bg-lime-300 text-slate-950 hover:bg-lime-200 disabled:bg-lime-300/30 disabled:text-slate-500">
              <Save className={`size-3.5 ${saving ? "animate-pulse" : ""}`} />
              {saving ? "Saving…" : "Save model settings"}
            </Button>
          </div>
        </>
      ) : null}
    </div>
  );
}

function ModelCard({
  role,
  index,
  setting,
  credentialEdit,
  connection,
  connectionMessage,
  onProviderChange,
  onModelChange,
  onCredentialEdit,
  onClearCredential,
}: {
  role: AgentRole;
  index: number;
  setting: ModelRoleSetting;
  credentialEdit: string | null | undefined;
  connection: ConnectionState;
  connectionMessage?: string;
  onProviderChange: (provider: Provider) => void;
  onModelChange: (model: string) => void;
  onCredentialEdit: (value: string) => void;
  onClearCredential: () => void;
}) {
  const details = roleDetails[role];
  const isLocal = setting.provider === "ollama";
  const value = typeof credentialEdit === "string" ? credentialEdit : "";
  const availableModels = providerModels[setting.provider].includes(setting.model)
    ? providerModels[setting.provider]
    : [setting.model, ...providerModels[setting.provider]];
  return (
    <Card className="dashboard-card overflow-hidden">
      <CardHeader className="flex flex-row items-start justify-between gap-3 px-5 pb-4 pt-5 sm:px-6">
        <div className="flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-white/[0.07] bg-white/[0.035] text-[10px] font-semibold" style={{ color: details.color }}>
            {details.initials}
          </span>
          <div>
            <CardTitle className="text-sm font-semibold text-slate-100">{details.label}</CardTitle>
            <p className="mt-1 text-[11px] text-slate-500">{details.description}</p>
          </div>
        </div>
        <ConnectionBadge state={connection} />
      </CardHeader>
      <CardContent className="space-y-4 px-5 pb-5 sm:px-6">
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-2">
            <label className="text-[11px] font-medium text-slate-400" htmlFor={`${role}-provider`}>Provider</label>
            <Select value={setting.provider} onValueChange={(selected) => {
              if (selected && isProvider(selected)) onProviderChange(selected);
            }}>
              <SelectTrigger id={`${role}-provider`} className="h-9 w-full border-white/[0.08] bg-[#0a1016] text-xs text-slate-200">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {providers.map((provider) => (
                  <SelectItem key={provider} value={provider}>{providerLabels[provider]}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <label className="text-[11px] font-medium text-slate-400" htmlFor={`${role}-model`}>Model</label>
            <Select value={setting.model} onValueChange={(model) => model && onModelChange(model)}>
              <SelectTrigger id={`${role}-model`} className="h-9 w-full border-white/[0.08] bg-[#0a1016] text-xs text-slate-200">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {availableModels.map((model) => (
                  <SelectItem key={model} value={model}>{model}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <label className="text-[11px] font-medium text-slate-400" htmlFor={`${role}-credential-ref`}>
              {isLocal ? "Credential reference" : "Environment variable reference"}
            </label>
            {setting.credential_ref_masked && credentialEdit === undefined && (
              <span className="inline-flex items-center gap-1.5 text-[10px] text-emerald-300">
                <LockKeyhole className="size-3" />
                {setting.credential_configured ? "Configured" : "Missing"} · {setting.credential_ref_masked}
              </span>
            )}
          </div>
          <div className="relative">
            <KeyRound className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-slate-600" />
            <Input
              id={`${role}-credential-ref`}
              type="text"
              autoComplete="off"
              value={value}
              onChange={(event) => onCredentialEdit(event.target.value)}
              placeholder={isLocal ? "Not required for Ollama" : "e.g. GEMINI_API_KEY"}
              disabled={isLocal}
              className="h-9 border-white/[0.08] bg-[#0a1016] pl-9 pr-10 font-mono text-xs text-slate-200 placeholder:font-sans placeholder:text-slate-600"
            />
          </div>
          <div className="flex items-center justify-between gap-3">
            <p className="text-[10px] text-slate-600">
              {isLocal
                ? "Ollama does not require an API credential."
                : credentialEdit === null
                  ? "The saved credential reference will be removed."
                  : credentialEdit === undefined && setting.credential_configured
                    ? "Leave empty to keep the configured environment reference."
                    : "Enter an environment variable name, never the secret value."}
            </p>
            {!isLocal && setting.credential_ref_masked && credentialEdit !== null && (
              <button type="button" onClick={onClearCredential} className="shrink-0 text-[10px] text-slate-500 underline underline-offset-2 hover:text-rose-200">
                Clear
              </button>
            )}
          </div>
        </div>

        {connectionMessage && (
          <p className={`text-[10px] ${connection === "connected" ? "text-emerald-200" : "text-slate-500"}`}>
            {connectionMessage}
          </p>
        )}

        <div className="flex items-center justify-between border-t border-white/[0.055] pt-3">
          <span className="inline-flex items-center gap-1.5 text-[10px] text-slate-600">
            <Signal className="size-3.5" /> Role {String(index).padStart(2, "0")}
          </span>
          <span className="inline-flex items-center gap-1.5 text-[10px] text-slate-500">
            <Sparkles className="size-3" /> Sequential stage
          </span>
        </div>
      </CardContent>
    </Card>
  );
}

function ConnectionBadge({ state }: { state: ConnectionState }) {
  if (state === "connected") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-300/15 bg-emerald-300/[0.06] px-2.5 py-1 text-[10px] font-medium text-emerald-200">
        <SignalHigh className="size-3" /> Connected
      </span>
    );
  }
  if (state === "missing") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-300/15 bg-amber-300/[0.05] px-2.5 py-1 text-[10px] font-medium text-amber-200">
        <CircleAlert className="size-3" /> Key required
      </span>
    );
  }
  if (state === "failed") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-rose-300/15 bg-rose-300/[0.05] px-2.5 py-1 text-[10px] font-medium text-rose-200">
        <CircleAlert className="size-3" /> Unreachable
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.03] px-2.5 py-1 text-[10px] text-slate-400">
      <span className={`size-1.5 rounded-full ${state === "checking" ? "animate-pulse bg-lime-200" : "bg-slate-500"}`} />
      {state === "checking" ? "Checking" : "Not tested"}
    </span>
  );
}
