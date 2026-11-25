export type AgentRole = "extractor" | "generator" | "critic" | "selenium";
export type Provider = "gemini" | "groq" | "ollama";
export type RunStatus = "completed" | "failed" | "running" | "queued";

export const agentRoles: AgentRole[] = [
  "extractor",
  "generator",
  "critic",
  "selenium",
];

export const roleDetails: Record<
  AgentRole,
  { label: string; description: string; initials: string; color: string }
> = {
  extractor: {
    label: "Extractor",
    description: "Finds and structures product requirements",
    initials: "EX",
    color: "#b8f36b",
  },
  generator: {
    label: "Generator",
    description: "Creates traceable test cases",
    initials: "GN",
    color: "#71d9c0",
  },
  critic: {
    label: "Critic",
    description: "Reviews quality and requirement coverage",
    initials: "CR",
    color: "#a89bff",
  },
  selenium: {
    label: "Selenium writer",
    description: "Builds validated browser test scripts",
    initials: "SW",
    color: "#f0b968",
  },
};

export const providers: Provider[] = ["gemini", "groq", "ollama"];
export const providerModels: Record<Provider, string[]> = {
  gemini: ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-pro"],
  groq: [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-20b",
  ],
  ollama: [
    "qwen2.5:7b-instruct",
    "llama3.1:8b",
    "mistral:7b-instruct",
  ],
};

export const providerLabels: Record<Provider, string> = {
  gemini: "Gemini API",
  groq: "Groq API",
  ollama: "Ollama",
};
