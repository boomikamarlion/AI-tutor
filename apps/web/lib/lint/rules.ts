// Instant pre-run lint. Grades the prompt itself in milliseconds so the learner gets
// signal before anything hits a model. Mirror of services/api/app/engine/features.py —
// keep rule ids in sync.

export type LintRule = {
  id: string;
  label: string;
  weight: number;
  pattern: RegExp;
  tip: string;
  technique: string;
};

export const RULES: LintRule[] = [
  {
    id: "role",
    label: "Role",
    weight: 2,
    pattern: /\b(you are|act as|you're an?|as an? (expert|experienced|senior))\b/im,
    tip: "Give the model a role so it knows whose standards to write to.",
    technique: "role-prompting",
  },
  {
    id: "task",
    label: "Clear task",
    weight: 3,
    pattern:
      /(^|[.!?:]\s+)(please\s+)?(write|create|generate|draft|summari[sz]e|classify|extract|list|rewrite|translate|analy[sz]e|explain|tag|answer|grade|evaluate|plan|convert|compare|identify|produce|suggest|design|review|turn|reply|respond)\b|\b(your task is|you will|i need you to)\b/im,
    tip: "Start with an action verb that names the deliverable.",
    technique: "explicit-task",
  },
  {
    id: "audience",
    label: "Audience",
    weight: 1,
    pattern:
      /\b(audience|reader|for (college )?students|for customers|for beginners|target(ed)? (at|to)|aimed at|who (are|is) (new|reading))\b/im,
    tip: "Say who will read the output.",
    technique: "audience-persona",
  },
  {
    id: "context",
    label: "Context",
    weight: 1,
    pattern: /\b(context|background|situation|goal is|because|we are|our )\b/im,
    tip: "Add the background the model can't know.",
    technique: "context-provision",
  },
  {
    id: "constraints",
    label: "Constraints",
    weight: 2,
    pattern:
      /\b(\d+\s*(words?|sentences?|bullets?|characters?|lines?|items?|points?|paragraphs?)|at most|no more than|under \d+|maximum|must|do not|don't|avoid|only)\b/im,
    tip: "Add checkable limits: length, tone, must / must-not.",
    technique: "constraints",
  },
  {
    id: "format",
    label: "Output format",
    weight: 2,
    pattern:
      /\b(format|json|table|bullet|numbered|markdown|headings?|sections?|csv|schema|columns?|template|return (only|exactly))\b/im,
    tip: "Describe the exact shape of the output.",
    technique: "output-format",
  },
  {
    id: "examples",
    label: "Examples",
    weight: 1,
    pattern: /\b(example|e\.g\.|for instance|sample)\b|^\s*(input|output)\s*:/im,
    tip: "Show one good example of input → output.",
    technique: "few-shot",
  },
  {
    id: "delimiters",
    label: "Delimiters",
    weight: 1,
    pattern: /(```|"""|<[a-z_]+>|^#{2,}\s|\{\{input\}\}|---)/im,
    tip: "Fence the data off from your instructions (tags, quotes, {{input}}).",
    technique: "delimiters",
  },
  {
    id: "uncertainty",
    label: "Allows 'not stated'",
    weight: 1,
    pattern:
      /(not stated|don't know|do not know|unknown|insufficient|if (any|the) .{0,40}(missing|unclear)|only (use|the) (information|facts|text)|do not (invent|make up|guess))/im,
    tip: "Tell the model what to do when the input doesn't say.",
    technique: "uncertainty-permission",
  },
  {
    id: "reasoning",
    label: "Reasoning guidance",
    weight: 1,
    pattern:
      /\b(step[- ]by[- ]step|first,? .{0,60}then|think (through|carefully)|plan|criteria|check (your|each))\b/im,
    tip: "State the success criteria or the steps to check.",
    technique: "decomposition",
  },
];

export type LintResult = {
  score: number;
  words: number;
  hits: Record<string, boolean>;
  missing: LintRule[];
};

export function lintPrompt(prompt: string): LintResult {
  const hits: Record<string, boolean> = {};
  let got = 0;
  let total = 0;
  for (const r of RULES) {
    hits[r.id] = r.pattern.test(prompt);
    total += r.weight;
    if (hits[r.id]) got += r.weight;
  }
  const words = prompt.trim() ? prompt.trim().split(/\s+/).length : 0;
  return {
    score: Math.round((100 * got) / total),
    words,
    hits,
    missing: RULES.filter((r) => !hits[r.id]).sort((a, b) => b.weight - a.weight),
  };
}
