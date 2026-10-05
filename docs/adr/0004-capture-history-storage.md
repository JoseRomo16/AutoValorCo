# ADR 0004 - Where the accumulated capture history lives

- Status: accepted
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

**A, the `data` branch.** It is in place with no account and no secrets, 25 MB/year is
negligible against the deadline it removes, and a visible capture history is worth
something in a project meant to be read. **Cloudflare R2 stays the documented upgrade
path**, and the mechanism is built so that taking it is a small change rather than a
rewrite: `AUTOVALOR_BRONZE_GLOB` already points dbt at the bronze layer through a single
glob, and DuckDB reads `s3://` directly, so the read side becomes a change of variable.

Detail-page enrichment was approved in the same decision, which is the condition this ADR
had flagged as a reason to prefer R2 from the start. It does not reverse the choice, for
two reasons that only became visible once the enrichment was scoped: it is **incremental
and motorcycle-only**, so it adds one row of parsed attributes per listing rather than
multiplying the capture, and the detail rows are stored parsed rather than as HTML. The
threshold to revisit is therefore a size one, recorded below, not the enrichment itself.

## Consequences

Chosen — **A**:

- The weekly workflow gains a commit step and `contents: write`; the token is the
  workflow's own `GITHUB_TOKEN`, scoped to this repository.
- `data/` stays in `.gitignore` for the working tree; the captures live only on the orphan
  branch, so a normal clone does not pay for them (`git clone --single-branch` by default
  fetches only the default branch).
- Rebuilding the lake is `make pull-history`, which copies the published Parquet into
  `data/bronze/` without overwriting anything, so the capture filenames and therefore
  bronze immutability survive the round trip. Silver and gold are rebuilt from there with
  `make transform`; only bronze is ever published.
- A capture committed by mistake can only be removed by rewriting the branch.
- One mechanism — `autovalor.ingest.history` — serves the workflow, the Makefile and a
  manual seed, so there is a single place where this can be wrong.

The upgrade to **B** costs, when the time comes:

- Four secrets (account id, access key id, secret access key, bucket) and a documented
  rotation step.
- `AUTOVALOR_BRONZE_GLOB` points at `s3://<bucket>/bronze/**/*.parquet` and dbt needs the
  DuckDB `httpfs` extension plus credentials in its profile; the write side replaces the
  publish step.
- Bucket versioning or a write-once policy has to be configured deliberately, because an
  object store will happily overwrite a key — git would not.

**When to revisit.** Three triggers, in the order they are likely to arrive: the branch
passes ~500 MB; a weekly capture stops fitting in a commit that is cheap to clone; or the
detail enrichment is extended beyond motorcycles and starts carrying per-listing HTML-sized
payloads rather than parsed rows.

Regardless:

- The artifact upload stays as a safety net, so a failure to publish does not lose a
  capture. The two paths are independent on purpose.
- The deadline was real and is now met: the branch is seeded ahead of **2027-01-03**, when
  the first scheduled capture's artifact would have expired.
