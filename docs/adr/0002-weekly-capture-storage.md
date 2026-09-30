# ADR 0002 - Where weekly captures are stored

- Status: accepted
- Date: 2026-09-29

## Context

From F1 onwards a GitHub Actions workflow captures listings every week. The dataset
only becomes useful by accumulating: F1 closes with at least 6.000 clean cars and 2.600
clean motorcycles, and the monthly price index needs a history of captures, not a
snapshot. But `data/` is deliberately in `.gitignore`, so a CI run has nowhere obvious
to leave its output.

Three options were considered:

1. **Workflow artifacts.** No extra infrastructure and no secrets, but artifacts expire
   (90 days here) and have to be downloaded by hand to be combined.
2. **Commit captures to a data branch.** Free, durable and diffable. A weekly sweep is
   roughly 500 kB of Parquet, so the repository would grow by ~25 MB a year, and the
   captures would be versioned alongside the code that produced them. It does, however,
   put data in git, which the project explicitly avoided for `data/`.
3. **Object storage (S3 / Cloudflare R2).** The right answer at scale, durable and cheap,
   but it needs an account, credentials in repository secrets and a storage layer in the
   code that nothing else needs yet.

## Decision

Weekly captures are uploaded as **workflow artifacts** for now, with a 90-day retention.
The workflow fails if a capture is empty, so a silent breakage surfaces as a red run
rather than as a gap in the data.

Object storage is the intended destination and will be adopted in a follow-up ADR once
the accumulated dataset is worth more than the setup cost — in practice, as soon as the
first captures are needed to train rather than to validate the pipeline.

## Consequences

- No credentials and no new infrastructure to run the weekly capture today.
- **Captures older than 90 days are lost**, so the retention window is a hard deadline
  for moving to object storage. Until then, the accumulating dataset has to be pulled
  down and kept locally.
- The bronze layer stays immutable and reproducible either way: each capture is a
  separate file named after its UTC timestamp, so downloaded artifacts can simply be
  unpacked side by side into `data/bronze/`.
