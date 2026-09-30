# F1 — capture quality and error sigma

Date: 2026-09-30 · Source: TuCarro, six departments (Bogotá D.C., Antioquia, Valle del
Cauca, Atlántico, Santander, Cundinamarca), 25 search pages per department and vertical.

The pilot existed to answer one question before scaling the capture: **how much price
variation does a simple model leave unexplained?** That answer turned out to change the
plan, so it is recorded here together with the full capture it led to.

## F1 volume targets

| Vertical    | Model-ready rows | F1 target | Status |
| ----------- | ---------------- | --------- | ------ |
| Cars        | 7.207            | ≥ 6.000   | met    |
| Motorcycles | 3.765            | ≥ 2.600   | met    |

| Layer  | Rows   | Notes                                                    |
| ------ | ------ | -------------------------------------------------------- |
| bronze | 13.696 | Every capture, append-only                                |
| silver | 10.982 | After collapsing repeats of the same listing and price    |
| gold   | 10.972 | Plausible rows only                                       |

Rejection is negligible: **10 rows** dropped between silver and gold. Price, model year,
mileage and location parse on essentially every card, and listing ids are unique within
each capture.

Feature coverage mined from the title, at no extra request cost:

| Vertical    | Make resolved | Engine size | Distinct makes | Distinct models |
| ----------- | ------------- | ----------- | -------------- | --------------- |
| Cars        | 99.2 %        | 86.0 %      | 47             | 498             |
| Motorcycles | 81.0 %        | 80.6 %      | 31             | 764             |

## Sigma by feature set

Hedonic OLS on `log(price)`; each row adds features to the previous one. Rare models are
collapsed into `otro` (fewer than 10 listings). The MAPE column is an in-sample proxy
computed from the log residuals — read it as an upper bound and a direction, not a score.

| Vertical    | Features               | n     | σ (log) | R²    | MAPE proxy |
| ----------- | ---------------------- | ----- | ------- | ----- | ---------- |
| Cars        | age + km + department  | 7.207 | 0.580   | 0.331 | 55.9 %     |
| Cars        | + make                 | 7.207 | 0.392   | 0.697 | 33.2 %     |
| Cars        | + make + model         | 7.207 | 0.252   | 0.877 | 17.6 %     |
| Cars        | + engine size          | 7.207 | **0.244** | 0.885 | 17.5 %   |
| Motorcycles | age + km + department  | 3.765 | 0.970   | 0.104 | 113.8 %    |
| Motorcycles | + make                 | 3.765 | 0.663   | 0.585 | 63.0 %     |
| Motorcycles | + make + model         | 3.765 | 0.587   | 0.682 | 50.2 %     |
| Motorcycles | + engine size          | 3.765 | **0.541** | 0.730 | 43.7 %   |
| Motorcycles | same, quads excluded   | 3.644 | 0.534   | 0.727 | 42.8 %     |

## What this means

**The bottleneck was never the sample size, it was the feature set.** With only age,
mileage and department, R² is 0.33 for cars and 0.10 for motorcycles: the model is blind
to the dominant price driver, *which vehicle this is*. Age and mileage cannot separate a
Renault Logan from a Toyota Fortuner of the same year. Note that going from 1.468 to
7.207 cars barely moved σ for the weakest feature set (0.578 → 0.580) — volume alone buys
nothing. What volume does buy is estimable model dummies: at 1.468 cars most of the 296
models fell into `otro`, which is why make+model improves σ far more at 7.200 rows
(0.252) than it did at 1.468 (0.352).

Make, model and engine size are not structured fields on the search card; they only exist
inside the title (`"Hyundai Hb20 2026 1.6 Advance Aut"`). Parsing them out is free and
takes cars from σ 0.580 to **0.244** — an in-sample MAPE proxy of 17.5 %, within sight of
the 15 % target once F2 replaces OLS with gradient boosting.

**Motorcycles are the open problem.** σ 0.54 and R² 0.73 are far from the target. Three
reasons, in order of size:

1. **Trim is missing and matters more than for cars.** Model alone does not separate a
   base from a fully-equipped variant, and motorcycle prices swing hard on it.
2. **19 % of titles resolve to no make**, against 0.8 % for cars. Motorcycle titles often
   name only the model, or open with filler (`"Moto ..."`, a dealer name). The
   high-volume cases are in the `vehicle_brands` seed; the rest is a long tail.
3. **The `model` token is noisier**: 764 distinct values for 3.765 listings means many
   are trim fragments rather than models.

## Other findings

- **Quads, buggies and side-by-sides sit inside the motorcycle vertical** — 121 listings,
  now flagged as `is_quad` in gold rather than dropped, so F2 can segment them. Excluding
  them moves σ from 0.541 to 0.534: real but small.
- **An offset past the last page returns 404**, not an empty page. Found when Atlántico
  ran out of motorcycles at 71 listings; it had already cost one full motorcycle capture
  before being handled.
- **Sponsored cards leak across regions.** A department sweep returns a handful of
  listings from elsewhere, so `department` counts are not a clean sampling frame.
- **A displacement typed as `4000cc` on a motorcycle passed through** until the explicit
  `NNNcc` match was given the same range check as the inferred one. Both are just numbers
  someone typed.

## Next

The remaining features — trim, transmission, fuel, body style, doors — live on the
listing detail page as a structured attribute table, at **one extra request per listing**.
At the polite 2–6 s pause that is roughly four hours for the current 11.000 listings. That
is a decision about the shape of the weekly workflow, not an implementation detail: it
goes from minutes to hours per run. The recommendation is an incremental enrichment pass
with a per-run budget, enriching only listings that do not have detail yet, rather than a
monolithic sweep.
