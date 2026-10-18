export type DiffPart = { kind: "same" | "add" | "del"; text: string };

/** Word-level diff (LCS). Prompts are short, so O(n·m) is fine; very long prompts fall back to lines. */
export function diffWords(a: string, b: string): DiffPart[] {
  const split = (s: string) => s.split(/(\s+)/).filter((x) => x.length);
  let A = split(a);
  let B = split(b);
  if (A.length * B.length > 4_000_000) {
    A = a.split(/(\n)/);
    B = b.split(/(\n)/);
  }
  const n = A.length;
  const m = B.length;
  const dp: Uint32Array[] = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--) dp[i][j] = A[i] === B[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out: DiffPart[] = [];
  const push = (kind: DiffPart["kind"], text: string) => {
    const last = out[out.length - 1];
    if (last && last.kind === kind) last.text += text;
    else out.push({ kind, text });
  };
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (A[i] === B[j]) {
      push("same", A[i]);
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) push("del", A[i++]);
    else push("add", B[j++]);
  }
  while (i < n) push("del", A[i++]);
  while (j < m) push("add", B[j++]);
  return out;
}
