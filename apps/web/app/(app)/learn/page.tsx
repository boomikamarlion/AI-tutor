"use client";

import Link from "next/link";
import { useApi, type Course, type Me } from "@/lib/api";

type Feed = {
  activity: { lab_id: string; lab_title: string; delta: number; technique: string | null; at: string }[];
  learners_today_by_lab: Record<string, number>;
  trending_techniques: { id: string; name: string; improvements: number }[];
};

const STAGE_LABEL: Record<string, string> = {
  empathise: "Empathise",
  define: "Define",
  ideate: "Ideate",
  prototype: "Prototype",
  test: "Test",
  none: "Start",
};

export default function Learn() {
  const { data: course } = useApi<Course>("/course");
  const { data: me } = useApi<Me>("/me");
  const { data: feed } = useApi<Feed>("/feed", { refreshInterval: 15_000 });

  if (!course) return <div className="shimmer h-64 rounded-2xl" />;
  const next = course.modules.find((m) => m.unlocked && m.labs_passed < m.labs_total) ?? course.modules[0];

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-6">
        <section className="card overflow-hidden">
          <div className="grid gap-4 p-6 sm:grid-cols-[1fr_auto] sm:items-center">
            <div>
              <div className="text-sm text-ink-2">Hi {me?.display_name?.split(" ")[0] ?? "there"} — pick up where you left off</div>
              <h1 className="text-2xl font-bold">{next.title}</h1>
              <p className="text-ink-2">{next.summary}</p>
            </div>
            <Link href={`/learn/${next.id}`} className="btn btn-accent">
              Continue →
            </Link>
          </div>
          <div className="border-t border-line bg-surface-2 px-6 py-3 text-sm">
            <span className="font-semibold">Running case: </span>
            {course.product_case.title} — <span className="text-ink-2">{course.product_case.summary.slice(0, 160)}…</span>
          </div>
        </section>

        <section>
          <h2 className="mb-3 text-lg font-semibold">{course.title}</h2>
          <ol className="grid gap-3 sm:grid-cols-2">
            {course.modules.map((m) => {
              const pct = m.labs_total ? Math.round((100 * m.labs_passed) / m.labs_total) : 0;
              return (
                <li key={m.id}>
                  <Link href={`/learn/${m.id}`} className="card flex h-full flex-col gap-2 p-4 transition hover:border-accent">
                    <div className="flex items-center gap-2 text-xs">
                      <span className="font-mono font-semibold text-ink-2">{String(m.order).padStart(2, "0")}</span>
                      <span className="chip">{STAGE_LABEL[m.design_stage] ?? m.design_stage}</span>
                      {!m.unlocked && <span className="chip">🔒 Pro</span>}
                      <span className="ml-auto text-ink-2">{m.estimated_minutes} min</span>
                    </div>
                    <div className="font-semibold">{m.title}</div>
                    <p className="line-clamp-2 text-sm text-ink-2">{m.summary}</p>
                    <div className="mt-auto flex items-center gap-2 pt-1">
                      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
                        <span className="block h-full bg-accent" style={{ width: `${pct}%` }} />
                      </span>
                      <span className="text-xs text-ink-2">
                        {m.labs_passed}/{m.labs_total} labs
                      </span>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ol>
        </section>
      </div>

      <aside className="space-y-4">
        <div className="card p-4">
          <div className="mb-2 flex items-center gap-2 font-semibold">
            <span className="h-2 w-2 animate-pulse rounded-full bg-good" /> Live
          </div>
          {!feed?.activity.length && <p className="text-sm text-ink-2">No improvements yet today. Be the first.</p>}
          <ul className="space-y-2">
            {feed?.activity.slice(0, 8).map((a, i) => (
              <li key={i} className="text-sm">
                Someone improved <span className="font-semibold">{a.lab_title}</span> by{" "}
                <span className="font-semibold text-good">+{a.delta}</span>
                {a.technique && <span className="text-ink-2"> with {a.technique}</span>}
              </li>
            ))}
          </ul>
        </div>
        {!!feed?.trending_techniques.length && (
          <div className="card p-4">
            <div className="mb-2 font-semibold">Working today</div>
            <div className="flex flex-wrap gap-2">
              {feed.trending_techniques.map((t) => (
                <span key={t.id} className="chip">
                  {t.name} · {t.improvements}
                </span>
              ))}
            </div>
          </div>
        )}
        <Link href="/join" className="card block p-4 hover:border-accent">
          <div className="font-semibold">Have a code?</div>
          <div className="text-sm text-ink-2">Join a hackathon or your class cohort.</div>
        </Link>
      </aside>
    </div>
  );
}
