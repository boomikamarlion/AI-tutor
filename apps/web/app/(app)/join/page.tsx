"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { mutate } from "swr";
import { api, ApiError } from "@/lib/api";

export default function Join() {
  const [code, setCode] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const router = useRouter();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setMsg(null);
    try {
      const r = await api<{ joined: string; id: string; name: string; lab_ids?: string[] }>("/me/join", { method: "POST", json: { code } });
      mutate("/me");
      if (r.joined === "event") router.push(`/events/${r.id}`);
      else setMsg(`You joined ${r.name}.`);
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : "Could not join");
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-md space-y-4">
      <h1 className="text-2xl font-bold">Join with a code</h1>
      <p className="text-ink-2">Hackathon codes start with H, class cohort codes with C.</p>
      <input className="input text-center font-mono text-2xl uppercase tracking-widest" value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} maxLength={12} placeholder="H7KD2QX" />
      <button className="btn btn-accent w-full justify-center">Join</button>
      {msg && <p className="text-center text-sm">{msg}</p>}
    </form>
  );
}
