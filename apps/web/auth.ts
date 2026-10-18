import NextAuth, { type NextAuthConfig } from "next-auth";
import Credentials from "next-auth/providers/credentials";
import MicrosoftEntraID from "next-auth/providers/microsoft-entra-id";
import { SignJWT } from "jose";

// Production identity: Microsoft Entra External ID (customer tenant, *.ciamlogin.com).
// The web app requests an access token for the API app registration and forwards it
// server-side (BFF) — the browser never sees it.
const entraConfigured = Boolean(process.env.AUTH_MICROSOFT_ENTRA_ID_ID);
const devLogin = process.env.AUTH_DEV_LOGIN === "true";
const apiScope = process.env.ENTRA_API_SCOPE; // api://<api-client-id>/access_as_user

async function mintDevToken(email: string, name: string, roles: string[]) {
  const secret = new TextEncoder().encode(process.env.DEV_JWT_SECRET ?? "dev-only-secret-change-me-dev-only-secret");
  return new SignJWT({ email, name, roles })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(email)
    .setIssuedAt()
    .setExpirationTime("24h")
    .sign(secret);
}

async function refreshEntra(refreshToken: string) {
  const issuer = process.env.AUTH_MICROSOFT_ENTRA_ID_ISSUER!.replace(/\/v2\.0\/?$/, "");
  const res = await fetch(`${issuer}/oauth2/v2.0/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: process.env.AUTH_MICROSOFT_ENTRA_ID_ID!,
      client_secret: process.env.AUTH_MICROSOFT_ENTRA_ID_SECRET!,
      grant_type: "refresh_token",
      refresh_token: refreshToken,
      scope: `openid profile email offline_access ${apiScope}`,
    }),
  });
  if (!res.ok) throw new Error(`refresh failed: ${res.status}`);
  return (await res.json()) as { access_token: string; refresh_token?: string; expires_in: number };
}

const providers: NextAuthConfig["providers"] = [];
if (entraConfigured) {
  providers.push(
    MicrosoftEntraID({
      issuer: process.env.AUTH_MICROSOFT_ENTRA_ID_ISSUER,
      authorization: { params: { scope: `openid profile email offline_access ${apiScope}` } },
    }),
  );
}
if (devLogin) {
  providers.push(
    Credentials({
      id: "dev",
      name: "Dev login",
      credentials: { email: {}, name: {}, roles: {}, code: {} },
      authorize: async (c) => {
        const email = String(c?.email ?? "").trim().toLowerCase();
        if (!email.includes("@")) return null;
        // On a shared staging deployment, dev login is gated by a passcode.
        const required = process.env.AUTH_DEV_LOGIN_CODE;
        if (required && String(c?.code ?? "") !== required) return null;
        const roles = String(c?.roles ?? "")
          .split(",")
          .map((r) => r.trim())
          .filter(Boolean);
        return { id: email, email, name: String(c?.name || email.split("@")[0]), roles } as never;
      },
    }),
  );
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  providers,
  session: { strategy: "jwt" },
  pages: { signIn: "/signin" },
  trustHost: true,
  callbacks: {
    async jwt({ token, account, user }) {
      if (account?.provider === "dev" && user) {
        const roles = ((user as { roles?: string[] }).roles ?? []) as string[];
        token.apiToken = await mintDevToken(user.email!, user.name ?? "", roles);
        token.apiTokenExpires = Date.now() + 23 * 3600 * 1000;
        return token;
      }
      if (account?.provider === "microsoft-entra-id") {
        token.apiToken = account.access_token;
        token.refreshToken = account.refresh_token;
        token.apiTokenExpires = (account.expires_at ?? 0) * 1000;
        return token;
      }
      // Refresh the API access token a minute before it expires.
      if (token.refreshToken && Date.now() > Number(token.apiTokenExpires ?? 0) - 60_000) {
        try {
          const r = await refreshEntra(String(token.refreshToken));
          token.apiToken = r.access_token;
          token.refreshToken = r.refresh_token ?? token.refreshToken;
          token.apiTokenExpires = Date.now() + r.expires_in * 1000;
        } catch {
          token.error = "RefreshFailed";
        }
      }
      return token;
    },
    async session({ session, token }) {
      // Deliberately does NOT copy apiToken into the session (the session is readable by the browser).
      (session as { error?: unknown }).error = token.error;
      return session;
    },
  },
});

export const authProviders = { entra: entraConfigured, dev: devLogin };
