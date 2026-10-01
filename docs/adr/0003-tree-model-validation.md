# ADR 0003 - How the tree models see features and how they are tuned

- Status: accepted
- Date: 2026-10-01

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
