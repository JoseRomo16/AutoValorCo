# ADR 0006 - Drop `city` from the model, and what the band does without it

- Status: **accepted** for dropping `city` (decided before the block). **Proposed** for the
  three points under "Open for the owner", which wait for a decision.
- Date: 2026-11-02
- Measurements: [`docs/reports/block4_baseline.json`](../reports/block4_baseline.json)
  (before) and [`docs/reports/block4_after.json`](../reports/block4_after.json) (after),
  both produced by `python -m autovalor.models.band_diagnostics` on the same holdout
  (1.689 cars, 901 motorcycles, seed 20260930).

## Context

The valuation form asks for the department and never the city. `api/features.py` therefore
sent the same constant on every request, `city = "Desconocida"`, while the trees used `city`
as a categorical feature. In training "Desconocida" was the level of the locations that did
not parse: a small, particular group that **does not occur once in the holdout**. Every real
valuation carried that group's effect.

The published figures could not see it, because they were measured with each listing's real
city, which the API never sends.

## Finding: the car label shipped on a band that missed the gate as served

Measured on bundle `2026-10-25.12948`. "Served" is the holdout with the values `/predict`
actually sends (city "Desconocida"; official store, quad and cargo `False`).

| | Cars, published | **Cars, served** | Motorcycles, published | **Motorcycles, served** |
| --- | --- | --- | --- | --- |
| Band coverage (gate window 78-82 %) | 80,0 % | **75,0 %** | 79,4 % | **69,7 %** |
| MAPE | 10,3 % | 10,4 % | 22,0 % | 21,7 % |
| Mean bias (log) | −0,009 | −0,019 | +0,001 | **−0,058** |

The car label was published because the gate read 80,0 %. For the rows the API actually
scores the band covered 75,0 %, **outside the window**, so the label was calling listings
bargains and expensive on a band that did not meet the product's own rule. Motorcycles
withheld the label already (on width), and their served coverage, 69,7 %, also missed.

The cause is one variable: forcing only the three booleans leaves car coverage at 80,6 %;
forcing only the city takes it to 75,7 %.

Two more consequences of the same variable:

- **The department did not carry geography.** On the same vehicle, switching department
  moved the estimate by −0,2 % to +0,2 % at most, while `/market` publishes up to +27 % for
  motorcycles in Antioquia. The city absorbed it.
- **The coverage under "Otro departamento" was not the problem.** With the real city,
  averaging over the other departments left coverage where it was (80,7 % / 79,8 %).

## Decision

1. **`city` leaves the model.** Out of `TREE_CATEGORICAL`, out of the API frame and out of
   the factor labels. The column stays in silver and gold as data.
2. **The published figures are measured as the API serves.** `models/serving.py` holds the
   one mapping of values `/predict` fixes (`SERVING_ASSUMPTIONS`); `to_frame` writes it into
   every request, and training applies it through `as_served` to the calibration rows and to
   the holdout before the error, the band and the gate are measured. Trees still fit on the
   real values, where a column like `is_official_store` works as a control.
3. **A parity test keeps it that way** (`tests/models/test_serving_parity.py`). It fails if
   `to_frame` fixes a model column that is not declared, or if the band is calibrated or
   scored with a value the API cannot send. A future column cannot reopen the gap silently.
4. **`/explain` flags assumptions.** `Factor.assumed` (additive) is true for the fixed
   columns, and a test pins that every factor is either typed by the caller, flagged, or the
   region stated as the average of departments.
5. In the same retraining, **motorcycle family prefixes are read with their number**:
   "BMW R 1250 GS" was model `r` for 101 listings spanning a R 18 to a R 1300, and "Yamaha
   MT 15" was `mt`. BMW levels keep BMW's spacing ("R 1250 GS"). No catalogue model is a
   single letter except the Zeekr X, whose name is the letter.

## Before and after

Same partition, same 40-trial search, same conformal calibration. "Before" is the old bundle
**as served**; "after" is the new bundle `2026-11-02.12948`, served and published being the
same thing now.

| | Cars before | **Cars after** | Motorcycles before | **Motorcycles after** |
| --- | --- | --- | --- | --- |
| MAPE (random partition) | 10,4 % | **10,0 %** | 21,7 % | **20,4 %** |
| MAPE (temporal partition) | 11,6 % | **11,4 %** | 23,5 % | **21,9 %** |
| Hedonic OLS reference | 12,9 % | 12,9 % | 34,6 % | 33,2 % |
| Band coverage | 75,0 % | **80,2 %** | 69,7 % | **80,5 %** |
| Mean band width | 37,5 % | 38,5 % | 84,7 % | **70,0 %** |
| Label | published (wrongly) | **published** | withheld | **withheld** (width only, 70 % > 60 %) |
| "Otro departamento" coverage | 75,7 % | **80,0 %** | 70,4 % | **80,4 %** |
| Estimate position, median (0 = P10, 1 = P90) | 0,51 | 0,49 | 0,45 | 0,50 |
| Rows where the band widens to contain the estimate | 4,9 % | **2,8 %** | 10,5 % | **4,0 %** |
| MAPE of the band's own P50 (first measured) | 10,9 % | 10,5 % | 23,3 % | 22,7 % |
| Department effect on the same vehicle | −0,2 to 0,0 % | **−3,2 to +1,6 %** | −0,1 to +0,2 % | **−7,3 to +3,2 %** |

