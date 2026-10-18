import Link from "next/link";
import { redirect } from "next/navigation";
import { auth } from "@/auth";

export default async function Home() {
  const session = await auth();
  if (session?.user) redirect("/learn");
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col justify-center gap-10 px-4 py-16">
      <div className="space-y-5">
        <span className="chip">Not a video course</span>
        <h1 className="text-4xl font-bold leading-tight sm:text-6xl">
          Learn to prompt <span className="text-accent">by doing.</span>
        </h1>
        <p className="max-w-2xl text-lg text-ink-2">
          Write a prompt for a real brief. Watch it run on a fixed test set. A critic grades it against a human
          rubric and shows exactly where your prompt fell short. Revise — and see your score move.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link href="/signin" className="btn btn-accent">
            Start your first lab →
          </Link>
          <Link href="/signin?join=1" className="btn btn-ghost">
            I have a hackathon code
          </Link>
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-4">
        {[
          ["Write", "a prompt for a messy, real brief"],
          ["Run", "it on pinned test cases — live"],
          ["Critique", "pinpoints where the prompt failed"],
          ["Improve", "v1 → v2, name the technique, earn XP"],
        ].map(([t, d], i) => (
          <div key={t} className="card p-4">
            <div className="text-xs font-semibold text-ink-2">0{i + 1}</div>
            <div className="text-lg font-semibold">{t}</div>
            <div className="text-sm text-ink-2">{d}</div>
          </div>
        ))}
      </div>
    </main>
  );
}
