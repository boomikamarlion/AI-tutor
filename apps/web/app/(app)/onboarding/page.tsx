"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { mutate } from "swr";
import { api, useApi, type Me } from "@/lib/api";

const INTERESTS = ["Writing & content", "Research", "App development", "Game development", "Data & analysis", "Design", "Business"];

export default function Onboarding() {
  const { data: me } = useApi<Me>("/me");
  const { data: scopes } = useApi<{ scopes: Record<string, string> }>("/consent-scopes");
  const router = useRouter();
  const [name, setName] = useState("");
  const [college, setCollege] = useState("");
  const [interests, setInterests] = useState<string[]>([]);
  const [consent, setConsent] = useState({ learner_analytics: true, cohort_sharing: false });
  const [busy, setBusy] = useState(false);

  async function finish(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    await api("/me", { method: "PATCH", json: { display_name: name || me?.display_name, college, interests, onboarded: true } });
    for (const [scope, granted] of Object.entries(consent)) {
      await api("/me/consents", { method: "POST", json: { scope, granted } });
    }
    await mutate("/me");  // refresh the shell's cached profile so it doesn't bounce back here
    router.replace("/learn");
  }

  return (
    <form onSubmit={finish} className="mx-auto max-w-xl space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Welcome 👋</h1>
        <p className="text-ink-2">Two quick things, then your first lab — it takes about 10 minutes.</p>
      </div>
      <div className="card space-y-3 p-5">
        <label className="block text-sm font-semibold">Your name</label>
        <input className="input" value={name} placeholder={me?.display_name} onChange={(e) => setName(e.target.value)} />
        <label className="block text-sm font-semibold">College</label>
        <input className="input" value={college} placeholder="e.g. The American College, Madurai" onChange={(e) => setCollege(e.target.value)} />
        <label className="block text-sm font-semibold">What do you want to use AI for?</label>
        <div className="flex flex-wrap gap-2">
          {INTERESTS.map((i) => (
            <button
              type="button"
              key={i}
              onClick={() => setInterests((xs) => (xs.includes(i) ? xs.filter((x) => x !== i) : [...xs, i]))}
              className={`chip ${interests.includes(i) ? "border-accent bg-accent text-accent-ink" : ""}`}
            >
              {i}
            </button>
          ))}
        </div>
      </div>
      <div className="card space-y-3 p-5">
        <div className="font-semibold">Your data, your choice</div>
        <p className="text-sm text-ink-2">You can change these any time in Progress → Privacy. Sharing with employers is off and separate.</p>
        {scopes &&
          (["learner_analytics", "cohort_sharing"] as const).map((s) => (
            <label key={s} className="flex items-start gap-3 text-sm">
              <input
                type="checkbox"
                className="mt-1"
                checked={consent[s]}
                onChange={(e) => setConsent((c) => ({ ...c, [s]: e.target.checked }))}
              />
              <span>{scopes.scopes[s]}</span>
            </label>
          ))}
      </div>
      <button className="btn btn-accent" disabled={busy}>
        {busy ? "Saving…" : "Take me to my first lab →"}
      </button>
    </form>
  );
}