- **The car target holds** (10,0 % against 15 %) and both verticals still beat the OLS.
- **No threshold was touched.** Motorcycles still fail the width condition, and the gate
  withholds their label on its own.
- **Dropping the city cost no accuracy**: both MAPEs went down.
- **The department now moves the estimate, in the direction `/market` reports** for most
  departments, but far less than the hedonic effect (+3,2 % against +27 % for motorcycles in
  Antioquia). The likely reading — not verified — is that the trees attribute part of the
  regional difference to the mix of makes and models, which the hedonic holds fixed through
  pooled brand groups only. It is a difference between two models answering different
  questions, not a bug, and Metodología should not present one as the other.

## Open for the owner

### (a) Withhold the label only under "Otro departamento"?

**Not needed.** The measurement specified in `docs/STATUS.md` (each row averaged over the
other departments, its own excluded and the weights renormalised) gives **80,0 %** on cars
and **80,4 %** on motorcycles, inside 78-82 %. Recommendation: keep the label for uncovered
departments; nothing to implement.

### (b) The estimate against an edge of the band

On the real holdout the estimate is centred (median position 0,49 and 0,50) and the band
widens to contain it in 2,8 % and 4,0 % of rows, down from 4,9 % and 10,5 %.

On the live audit's grid (five most-listed makes, their commonest model, years
2012/2018/2023, 20.000/80.000 km, Bogotá), rebuilt from the bundle's catalogue:

| | Old bundle median | Old outer share | New median | New outer share |
| --- | --- | --- | --- | --- |
| Cars | 0,36 | 20 % | 0,53 | 23 % |
| Motorcycles | **0,11** | **77 %** | 0,30 | 40 % |

The audit's 0,10 on motorcycles was mostly the city: without it the grid moves to 0,30.
It is still below centre on the grid, and the P90 still reaches ~6× the P10 for some cheap
motorcycles, but the grid is 30 hand-picked combinations, several of them unusual (a 2012
motorcycle with 20.000 km), while the holdout is the real distribution of listings.

Options, as the plan framed them:

- **e) Centre the band on the point estimate** and recalibrate the conformal widening on
  that band. Guarantees the estimate sits in the middle by construction; costs a retrain
  and a new calibration, and throws away the quantile models' asymmetry, which is real for
  prices (a cheap vehicle can be overpriced by more than it can be underpriced).
- **f) Use the band's P50 as the estimate.** Its MAPE is now measured and is worse: 10,5 %
  against 10,0 % on cars, 22,7 % against 20,4 % on motorcycles. Not recommended.
- **g) Change nothing.** Supported by the holdout.

**Recommendation: g**, with the regression test that now pins the grid
(`tests/models/test_served_band_position.py`: median within 0,25-0,75, at most half the
grid in the outer fifths; the old bundle fails both on motorcycles). If the owner prefers e,
it goes in its own PR, as agreed.

### (c) Which error Metodología publishes

`/model-info` carries both: the random partition (`metrics.mape`, 10,0 % / 20,4 %) and the
temporal one (`metrics_temporal.mape`, 11,4 % / 21,9 %), where the most recent fifth of the
listings is held out by date.

- The **random** figure is the one the gate, the band and the README use, and the only one
  measured on the served model itself.
- The **temporal** figure is closer to the question a user asks ("how wrong will it be on a
  listing published after training?"), but with 19 days of captures it separates very
  little: the cut falls inside the same capture window, and the split-by-date decision is
  still open (`docs/STATUS.md`).

**Recommendation: publish both, with their definitions** — the random one as the headline,
because it is the one every other published figure is measured against, and the temporal
one beside it as "on listings newer than the training data", with the caveat about the span
until the capture resumes. The page already reads both from `model.json`, so this is copy,
not data.

## Consequences

- Bundles exported before this change read `city` and **cannot be served** by this API; the
  new bundle ships in the same PR. Deploy the API before the site.
- Every published figure moved, and README, `docs/results/` and Metodología read the new
  ones from files; nothing was typed.
- The parity test turns "a figure measured on values the API cannot send" from a silent
  error into a red CI run.
