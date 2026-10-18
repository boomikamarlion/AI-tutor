"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { mutate } from "swr";
import { ConceptCard } from "@/components/ConceptCard";
import { Markdown } from "@/components/Markdown";
import {
  AnnotatedPrompt,
  AwardsBurst,
  CritiquePanel,
  LintBar,
  PredictionCard,
  PromptDiff,
  RunCards,
  TechniquePicker,
} from "@/components/canvas/parts";
import { api, ApiError, useApi, type AttemptView, type CardData, type LabDetail, type Technique } from "@/lib/api";
import { lintPrompt, RULES } from "@/lib/lint/rules";
import { useRunStream } from "@/lib/useRunStream";

export default function LabPage() {
  return (
    <Suspense fallback={<div className="shimmer h-96 rounded-2xl" />}>
      <LabCanvas />
    </Suspense>
  );
}

function LabCanvas() {
  const { labId } = useParams<{ labId: string }>();
  const eventId = useSearchParams().get("event");
  const { data: lab, error: labError } = useApi<LabDetail>(`/labs/${labId}`);
  const { data: techniques = [] } = useApi<Technique[]>("/techniques");
  const [attempt, setAttempt] = useState<AttemptView | null>(null);
  const [sel, setSel] = useState<number>(-1); // index into attempt.prompts; -1 = new draft
  const [draftState, setDraft] = useState<string | null>(null);
  const [technique, setTechnique] = useState("");
  const [reflection, setReflection] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [hints, setHints] = useState(0);
  const [tab, setTab] = useState<"brief" | "canvas" | "learn">("canvas");

  const reload = async () => {
    const a = await api<AttemptView>(`/labs/${labId}/attempt${eventId ? `?event_id=${eventId}` : ""}`, { method: "POST" });
    setAttempt(a);
    return a;
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const a = await api<AttemptView>(`/labs/${labId}/attempt${eventId ? `?event_id=${eventId}` : ""}`, { method: "POST" });
      if (cancelled) return;
      setAttempt(a);
      if (a.prompts.length) {
        const last = a.prompts[a.prompts.length - 1];
        setSel(a.prompts.length - 1);
        setRunId(last.runs[last.runs.length - 1]?.id ?? null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [labId, eventId]);

  const live = useRunStream(runId, () => {
    reload();
    mutate("/me");
  });

  const prompts = useMemo(() => attempt?.prompts ?? [], [attempt]);
  const current = sel >= 0 ? prompts[sel] : null;
  // Until the learner types, the editor shows the selected version (or the lab's starter prompt).
  const draft = draftState ?? current?.text ?? lab?.starter_prompt ?? "";
  const previous = sel > 0 ? prompts[sel - 1] : null;
  const isNewVersion = !current || draft.trim() !== current.text.trim();
  const nextVersion = prompts.length + 1;
  const needsTechnique = isNewVersion && nextVersion > 1;
  const inFlight = ["connecting", "queued", "running", "critiquing"].includes(live.status) && !!runId;

  const focusCards = useApi<CardData[]>(
    live.critique?.next_focus ? `/cards?technique=${live.critique.next_focus}` : lab ? `/cards?technique=${lab.techniques_targeted[0]}` : null,
  ).data;

  async function run() {
    if (!attempt || !draft.trim()) return;
    setErr(null);
    setBusy(true);
    try {
      let promptId = current?.id;
      if (isNewVersion) {
        const pv = await api<{ id: string }>(`/attempts/${attempt.id}/prompts`, {
          method: "POST",
          json: { text: draft, technique_id: technique || null, reflection: reflection || null, client_lint: lintPrompt(draft).hits },
        });
        promptId = pv.id;
        setTechnique("");
        setReflection("");
        const a = await reload();
        setSel(a.prompts.length - 1);
      }
      const r = await api<{ id: string }>(`/prompts/${promptId}/runs`, { method: "POST" });
      setRunId(r.id);
      setTab("canvas");
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  function selectVersion(i: number) {
    setSel(i);
    setDraft(prompts[i].text);
    const runs = prompts[i].runs;
    setRunId(runs[runs.length - 1]?.id ?? null);
  }

  // Suggest the techniques whose lint signal this draft newly satisfies, then the lab's targets.
  const suggested = useMemo(() => {
    const before = lintPrompt(prompts[prompts.length - 1]?.text ?? "").hits;
    const now = lintPrompt(draft).hits;
    const gained = RULES.filter((r) => now[r.id] && !before[r.id]).map((r) => r.technique);
    return [...new Set([...gained, ...(lab?.techniques_targeted ?? [])])];
  }, [prompts, draft, lab]);

  const scoreTrail = useMemo(
    () => prompts.map((p) => p.runs.filter((r) => r.status === "done").slice(-1)[0]?.score ?? null),
    [prompts],
  );

  if (labError) {
    return (
      <div className="card mx-auto max-w-lg p-6 text-center">
        <div className="text-lg font-semibold">{labError.status === 402 ? "This lab is part of Pro" : "Lab not available"}</div>
        <Link href="/learn" className="btn btn-ghost mt-4">
          ← Back to course
        </Link>
      </div>
    );
  }
  if (!lab || !attempt) return <div className="shimmer h-96 rounded-2xl" />;

  const brief = (
    <div className="space-y-4">
      <div className="card p-4">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-2">The brief</div>
        <Markdown text={lab.brief} className="prose-brief text-sm" />
      </div>
      {lab.success_criteria.length > 0 && (
        <div className="card p-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-2">Success looks like</div>
          <ul className="space-y-1 text-sm">
            {lab.success_criteria.map((s, i) => (
              <li key={i}>• {s}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="card p-4">
        <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-2">Hints</div>
        {lab.hints.slice(0, hints).map((h, i) => (
          <p key={i} className="mb-2 text-sm">
            💡 {h}
          </p>
        ))}
        {hints < lab.hints.length && (
          <button className="btn btn-ghost text-xs" onClick={() => setHints(hints + 1)}>
            Show a hint ({hints + 1}/{lab.hints.length})
          </button>
        )}
      </div>
      <div className="card p-4 text-xs text-ink-2">
        Your prompt runs on {lab.test_cases.length} fixed test cases. Use <code className="font-mono">{"{{input}}"}</code> where each
        input should go — or leave it out and it is appended at the end.
      </div>
    </div>
  );

  const learn = (
    <div className="space-y-4">
      {focusCards?.[0] && <ConceptCard card={focusCards[0]} compact />}
      <CoachPanel attemptId={attempt.id} />
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link href={`/learn/${lab.module_id}`} className="text-sm text-ink-2">
          ← Module
        </Link>
        <h1 className="text-xl font-bold">{lab.title}</h1>
        <div className="ml-auto flex items-center gap-1">
          {scoreTrail.map((s, i) => (
            <button
              key={i}
              onClick={() => selectVersion(i)}
              className={`chip ${i === sel ? "border-ink" : ""}`}
              title={s != null ? `score ${s}` : "not run"}
            >
              v{i + 1}
              {s != null && <span className={s >= 70 ? "text-good" : "text-warn"}>{Math.round(s)}</span>}
            </button>
          ))}
        </div>
      </div>

      <div className="flex gap-2 lg:hidden">
        {(["brief", "canvas", "learn"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`chip ${tab === t ? "border-accent" : ""}`}>
            {t === "brief" ? "Brief" : t === "canvas" ? "Canvas" : "Learn & coach"}
          </button>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-[320px_1fr_320px]">
        <aside className={`${tab === "brief" ? "" : "hidden"} lg:block`}>{brief}</aside>

        <section className={`${tab === "canvas" ? "" : "hidden"} space-y-4 lg:block`}>
          <div className="card space-y-3 p-4">
            <div className="flex items-center gap-2">
              <div className="text-sm font-semibold">{isNewVersion ? `Draft v${nextVersion}` : `Prompt v${current?.version}`}</div>
              {current?.technique_id && !isNewVersion && <span className="chip">{techniques.find((t) => t.id === current.technique_id)?.name}</span>}
            </div>
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              rows={10}
              spellCheck={false}
              className="input font-mono text-[13px] leading-relaxed"
              placeholder="Write your prompt. Use {{input}} where each test input should go."
            />
            <LintBar text={draft} />
            {needsTechnique && (
              <div className="space-y-2 rounded-xl bg-surface-2 p-3">
                <TechniquePicker techniques={techniques} suggested={suggested} value={technique} onChange={setTechnique} />
                <input
                  className="input text-sm"
                  value={reflection}
                  onChange={(e) => setReflection(e.target.value)}
                  placeholder="In one line: what did you change and why? (judges read this)"
                />
              </div>
            )}
            <div className="flex items-center gap-3">
              <button className="btn btn-accent" onClick={run} disabled={busy || inFlight || !draft.trim() || (needsTechnique && !technique)}>
                {busy ? "Starting…" : inFlight ? "Running…" : isNewVersion ? `Run v${nextVersion} ▶` : "Run again ▶"}
              </button>
              {needsTechnique && !technique && <span className="text-xs text-ink-2">Name the technique to run your revision.</span>}
              {err && <span className="text-sm text-bad">{err}</span>}
            </div>
          </div>

          {runId && (
            <>
              {lab.predictions.length > 0 && (
                <PredictionCard key={runId} lab={lab} runId={runId} revealed={!inFlight && !!live.critique} />
              )}
              <RunCards lab={lab} live={live} />
              {live.status === "critiquing" && <div className="card shimmer h-24" />}
              {live.status === "failed" && <div className="card border-bad p-4 text-sm text-bad">{live.error ?? "The run failed."}</div>}
              {live.critique && (
                <>
                  <AwardsBurst awards={live.awards} />
                  <CritiquePanel critique={live.critique} delta={live.critique.delta} criteria={lab.criteria} techniques={techniques} />
                  <div className="card space-y-2 p-4">
                    <div className="text-sm font-semibold">Where your prompt fell short</div>
                    <AnnotatedPrompt text={current?.text ?? draft} spans={live.critique.prompt_spans} />
                  </div>
                </>
              )}
            </>
          )}

          {previous && current && (
            <div className="card space-y-2 p-4">
              <div className="text-sm font-semibold">
                v{previous.version} → v{current.version}
                {current.reflection && <span className="ml-2 font-normal text-ink-2">“{current.reflection}”</span>}
              </div>
              <PromptDiff before={previous.text} after={current.text} />
            </div>
          )}
        </section>

        <aside className={`${tab === "learn" ? "" : "hidden"} lg:block`}>{learn}</aside>
      </div>
    </div>
  );
}

function CoachPanel({ attemptId }: { attemptId: string }) {
  const [q, setQ] = useState("");
  const [log, setLog] = useState<{ q: string; a: string }[]>([]);
  const [busy, setBusy] = useState(false);
  async function ask(e: React.FormEvent) {
    e.preventDefault();
    if (!q.trim()) return;
    setBusy(true);
    const question = q;
    setQ("");
    try {
      const r = await api<{ answer: string }>(`/attempts/${attemptId}/coach`, { method: "POST", json: { question } });
      setLog((l) => [...l, { q: question, a: r.answer }]);
    } catch {
      setLog((l) => [...l, { q: question, a: "The coach is unavailable right now." }]);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="card space-y-3 p-4">
      <div>
        <div className="font-semibold">Coach</div>
        <div className="text-xs text-ink-2">Asks you questions and points to techniques. It won&apos;t write the prompt for you.</div>
      </div>
      <div className="max-h-80 space-y-3 overflow-auto">
        {log.map((m, i) => (
          <div key={i} className="space-y-1 text-sm">
            <div className="font-medium">You: {m.q}</div>
            <div className="whitespace-pre-wrap rounded-xl bg-surface-2 p-2 text-model">{m.a.replace(/\*\*/g, "")}</div>
          </div>
        ))}
      </div>
      <form onSubmit={ask} className="flex gap-2">
        <input className="input text-sm" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Why did my score drop?" />
        <button className="btn btn-primary" disabled={busy}>
          {busy ? "…" : "Ask"}
        </button>
      </form>
    </div>
  );
}
