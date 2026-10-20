"use client";

/**
 * The valuation form and its result.
 *
 * Three decisions worth knowing before changing this.
 *
 * **The lists come from `/catalog`, not from constants.** The served trees carry frozen
 * categorical levels, so a make they never saw is routed down their missing branch and
 * still yields a confident-looking number. A `<select>` built from the model's own
 * training rows cannot ask that question. It also means the first paint has no lists and
 * says so, instead of rendering empty dropdowns.
 *
 * **`/predict` and `/explain` are requested together.** They are two calls against the
 * same model and the same row, and after the consistency fix they agree on the estimate
 * exactly, so showing one without the other would be showing half an answer.
 *
 * **The cold start is a product fact, not an error.** The free instance sleeps, so the
 * first request of the day takes about a minute. The notice is on screen before anyone
 * presses the button, and a failure says what probably happened rather than printing a
 * bare TypeError.
 */

import { useEffect, useMemo, useState } from "react";

import { useLang } from "./LanguageProvider";
import { PriceResult } from "./PriceResult";
import {
  ApiError,
  fetchCatalog,
  fetchExplanation,
  fetchPrediction,
  type ExplainResponse,
  type PredictRequest,
  type PredictResponse,
  type VehicleType,
  type VerticalCatalog,
} from "@/lib/api";
import { copy } from "@/lib/i18n";
import { integer } from "@/lib/format";

/** Below this many training listings a model token goes under "show all". */
const RARE_MODEL_LISTINGS = 3;

const FIELD =
  "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm transition focus:border-emerald-600 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900";
const LABEL = "mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300";
const HINT = "mt-1 text-xs text-slate-500 dark:text-slate-400";

type Status = "loading-catalog" | "ready" | "submitting" | "failed";

