import "next-auth/jwt";

declare module "next-auth/jwt" {
  interface JWT {
    apiToken?: string;
    refreshToken?: string;
    apiTokenExpires?: number;
    error?: string;
  }
}
