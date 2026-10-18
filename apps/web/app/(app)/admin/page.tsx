"use client";

import { useState } from "react";
import { api, ApiError, hasRole, useApi, type Me } from "@/lib/api";

type Usage = {
  credit_pool_usd: number;
  spent_total_usd: number;
  remaining_usd: number;
  burn_per_day_7d_usd: number;
  runway_days: number | null;
  active_learners: number;
  cost_per_active_learner_usd: number | null;
  runs_by_status: Record<string, number>;
  daily: { day: string; role: string; deployment: string; cost_usd: number; calls: number; cache_hits: number }[];
};
type Org = { id: string; name: string; kind: string; city: string | null };
type Cohort = { id: string; name: string; join_code: string };
type Ev = { id: string; name: string; join_code: string; starts_at: string; lab_ids: string[] };
type UserRow = { id: string; email: string; display_name: string; plan: string; xp: number; roles: { id: string; role: string; scope_type: string }[] };

const TABS = ["Credits", "Organisations", "People & roles", "Content"] as const;

export default function Admin() {
  const { data: me } = useApi<Me>("/me");
  const isAdmin = hasRole(me, "admin");
  const [picked, setTab] = useState<(typeof TABS)[number] | null>(null);
  const tab = picked ?? (isAdmin ? "Credits" : "Organisations");
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold">Admin</h1>
      <div className="flex flex-wrap gap-2">
        {TABS.filter((t) => isAdmin || t === "Organisations").map((t) => (
          <button key={t} onClick={() => setTab(t)} className={`chip ${tab === t ? "border-accent" : ""}`}>
            {t}
          </button>
        ))}
      </div>
      {tab === "Credits" && isAdmin && <Credits />}
      {tab === "Organisations" && <Orgs isAdmin={isAdmin} />}
      {tab === "People & roles" && isAdmin && <People />}
      {tab === "Content" && isAdmin && <Content />}
    </div>
  );
}

