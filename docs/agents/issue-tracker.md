# Issue tracker: GitHub

Issues and specs live in GitHub Issues for `smrik/argus-dd`. Use the `gh` CLI from this repo.
GitHub writes require user authorization; a direct request provides it. Choosing this tracker alone does not authorize publishing issues, comments, or labels.

## Conventions

- Read an issue: `gh issue view <number> --comments`. Fetch structured details, including labels, with `--json` when needed.
- List issues: `gh issue list --state open --json number,title,body,labels,comments`. Add appropriate state and label filters.
- Create an issue: `gh issue create --title "..." --body-file <file>`.
- Comment: `gh issue comment <number> --body-file <file>`.
- Add or remove labels: `gh issue edit <number> --add-label "..."` or `--remove-label "..."`.
- Close: `gh issue close <number>`. Publish any closing explanation with the comment command first.

For multiline bodies, save the exact text to a temporary UTF-8 file and pass `--body-file`.
The Git remote identifies the repository; `gh` resolves it automatically inside this clone.

## Pull requests as a triage surface

**PRs as a request surface: no.**

If this flag is changed to `yes`, triage external PRs with the same role labels, using `gh pr view`, `gh pr diff`, `gh pr list`, `gh pr comment`, `gh pr edit`, and `gh pr close`.
Keep PRs from `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE`; exclude `OWNER`, `MEMBER`, and `COLLABORATOR`.
GitHub issues and PRs share a number space. For an ambiguous number, try `gh pr view <number>` and fall back to `gh issue view <number>`.

## Skill instructions

- "Publish to the issue tracker" means create a GitHub issue, after user approval.
- "Fetch the relevant ticket" means run `gh issue view <number> --comments`.

## Wayfinding operations

- Map: one issue labelled `wayfinder:map`, with Notes, Decisions-so-far, and Fog sections.
- Child ticket: a GitHub sub-issue of the map. If sub-issues are unavailable, use a task list in the map and a `Part of #<map>` line in the child. Label by type: `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, or `wayfinder:task`.
- Blocking: use native issue dependencies. Add an edge with `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`. Get the numeric database ID with `gh api repos/<owner>/<repo>/issues/<number> --jq .id`; do not use the issue number or node ID. If dependencies are unavailable, use a `Blocked by: #<number>, ...` line.
- Frontier: inspect the map's open children in map order. Skip assigned children and any with open blockers. `issue_dependencies_summary.blocked_by` counts open blockers when native dependencies are available.
- Claim: after user approval, assign the first available child with `gh issue edit <number> --add-assignee @me` before starting work.
- Resolve: after user approval, comment with the answer, close the child, and add a short result and context link to the map's Decisions-so-far section.
