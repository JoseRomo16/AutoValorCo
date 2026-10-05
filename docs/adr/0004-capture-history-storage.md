# ADR 0004 - Where the accumulated capture history lives

- Status: **proposed** — awaiting a decision
- Date: 2026-10-05

## Context

[ADR 0002](0002-weekly-capture-storage.md) parked the weekly captures in workflow
artifacts and said so explicitly as an interim measure: artifacts are retained for 90
days, and object storage was "the intended destination [...] in a follow-up ADR". This is
that follow-up, and the clock has started. The weekly workflow's first scheduled run was
Monday 2026-10-05, so its artifact disappears around **2027-01-03**. Every week that
passes without a destination is a week of history that will be lost rather than
accumulated.

The history is not optional. The monthly used-price index and the depreciation curves in
F3 are time series: they need captures from many weeks, not the latest snapshot. Temporal
validation is blocked for the same reason — `--split temporal` fails on purpose until the
lake spans 14 days (see `docs/STATUS.md`). None of that works off artifacts that expire
and have to be downloaded and unpacked by hand.

### What the data actually weighs

Measured on the current lake, not estimated: 13.696 bronze rows across 6 Parquet files
total **0,66 MB**. A full six-department sweep of both verticals is ~11.000 listings, so
roughly **0,4–0,5 MB per week**, or **~25 MB per year**. Parquet is already compressed, so
neither git nor an object store will shrink it further.

One thing would change that number by an order of magnitude: the detail-page enrichment
that is still an open decision in `docs/STATUS.md`. Version, transmission, fuel, body and
doors per listing turn one row of title tokens into a row of structured fields, and that
pass would also make the weekly workflow run for hours rather than minutes.

### The two candidates

**A. A `data` branch in this repository.** The weekly workflow commits each capture to an
orphan branch that holds no code. Free, no account, no credentials beyond a workflow token,
and every capture becomes a commit with a date — the history is auditable by anyone who can
read the repo, which has real value for a portfolio project. Three costs: it puts data in
git, which the project deliberately avoided for `data/`; the repository grows permanently,
because removing a capture later means rewriting history; and the capture workflow needs
`permissions: contents: write`, so a job that parses third-party HTML gains the ability to
write to the repository.

**B. Cloudflare R2.** S3-compatible object storage; the free tier is 10 GB with no egress
charges, so ~25 MB/year costs nothing and stays nothing for years. It keeps data out of
git, it is the only option that still works if the lake grows by an order of magnitude, and
it fits the pipeline unusually well: DuckDB reads `s3://` paths directly through `httpfs`,
and dbt already resolves the bronze source from a single glob
(`AUTOVALOR_BRONZE_GLOB`, see `.env.example`). Pointing that variable at a bucket is the
whole migration on the read side — no download step, no new code path in dbt. The costs are
an account, four secrets in the repository, credential rotation, and a small storage layer
plus a dependency that nothing else in the project needs today.

## Decision

**Not taken yet.** This ADR exists so the trade-off is on the record before the artifact
retention window forces the choice.

The recommendation is **A, the `data` branch**, on the grounds that it can be in place this
week with no account and no secrets, that 25 MB/year is negligible against the deadline it
removes, and that a visible capture history is worth something in a project meant to be
read. R2 stays the documented upgrade path.

One condition flips it: **if detail-page enrichment is approved, choose B.** Enrichment
multiplies the per-capture size and makes a permanently growing git history the wrong
container. The two decisions should therefore be taken in that order — enrichment first,
storage second.

## Consequences

If **A** is chosen:

- The weekly workflow gains a commit step and `contents: write`; the token is the
  workflow's own `GITHUB_TOKEN`, scoped to this repository.
- `data/` stays in `.gitignore` for the working tree; the captures live only on the orphan
  branch, so a normal clone does not pay for them (`git clone --single-branch` by default
  fetches only the default branch).
- Rebuilding the lake becomes `git fetch origin data` plus a checkout into `data/bronze/`,
  which keeps the capture filenames and therefore bronze immutability intact.
- A capture committed by mistake can only be removed by rewriting the branch.

If **B** is chosen:

- Four secrets (account id, access key id, secret access key, bucket) and a documented
  rotation step.
- `AUTOVALOR_BRONZE_GLOB` points at `s3://<bucket>/bronze/**/*.parquet` and dbt needs the
  DuckDB `httpfs` extension plus credentials in its profile; the write side needs an
  upload step in the workflow.
- Bucket versioning or a write-once policy has to be configured deliberately, because an
  object store will happily overwrite a key — git would not.

Either way:

- The artifact upload stays as a safety net, so a storage outage does not lose a capture.
- The deadline is real: whatever is chosen has to be running before **2027-01-03**, when
  the first scheduled capture's artifact expires.
