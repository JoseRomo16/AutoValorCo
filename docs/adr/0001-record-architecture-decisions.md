# ADR 0001 - Record architecture decisions

- Status: accepted
- Date: 2026-09-29

## Context

AutoValor CO spans scraping, a medallion data lake, modeling and a public API. Decisions
taken in one layer (for example modeling `log(price)`, or excluding `valor_fasecolda` from
the feature set) constrain the others, and the reasons behind them are easy to lose.

## Decision

Every non-trivial technical decision is recorded as a numbered ADR in `docs/adr/`, using
this template: Context, Decision, Consequences. ADRs are immutable once accepted; a change
of course is a new ADR that supersedes the previous one.

## Consequences

- New contributors can reconstruct the reasoning without reading the full history.
- Each phase (F0-F4) closes with its decisions written down, not only with working code.
- Small overhead per decision; trivial choices are not recorded.
