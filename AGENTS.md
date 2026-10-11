# Project instructions

## Working rules

- Follow global Codex guidance and any more specific `AGENTS.md` instructions in the area being edited.
- Keep changes focused on the requested task. Preserve unrelated user changes and prefer simple solutions.
- Report extremely concisely.
- Inspect `git status` and relevant diffs before finishing. Do not commit or push unless requested.
- Destructive Git operations and external writes require user authorization. A direct request counts as authorization; do not ask again for an already authorized action.
- Do not expose or commit secrets. Read credential files only when required by the task and explicitly allowed.
- Invoke optional skills, subagents, handoff systems, and workflow frameworks only when requested or explicitly enabled by this project. The configuration below records conventions; it does not enable automatic invocation.

## OpenAI GPT-6 guidance

Applies to `gpt-6.1-sol`, `gpt-6-astra`, and other GPT-6 models. Verified 2026-10-09 against [OpenAI's GPT-6 prompting guide](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra.md#prompting-best-practices). OpenAI describes Astra behaviors and recommends evaluating these prompts with the chosen model and workload.

- Treat action requests as instructions to complete the scoped work. Make reasonable assumptions for routine gaps; ask only when missing input materially changes the outcome.
- Before required approval, finish authorized preparation and present a concrete result to review. Respect the authorization boundaries above.
- User instructions take precedence over skill guidance. If a skill blocks progress, link its exact `SKILL.md`, quote the rule, and explain its application. Do not infer extra approval gates.
- Lead with the result. Use plain, concise language, essential evidence, and minimal formatting; avoid jargon and stock phrases.
- Subagents remain opt-in; when authorized, assign independent tasks with clear scope and readable messages.
- Calibrate verification to the change. Run relevant checks; repeat or broaden them only for new changes, failures, or unresolved concerns. Avoid tests that merely mirror low-impact reversible edits.

## Agent skills

### Issue tracker

Track issues and specs in GitHub Issues for `smrik/argus-dd`. See `docs/agents/issue-tracker.md`.

### Triage labels

Use casual labels: `needs-a-look`, `need-more-info`, `ready-for-ai`, `ready-for-me`, and `not-doing`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context layout: root `CONTEXT.md` and `docs/adr/`. See `docs/agents/domain.md`.

### Research notes

`docs/research/<topic>.md`: verified external facts (sources, APIs, codes) so they are not re-researched. Check here before web research. Format: frontmatter (`topic`, `researched` date, `status`), terse bullets/tables, source URL per fact, unverified items only under `## Open`. Update in place; bump `researched`.

- `ajpes.md`: AJPES LP API, data limits, key AOP codes.
- `tb-sources.md`: publicly exposed real trial balances (web harvest), official kontni načrt locations.
