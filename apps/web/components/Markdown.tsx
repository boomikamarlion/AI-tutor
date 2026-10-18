// Tiny, safe markdown for briefs: paragraphs, "- " bullets, **bold**, `code`. No HTML injection.
import { Fragment } from "react";

function inline(text: string) {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((t, i) =>
    t.startsWith("**") && t.endsWith("**") ? (
      <strong key={i}>{t.slice(2, -2)}</strong>
    ) : t.startsWith("`") && t.endsWith("`") ? (
      <code key={i} className="rounded bg-surface-2 px-1 font-mono text-[0.9em]">
        {t.slice(1, -1)}
      </code>
    ) : (
      <Fragment key={i}>{t}</Fragment>
    ),
  );
}

export function Markdown({ text, className }: { text: string; className?: string }) {
  const blocks = text.trim().split(/\n{2,}/);
  return (
    <div className={className}>
      {blocks.map((b, i) => {
        const lines = b.split("\n");
        if (lines.every((l) => /^\s*[-*•]\s+/.test(l))) {
          return (
            <ul key={i}>
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(/^\s*[-*•]\s+/, ""))}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={i}>
            {lines.map((l, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                {/^\s*[-*•]\s+/.test(l) && "• "}
                {inline(l.replace(/^\s*[-*•]\s+/, ""))}
              </Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}
