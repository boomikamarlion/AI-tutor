"use client";

import { api, useApi, type Me, type Technique } from "@/lib/api";

type Progress = {
  modules: { id: string; title: string; labs_total: number; labs_passed: number }[];
  mastery: { technique_id: string; uses: number; improving_uses: number; labs: string[]; best_delta: number; mastered_at: string | null }[];
  recent_xp: { amount: number; reason: string; ref: string | null; at: string }[];
};

export default function ProgressPage() {
  const { data: me, mutate: refreshMe } = useApi<Me>("/me");
  const { data: p } = useApi<Progress>("/me/progress");
  const { data: techniques = [] } = useApi<Technique[]>("/techniques");
  const { data: scopes } = useApi<{ scopes: Record<string, string> }>("/consent-scopes");
  if (!me || !p) return <div className="shimmer h-64 rounded-2xl" />;
  const name = (id: string) => techniques.find((t) => t.id === id)?.name ?? id;

  async function toggle(scope: string, granted: boolean) {
    await api("/me/consents", { method: "POST", json: { scope, granted } });
    refreshMe();
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <section className="card space-y-3 p-5">
        <h2 className="text-lg font-semibold">You</h2>
        <div className="grid grid-cols-3 gap-3 text-center">
          <Stat label="Level" value={me.level} />
          <Stat label="XP" value={me.xp} />
          <Stat label="Day streak" value={me.streak_days} />
        </div>
        <div className="text-sm text-ink-2">
          Plan: <span className="font-semibold text-ink">{me.has_pro ? "Pro" : "Free"}</span> · Today&apos;s AI budget used:{" "}
          {Math.round((100 * me.budget.spent_usd) / me.budget.hard_usd)}%
        </div>
      </section>

      <section className="card space-y-3 p-5">
        <h2 className="text-lg font-semibold">Techniques</h2>
        <p className="text-sm text-ink-2">A technique is mastered when it produced a real score gain on two different labs.</p>
        <div className="flex flex-wrap gap-2">
          {p.mastery.length === 0 && <span className="text-sm text-ink-2">Name a technique on your next revision to start.</span>}
          {p.mastery
            .sort((a, b) => Number(!!b.mastered_at) - Number(!!a.mastered_at) || b.improving_uses - a.improving_uses)
            .map((m) => (
              <span key={m.technique_id} className={`chip ${m.mastered_at ? "border-accent bg-accent text-accent-ink" : ""}`} title={`best +${m.best_delta}`}>
                {m.mastered_at ? "🏅" : `${m.labs.length}/2`} {name(m.technique_id)}
              </span>
            ))}
        </div>
      </section>

      <section className="card space-y-3 p-5">
        <h2 className="text-lg font-semibold">Course progress</h2>
        {p.modules.map((m) => (
          <div key={m.id} className="flex items-center gap-3 text-sm">
            <span className="w-56 truncate">{m.title}</span>
            <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-2">
              <span className="block h-full bg-accent" style={{ width: `${m.labs_total ? (100 * m.labs_passed) / m.labs_total : 0}%` }} />
            </span>
            <span className="w-10 text-right text-ink-2">
              {m.labs_passed}/{m.labs_total}
            </span>
          </div>
        ))}
      </section>

      <section className="card space-y-3 p-5">
        <h2 className="text-lg font-semibold">Recent XP</h2>
        <ul className="space-y-1 text-sm">
          {p.recent_xp.map((x, i) => (
            <li key={i} className="flex justify-between">
              <span>{x.reason.replace("_", " ")}</span>
              <span className="font-semibold text-accent">+{x.amount}</span>
            </li>
          ))}
        </ul>
      </section>

      <section id="privacy" className="card space-y-3 p-5 lg:col-span-2">
        <h2 className="text-lg font-semibold">Privacy & consent</h2>
        <p className="text-sm text-ink-2">
          Each permission is separate and you can withdraw it any time. Withdrawing stops future use immediately.
        </p>
        {scopes &&
          Object.entries(scopes.scopes).map(([scope, text]) => (
            <label key={scope} className="flex items-start gap-3 text-sm">
              <input type="checkbox" className="mt-1" checked={!!me.consents[scope]} onChange={(e) => toggle(scope, e.target.checked)} />
              <span>
                <span className="font-semibold">{scope.replace("_", " ")}</span> — {text}
                {me.consents[scope] && <span className="text-ink-2"> (since {new Date(me.consents[scope].granted_at).toLocaleDateString()})</span>}
              </span>
            </label>
          ))}
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl bg-surface-2 p-3">
      <div className="text-2xl font-bold">{value}</div>
      <div className="text-xs text-ink-2">{label}</div>
    </div>
  );
}
