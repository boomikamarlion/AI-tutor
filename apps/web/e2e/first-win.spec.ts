import { expect, test } from "@playwright/test";

// The hackathon "first win": sign in → onboard → first lab → v1 → critique → v2 with a named
// technique → visible positive delta. Must be completable in well under 15 minutes.
test("first win: v1 → critique → v2 delta", async ({ page }, info) => {
  const email = `e2e-${info.project.name}-${Date.now()}@ecosys.dev`;
  await page.goto("/signin");
  await page.getByPlaceholder("you@college.edu").fill(email);
  await page.getByPlaceholder("Your name").fill("E2E Learner");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();

  await page.waitForURL("**/onboarding");
  await page.getByPlaceholder(/American College/).fill("Test College, Madurai");
  await page.getByRole("button", { name: /first lab/ }).click();
  await page.waitForURL("**/learn");
  await expect(page.getByRole("button", { name: "Continue →" }).or(page.getByRole("link", { name: "Continue →" }))).toBeVisible();

  await page.goto("/lab/m00-lab-canteen-feedback");
  const editor = page.getByPlaceholder(/Write your prompt/);
  await editor.fill("Summarise this feedback.");
  await expect(page.getByText(/Pre-run check/)).toBeVisible();
  await page.getByRole("button", { name: /Run v1/ }).click();
  await expect(page.getByText(/Where your prompt fell short/)).toBeVisible({ timeout: 60_000 });
  await page.screenshot({ path: `e2e/screens/${info.project.name}-v1.png`, fullPage: true });

  await editor.fill(
    "You are the student council's food committee secretary. Summarise the canteen feedback slips below " +
      "for the canteen manager in at most 4 bullets. Only use the text; write 'not stated' if something is missing. " +
      "Format: one bullet per issue, most serious first.\n<slips>{{input}}</slips>",
  );
  await page.getByRole("button", { name: "Constraints", exact: true }).first().click();
  await page.getByPlaceholder(/what did you change/).fill("Added role, audience, limits and format");
  await page.getByRole("button", { name: /Run v2/ }).click();
  await expect(page.getByText(/vs last version/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/▲ \+/)).toBeVisible();
  await expect(page.getByText(/XP · Improvement/)).toBeVisible();
  await page.screenshot({ path: `e2e/screens/${info.project.name}-v2.png`, fullPage: true });
});
