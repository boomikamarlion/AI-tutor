import { redirect } from "next/navigation";
import { auth, authProviders, signIn } from "@/auth";

const DEV_PERSONAS = [
  { email: "learner@ecosys.dev", name: "Priya (learner)", roles: "" },
  { email: "author@ecosys.dev", name: "Content author", roles: "author" },
  { email: "admin@ecosys.dev", name: "Platform admin", roles: "admin" },
];

export default async function SignIn({ searchParams }: PageProps<"/signin">) {
  const params = await searchParams;
  const session = await auth();
  const next = params.join ? "/join" : "/learn";
  if (session?.user) redirect(next);
  const devCodeRequired = Boolean(process.env.AUTH_DEV_LOGIN_CODE);

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-6 px-4 py-16">
      <h1 className="text-3xl font-bold">Sign in</h1>
      {authProviders.entra && (
        <form
          action={async () => {
            "use server";
            await signIn("microsoft-entra-id", { redirectTo: next });
          }}
        >
          <button className="btn btn-primary w-full justify-center py-3">Continue with email, Google or Microsoft</button>
        </form>
      )}
      {authProviders.dev && (
        <div className="card space-y-4 p-5">
          <div>
            <div className="font-semibold">Developer login</div>
            <p className="text-sm text-ink-2">Local only. Pick a persona or type any email.</p>
          </div>
          <form
            className="space-y-3"
            action={async (fd: FormData) => {
              "use server";
              await signIn("dev", {
                email: fd.get("email"),
                name: fd.get("name"),
                roles: fd.get("roles") ?? "",
                code: fd.get("code") ?? "",
                redirectTo: next,
              });
            }}
          >
            <input name="email" className="input" placeholder="you@college.edu" required />
            {devCodeRequired && <input name="code" type="password" className="input" placeholder="Staging passcode" required />}
            <input name="name" className="input" placeholder="Your name" />
            <select name="roles" className="input" defaultValue="">
              <option value="">Learner</option>
              <option value="author">Author</option>
              <option value="admin">Admin</option>
            </select>
            <button className="btn btn-primary w-full justify-center">Sign in</button>
          </form>
          {!devCodeRequired && <div className="flex flex-wrap gap-2">
            {DEV_PERSONAS.map((p) => (
              <form
                key={p.email}
                action={async () => {
                  "use server";
                  await signIn("dev", { email: p.email, name: p.name, roles: p.roles, redirectTo: next });
                }}
              >
                <button className="chip hover:border-accent">{p.name}</button>
              </form>
            ))}
          </div>}
        </div>
      )}
      {!authProviders.entra && !authProviders.dev && (
        <p className="text-bad">No sign-in method is configured. Set AUTH_MICROSOFT_ENTRA_ID_* or AUTH_DEV_LOGIN.</p>
      )}
    </main>
  );
}