function Credits() {
  const { data: u } = useApi<Usage>("/admin/usage", { refreshInterval: 30_000 });
  if (!u) return <div className="shimmer h-40 rounded-2xl" />;
  const byDay = Object.entries(
    u.daily.reduce<Record<string, number>>((acc, d) => ({ ...acc, [d.day]: (acc[d.day] ?? 0) + d.cost_usd }), {}),
  );
  const max = Math.max(0.0001, ...byDay.map(([, v]) => v));
  const byRole = u.daily.reduce<Record<string, { cost: number; calls: number; hits: number }>>((acc, d) => {
    const r = (acc[`${d.role} · ${d.deployment}`] ??= { cost: 0, calls: 0, hits: 0 });
    r.cost += d.cost_usd;
    r.calls += d.calls;
    r.hits += d.cache_hits;
    return acc;
  }, {});
  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-4">
        <Kpi label="Credits remaining" value={`$${u.remaining_usd.toLocaleString()}`} sub={`of $${u.credit_pool_usd.toLocaleString()}`} />
        <Kpi label="Burn / day (7d)" value={`$${u.burn_per_day_7d_usd}`} sub={u.runway_days ? `${u.runway_days} days runway` : "—"} />
        <Kpi label="Active learners (14d)" value={String(u.active_learners)} sub={u.cost_per_active_learner_usd != null ? `$${u.cost_per_active_learner_usd} each` : ""} />
        <Kpi label="Runs (14d)" value={String(Object.values(u.runs_by_status).reduce((a, b) => a + b, 0))} sub={`${u.runs_by_status.failed ?? 0} failed`} />
      </div>
      <div className="card p-4">
        <div className="mb-3 text-sm font-semibold">Daily spend (USD)</div>
        <div className="flex h-40 items-end gap-1">
          {byDay.map(([day, v]) => (
            <div key={day} className="flex flex-1 flex-col items-center gap-1" title={`${day}: $${v.toFixed(3)}`}>
              <div className="w-full rounded-t bg-accent" style={{ height: `${(100 * v) / max}%` }} />
              <div className="text-[10px] text-ink-2">{day.slice(5)}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-ink-2">
            <tr>
              <th className="px-3 py-2">Role · deployment</th>
              <th className="px-3 py-2">Calls</th>
              <th className="px-3 py-2">Cache hit rate</th>
              <th className="px-3 py-2">Cost</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(byRole).map(([k, r]) => (
              <tr key={k} className="border-t border-line">
                <td className="px-3 py-2">{k}</td>
                <td className="px-3 py-2">{r.calls}</td>
                <td className="px-3 py-2">{r.calls ? Math.round((100 * r.hits) / r.calls) : 0}%</td>
                <td className="px-3 py-2">${r.cost.toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="card p-4">
      <div className="text-xs text-ink-2">{label}</div>
      <div className="text-2xl font-bold">{value}</div>
      {sub && <div className="text-xs text-ink-2">{sub}</div>}
    </div>
  );
}

function Orgs({ isAdmin }: { isAdmin: boolean }) {
  const { data: orgs, mutate } = useApi<Org[]>("/orgs");
  const [name, setName] = useState("");
  const [sel, setSel] = useState<string | null>(null);
  return (
    <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
      <div className="space-y-2">
        {isAdmin && (
          <form
            className="flex gap-2"
            onSubmit={async (e) => {
              e.preventDefault();
              await api("/orgs", { method: "POST", json: { name } });
              setName("");
              mutate();
            }}
          >
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="New college / org" />
            <button className="btn btn-primary">Add</button>
          </form>
        )}
        {orgs?.map((o) => (
          <button key={o.id} onClick={() => setSel(o.id)} className={`card block w-full p-3 text-left ${sel === o.id ? "border-accent" : ""}`}>
            <div className="font-semibold">{o.name}</div>
            <div className="text-xs text-ink-2">
              {o.kind} · {o.city}
            </div>
          </button>
        ))}
      </div>
      {sel ? <OrgDetail orgId={sel} /> : <p className="text-ink-2">Select an organisation.</p>}
    </div>
  );
}

function OrgDetail({ orgId }: { orgId: string }) {
  const { data: cohorts, mutate: mc } = useApi<Cohort[]>(`/orgs/${orgId}/cohorts`);
  const { data: events, mutate: me } = useApi<Ev[]>(`/orgs/${orgId}/events`);
  const [cohortName, setCohortName] = useState("");
  const [ev, setEv] = useState({ name: "", date: "", labs: "m00-lab-leave-letter,m00-lab-canteen-feedback,m01-lab-case-empathy-questions" });
  const [role, setRole] = useState({ email: "", role: "mentor", scope: "" });
  const [msg, setMsg] = useState<string | null>(null);

  async function wrap(f: () => Promise<unknown>) {
    setMsg(null);
    try {
      await f();
      setMsg("Saved.");
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : "Failed");
    }
  }

  return (
    <div className="space-y-4">
      <div className="card space-y-3 p-4">
        <div className="font-semibold">Cohorts</div>
        <ul className="space-y-1 text-sm">
          {cohorts?.map((c) => (
            <li key={c.id}>
              {c.name} — code <span className="font-mono font-semibold">{c.join_code}</span>
            </li>
          ))}
        </ul>
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            wrap(async () => {
              await api(`/orgs/${orgId}/cohorts`, { method: "POST", json: { name: cohortName } });
              setCohortName("");
              mc();
            });
          }}
        >
          <input className="input" value={cohortName} onChange={(e) => setCohortName(e.target.value)} placeholder="e.g. B.Sc CS 2nd year" />
          <button className="btn btn-primary">Create</button>
        </form>
      </div>

      <div className="card space-y-3 p-4">
        <div className="font-semibold">Hackathons</div>
        <ul className="space-y-1 text-sm">
          {events?.map((e) => (
            <li key={e.id}>
              {e.name} · {new Date(e.starts_at).toLocaleDateString()} — code <span className="font-mono font-semibold">{e.join_code}</span> ·{" "}
              <a className="underline" href={`/api/backend/events/${e.id}/export.csv`}>
                export CSV
              </a>
            </li>
          ))}
        </ul>
        <form
          className="grid gap-2 sm:grid-cols-[1fr_200px]"
          onSubmit={(e) => {
            e.preventDefault();
            const start = new Date(ev.date || Date.now());
            wrap(async () => {
              await api(`/orgs/${orgId}/events`, {
                method: "POST",
                json: {
                  name: ev.name,
                  starts_at: start.toISOString(),
                  ends_at: new Date(start.getTime() + 10 * 3600 * 1000).toISOString(),
                  lab_ids: ev.labs.split(",").map((s) => s.trim()).filter(Boolean),
                  grants_pro_days: 30,
                  entry_fee_inr: 200,
                  prize_inr: 10000,
                },
              });
              me();
            });
          }}
        >
          <input className="input" value={ev.name} onChange={(e) => setEv({ ...ev, name: e.target.value })} placeholder="Prompt Hackathon — College name" />
          <input className="input" type="datetime-local" value={ev.date} onChange={(e) => setEv({ ...ev, date: e.target.value })} />
          <input className="input sm:col-span-2 font-mono text-xs" value={ev.labs} onChange={(e) => setEv({ ...ev, labs: e.target.value })} />
          <button className="btn btn-primary w-fit">Create event (10h, ₹200 entry, ₹10,000 prize, 30 days Pro)</button>
        </form>
      </div>

      <div className="card space-y-3 p-4">
        <div className="font-semibold">Assign a role in this organisation</div>
        <form
          className="grid gap-2 sm:grid-cols-4"
          onSubmit={(e) => {
            e.preventDefault();
            const [scope_type, scope_id] = role.scope ? role.scope.split(":") : ["org", orgId];
            wrap(() => api("/role-assignments", { method: "POST", json: { email: role.email, role: role.role, scope_type, scope_id } }));
          }}
        >
          <input className="input sm:col-span-2" value={role.email} onChange={(e) => setRole({ ...role, email: e.target.value })} placeholder="email (must have signed in once)" />
          <select className="input" value={role.role} onChange={(e) => setRole({ ...role, role: e.target.value })}>
            <option value="mentor">Mentor (cohort)</option>
            <option value="judge">Judge (event)</option>
            <option value="org_admin">Org admin</option>
          </select>
          <select className="input" value={role.scope} onChange={(e) => setRole({ ...role, scope: e.target.value })}>
            <option value="">Whole organisation</option>
            {cohorts?.map((c) => (
              <option key={c.id} value={`cohort:${c.id}`}>
                Cohort: {c.name}
              </option>
            ))}
            {events?.map((e) => (
              <option key={e.id} value={`event:${e.id}`}>
                Event: {e.name}
              </option>
            ))}
          </select>
          <button className="btn btn-primary w-fit">Assign</button>
        </form>
        {msg && <div className="text-sm">{msg}</div>}
      </div>
    </div>
  );
}

function People() {
  const [q, setQ] = useState("");
  const { data: users, mutate } = useApi<UserRow[]>(`/admin/users${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  return (
    <div className="space-y-3">
      <input className="input max-w-sm" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search name or email" />
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-ink-2">
            <tr>
              {["Name", "Email", "Plan", "XP", "Roles", ""].map((h) => (
                <th key={h} className="px-3 py-2">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {users?.map((u) => (
              <tr key={u.id} className="border-t border-line">
                <td className="px-3 py-2">{u.display_name}</td>
                <td className="px-3 py-2 text-ink-2">{u.email}</td>
                <td className="px-3 py-2">{u.plan}</td>
                <td className="px-3 py-2">{u.xp}</td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-1">
                    {u.roles.map((r) => (
                      <button
                        key={r.id}
                        className="chip hover:border-bad"
                        title="Click to revoke"
                        onClick={async () => {
                          await api(`/role-assignments/${r.id}`, { method: "DELETE" });
                          mutate();
                        }}
                      >
                        {r.role}@{r.scope_type} ✕
                      </button>
                    ))}
                  </div>
                </td>
                <td className="px-3 py-2">
                  <div className="flex gap-1">
                    <button
                      className="chip"
                      onClick={async () => {
                        await api(`/admin/users/${u.id}/plan`, { method: "PATCH", json: { plan: u.plan === "pro" ? "free" : "pro", days: 30 } });
                        mutate();
                      }}
                    >
                      {u.plan === "pro" ? "→ free" : "→ pro 30d"}
                    </button>
                    {(["author", "admin"] as const).map((r) => (
                      <button
                        key={r}
                        className="chip"
                        onClick={async () => {
                          await api("/role-assignments", { method: "POST", json: { email: u.email, role: r, scope_type: "platform" } });
                          mutate();
                        }}
                      >
                        +{r}
                      </button>
                    ))}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Content() {
  const [res, setRes] = useState<string | null>(null);
  return (
    <div className="card space-y-3 p-4">
      <div className="font-semibold">Course content</div>
      <p className="text-sm text-ink-2">
        Content lives in <code className="font-mono">content/</code> in the repo and is reviewed by pull request. Reload after a deploy to
        project it into the database. Lab versions change automatically when a brief or test set changes, so old runs stay comparable.
      </p>
      <button
        className="btn btn-primary"
        onClick={async () => {
          try {
            setRes(JSON.stringify(await api("/admin/content/reload", { method: "POST" })));
          } catch (e) {
            setRes(e instanceof ApiError ? JSON.stringify(e.detail) : "Failed");
          }
        }}
      >
        Reload content
      </button>
      {res && <pre className="whitespace-pre-wrap rounded-lg bg-surface-2 p-2 text-xs">{res}</pre>}
    </div>
  );
}
