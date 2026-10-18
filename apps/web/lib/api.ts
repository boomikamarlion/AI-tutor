"use client";

import useSWR, { type SWRConfiguration } from "swr";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: unknown,
  ) {
    super(typeof detail === "string" ? detail : ((detail as { message?: string })?.message ?? `HTTP ${status}`));
  }
}

export async function api<T = unknown>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init ?? {};
  const res = await fetch(`/api/backend${path}`, {
    ...rest,
    headers: { ...(json !== undefined ? { "Content-Type": "application/json" } : {}), ...(rest.headers ?? {}) },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  });
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      detail = (await res.json()).detail;
    } catch {}
    throw new ApiError(res.status, detail);
  }
  const ct = res.headers.get("content-type") ?? "";
  return (ct.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

export function useApi<T>(path: string | null, config?: SWRConfiguration) {
  return useSWR<T>(path, (p: string) => api<T>(p), { revalidateOnFocus: false, ...config });
}

// ---------------------------------------------------------------- shared types

export type Me = {
  id: string;
  email: string | null;
  display_name: string;
  college: string | null;
  interests: string[];
  onboarded: boolean;
  plan: string;
  has_pro: boolean;
  xp: number;
  level: number;
  level_floor_xp: number;
  next_level_xp: number;
  streak_days: number;
  roles: { platform: string[]; scoped: { role: string; scope_type: string; scope_id: string }[] };
  consents: Record<string, { granted_at: string }>;
  budget: { spent_usd: number; soft_usd: number; hard_usd: number; cache_only: boolean; allowed: boolean };
};

export type ModuleSummary = {
  id: string;
  order: number;
  title: string;
  summary: string;
  design_stage: string;
  tier: string;
  unlocked: boolean;
  estimated_minutes: number;
  techniques: string[];
  labs_total: number;
  labs_passed: number;
};

export type Course = {
  id: string;
  title: string;
  summary: string;
  product_case: { id: string; title: string; summary: string };
  modules: ModuleSummary[];
};

export type CardData = {
  id: string;
  title: string;
  technique?: string;
  template: "anatomy" | "compare" | "flow" | "checklist" | "callout" | "spectrum";
  takeaway: string;
  body?: string;
  data: Record<string, unknown>;
  source?: string;
};

export type LabSummary = {
  id: string;
  title: string;
  difficulty: number;
  estimated_minutes: number;
  techniques_targeted: string[];
  uses_product_case: boolean;
  best_score: number | null;
  passed: boolean;
};

export type ModuleDetail = {
  id: string;
  title: string;
  summary: string;
  design_stage: string;
  design_stage_note?: string;
  objectives: string[];
  techniques: string[];
  unlocked: boolean;
  tier: string;
  cards: CardData[];
  labs: LabSummary[];
};

export type Criterion = { id: string; name: string; weight: number; description: string; anchors: Record<string, string> };

export type LabDetail = {
  id: string;
  title: string;
  module_id: string;
  difficulty: number;
  brief: string;
  input_label: string;
  test_cases: { id: string; input: string; note?: string }[];
  starter_prompt?: string;
  reference_prompt?: string;
  success_criteria: string[];
  techniques_targeted: string[];
  predictions: { id: string; question: string; options: string[] }[];
  hints: string[];
  criteria: Criterion[];
};

export type CritiqueView = {
  total: number;
  summary: string;
  scores: Record<string, { criterion_id: string; evidence: string; score: number; prompt_diagnosis: string }>;
  prompt_spans: { quote: string; criterion_id: string; issue: string; fix_hint: string }[];
  detected_techniques: string[];
  next_focus: string | null;
};

export type RunView = {
  id: string;
  prompt_version_id: string;
  status: "queued" | "running" | "critiquing" | "done" | "failed";
  error: string | null;
  score: number | null;
  delta: number | null;
  xp_awarded: number;
  cases: { test_case_id: string; output: string; status: string; cache_hit: boolean; latency_ms: number | null }[];
  critique: CritiqueView | null;
};

export type PromptView = {
  id: string;
  version: number;
  text: string;
  technique_id: string | null;
  reflection: string | null;
  runs: RunView[];
};

export type AttemptView = {
  id: string;
  lab_id: string;
  event_id: string | null;
  first_score: number | null;
  best_score: number | null;
  passed: boolean;
  prompts: PromptView[];
};

export type Technique = { id: string; name: string; category: string; definition: string };

export function hasRole(me: Me | undefined, role: string): boolean {
  if (!me) return false;
  return me.roles.platform.includes(role) || me.roles.scoped.some((r) => r.role === role);
}
