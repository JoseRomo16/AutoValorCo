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

## Baseline sigma

Hedonic OLS on `log(price)`, using only what the search card provides:
`vehicle_age_years + log1p(mileage_km) + department + is_official_store`.

| Vertical    | n     | σ (log) | R²    | In-sample MAPE | n for ±5 % segment mean |
| ----------- | ----- | ------- | ----- | -------------- | ----------------------- |
| Cars        | 1.468 | 0.578   | 0.358 | 54.6 %         | 514                     |
| Motorcycles | 1.321 | 0.922   | 0.112 | 102.3 %        | 1.308                   |

## What this means

**The bottleneck is the feature set, not the sample size.** σ of 0.58 and 0.92 implies a
MAPE far above the 15 % target, and R² of 0.36 / 0.11 says the model is missing the
dominant price driver: *which vehicle this is*. Age and mileage cannot separate a
Renault Logan from a Toyota Fortuner of the same year.

Two consequences for the rest of F1:

1. **Make, model and trim have to become features.** The search card does not carry
   them as structured fields, only inside the title string
   (`"Hyundai Hb20 2026 1.6 Advance Aut"`). Parsing brand and model out of the title is
   free and should come first, since it is likely to move R² more than any extra volume
   of listings.
2. **The listing detail page carries the rest** — transmission, fuel, engine
   displacement, body style, doors, trim — as a structured attribute table. Capturing it
   costs **one extra request per listing**. At the polite 2–6 s pause that is roughly
   three hours for a 2.700-listing sweep, and it grows linearly with the F1 target of
   6.000 cars and 2.600 motorcycles (~8 hours). That is a real decision, not an
   implementation detail: it changes the weekly workflow from minutes to hours.

The sample-size column is therefore a lower bound, useful for per-segment reporting
(≈500 cars per segment for a ±5 % mean) but not a substitute for better features. The F1
targets of 6.000 cars and 2.600 motorcycles remain the right volume; they are simply not
sufficient on their own.
