"""Economic results read off the hedonic model (F3).

F2 asked one question — how accurately can a price be predicted — and answered it with
ensembles, which are good at prediction and silent about magnitudes. F3 asks the opposite
kind of question: *how much* does a year of age cost, what does 10.000 km take off a price,
is the same vehicle cheaper in Antioquia than in Bogotá. Those are coefficients with
confidence intervals, so they come from the hedonic OLS and not from LightGBM.

The split of labour between this package and :mod:`autovalor.models` is deliberate:

:mod:`autovalor.models`
    Prediction. Judged out of sample on MAPE; the model of record is LightGBM.
:mod:`autovalor.analysis`
    Explanation. Judged on whether an effect is distinguishable from zero; the model of
    record is OLS with heteroskedasticity-robust standard errors.

The one place they meet is :mod:`autovalor.analysis.segments`, which reports *where* the
served model's error lands, and :mod:`autovalor.analysis.catalogue`, which contrasts what
SHAP says LightGBM leans on against what the hedonic estimates the same variable is worth.
"""
