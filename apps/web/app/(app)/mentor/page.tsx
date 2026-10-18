"use client";

import { useState } from "react";
import { useApi } from "@/lib/api";

type Cohort = { id: string; name: string; org_id: string; join_code: string };
type CohortProgress = {
  cohort: { id: string; name: string };
  members: number;
  sharing: number;
  learners: {
    user_id: string;
    display_name: string;
    xp: number;
    streak_days: number;
    labs_attempted: number;
    labs_passed: number;
    avg_improvement: number | null;
    last_seen_at: string | null;
  }[];
};

export default function Mentor() {
  const { data: cohorts } = useApi<Cohort[]>("/mentor/cohorts");
  const [sel, setSel] = useState<string | null>(null);
  const { data: prog } = useApi<CohortProgress>(sel ? `/cohorts/${sel}/progress` : null);

  return (
    <div className="grid gap-6 lg:grid-cols-[280px_1fr]">
      <aside className="space-y-2">
        <h1 className="text-xl font-bold">Cohorts</h1>
        {cohorts?.length === 0 && <p className="text-sm text-ink-2">No cohorts assigned to you yet.</p>}
        {cohorts?.map((c) => (
          <button key={c.id} onClick={() => setSel(c.id)} className={`card block w-full p-3 text-left ${sel === c.id ? "border-accent" : ""}`}>
            <div className="font-semibold">{c.name}</div>
            <div className="font-mono text-xs text-ink-2">code {c.join_code}</div>
          </button>
        ))}
      </aside>
      <section>
        {!prog && <p className="text-ink-2">Pick a cohort.</p>}
        {prog && (
          <div className="space-y-3">
            <div>
              <h2 className="text-lg font-semibold">{prog.cohort.name}</h2>
              <p className="text-sm text-ink-2">
                {prog.sharing} of {prog.members} learners share their progress with mentors. Learners who haven&apos;t opted in are not shown.
              </p>
            </div>
            <div className="card overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-ink-2">
                  <tr>
                    {["Learner", "XP", "Streak", "Labs passed", "Avg improvement", "Last seen"].map((h) => (
                      <th key={h} className="px-3 py-2">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {prog.learners.map((l) => (
                    <tr key={l.user_id} className="border-t border-line">
                      <td className="px-3 py-2 font-medium">{l.display_name}</td>
                      <td className="px-3 py-2">{l.xp}</td>
                      <td className="px-3 py-2">{l.streak_days}</td>
                      <td className="px-3 py-2">
                        {l.labs_passed}/{l.labs_attempted}
                      </td>
                      <td className="px-3 py-2">{l.avg_improvement != null ? `+${l.avg_improvement}` : "—"}</td>
                      <td className="px-3 py-2 text-ink-2">{l.last_seen_at ? new Date(l.last_seen_at).toLocaleDateString() : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