export function ValuationForm() {
  const { lang, t } = useLang();

  const [catalogs, setCatalogs] = useState<VerticalCatalog[]>([]);
  const [status, setStatus] = useState<Status>("loading-catalog");
  const [error, setError] = useState<string | null>(null);

  const [vehicleType, setVehicleType] = useState<VehicleType>("car");
  const [brand, setBrand] = useState("");
  const [model, setModel] = useState("");
  const [year, setYear] = useState("");
  const [mileage, setMileage] = useState("");
  const [department, setDepartment] = useState("");
  const [engineCc, setEngineCc] = useState("");
  const [askingPrice, setAskingPrice] = useState("");
  const [showRareModels, setShowRareModels] = useState(false);

  const [prediction, setPrediction] = useState<PredictResponse | null>(null);
  const [explanation, setExplanation] = useState<ExplainResponse | null>(null);
  const [reloads, setReloads] = useState(0);

  // The effect only starts the request; the state lands in the promise callbacks. Setting
  // status synchronously here would be a cascading render, and the initial state already
  // says "loading", so there is nothing to synchronise.
  useEffect(() => {
    let live = true;
    fetchCatalog()
      .then((response) => {
        if (!live) return;
        setCatalogs(response.verticals);
        setStatus("ready");
      })
      .catch((cause: unknown) => {
        if (!live) return;
        setError(cause instanceof ApiError ? cause.message : String(cause));
        setStatus("failed");
      });
    return () => {
      live = false;
    };
  }, [reloads]);

  const catalog = useMemo(
    () => catalogs.find((entry) => entry.vehicle_type === vehicleType),
    [catalogs, vehicleType],
  );

  /**
   * Switching vertical invalidates every level — motorcycle makes are not car makes — so
   * the reset happens in the handler rather than in an effect watching `vehicleType`.
   * An effect would render the stale form once before clearing it.
   */
  function chooseVehicleType(next: VehicleType) {
    setVehicleType(next);
    setBrand("");
    setModel("");
    setDepartment("");
    setEngineCc("");
    setShowRareModels(false);
    setPrediction(null);
    setExplanation(null);
  }

  const brands = catalog?.brands ?? [];
  const selectedBrand = brands.find((entry) => entry.name === brand);
  const models = selectedBrand?.models ?? [];
  const commonModels = models.filter((entry) => entry.listings >= RARE_MODEL_LISTINGS);
  const shownModels = showRareModels || commonModels.length === 0 ? models : commonModels;

  const years = useMemo(() => {
    if (!catalog) return [];
    const { min, max } = catalog.model_year;
    return Array.from({ length: Math.round(max - min) + 1 }, (_, index) => Math.round(max) - index);
  }, [catalog]);

  const complete = brand !== "" && year !== "" && mileage !== "" && department !== "";

  function payload(): PredictRequest {
    return {
      vehicle_type: vehicleType,
      brand,
      model: model === "" ? null : model,
      model_year: Number(year),
      mileage_km: Number(mileage),
      department,
      engine_cc: engineCc === "" ? null : Number(engineCc),
      asking_price_cop: askingPrice === "" ? null : Number(askingPrice),
    };
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!complete) return;

    const body = payload();
    setStatus("submitting");
    setError(null);
    // Both at once: they describe the same estimate, and two round trips in sequence
    // would double a cold start that already costs a minute.
    Promise.all([fetchPrediction(body), fetchExplanation(body)])
      .then(([predicted, explained]) => {
        setPrediction(predicted);
        setExplanation(explained);
        setStatus("ready");
      })
      .catch((cause: unknown) => {
        setError(cause instanceof ApiError ? cause.message : String(cause));
        setStatus("failed");
      });
  }

  const busy = status === "submitting";

  return (
    <div className="space-y-8">
      <section
        aria-labelledby="cold-start"
        className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-700/60 dark:bg-amber-950/30"
      >
        <h2 id="cold-start" className="font-semibold">
          {t(copy.coldStart.title)}
        </h2>
        <p className="mt-1 text-slate-700 dark:text-slate-300">{t(copy.coldStart.body)}</p>
      </section>

      <form onSubmit={submit} className="space-y-6">
        <fieldset disabled={status === "loading-catalog" || busy} className="space-y-6">
          <div>
            <span className={LABEL}>{t(copy.form.vehicleType)}</span>
            <div className="inline-flex rounded-md border border-slate-300 p-0.5 dark:border-slate-700">
              {(["car", "motorcycle"] as const).map((candidate) => (
                <button
                  key={candidate}
                  type="button"
                  onClick={() => chooseVehicleType(candidate)}
                  aria-pressed={vehicleType === candidate}
                  className={`rounded px-4 py-1.5 text-sm font-medium transition ${
                    vehicleType === candidate
                      ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                      : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                  }`}
                >
                  {t(candidate === "car" ? copy.form.car : copy.form.motorcycle)}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className={LABEL} htmlFor="brand">
                {t(copy.form.brand)} *
              </label>
              <select
                id="brand"
                required
                className={FIELD}
                value={brand}
                onChange={(event) => {
                  setBrand(event.target.value);
                  setModel("");
                }}
              >
                <option value="">—</option>
                {brands.map((entry) => (
                  <option key={entry.name} value={entry.name}>
                    {entry.name} ({integer(entry.listings, lang)})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className={LABEL} htmlFor="model">
                {t(copy.form.model)}
              </label>
              <select
                id="model"
                className={FIELD}
                value={model}
                onChange={(event) => setModel(event.target.value)}
                disabled={brand === ""}
              >
                <option value="">{t(copy.form.modelAny)}</option>
                {shownModels.map((entry) => (
                  <option key={entry.name} value={entry.name}>
                    {entry.name} ({integer(entry.listings, lang)})
                  </option>
                ))}
              </select>
              {brand !== "" && shownModels.length < models.length && (
                <button
                  type="button"
                  className={`${HINT} underline`}
                  onClick={() => setShowRareModels(true)}
                >
                  +{models.length - shownModels.length} · {t(copy.form.modelShowAll)}
                </button>
              )}
            </div>

            <div>
              <label className={LABEL} htmlFor="year">
                {t(copy.form.year)} *
              </label>
              <select
                id="year"
                required
                className={FIELD}
                value={year}
                onChange={(event) => setYear(event.target.value)}
              >
                <option value="">—</option>
                {years.map((candidate) => (
                  <option key={candidate} value={candidate}>
                    {candidate}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className={LABEL} htmlFor="mileage">
                {t(copy.form.mileage)} (km) *
              </label>
              <input
                id="mileage"
                required
                type="number"
                inputMode="numeric"
                min={0}
                max={2_000_000}
                // step="any" on every numeric field here, deliberately. A step of 1000
                // makes 60.500 km fail the browser's own constraint validation, which
                // blocks submit before onSubmit ever runs — a refusal the user cannot
                // explain. The ranges are still enforced, by min/max here and by the
                // API's schema at the edge.
                step="any"
                className={FIELD}
                value={mileage}
                onChange={(event) => setMileage(event.target.value)}
              />
            </div>

            <div>
              <label className={LABEL} htmlFor="department">
                {t(copy.form.department)} *
              </label>
              <select
                id="department"
                required
                className={FIELD}
                value={department}
                onChange={(event) => setDepartment(event.target.value)}
              >
                <option value="">—</option>
                {(catalog?.departments ?? []).map((entry) => (
                  <option key={entry.name} value={entry.name}>
                    {entry.name} ({integer(entry.listings, lang)})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className={LABEL} htmlFor="engine">
                {t(copy.form.engine)}
              </label>
              <input
                id="engine"
                type="number"
                inputMode="numeric"
                min={catalog?.engine_cc?.min ?? 1}
                max={catalog?.engine_cc?.max ?? 10_000}
                step="any"
                placeholder={
                  catalog?.engine_cc
                    ? `${integer(catalog.engine_cc.min, lang)}–${integer(catalog.engine_cc.max, lang)}`
                    : ""
                }
                className={FIELD}
                value={engineCc}
                onChange={(event) => setEngineCc(event.target.value)}
              />
              <p className={HINT}>{t(copy.form.engineOptional)}</p>
            </div>

            <div className="sm:col-span-2">
              <label className={LABEL} htmlFor="asking">
                {t(copy.form.askingPrice)}
              </label>
              <input
                id="asking"
                type="number"
                inputMode="numeric"
                min={1}
                step="any"
                className={FIELD}
                value={askingPrice}
                onChange={(event) => setAskingPrice(event.target.value)}
              />
              <p className={HINT}>{t(copy.form.askingPriceHint)}</p>
            </div>
          </div>
        </fieldset>

        <div className="flex flex-wrap items-center gap-4">
          <button
            type="submit"
            disabled={!complete || busy || status === "loading-catalog"}
            className="rounded-md bg-emerald-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? t(copy.form.submitting) : t(copy.form.submit)}
          </button>

          {status === "loading-catalog" && (
            <span className="text-sm text-slate-600 dark:text-slate-400" role="status">
              {t(copy.form.loadingCatalog)}
            </span>
          )}
          {catalog && status !== "loading-catalog" && (
            <span className="text-sm text-slate-500 dark:text-slate-400">
              {integer(catalog.trained_on_rows, lang)} {t(copy.form.listings)} · {catalog.model_version}
            </span>
          )}
        </div>
      </form>

      {status === "failed" && error !== null && (
        <div
          role="alert"
          className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm dark:border-red-800 dark:bg-red-950/30"
        >
          <p className="font-semibold">{t(copy.result.error)}</p>
          {/* The two causes worth naming. A 404 on /catalog means the deployed image
              predates this site, which is exactly what a first deploy looks like for a
              few minutes; anything else on the first load is usually the cold start. */}
          <p className="mt-1 text-slate-700 dark:text-slate-300">
            {error.includes("404") ? t(copy.result.errorOutdated) : t(copy.result.errorOffline)}
          </p>
          <p className="mt-1 break-words text-xs text-slate-500 dark:text-slate-400">{error}</p>
          <button
            type="button"
            onClick={() => {
              setError(null);
              if (catalogs.length === 0) {
                // The lists never arrived, so retry means fetching them again.
                setStatus("loading-catalog");
                setReloads((count) => count + 1);
              } else {
                setStatus("ready");
              }
            }}
            className="mt-3 rounded-md border border-red-400 px-3 py-1.5 font-medium"
          >
            {t(copy.result.retry)}
          </button>
        </div>
      )}

      {prediction && explanation && (
        <PriceResult
          prediction={prediction}
          explanation={explanation}
          askingPrice={askingPrice === "" ? null : Number(askingPrice)}
        />
      )}
    </div>
  );
}
