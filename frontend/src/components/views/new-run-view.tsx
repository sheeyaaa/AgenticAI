"use client";

import { useEffect, useRef, useState } from "react";
import {
  ArrowUpRight,
  FilePlus2,
  FileText,
  FileUp,
  Info,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";
import { PageHeading } from "@/components/page-heading";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, type ModelsConfigResponse, type RunRecord, type SampleItem } from "@/lib/api";
import { agentRoles, providerLabels, roleDetails } from "@/lib/types";

const allowedTypes = [".pdf", ".md", ".txt", ".docx"];
const maxBytes = 10 * 1024 * 1024;

export function NewRunView({
  onManageModels,
  onRunStarted,
}: {
  onManageModels: () => void;
  onRunStarted: (runId: string) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [sourceMode, setSourceMode] = useState<"sample" | "upload">("sample");
  const [samples, setSamples] = useState<SampleItem[]>([]);
  const [selectedSample, setSelectedSample] = useState("");
  const [samplesLoading, setSamplesLoading] = useState(true);
  const [samplesError, setSamplesError] = useState<string | null>(null);
  const [modelConfig, setModelConfig] = useState<ModelsConfigResponse["roles"] | null>(null);
  const [modelError, setModelError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [uploadId, setUploadId] = useState<string | null>(null);
  const [preview, setPreview] = useState("");
  const [originalPreview, setOriginalPreview] = useState("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewUnavailable, setPreviewUnavailable] = useState(false);
  const [fileError, setFileError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [starting, setStarting] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api.samples()
      .then((response) => {
        if (!active) return;
        setSamples(response.items);
        setSelectedSample(response.items[0]?.id ?? "");
        setSamplesError(null);
      })
      .catch((reason: unknown) => {
        if (active) setSamplesError(reason instanceof Error ? reason.message : "Could not load sample PRDs.");
      })
      .finally(() => {
        if (active) setSamplesLoading(false);
      });
    api.modelConfig()
      .then((response) => {
        if (active) setModelConfig(response.roles);
      })
      .catch((reason: unknown) => {
        if (active) setModelError(reason instanceof Error ? reason.message : "Could not load model settings.");
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  async function chooseFile(nextFile?: File) {
    if (fileInput.current) fileInput.current.value = "";
    setFile(null);
    setUploadId(null);
    setFileError("");
    setPreview("");
    setOriginalPreview("");
    setPreviewUnavailable(false);
    setPreviewUrl(null);
    if (!nextFile) return;
    const extension = `.${nextFile.name.split(".").pop()?.toLowerCase() ?? ""}`;
    if (!allowedTypes.includes(extension)) {
      setFileError("Choose a PDF, Markdown, TXT, or DOCX PRD.");
      return;
    }
    if (nextFile.size === 0) {
      setFileError("The selected PRD is empty.");
      return;
    }
    if (nextFile.size > maxBytes) {
      setFileError("This file exceeds the 10 MB upload limit.");
      return;
    }
    setFile(nextFile);
    if (extension === ".md" || extension === ".txt") {
      try {
        const text = await nextFile.text();
        setPreview(text);
        setOriginalPreview(text);
      } catch {
        setFileError("The selected file could not be previewed.");
      }
    } else if (extension === ".pdf") {
      setPreviewUrl(URL.createObjectURL(nextFile));
    } else {
      setPreviewUnavailable(true);
    }
  }

  function removeFile() {
    setFile(null);
    setUploadId(null);
    setPreview("");
    setOriginalPreview("");
    setPreviewUrl(null);
    setPreviewUnavailable(false);
    setFileError("");
    if (fileInput.current) fileInput.current.value = "";
  }

  function handlePreviewChange(nextText: string) {
    setPreview(nextText);
    setUploadId(null);
    if (nextText.trim().length === 0) {
      setFileError("PRD content cannot be empty.");
    } else {
      setFileError("");
    }
  }

  const isTextEditable = Boolean(file && !previewUrl && !previewUnavailable);
  const isModified = isTextEditable && preview !== originalPreview;

  async function startExecution() {
    if (
      starting ||
      (sourceMode === "sample" && !selectedSample) ||
      (sourceMode === "upload" && (!file || (isTextEditable && preview.trim().length === 0)))
    ) {
      return;
    }
    setStarting(true);
    setRunError(null);
    try {
      let run: RunRecord;
      if (sourceMode === "sample") {
        run = await api.startRun({ sample_id: selectedSample });
      } else {
        if (!file) return;
        const fileToUpload = isTextEditable && isModified
          ? new File([preview], file.name, { type: file.type || "text/markdown" })
          : file;
        const id = uploadId ?? (await api.uploadPrd(fileToUpload)).upload_id;
        setUploadId(id);
        run = await api.startRun({ upload_id: id });
      }
      onRunStarted(run.run_id);
    } catch (reason) {
      setRunError(reason instanceof Error ? reason.message : "Could not start the PRD run.");
    } finally {
      setStarting(false);
    }
  }

  const selectedSampleItem = samples.find((sample) => sample.id === selectedSample);

  return (
    <div className="space-y-6">
      <PageHeading
        eyebrow="Pipeline"
        title="New PRD run"
        description="Choose a PRD source. Runs execute using the server-side pipeline configuration."
      />

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(330px,0.8fr)]">
        <div className="space-y-5">
          <Card className="dashboard-card">
            <CardHeader className="px-5 pb-3 pt-5 sm:px-6">
              <div>
                <CardTitle className="text-sm font-semibold text-slate-100">Choose a PRD</CardTitle>
                <p className="mt-1 text-xs text-slate-500">Select a bundled PRD or upload your own document.</p>
              </div>
              <div className="mt-4 flex w-fit rounded-lg border border-white/[0.07] bg-black/10 p-1">
                <button
                  type="button"
                  onClick={() => setSourceMode("sample")}
                  className={`rounded-md px-3 py-1.5 text-[11px] transition ${sourceMode === "sample" ? "bg-white/[0.09] font-medium text-slate-100" : "text-slate-500 hover:text-slate-300"}`}
                >
                  Existing PRD
                </button>
                <button
                  type="button"
                  onClick={() => setSourceMode("upload")}
                  className={`rounded-md px-3 py-1.5 text-[11px] transition ${sourceMode === "upload" ? "bg-white/[0.09] font-medium text-slate-100" : "text-slate-500 hover:text-slate-300"}`}
                >
                  Upload a file
                </button>
              </div>
            </CardHeader>
            <CardContent className="px-5 pb-5 sm:px-6">
              {sourceMode === "sample" ? (
                <div className="space-y-3">
                  <label htmlFor="sample-prd" className="text-[11px] font-medium text-slate-400">
                    PRDs available in the samples folder
                  </label>
                  {samplesLoading ? (
                    <div className="flex h-11 items-center gap-2 rounded-lg border border-white/[0.07] px-3 text-xs text-slate-500">
                      <RefreshCw className="size-3.5 animate-spin" /> Loading PRDs…
                    </div>
                  ) : samples.length ? (
                    <>
                      <Select value={selectedSample} onValueChange={(value) => value && setSelectedSample(value)}>
                        <SelectTrigger id="sample-prd" className="h-11 w-full border-white/[0.08] bg-[#0a1016] text-xs text-slate-200">
                          <SelectValue placeholder="Choose an existing PRD" />
                        </SelectTrigger>
                        <SelectContent>
                          {samples.map((sample) => (
                            <SelectItem key={sample.id} value={sample.id}>
                              {sample.name} · {sample.filename}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {selectedSampleItem && (
                        <div className="flex items-center gap-3 rounded-xl border border-white/[0.06] bg-white/[0.02] p-3.5">
                          <span className="grid size-9 place-items-center rounded-lg border border-white/[0.06] bg-white/[0.03] text-slate-400">
                            <FileText className="size-4" />
                          </span>
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-xs font-medium text-slate-200">{selectedSampleItem.name}</p>
                            <p className="mt-0.5 truncate text-[10px] text-slate-500">{selectedSampleItem.filename}</p>
                          </div>
                          <span className="rounded-full border border-emerald-300/15 bg-emerald-300/[0.05] px-2 py-1 text-[9px] text-emerald-200">Ready</span>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="rounded-xl border border-dashed border-white/[0.08] px-4 py-8 text-center">
                      <p className="text-xs text-slate-400">No sample PRDs were returned by the API.</p>
                      <p className="mt-1 text-[10px] text-slate-600">Add a Markdown PRD to the backend samples folder or upload a file.</p>
                      <Button variant="outline" size="sm" onClick={() => setSourceMode("upload")} className="mt-3 border-white/[0.09] text-slate-300">
                        Upload a PRD
                      </Button>
                    </div>
                  )}
                  {samplesError && (
                    <p role="alert" className="text-xs text-rose-300">Could not load existing PRDs: {samplesError}</p>
                  )}
                </div>
              ) : (
                <div className="space-y-3">
                  {!file ? (
                    <button
                      type="button"
                      className={`flex min-h-[220px] w-full flex-col items-center justify-center rounded-xl border border-dashed px-5 py-8 text-center transition ${
                        dragging
                          ? "border-lime-300/70 bg-lime-300/[0.07]"
                          : "border-slate-700/80 bg-[#0b1117]/80 hover:border-slate-500 hover:bg-white/[0.025]"
                      }`}
                      onClick={() => fileInput.current?.click()}
                      onDragOver={(event) => {
                        event.preventDefault();
                        setDragging(true);
                      }}
                      onDragLeave={() => setDragging(false)}
                      onDrop={(event) => {
                        event.preventDefault();
                        setDragging(false);
                        void chooseFile(event.dataTransfer.files[0]);
                      }}
                      aria-label="Choose or drop a PRD file"
                    >
                      <span className="grid size-12 place-items-center rounded-2xl border border-lime-200/10 bg-lime-300/[0.08] text-lime-200">
                        <FileUp className="size-5" />
                      </span>
                      <span className="mt-4 text-sm font-medium text-slate-200">Drag and drop your PRD here</span>
                      <span className="mt-1.5 text-xs text-slate-500">
                        or <span className="text-lime-200 underline underline-offset-2">browse files</span>
                      </span>
                      <span className="mt-5 flex flex-wrap justify-center gap-2">
                        {["PDF", "Markdown", "TXT", "DOCX"].map((kind) => (
                          <span key={kind} className="rounded-md border border-white/[0.07] bg-white/[0.025] px-2 py-1 text-[10px] text-slate-500">{kind}</span>
                        ))}
                      </span>
                    </button>
                  ) : (
                    <div className="rounded-xl border border-lime-200/15 bg-lime-300/[0.035] p-4">
                      <div className="flex items-start gap-3">
                        <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-lime-300/10 text-lime-200">
                          <FileText className="size-5" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-slate-100">{file.name}</p>
                          <p className="mt-1 text-xs text-slate-500">{(file.size / 1024).toFixed(0)} KB · Ready to upload</p>
                        </div>
                        <Button variant="ghost" size="icon-sm" onClick={removeFile} aria-label="Remove selected file" className="text-slate-500 hover:text-rose-300">
                          <X />
                        </Button>
                      </div>
                      <div className="mt-4 overflow-hidden rounded-lg border border-white/[0.06] bg-[#080d12]/65">
                        <div className="flex items-center justify-between border-b border-white/[0.06] px-3.5 py-2.5">
                          <span className="text-[11px] font-medium text-slate-300">
                            {isTextEditable ? "PRD content (editable)" : "Document preview"}
                          </span>
                          {isTextEditable && (
                            <div className="flex items-center gap-2">
                              {isModified && (
                                <button
                                  type="button"
                                  onClick={() => handlePreviewChange(originalPreview)}
                                  className="text-[10px] text-lime-200 hover:text-lime-100 underline underline-offset-2"
                                >
                                  Reset changes
                                </button>
                              )}
                              <span className="rounded border border-white/[0.08] bg-white/[0.03] px-1.5 py-0.5 text-[10px] text-slate-400">
                                {isModified ? "Modified" : "Editable"}
                              </span>
                            </div>
                          )}
                        </div>
                        {previewUrl ? (
                          <iframe src={previewUrl} title={`PDF preview of ${file.name}`} className="h-[360px] w-full rounded-b-lg bg-white" />
                        ) : previewUnavailable ? (
                          <div className="flex min-h-32 flex-col items-center justify-center px-6 text-center">
                            <ShieldCheck className="size-5 text-slate-500" />
                            <p className="mt-2 text-xs text-slate-400">DOCX content will be extracted by the backend after upload.</p>
                          </div>
                        ) : (
                          <Textarea
                            aria-label="Uploaded PRD content"
                            value={preview}
                            onChange={(event) => handlePreviewChange(event.target.value)}
                            rows={10}
                            className="min-h-48 w-full resize-y rounded-none border-0 bg-transparent p-3.5 font-mono text-[11px] leading-5 text-slate-200 focus-visible:ring-1 focus-visible:ring-lime-300/40"
                            placeholder="Edit PRD content before running the pipeline..."
                          />
                        )}
                      </div>
                    </div>
                  )}
                  <input
                    ref={fileInput}
                    type="file"
                    accept=".pdf,.md,.txt,.docx,application/pdf,text/markdown,text/plain"
                    className="sr-only"
                    onChange={(event) => void chooseFile(event.target.files?.[0])}
                  />
                  {fileError && (
                    <p role="alert" className="flex items-center gap-2 text-xs text-rose-300">
                      <Info className="size-3.5" /> {fileError}
                    </p>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="dashboard-card">
            <CardHeader className="px-5 pb-3 pt-5 sm:px-6">
              <CardTitle className="text-sm font-semibold text-slate-100">Configured pipeline models</CardTitle>
              <p className="mt-1 text-xs text-slate-500">These server-side models will be used for this run.</p>
            </CardHeader>
            <CardContent className="grid gap-2 px-5 pb-5 sm:grid-cols-2 sm:px-6">
              {modelError && <p role="alert" className="text-xs text-rose-300 sm:col-span-2">Could not load model configuration: {modelError}</p>}
              {!modelConfig && !modelError && <p className="text-xs text-slate-500 sm:col-span-2">Loading model configuration…</p>}
              {modelConfig && agentRoles.map((role) => {
                const setting = modelConfig[role];
                return (
                  <div key={role} className="flex min-w-0 items-center gap-2.5 rounded-lg border border-white/[0.055] bg-white/[0.018] p-3">
                    <span className="grid size-7 shrink-0 place-items-center rounded-md bg-white/[0.035] text-[9px] font-semibold" style={{ color: roleDetails[role].color }}>
                      {roleDetails[role].initials}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-[10px] text-slate-500">{roleDetails[role].label}</p>
                      <p className="truncate text-[11px] font-medium text-slate-200">{providerLabels[setting.provider]} · {setting.model}</p>
                    </div>
                    <span className={`size-1.5 shrink-0 rounded-full ${setting.provider === "ollama" || setting.credential_configured ? "bg-emerald-300" : "bg-amber-300"}`} title={setting.credential_configured ? "Credential configured" : "Credential not configured"} />
                  </div>
                );
              })}
              <Button variant="ghost" size="sm" onClick={onManageModels} className="justify-start gap-1.5 px-1 text-[11px] text-lime-200 hover:text-lime-100 sm:col-span-2">
                Manage model settings <ArrowUpRight className="size-3.5" />
              </Button>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-5 xl:sticky xl:top-6">
          <Card className="overflow-hidden border-lime-200/10 bg-[linear-gradient(145deg,rgba(184,243,107,.07),rgba(16,23,30,.8)_58%)]">
            <CardContent className="p-5">
              <div className="flex items-start gap-3">
                <span className="grid size-9 place-items-center rounded-xl border border-lime-200/10 bg-lime-300/[0.08] text-lime-200">
                  <ShieldCheck className="size-4" />
                </span>
                <div>
                  <p className="text-xs font-semibold text-slate-100">Sequential blackboard pipeline</p>
                  <p className="mt-1 text-[11px] leading-5 text-slate-500">Extractor → Generator → Critic → Selenium writer</p>
                </div>
              </div>
              <p className="mt-4 border-t border-white/[0.06] pt-3 text-[10px] leading-5 text-slate-500">
                The API stores uploaded files on the backend and uses server-side model credentials.
              </p>
            </CardContent>
          </Card>

          {runError && (
            <div role="alert" className="rounded-xl border border-rose-300/15 bg-rose-300/[0.045] p-3.5">
              <p className="text-xs font-medium text-rose-200">Run could not be started</p>
              <p className="mt-1 break-words text-[11px] text-slate-400">{runError}</p>
            </div>
          )}

          <Button
            onClick={() => void startExecution()}
            disabled={
              starting ||
              (sourceMode === "sample" && (!selectedSample || samplesLoading || Boolean(samplesError))) ||
              (sourceMode === "upload" && (!file || (isTextEditable && preview.trim().length === 0)))
            }
            className="h-11 w-full justify-center gap-2 bg-lime-300 text-sm font-semibold text-slate-950 shadow-[0_8px_24px_rgba(184,243,107,.12)] hover:bg-lime-200 disabled:bg-lime-300/30 disabled:text-slate-500"
          >
            {starting ? <><LoaderCircle className="size-4 animate-spin" /> Starting run…</> : <><FilePlus2 className="size-4" /> Start execution</>}
          </Button>
          <p className="text-center text-[10px] leading-4 text-slate-600">
            {sourceMode === "sample" && selectedSampleItem
              ? `Using ${selectedSampleItem.filename}`
              : sourceMode === "upload" && file
                ? "The selected file will be uploaded to the API."
                : "Choose an existing PRD or select a file to continue."}
          </p>
        </div>
      </div>
    </div>
  );
}
