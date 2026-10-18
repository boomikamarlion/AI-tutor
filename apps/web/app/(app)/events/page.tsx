"use client";

import Link from "next/link";
import { useApi } from "@/lib/api";

type MyEvent = { id: string; name: string; starts_at: string; ends_at: string; lab_ids: string[]; is_judge: boolean };

export default function Events() {
  const { data } = useApi<MyEvent[]>("/me/events");
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Your events</h1>
        <Link href="/join" className="btn btn-ghost">
          Join with a code
        </Link>
      </div>
      {data?.length === 0 && <p className="text-ink-2">You haven&apos;t joined a hackathon yet.</p>}
      <div className="grid gap-3 sm:grid-cols-2">
        {data?.map((e) => (
          <Link key={e.id} href={`/events/${e.id}`} className="card p-4 hover:border-accent">
            <div className="font-semibold">{e.name}</div>
            <div className="text-sm text-ink-2">
              {new Date(e.starts_at).toLocaleString()} · {e.lab_ids.length} labs
            </div>
            {e.is_judge && <span className="chip mt-2">Judge</span>}
          </Link>
        ))}
      </div>
    </div>
  );
}
