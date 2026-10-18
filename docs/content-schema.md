# Content schema

All learning content lives in `content/` as YAML and is loaded into Postgres by
`python -m app.content.seed` (services/api). Content is versioned in git and
reviewed by PR — rubrics in particular stay human-authored.

```
content/
  course.yaml                 course metadata, product case, module order
  techniques.yaml             controlled vocabulary (technique ids)
  rubrics/core-v1.yaml        core rubric (criteria ids: task_fit, structure,
                              constraints, groundedness, consistency, efficiency)
  modules/<module-id>/
    module.yaml
    cards/<card-id>.yaml      concept cards (rendered into visual templates)
    labs/<lab-id>.yaml        hands-on labs (brief + pinned test set)
```

IDs are kebab-case and globally unique. Card ids are prefixed by the module
number (`m03-few-shot-anatomy`), lab ids too (`m03-lab-review-tagger`).

## module.yaml

```yaml
id: m03-examples
order: 3
title: Show, don't just tell — examples
summary: One or two sentences, learner-facing.
design_stage: define          # empathise | define | ideate | prototype | test | none
design_stage_note: How this module advances the Meenakshi Textiles case.
tier: free                    # free | pro   (m00-m02 free, rest pro)
estimated_minutes: 35
techniques: [zero-shot, one-shot, few-shot, exemplar-selection]
objectives:
  - Learner-facing "you will be able to…" statements (3-4)
cards: [m03-why-examples, m03-few-shot-anatomy, m03-choosing-examples]   # in order
labs: [m03-lab-review-tagger, m03-lab-case-whatsapp-replies]             # in order
```

## Concept card (`cards/*.yaml`)

```yaml
id: m03-few-shot-anatomy
title: Anatomy of a few-shot prompt
technique: few-shot           # one technique id from techniques.yaml
template: anatomy             # anatomy | compare | flow | checklist | callout | spectrum
takeaway: One sentence the learner should remember.
body: >                       # 2-4 sentences of explanation, plain English, no fluff
  ...
data: { ... }                 # shape depends on template, see below
source: Attribution string (paper / guide). Original wording only — do not copy text.
```

Template `data` shapes:

- **anatomy** — an annotated prompt, split into labelled segments:
  `{ parts: [ { label: "Role", text: "You are…", note: "why this part matters" } ] }`
- **compare** — weak vs strong prompt with their (illustrative) outputs:
  `{ left: { label: "Before", prompt: "...", output: "..." }, right: { label: "After", prompt: "...", output: "..." }, verdict: "what changed and why" }`
- **flow** — ordered steps: `{ steps: [ { label: "...", detail: "..." } ] }`
- **checklist** — `{ items: [ { label: "...", detail: "..." } ] }`
- **callout** — `{ headline: "...", stat: "optional short number/fact", detail: "..." }`
- **spectrum** — `{ left_label: "...", right_label: "...", points: [ { label: "...", position: 0-100, note: "..." } ] }`

## Lab (`labs/*.yaml`)

```yaml
id: m03-lab-review-tagger
title: Tag customer reviews
difficulty: 2                 # 1 easy | 2 medium | 3 hard
estimated_minutes: 12
techniques_targeted: [few-shot, exemplar-selection]
uses_product_case: false      # true for the Meenakshi Textiles lab of the module
brief: |
  A real, slightly messy brief written as the requester would write it (an
  email/WhatsApp message from a person with a goal). Markdown allowed.
  Include the hidden constraints a good prompt must surface (audience, length,
  tone, format, what must not be done).
input_label: Review           # what each test-case input is called in the UI
test_cases:                   # 3-4 pinned inputs; the LAST one is the hard edge case
  - id: tc1
    input: |
      The text that fills {{input}} in the learner's prompt.
    note: What makes this case interesting (shown to learner after the run).
starter_prompt: |             # a weak v0 the learner can start from (optional but recommended)
  ...
reference_prompt: |           # a strong prompt — hidden from learners; used for
  ...                         # cache precompute and critic calibration. Must use {{input}}.
success_criteria:             # brief-specific, checkable statements for the critic
  - Each tag is one of: product, service, price, delivery.
rubric:
  base: core                  # always core
  extra_criteria:             # optional, 0-2 lab-specific criteria, same shape as core
    - id: label_accuracy
      name: Label accuracy
      weight: 2
      description: ...
      diagnoses_prompt: ...
      anchors: {0: ..., 1: ..., 2: ..., 3: ..., 4: ...}
predictions:                  # 1-2 one-tap prediction questions shown while the run is in flight
  - id: p1
    question: "You added two examples. What will change most?"
    options: ["...", "...", "..."]
    answer: 1                 # 0-based index
    explanation: Revealed when the output lands.
hints:                        # progressive hints, mildest first (2-3)
  - ...
```

Prompt execution: the learner's prompt is run once per test case. `{{input}}`
in the prompt is replaced by the test-case input; if it is absent the input is
appended after the prompt inside `<input>…</input>` tags. Use `{{input}}` in
reference prompts.

Writing guidelines:
- Briefs are realistic for Indian college students and Madurai contexts
  (local businesses, college clubs, internships, regional languages), varied
  across domains (writing, data, code/SQL, design critique, research).
- Plain, warm English. No hype words. Short sentences.
- Test cases must differ meaningfully; the last one must break a naive prompt.
- All text is original. Cite ideas in `source`, never copy passages.
