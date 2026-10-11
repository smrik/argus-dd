# Domain docs

This repo uses a single context.

## Before exploring

- Read root `CONTEXT.md` for domain terms and relationships.
- Read relevant decisions in `docs/adr/`.
- If a root `CONTEXT-MAP.md` is added later, follow its pointers to the context files relevant to the work.

If these files are missing, proceed silently. Do not flag their absence or create placeholders.
Domain-modeling workflows create context and decision documents when terms or decisions are resolved.

## Layout

- `CONTEXT.md`: shared vocabulary and relationships.
- `docs/adr/`: numbered architecture decision records.

## Vocabulary

Use terms defined in `CONTEXT.md` in issue titles, proposals, hypotheses, and tests.
Avoid synonyms the glossary rejects. If a term is missing, reconsider invented terminology or note the gap for domain modeling.

## Decision conflicts

If a proposal conflicts with an existing ADR, explicitly name the ADR and explain why the decision should be reconsidered.
