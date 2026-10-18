// Concept cards are rendered from structured YAML data into a handful of visual templates —
// fast, consistent and cacheable, instead of generating an infographic per view.
import type { CardData } from "@/lib/api";

type Part = { label: string; text: string; note?: string };
type Side = { label: string; prompt: string; output?: string };
type Step = { label: string; detail?: string };
type Point = { label: string; position: number; note?: string };

const PART_COLORS = ["#e8930c", "#3d42d6", "#14804a", "#c2362b", "#7c3aed", "#0e7490", "#b45309"];

export function ConceptCard({ card, compact = false }: { card: CardData; compact?: boolean }) {
  return (
    <article className="card flex h-full flex-col gap-3 p-5">
      <header>
        <div className="text-xs font-semibold uppercase tracking-wide text-ink-2">{card.template}</div>
        <h3 className="text-lg font-semibold leading-snug">{card.title}</h3>
      </header>
      {!compact && card.body && <p className="text-sm text-ink-2">{card.body}</p>}
      <div className="flex-1">
        <Visual card={card} />
      </div>
      <footer className="rounded-xl bg-surface-2 p-3 text-sm">
        <span className="font-semibold">Remember: </span>
        {card.takeaway}
      </footer>
      {!compact && card.source && <div className="text-[11px] text-ink-2">Source: {card.source}</div>}
    </article>
  );
}

function Visual({ card }: { card: CardData }) {
  const d = card.data as Record<string, unknown>;
  switch (card.template) {
    case "anatomy": {
      const parts = (d.parts as Part[]) ?? [];
      return (
        <div className="space-y-2">
          <div className="rounded-xl border border-line bg-bg p-3 font-mono text-[13px] leading-relaxed">
            {parts.map((p, i) => (
              <span key={i} style={{ borderBottom: `2px solid ${PART_COLORS[i % PART_COLORS.length]}` }} className="mr-1">
                {p.text}{" "}
              </span>
            ))}
          </div>
          <ul className="grid gap-1.5 sm:grid-cols-2">
            {parts.map((p, i) => (
              <li key={i} className="flex gap-2 text-sm">
                <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: PART_COLORS[i % PART_COLORS.length] }} />
                <span>
                  <span className="font-semibold">{p.label}</span>
                  {p.note && <span className="text-ink-2"> — {p.note}</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      );
    }
    case "compare": {
      const left = d.left as Side;
      const right = d.right as Side;
      return (
        <div className="space-y-2">
          <div className="grid gap-2 sm:grid-cols-2">
            {[left, right].map((s, i) => (
              <div key={i} className={`rounded-xl border p-3 ${i ? "border-good" : "border-bad/50"}`}>
                <div className={`mb-1 text-xs font-bold ${i ? "text-good" : "text-bad"}`}>{s?.label}</div>
                <pre className="whitespace-pre-wrap font-mono text-[12.5px]">{s?.prompt}</pre>
                {s?.output && (
                  <div className="mt-2 border-t border-line pt-2 text-[12.5px] text-model">
                    <span className="font-semibold">→ </span>
                    <span className="whitespace-pre-wrap">{s.output}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
          {typeof d.verdict === "string" && <p className="text-sm">{d.verdict}</p>}
        </div>
      );
    }
    case "flow": {
      const steps = (d.steps as Step[]) ?? [];
      return (
        <ol className="relative space-y-3 border-l-2 border-accent/60 pl-5">
          {steps.map((s, i) => (
            <li key={i} className="relative">
              <span className="absolute -left-[29px] grid h-5 w-5 place-items-center rounded-full bg-accent text-[11px] font-bold text-accent-ink">
                {i + 1}
              </span>
              <div className="font-semibold">{s.label}</div>
              {s.detail && <div className="text-sm text-ink-2">{s.detail}</div>}
            </li>
          ))}
        </ol>
      );
    }
    case "checklist": {
      const items = (d.items as Step[]) ?? [];
      return (
        <ul className="space-y-2">
          {items.map((it, i) => (
            <li key={i} className="flex gap-2">
              <span className="mt-0.5 text-good">✔</span>
              <span className="text-sm">
                <span className="font-semibold">{it.label}</span>
                {it.detail && <span className="text-ink-2"> — {it.detail}</span>}
              </span>
            </li>
          ))}
        </ul>
      );
    }
    case "callout":
      return (
        <div className="rounded-xl bg-ink p-4 text-bg">
          {typeof d.stat === "string" && <div className="text-3xl font-bold text-accent">{d.stat}</div>}
          <div className="text-lg font-semibold">{String(d.headline ?? "")}</div>
          {typeof d.detail === "string" && <p className="mt-1 text-sm opacity-80">{d.detail}</p>}
        </div>
      );
    case "spectrum": {
      const points = (d.points as Point[]) ?? [];
      return (
        <div className="space-y-3 pt-6">
          <div className="relative h-2 rounded-full bg-gradient-to-r from-surface-2 via-accent/40 to-accent">
            {points.map((p, i) => (
              <span
                key={i}
                className="absolute -top-1.5 h-5 w-5 -translate-x-1/2 rounded-full border-2 border-bg bg-model"
                style={{ left: `${Math.max(0, Math.min(100, p.position))}%` }}
                title={p.note}
              />
            ))}
          </div>
          <div className="flex justify-between text-xs font-semibold text-ink-2">
            <span>{String(d.left_label ?? "")}</span>
            <span>{String(d.right_label ?? "")}</span>
          </div>
          <ul className="space-y-1 text-sm">
            {[...points].sort((a, b) => a.position - b.position).map((p, i) => (
              <li key={i}>
                <span className="font-semibold">{p.label}</span>
                {p.note && <span className="text-ink-2"> — {p.note}</span>}
              </li>
            ))}
          </ul>
        </div>
      );
    }
  }
}
