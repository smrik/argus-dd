# 0002: Deterministic core, Excel first, LLM only for small judgements

Date: 2026-10-09 · Status: accepted

## Context
Most FDD hours are "empty": organising data, building pivot-style tables, charting, and writing descriptive commentary. About 90% of slides (user estimate, not yet validated) fit five standard layouts. Professionals distrust "AI slides". Excel is the trusted working medium.

## Decision
- Code computes every number (group-by / SUMIFS-style analyses over a dataset). No LLM ever produces a figure.
- The LLM is limited to small judgements (e.g. classifying an account, flagging candidate one-offs) and to the wording of commentary around numbers code has already computed.
- Every number in generated text is verified against the data automatically.
- Excel is the system of record. PowerPoint is an export: native, editable charts and tables, never images.
- Output aims to get roughly 90% of the way; a manager reviews before anything goes out. The tool marks every LLM-made judgement so the reviewer knows where to look.
- Positioning: a workflow tool, not "AI slides" or "Canva for FDD".

## Consequences
- The layouts and analyses form a closed, versioned set, extended deliberately.
- Plain wording templates must work with the LLM switched off. The LLM only improves on them.
- Layouts are our own generic designs, never copied from a firm's templates.
