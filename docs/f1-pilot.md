# F1 pilot — capture quality and error sigma

Date: 2026-09-30 · Capture: 1.431 cars + 1.273 motorcycles, six departments, 5 search
pages per department and vertical.

The pilot exists to answer one question before scaling the capture: **how much price
variation does a simple model leave unexplained?** That number sizes the rest of F1.

## Capture quality

| Layer  | Rows  | Notes                                            |
| ------ | ----- | ------------------------------------------------ |
| bronze | 2.800 | Includes 96 rows from an earlier smoke capture   |
| silver | 2.791 | After collapsing repeats of the same asking price |
| gold   | 2.789 | Plausible rows only                              |

Only **2 rows** were rejected, both `price_too_high`. Every key field parses: price,
model year, mileage and location were present on 100 % of cards, and listing ids were
unique within each capture.

Coverage by department reflects the requested sweep, plus a tail from sponsored cards
that leak in from other regions:

| Department          | Cars | Motorcycles |
| ------------------- | ---- | ----------- |
| Bogotá D.C.         | 281  | 380         |
| Antioquia           | 239  | 241         |
| Valle del Cauca     | 231  | 239         |
| Cundinamarca        | 220  | 240         |
| Atlántico           | 240  | 74          |
| Santander           | 213  | 92          |
| Others (tail)       | 44   | 55          |

Atlántico has only 74 motorcycle listings in total — the result set ends after two
pages. This is how the 404-past-the-last-page behaviour was found.

## Baseline sigma by feature set

Hedonic OLS on `log(price)`. Each row adds features to the previous one. Rare models are
collapsed into `otro` (fewer than 10 listings) so the comparison is fair. The MAPE column
is an in-sample proxy computed from the log residuals, so read it as an upper bound and a
direction, not as a score.

| Vertical    | Features               | n     | σ (log) | R²    | MAPE proxy |
| ----------- | ---------------------- | ----- | ------- | ----- | ---------- |
| Cars        | age + km + department  | 1.468 | 0.578   | 0.358 | 54.6 %     |
| Cars        | + make                 | 1.468 | 0.416   | 0.677 | 34.9 %     |
| Cars        | + make + model         | 1.468 | 0.352   | 0.775 | 27.2 %     |
| Motorcycles | age + km + department  | 1.321 | 0.922   | 0.112 | 102.3 %    |
| Motorcycles | + make                 | 1.321 | 0.675   | 0.535 | 62.4 %     |
| Motorcycles | + make + model         | 1.321 | 0.630   | 0.604 | 54.5 %     |

Sample size needed for a segment mean within ±5 % at 95 % confidence, at the best σ
above: **199 cars** and **610 motorcycles** per segment.

## What this means

**The bottleneck was never the sample size, it was the feature set.** With only age,
mileage and department, R² is 0.36 for cars and 0.11 for motorcycles — the model is blind
to the dominant price driver, *which vehicle this is*. Age and mileage cannot separate a
Renault Logan from a Toyota Fortuner of the same year.

Make and model are not structured fields on the search card; they only exist inside the
title (`"Hyundai Hb20 2026 1.6 Advance Aut"`). Parsing them out costs no extra requests
and more than halves σ for cars. That is now part of gold, resolved against the
`vehicle_brands` seed: **99.2 % of cars** and **83.0 % of motorcycles** get a make.

What is still missing, and why the target is not yet in reach:

1. **Trim and engine displacement.** For motorcycles this is decisive — a 150 cc and a
   1200 cc of the same make and year differ by an order of magnitude in price, and
   displacement is often in the title (`"Xre 300"`, `"R 1200 Gs"`), so some of it can
   still be mined for free.
2. **The listing detail page** carries the rest as a structured attribute table:
   transmission, fuel, body style, doors, displacement, trim. Capturing it costs **one
   extra request per listing**. At the polite 2–6 s pause that is roughly three hours for
   a 2.700-listing sweep, and about **eight hours** at the F1 target of 6.000 cars and
   2.600 motorcycles. That is a decision about the shape of the weekly workflow, not an
   implementation detail: it goes from minutes to hours per run.

## Other findings

- **Quads and buggies sit inside the motorcycle vertical.** The pilot found ~30
  `cuatrimoto`/`buggy`/Can-Am/Polaris listings. They are a different market with a
  different price mechanism and should be segmented out, or modeled separately, before
  they distort the motorcycle model.
- **225 motorcycle titles still resolve to no make** (17 %). Most are titles that name
  only the model, or that open with filler (`"Moto ..."`, `"Hermosa ..."`, a dealer
  name). The high-volume cases were added to the seed; the rest is a long tail.
- **Sponsored cards leak across regions.** A department sweep returns a handful of
  listings from elsewhere (Quindío, Norte de Santander, Meta appear without being
  requested). Harmless for modeling, but it means `department` counts are not a clean
  sampling frame.
