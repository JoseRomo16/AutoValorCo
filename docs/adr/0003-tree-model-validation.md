# ADR 0003 - How the tree models see features and how they are tuned

- Status: accepted
- Date: 2026-10-01
- Updated: 2026-10-06 — CatBoost leaves the default run; see "CatBoost's place" below.

## Context

F2 compares the hedonic OLS baseline against LightGBM and CatBoost. Two choices in that
comparison are not obvious, and both would quietly invalidate the result if made the other
way.

**Feature encoding.** The baseline in `models/hedonic.py` one-hot encodes the categorical
columns and pools levels rarer than five listings into an "infrequent" bucket, because an
OLS cannot do anything else with 498 car models and 764 motorcycle models over 7.207 and
3.765 rows. Reusing that pipeline for the trees would have been convenient — the code
already exists and the comparison would look cleaner with a shared input.

**Validation during tuning.** Optuna needs a score per trial. The cheapest option is to
score against the held-out test set, which is also what makes the final number
meaningless: a holdout used to choose hyperparameters is a training set.

A third question sits underneath: the split already groups reposted vehicles, because the
same vehicle reappears under a new `listing_id` for about 7 % of car rows. Whether the
inner folds need the same treatment was an open question.

## Decision

**The tree models take categorical columns raw**, in each library's native form —
`category` dtype for LightGBM, `cat_features` for CatBoost — and do not reuse the hedonic
pipeline. Handling high cardinality without pooling is precisely the capability being
tested; feeding the trees a pre-pooled one-hot matrix would hold them to the baseline's
limitation and make the comparison answer a different question.

The tree feature set also drops `vehicle_age_squared` and `log_mileage_km`. Trees are
invariant to monotone transformations of a feature, so those columns add correlated splits
and nothing else.

**Tuning runs on grouped K-fold cross-validation over the training rows only**, three
folds, with groups from `dataset.group_keys` — the same function the train/test split uses.
The holdout is scored once, after the search, per model. The objective is the MAPE in
pesos, the same metric F2 accepts on, rather than a proxy on the log scale.

The budget is **asymmetric by model**: 40 trials for LightGBM, 20 for CatBoost. One fit on
the car vertical measures at ~6 s for LightGBM and ~18-55 s for CatBoost, so an equal
budget would spend most of the run on one model.

## Consequences

- The comparison answers the question it looks like it answers: whether native handling of
  high-cardinality categories beats pooled one-hot on this data.
- The reported held-out MAPE stays out-of-sample for every model, tuned or not.
- A reposted vehicle cannot inflate a fold score, so Optuna cannot select parameters that
  exploit the duplication.
- Three folds rather than five is a deliberate loss of precision in the *ranking* of
  hyperparameters, bought back as runtime. It does not touch the reported metric, which
  comes from the holdout.
- CatBoost is explored less thoroughly than LightGBM, so a CatBoost loss is weaker evidence
  than a LightGBM loss. Worth remembering before dropping it.
- `cv_mape` is logged next to `test_mape` in every MLflow run. A wide gap between them is
  the signal that the search overfitted the folds.

## CatBoost's place, settled 2026-10-06

Held-out MAPE, measured twice on two different lakes:

| Vertical | LightGBM | CatBoost | Gap |
| --- | --- | --- | --- |
| Cars, 7.207 rows | 11,5 % | 13,1 % | −1,6 pt |
| Cars, 7.639 rows | 11,3 % | 13,1 % | −1,8 pt |
| Motorcycles, 3.765 rows | 26,7 % | 26,8 % | −0,1 pt |
| Motorcycles, 4.052 rows | 24,1 % | **23,6 %** | **+0,5 pt** |

**On the 2026-10-06 lake CatBoost wins the motorcycle holdout**, which it had never done
before. It does not survive looking at the other half of the evidence: on the *same*
vertical the cross-validated MAPE goes the other way, 24,8 % for CatBoost against 24,0 %
for LightGBM. A ranking that flips depending on which partition you read is a tie. Cars are
unambiguous — CatBoost loses by 1,8 points on the holdout and 2,0 on CV.

**CatBoost is removed from the default `make train`** and stays reachable with
`--model catboost`. The reasons are about cost and coupling, not about a clean loss:

- **Switching the served model on motorcycles would cost the band and the explanation.**
  `models/quantiles.py` and `models/explain.py` are LightGBM-only. Serving CatBoost there
  means writing its three quantile models and its attribution path — and motorcycles are
  precisely the vertical whose range *is* published — all for 0,5 points that CV
  contradicts.
- **It costs more than half the run**: 46 of the ~110 minutes on cars, ~105 minutes on
  motorcycles. A default command that doubles in length to re-confirm a tie is a default
  that stops being run.

The asymmetric-budget caveat above is now the live question rather than a footnote: CatBoost
reached a tie on motorcycles with *half* the search budget. If that 0,5 points ever matters
— if motorcycles approach the 15 % target and the margin starts to count — the right move
is to re-measure both at 40 trials before changing anything, not to switch on this
evidence.
