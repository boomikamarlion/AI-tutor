"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ConceptCard } from "@/components/ConceptCard";
import { useApi, type ModuleDetail } from "@/lib/api";

export default function ModulePage() {
  const { moduleId } = useParams<{ moduleId: string }>();
  const { data: m } = useApi<ModuleDetail>(`/modules/${moduleId}`);
  const [i, setI] = useState(0);
  if (!m) return <div className="shimmer h-64 rounded-2xl" />;
  const card = m.cards[i];

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <Link href="/learn" className="text-sm text-ink-2">
          ← Course
        </Link>
        <h1 className="text-3xl font-bold">{m.title}</h1>
        <p className="max-w-3xl text-ink-2">{m.summary}</p>
        {m.design_stage_note && (
          <p className="max-w-3xl text-sm">
            <span className="chip mr-2">{m.design_stage}</span>
            {m.design_stage_note}
          </p>
        )}
      </header>

      {m.cards.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Concepts</h2>
            <div className="flex items-center gap-2">
              {m.cards.map((c, idx) => (
                <button
                  key={c.id}
                  aria-label={c.title}
                  onClick={() => setI(idx)}
                  className={`h-2 rounded-full transition-all ${idx === i ? "w-6 bg-accent" : "w-2 bg-line"}`}
                />
              ))}
            </div>
          </div>
          <div className="grid gap-3 lg:grid-cols-[1fr_auto]">
            <ConceptCard card={card} />
            <div className="flex gap-2 lg:flex-col">
              <button className="btn btn-ghost" disabled={i === 0} onClick={() => setI(i - 1)}>
                ← Prev
              </button>
              <button className="btn btn-primary" disabled={i === m.cards.length - 1} onClick={() => setI(i + 1)}>
                Next →
              </button>
            </div>
          </div>
        </section>
      )}

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Labs</h2>
        {!m.unlocked && (
          <div className="card border-accent p-4 text-sm">
            🔒 Labs in this module are part of <span className="font-semibold">Pro</span>. Join a hackathon with a code
            or ask your college coordinator for access.
          </div>
        )}
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {m.labs.map((lab) => (
            <Link
              key={lab.id}
              href={m.unlocked ? `/lab/${lab.id}` : "#"}
              className={`card flex flex-col gap-2 p-4 ${m.unlocked ? "hover:border-accent" : "opacity-60"}`}
            >
              <div className="flex items-center gap-2 text-xs">
                <span>{"●".repeat(lab.difficulty)}{"○".repeat(3 - lab.difficulty)}</span>
                {lab.uses_product_case && <span className="chip">Meenakshi Textiles</span>}
                <span className="ml-auto text-ink-2">{lab.estimated_minutes} min</span>
              </div>
              <div className="font-semibold">{lab.title}</div>
              <div className="mt-auto flex items-center justify-between text-sm">
                <span className="text-ink-2">{lab.techniques_targeted.slice(0, 2).join(" · ")}</span>
                {lab.best_score != null && (
                  <span className={`font-semibold ${lab.passed ? "text-good" : "text-warn"}`}>
                    {Math.round(lab.best_score)}
                  </span>
                )}
              </div>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
