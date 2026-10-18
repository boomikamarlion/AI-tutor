"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { hasRole, useApi, type Me } from "@/lib/api";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { data: me } = useApi<Me>("/me", { refreshInterval: 30_000 });
  const path = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (me && !me.onboarded && path !== "/onboarding") router.replace("/onboarding");
  }, [me, path, router]);

  const links: [string, string, boolean][] = [
    ["/learn", "Learn", true],
    ["/progress", "Progress", true],
    ["/events", "Events", true],
    ["/mentor", "Mentor", hasRole(me, "mentor") || hasRole(me, "org_admin") || hasRole(me, "admin")],
    ["/admin", "Admin", hasRole(me, "admin") || hasRole(me, "org_admin")],
  ];

  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="sticky top-0 z-20 border-b border-line bg-bg/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-4 px-4 py-2.5">
          <Link href="/learn" className="text-lg font-bold tracking-tight">
            eco<span className="text-accent">sys</span>
          </Link>
          <nav className="hidden gap-1 sm:flex">
            {links
              .filter(([, , show]) => show)
              .map(([href, label]) => (
                <Link
                  key={href}
                  href={href}
                  className={`rounded-full px-3 py-1 text-sm font-medium ${
                    path.startsWith(href) ? "bg-surface-2 text-ink" : "text-ink-2 hover:text-ink"
                  }`}
                >
                  {label}
                </Link>
              ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">{me && <XpMeter me={me} />}</div>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-4 pb-2 sm:hidden">
          {links
            .filter(([, , show]) => show)
            .map(([href, label]) => (
              <Link
                key={href}
                href={href}
                className={`chip shrink-0 ${path.startsWith(href) ? "border-accent" : ""}`}
              >
                {label}
              </Link>
            ))}
        </nav>
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6">{children}</main>
    </div>
  );
}

function XpMeter({ me }: { me: Me }) {
  const span = Math.max(1, me.next_level_xp - me.level_floor_xp);
  const pct = Math.min(100, Math.round((100 * (me.xp - me.level_floor_xp)) / span));
  return (
    <Link href="/progress" className="flex items-center gap-3" title={`${me.xp} XP`}>
      <span className="chip" title="Daily streak">
        🔥 {me.streak_days}
      </span>
      <span className="hidden items-center gap-2 sm:flex">
        <span className="text-xs font-semibold">Lv {me.level}</span>
        <span className="h-2 w-24 overflow-hidden rounded-full bg-surface-2">
          <span className="block h-full rounded-full bg-accent transition-all" style={{ width: `${pct}%` }} />
        </span>
      </span>
      <span className="grid h-8 w-8 place-items-center rounded-full bg-ink text-xs font-bold text-bg">
        {(me.display_name || "?").slice(0, 1).toUpperCase()}
      </span>
    </Link>
  );
}
