"use client";

import { useState } from "react";
import { api, type CritiqueView, type Criterion, type LabDetail, type Technique } from "@/lib/api";
import { diffWords } from "@/lib/diff";
import { lintPrompt, RULES } from "@/lib/lint/rules";
import type { Award, LiveRun } from "@/lib/useRunStream";

// ---------------------------------------------------------------- instant lint

export function LintBar({ text }: { text: string }) {
  const lint = lintPrompt(text);
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <div className="text-xs font-semibold text-ink-2">Pre-run check</div>
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
          <div className="h-full rounded-full bg-model transition-all" style={{ width: `${lint.score}%` }} />
        </div>
        <div className="text-xs tabular-nums text-ink-2">
          {lint.score}% · {lint.words} words
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {RULES.map((r) => (
          <span
            key={r.id}
            title={lint.hits[r.id] ? `${r.label} ✓` : r.tip}
            className={`chip cursor-help ${lint.hits[r.id] ? "border-good/50 text-good" : "text-ink-2"}`}
          >
            {lint.hits[r.id] ? "✓" : "○"} {r.label}
          </span>
        ))}
      </div>
      {text.trim() && lint.missing[0] && (
        <div className="text-xs text-ink-2">
          Biggest gap: <span className="font-semibold text-ink">{lint.missing[0].label}</span> — {lint.missing[0].tip}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- live run cards

export function RunCards({ lab, live }: { lab: LabDetail; live: LiveRun }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {lab.test_cases.map((tc, idx) => {
        const c = live.cases[tc.id];
        const last = idx === lab.test_cases.length - 1;
        return (
          <div key={tc.id} className="card flex flex-col p-3">
            <div className="mb-2 flex items-center gap-2 text-xs">
              <span className="font-semibold">
                {lab.input_label} {idx + 1}
              </span>
              {last && <span className="chip text-warn">edge case</span>}
              <span className="ml-auto text-ink-2">
                {c?.done ? (c.cache_hit ? "⚡ instant" : c.latency_ms ? `${(c.latency_ms / 1000).toFixed(1)}s` : "done") : c?.text ? "streaming…" : "queued"}
              </span>
            </div>
            <button onClick={() => setOpen(open === tc.id ? null : tc.id)} className="mb-2 text-left text-xs text-ink-2">
              {open === tc.id ? "▾ hide input" : "▸ show input"}
            </button>
            {open === tc.id && <pre className="mb-2 max-h-40 overflow-auto whitespace-pre-wrap rounded-lg bg-surface-2 p-2 text-xs">{tc.input}</pre>}
            <div className="min-h-24 flex-1 whitespace-pre-wrap text-sm text-model">
              {c?.text || <div className="shimmer h-16 rounded-lg" />}
              {c && !c.done && c.text && <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-model align-middle" />}
            </div>
            {c?.done && tc.note && <div className="mt-2 border-t border-line pt-2 text-xs text-ink-2">Why this case: {tc.note}</div>}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------- prediction before reveal

export function PredictionCard({ lab, runId, revealed }: { lab: LabDetail; runId: string; revealed: boolean }) {
  const pred = lab.predictions[0];
  const [choice, setChoice] = useState<number | null>(null);
  const [result, setResult] = useState<{ correct: boolean; answer: number; explanation: string } | null>(null);
  if (!pred) return null;

  async function pick(i: number) {
    if (choice !== null) return;
    setChoice(i);
    setResult(await api(`/runs/${runId}/predictions`, { method: "POST", json: { prediction_id: pred.id, choice: i } }));
  }
  const show = revealed && result;
  return (
    <div className="card border-model/40 p-4">
      <div className="mb-1 text-xs font-semibold text-model">Predict while it runs</div>
      <div className="mb-3 font-semibold">{pred.question}</div>
      <div className="grid gap-2">
        {pred.options.map((o, i) => (
          <button
            key={i}
            onClick={() => pick(i)}
            disabled={choice !== null}
            className={`rounded-xl border p-2.5 text-left text-sm transition ${
              show && i === result.answer
                ? "border-good bg-good/10"
                : show && i === choice
                  ? "border-bad bg-bad/10"
                  : choice === i
                    ? "border-model"
                    : "border-line hover:border-model"
            }`}
          >
            {o}
          </button>
        ))}
      </div>
      {choice !== null && !show && <div className="mt-3 text-xs text-ink-2">Locked in. The answer appears when the output lands…</div>}
      {show && (
        <div className="pop mt-3 text-sm">
          <span className={`font-semibold ${result.correct ? "text-good" : "text-bad"}`}>{result.correct ? "Called it! +3 XP. " : "Not quite. "}</span>
          {result.explanation}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- critique

function ScoreRing({ value }: { value: number }) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const color = value >= 70 ? "var(--good)" : value >= 45 ? "var(--warn)" : "var(--bad)";
  return (
    <svg width="88" height="88" viewBox="0 0 88 88" className="shrink-0">
      <circle cx="44" cy="44" r={r} stroke="var(--surface-2)" strokeWidth="8" fill="none" />
      <circle
        cx="44"
        cy="44"
        r={r}
        stroke={color}
        strokeWidth="8"
        fill="none"
        strokeDasharray={`${(value / 100) * c} ${c}`}
        strokeLinecap="round"
        transform="rotate(-90 44 44)"
        style={{ transition: "stroke-dasharray 0.8s ease" }}
      />
      <text x="44" y="50" textAnchor="middle" fontSize="22" fontWeight="700" fill="var(--ink)">
        {Math.round(value)}
      </text>
    </svg>
  );
}

export function CritiquePanel({
  critique,
  delta,
  criteria,
  techniques,
}: {
  critique: CritiqueView;
  delta: number | null | undefined;
  criteria: Criterion[];
  techniques: Technique[];
}) {
  const name = (id: string | null) => techniques.find((t) => t.id === id)?.name ?? id;
  return (
    <div className="card pop space-y-4 p-4">
      <div className="flex items-center gap-4">
        <ScoreRing value={critique.total} />
        <div className="flex-1">
          {delta != null && (
            <div className={`text-2xl font-bold ${delta > 0 ? "text-good" : delta < 0 ? "text-bad" : "text-ink-2"}`}>
              {delta > 0 ? "▲ +" : delta < 0 ? "▼ " : "± "}
              {delta} vs last version
            </div>
          )}
          <p className="text-sm">{critique.summary}</p>
        </div>
      </div>
      <div className="space-y-2.5">
        {criteria.map((c) => {
          const s = critique.scores[c.id];
          if (!s) return null;
          return (
            <details key={c.id} className="group">
              <summary className="flex cursor-pointer list-none items-center gap-3">
                <span className="w-40 shrink-0 text-sm font-medium">{c.name}</span>
                <span className="flex flex-1 gap-1">
                  {[0, 1, 2, 3].map((i) => (
                    <span key={i} className={`h-2 flex-1 rounded-full ${i < s.score ? (s.score >= 3 ? "bg-good" : s.score === 2 ? "bg-warn" : "bg-bad") : "bg-surface-2"}`} />
                  ))}
                </span>
                <span className="w-8 text-right text-xs tabular-nums text-ink-2">{s.score}/4</span>
              </summary>
              <div className="mt-2 space-y-1 rounded-lg bg-surface-2 p-3 text-sm">
                <div>
                  <span className="font-semibold">Evidence: </span>
                  {s.evidence}
                </div>
                <div>
                  <span className="font-semibold">In your prompt: </span>
                  {s.prompt_diagnosis}
                </div>
                <div className="text-xs text-ink-2">Anchor for 4: {c.anchors["4"]}</div>
              </div>
            </details>
          );
        })}
      </div>
      {critique.next_focus && (
        <div className="rounded-xl border border-accent/60 bg-accent/10 p-3 text-sm">
          <span className="font-semibold">Try next: </span>
          {name(critique.next_focus)}
        </div>
      )}
    </div>
  );
}

/** The learner's prompt with the critic's diagnosed spans highlighted in place. */
export function AnnotatedPrompt({ text, spans }: { text: string; spans: CritiqueView["prompt_spans"] }) {
  const found = spans
    .filter((s) => s.quote && text.includes(s.quote))
    .map((s) => ({ ...s, start: text.indexOf(s.quote) }))
    .sort((a, b) => a.start - b.start);
  const parts: React.ReactNode[] = [];
  let pos = 0;
  for (const s of found) {
    if (s.start < pos) continue;
    parts.push(text.slice(pos, s.start));
    parts.push(
      <mark key={s.start} title={`${s.issue} → ${s.fix_hint}`} className="cursor-help rounded bg-bad/15 px-0.5 text-ink underline decoration-bad decoration-wavy">
        {s.quote}
      </mark>,
    );
    pos = s.start + s.quote.length;
  }
  parts.push(text.slice(pos));
  const missing = spans.filter((s) => !s.quote || !text.includes(s.quote));
  return (
    <div className="space-y-2">
      <pre className="whitespace-pre-wrap rounded-xl border border-line bg-bg p-3 font-mono text-[13px]">{parts}</pre>
      {missing.length > 0 && (
        <ul className="space-y-1 text-sm">
          {missing.map((s, i) => (
            <li key={i}>
              <span className="chip mr-2 text-bad">missing</span>
              {s.issue} <span className="text-ink-2">→ {s.fix_hint}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function PromptDiff({ before, after }: { before: string; after: string }) {
  return (
    <pre className="whitespace-pre-wrap rounded-xl border border-line bg-bg p-3 font-mono text-[13px]">
      {diffWords(before, after).map((p, i) =>
        p.kind === "same" ? (
          <span key={i}>{p.text}</span>
        ) : p.kind === "add" ? (
          <ins key={i} className="rounded bg-good/15 text-good no-underline">
            {p.text}
          </ins>
        ) : (
          <del key={i} className="rounded bg-bad/10 text-bad">
            {p.text}
          </del>
        ),
      )}
    </pre>
  );
}

// ---------------------------------------------------------------- awards

export function AwardsBurst({ awards }: { awards: Award[] }) {
  if (!awards.length) return null;
  const label: Record<string, string> = {
    run: "Ran it",
    improvement: "Improvement",
    lab_pass: "Lab passed",
    module_complete: "Module complete",
    mastery: "Technique mastered",
  };
  return (
    <div className="flex flex-wrap gap-2">
      {awards.map((a, i) => (
        <span key={i} className="pop chip border-accent bg-accent text-accent-ink" style={{ animationDelay: `${i * 120}ms` }}>
          +{a.xp} XP · {label[a.kind] ?? a.kind}
          {a.technique ? ` · ${a.technique}` : ""}
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- technique reflection

export function TechniquePicker({
  techniques,
  suggested,
  value,
  onChange,
}: {
  techniques: Technique[];
  suggested: string[];
  value: string;
  onChange: (v: string) => void;
}) {
  const top = techniques.filter((t) => suggested.includes(t.id));
  return (
    <div className="space-y-2">
      <div className="text-sm font-semibold">Which technique did you apply in this version?</div>
      <div className="flex flex-wrap gap-1.5">
        {top.map((t) => (
          <button
            type="button"
            key={t.id}
            onClick={() => onChange(t.id)}
            className={`chip ${value === t.id ? "border-accent bg-accent text-accent-ink" : ""}`}
            title={t.definition}
          >
            {t.name}
          </button>
        ))}
        <select className="chip" value={top.some((t) => t.id === value) ? "" : value} onChange={(e) => onChange(e.target.value)}>
          <option value="">Other…</option>
          {techniques.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
