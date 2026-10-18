"use client";

import { useEffect, useReducer } from "react";
import type { CritiqueView, RunView } from "@/lib/api";

export type Award = { kind: string; xp: number; technique?: string; delta?: number; lab_id?: string; module_id?: string };

export type LiveRun = {
  status: RunView["status"] | "connecting";
  cases: Record<string, { text: string; done: boolean; cache_hit?: boolean; latency_ms?: number }>;
  critique: (CritiqueView & { delta?: number | null }) | null;
  awards: Award[];
  error?: string;
};

type Action =
  | { type: "reset" }
  | { type: "snapshot"; data: { status: string | null; cases: Record<string, { text: string; cache_hit?: boolean }> } }
  | { type: "final"; data: RunView }
  | { type: "status"; data: { status: string; error?: string } }
  | { type: "delta"; data: { case_id: string; offset: number; text: string } }
  | { type: "case_done"; data: { case_id: string; cache_hit: boolean; latency_ms: number } }
  | { type: "critique"; data: CritiqueView & { delta: number | null } }
  | { type: "awards"; data: { awards: Award[] } };

const initial: LiveRun = { status: "connecting", cases: {}, critique: null, awards: [] };

function reducer(s: LiveRun, a: Action): LiveRun {
  switch (a.type) {
    case "reset":
      return initial;
    case "snapshot": {
      const cases = { ...s.cases };
      for (const [id, c] of Object.entries(a.data.cases)) {
        const cur = cases[id]?.text ?? "";
        cases[id] = { ...cases[id], text: c.text.length >= cur.length ? c.text : cur, done: c.cache_hit !== undefined };
      }
      return { ...s, status: (a.data.status as LiveRun["status"]) ?? "queued", cases };
    }
    case "final": {
      const cases: LiveRun["cases"] = {};
      for (const c of a.data.cases) cases[c.test_case_id] = { text: c.output, done: true, cache_hit: c.cache_hit };
      return {
        ...s,
        status: a.data.status,
        cases,
        critique: a.data.critique ? { ...a.data.critique, delta: a.data.delta } : null,
        error: a.data.error ?? undefined,
      };
    }
    case "status":
      return { ...s, status: a.data.status as LiveRun["status"], error: a.data.error };
    case "delta": {
      const cur = s.cases[a.data.case_id]?.text ?? "";
      // Offsets make deltas idempotent against the snapshot.
      if (a.data.offset > cur.length) return s;
      const text = cur.slice(0, a.data.offset) + a.data.text;
      return { ...s, cases: { ...s.cases, [a.data.case_id]: { ...s.cases[a.data.case_id], text, done: false } } };
    }
    case "case_done":
      return {
        ...s,
        cases: {
          ...s.cases,
          [a.data.case_id]: { ...s.cases[a.data.case_id], text: s.cases[a.data.case_id]?.text ?? "", done: true, cache_hit: a.data.cache_hit, latency_ms: a.data.latency_ms },
        },
      };
    case "critique":
      return { ...s, critique: a.data };
    case "awards":
      return { ...s, awards: a.data.awards };
  }
}

export function useRunStream(runId: string | null, onDone?: () => void) {
  const [state, dispatch] = useReducer(reducer, initial);

  useEffect(() => {
    if (!runId) return;
    dispatch({ type: "reset" });
    const es = new EventSource(`/api/backend/runs/${runId}/stream`);
    const on = (type: Action["type"]) => (e: MessageEvent) => dispatch({ type, data: JSON.parse(e.data) } as Action);
    for (const t of ["snapshot", "final", "status", "delta", "case_done", "critique", "awards"] as const) {
      es.addEventListener(t, on(t));
    }
    es.addEventListener("final", () => {
      es.close();
      onDone?.();
    });
    es.addEventListener("status", (e) => {
      const st = JSON.parse((e as MessageEvent).data).status;
      if (st === "done" || st === "failed") {
        es.close();
        onDone?.();
      }
    });
    es.onerror = () => {
      // The browser retries automatically; a finished run replies with "final".
    };
    return () => es.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  return state;
}
