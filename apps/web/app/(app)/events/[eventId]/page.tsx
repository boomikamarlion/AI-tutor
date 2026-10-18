"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { api, useApi } from "@/lib/api";

type Board = {
  event: { id: string; name: string; lab_ids: string[]; ends_at: string; prize_inr: number };
  board: {
    rank: number;
    user_id: string;
    display_name: string;
    college: string | null;
    best_improvement: number;
    best_score: number;
    reflected_revisions: number;
    trail_score: number;
    judge_score: number | null;
    final: number;
    is_me: boolean;
  }[];
};

type Trail = {
  user_id: string;
  display_name: string;
  college: string | null;
  my_score: { craft: number; reasoning: number; notes: string | null } | null;
  attempts: {
    lab_id: string;
    first_score: number | null;
    best_score: number | null;
    trail: { version: number; text: string; technique_id: string | null; reflection: string | null; score: number | null; delta: number | null }[];
  }[];
};

export default function EventPage() {
  const { eventId } = useParams<{ eventId: string }>();
  const { data } = useApi<Board>(`/events/${eventId}/leaderboard`, { refreshInterval: 10_000 });
  const [judging, setJudging] = useState(false);
  const { data: trails, mutate } = useApi<Trail[]>(judging ? `/events/${eventId}/trails` : null);
  if (!data) return <div className="shimmer h-64 rounded-2xl" />;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end gap-3">
        <div>
          <h1 className="text-2xl font-bold">{data.event.name}</h1>
          <p className="text-sm text-ink-2">
            Ranked on your iteration trail — improvement and reasoning — not a lucky final output. Prize ₹
            {data.event.prize_inr.toLocaleString("en-IN")}.
          </p>
        </div>
        <button className="btn btn-ghost ml-auto" onClick={() => setJudging((j) => !j)}>
          {judging ? "Leaderboard" : "Judge view"}
        </button>
      </header>

      {!judging && (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            {data.event.lab_ids.map((id) => (
              <Link key={id} href={`/lab/${id}?event=${eventId}`} className="card p-4 hover:border-accent">
                <div className="text-xs text-ink-2">Event lab</div>
                <div className="font-semibold">{id.replace(/^m\d+-lab-/, "").replaceAll("-", " ")}</div>
              </Link>
            ))}
          </div>
          <div className="card overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-xs text-ink-2">
                <tr>
                  {["#", "Learner", "Best gain", "Best score", "Reflections", "Trail", "Judges", "Final"].map((h) => (
                    <th key={h} className="px-3 py-2 font-semibold">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.board.map((b) => (
                  <tr key={b.user_id} className={`border-t border-line ${b.is_me ? "bg-accent/10" : ""}`}>
                    <td className="px-3 py-2 font-bold">{b.rank}</td>
                    <td className="px-3 py-2">
                      {b.display_name}
                      <div className="text-xs text-ink-2">{b.college}</div>
                    </td>
                    <td className="px-3 py-2 text-good">+{b.best_improvement.toFixed(1)}</td>
                    <td className="px-3 py-2">{b.best_score.toFixed(0)}</td>
                    <td className="px-3 py-2">{b.reflected_revisions}</td>
                    <td className="px-3 py-2">{b.trail_score}</td>
                    <td className="px-3 py-2">{b.judge_score ?? "—"}</td>
                    <td className="px-3 py-2 font-semibold">{b.final}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {judging && !trails && <p className="text-ink-2">Loading trails… (judges and organisers only)</p>}
      {judging &&
        trails?.map((t) => <TrailCard key={t.user_id} eventId={eventId} trail={t} onSaved={() => mutate()} />)}
    </div>
  );
}

function TrailCard({ eventId, trail, onSaved }: { eventId: string; trail: Trail; onSaved: () => void }) {
  const [craft, setCraft] = useState(trail.my_score?.craft ?? 5);
  const [reasoning, setReasoning] = useState(trail.my_score?.reasoning ?? 5);
  const [notes, setNotes] = useState(trail.my_score?.notes ?? "");
  return (
    <div className="card space-y-3 p-4">
      <div className="font-semibold">
        {trail.display_name} <span className="font-normal text-ink-2">{trail.college}</span>
      </div>
      {trail.attempts.map((a) => (
        <div key={a.lab_id} className="space-y-2">
          <div className="text-xs text-ink-2">
            {a.lab_id} · {a.first_score?.toFixed(0) ?? "—"} → {a.best_score?.toFixed(0) ?? "—"}
          </div>
          <div className="grid gap-2 md:grid-cols-3">
            {a.trail.map((v) => (
              <div key={v.version} className="rounded-xl border border-line p-2 text-xs">
                <div className="mb-1 flex gap-2 font-semibold">
                  v{v.version}
                  {v.score != null && <span>{v.score.toFixed(0)}</span>}
                  {v.delta != null && <span className={v.delta > 0 ? "text-good" : "text-bad"}>{v.delta > 0 ? "+" : ""}{v.delta}</span>}
                  {v.technique_id && <span className="chip">{v.technique_id}</span>}
                </div>
                {v.reflection && <div className="mb-1 italic">“{v.reflection}”</div>}
                <pre className="max-h-32 overflow-auto whitespace-pre-wrap font-mono text-[11px] text-ink-2">{v.text}</pre>
              </div>
            ))}
          </div>
        </div>
      ))}
      <form
        className="flex flex-wrap items-center gap-3 border-t border-line pt-3 text-sm"
        onSubmit={async (e) => {
          e.preventDefault();
          await api(`/events/${eventId}/judge-scores/${trail.user_id}`, { method: "PUT", json: { craft, reasoning, notes } });
          onSaved();
        }}
      >
        <label>
          Craft <input type="number" min={0} max={10} value={craft} onChange={(e) => setCraft(+e.target.value)} className="input w-16" />
        </label>
        <label>
          Reasoning <input type="number" min={0} max={10} value={reasoning} onChange={(e) => setReasoning(+e.target.value)} className="input w-16" />
        </label>
        <input className="input flex-1" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes" />
        <button className="btn btn-primary">{trail.my_score ? "Update" : "Score"}</button>
      </form>
    </div>
  );
}
