# 0001: Trial balance is the primary input; AJPES is a cross-check

Date: 2026-10-09 · Status: accepted

## Context
The public AJPES data is not enough to run FDD on: it has about 89 lines a year, annual only, and covers capital companies only (see `docs/research/ajpes.md`). FDD analyses (QoE, NWC, net debt) need account-level, period-level data.

## Decision
- Every analysis starts from the target's trial balance (TB).
- Each account (konto) is mapped to an AOP line; the FDD views are built on that mapping.
- AJPES filings are used only as a cross-check: rolled-up TB at FY end vs. the filed AOP figures, with variances flagged.

## Consequences
- The konto→AOP mapping is the core component. The Enotni kontni okvir (standard chart of accounts) lets most of it be rule-based.
- The cross-check is possible only at financial year ends and only for companies that file with AJPES. For s.p. and some partnerships no API data exists.
- AJPES numbers never feed an analysis directly.
