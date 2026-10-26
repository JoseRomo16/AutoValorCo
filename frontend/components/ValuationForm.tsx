"use client";

/**
 * The valuation form.
 *
 * Four decisions worth knowing before changing this.
 *
 * **The lists come from `/catalog`, not from constants.** The served trees carry frozen
 * categorical levels, so a make they never saw is routed down their missing branch and
 * still yields a confident-looking number. A list built from the model's own training rows
 * cannot ask that question.
 *
 * **`/predict` and `/explain` are requested together.** They are two calls against the same
 * model and the same row, and they agree on the estimate exactly, so showing one without
 * the other would be showing half an answer.
 *
 * **The cold start is a product fact, not an error.** Requesting the catalogue on mount
 * wakes the sleeping instance while the form is being filled in. Until it answers, the only
 * thing on screen is a line of state next to the button; the long explanation appears only
 * once the wait has actually become one.
 *
 * **Validation happens when a field is left, never only on submit.** The browser's own
 * constraint UI blocks submission with a tooltip that cannot be translated or styled, so
 * every field here is a text input and the rules live in `validate` below, where they can
 * say what is wrong in the reader's language.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { useLang } from "./LanguageProvider";
import { PriceResult } from "./PriceResult";
import { WRAP } from "./SiteChrome";
import { Combobox } from "./ui/Combobox";
import type { ComboOption } from "./ui/Combobox";
import { NumberField } from "./ui/NumberField";
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
import { integer } from "@/lib/format";
import { copy, fill } from "@/lib/i18n";
import type { Localized } from "@/lib/i18n";

/**
 * Below this many training listings a department is offered in its own group at the end of
 * the list, with a notice when it is chosen.
 *
 * Fifty rather than a rounder number because that is where the catalogue actually splits:
 * three of ten car departments sit under it (Cauca 1, Meta 2, Quindío 12) and the next one
 * up has an order of magnitude more. Hiding them would leave whoever lives there with no
 * service at all, which costs more than telling them the estimate is thinner.
 */
const LOW_DATA_LISTINGS = 50;

/**
 * The lake's unresolved-make bucket, which must never be offered as a make.
 *
 * Catalogue cleaning pushed the remaining junk into this one level rather than removing it,
 * so excluding it here drops every unusable model token with it. It is a safety net: the
 * real fix lives in the data layer.
 */
const UNKNOWN_LEVEL = "Desconocida";

const MAX_MILEAGE_KM = 2_000_000;

type Status = "loading-catalog" | "ready" | "submitting" | "failed";
type FieldName = "brand" | "year" | "mileage" | "department" | "engine" | "asking";

/**
 * Turn a failure into something a person can act on.
 *
 * Three causes are worth telling apart and the browser reports two of them identically: a
 * sleeping instance, a client with no network and a rejected cross-origin request all
 * arrive as the same opaque `TypeError`. The tie-break is whether the lists ever landed. On
 * a first load the service waking up is by far the likeliest, and the advice is the same
 * either way; later, with the lists in hand, a dropped request is the connection.
 */
function classify(error: string | null, firstLoad: boolean): { title: Localized; body: Localized } {
  const text = error ?? "";
  if (/not enough|no listings|insufficient/i.test(text)) {
    return { title: copy.result.errors.noDataTitle, body: copy.result.errors.noDataBody };
  }
  if (/^HTTP \d|\b40\d\b|\b50\d\b/.test(text)) {
    return { title: copy.result.errors.unexpectedTitle, body: copy.result.errors.unexpectedBody };
  }
  return firstLoad
    ? { title: copy.result.errors.wakingTitle, body: copy.result.errors.wakingBody }
    : { title: copy.result.errors.offlineTitle, body: copy.result.errors.offlineBody };
}

function Fieldset({
  legend,
  children,
  disabled,
}: {
  legend: string;
  children: React.ReactNode;
  disabled: boolean;
}) {
  return (
    <fieldset disabled={disabled} className="mb-7 min-w-0 border-0 p-0 last:mb-0">
      <legend className="mb-3.5 p-0 font-mono text-xs uppercase tracking-[0.1em] text-accent-text">
        {legend}
      </legend>
      <div className="grid gap-[18px] sm:grid-cols-2">{children}</div>
    </fieldset>
  );
}

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
  const [touched, setTouched] = useState<Set<FieldName>>(new Set());

  const [prediction, setPrediction] = useState<PredictResponse | null>(null);
  const [explanation, setExplanation] = useState<ExplainResponse | null>(null);
  const [predictedFor, setPredictedFor] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);
  const [slowStart, setSlowStart] = useState(false);
  const resultRef = useRef<HTMLDivElement>(null);

  // Five seconds is the line between "loading" and "the instance was asleep". Under it the
  // indicator next to the button is enough; over it the wait needs explaining.
  useEffect(() => {
    if (status !== "loading-catalog") return;
    const timer = window.setTimeout(() => setSlowStart(true), 5_000);
    return () => window.clearTimeout(timer);
  }, [status]);

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
   * Switching vertical invalidates the categorical levels but not the numbers: motorcycle
   * makes are not car makes, while a year and an odometer reading mean the same thing on
   * both. Keeping them is what makes "actually, price the bike instead" one click.
   *
   * It happens in the handler rather than in an effect watching `vehicleType`, because an
   * effect would render the stale form once before clearing it.
   */
  function chooseVehicleType(next: VehicleType) {
    if (next === vehicleType) return;
    setVehicleType(next);
    setBrand("");
    setModel("");
    setDepartment("");
    setEngineCc("");
    setPrediction(null);
    setExplanation(null);
    setTouched(new Set());
  }

  const brandOptions = useMemo<ComboOption[]>(() => {
    const listed = catalog?.brands ?? [];
    return listed
      .filter((entry) => entry.name !== UNKNOWN_LEVEL)
      .map((entry) => ({
        value: entry.name,
        label: entry.display_name ?? entry.name,
        count: entry.listings,
      }));
  }, [catalog]);

  const modelOptions = useMemo<ComboOption[]>(() => {
    const selected = catalog?.brands.find((entry) => entry.name === brand);
    return (selected?.models ?? []).map((entry) => ({
      value: entry.name,
      label: entry.display_name ?? entry.name,
      count: entry.listings,
    }));
  }, [catalog, brand]);

  /**
   * Departments, with the thin ones grouped at the end rather than hidden or dropped.
   *
   * Alphabetical inside each group: unlike makes, nobody scans departments by popularity —
   * they look for the one they live in.
   */
  const departmentOptions = useMemo<ComboOption[]>(() => {
    const entries = catalog?.departments ?? [];
    const byName = (a: { name: string }, b: { name: string }) => a.name.localeCompare(b.name, lang);
    const toOption = (entry: (typeof entries)[number], group?: string): ComboOption => ({
      value: entry.name,
      label: entry.display_name ?? entry.name,
      count: entry.listings,
      group,
    });
    const common = entries.filter((entry) => entry.listings >= LOW_DATA_LISTINGS).sort(byName);
    const thin = entries.filter((entry) => entry.listings < LOW_DATA_LISTINGS).sort(byName);
    return [
      ...common.map((entry) => toOption(entry)),
      ...thin.map((entry) => toOption(entry, t(copy.form.departmentLowData))),
    ];
  }, [catalog, lang, t]);

  const chosenDepartment = (catalog?.departments ?? []).find((entry) => entry.name === department);
  const departmentIsThin =
    chosenDepartment !== undefined && chosenDepartment.listings < LOW_DATA_LISTINGS;

  const yearRange = catalog?.model_year;
  const engineRange = catalog?.engine_cc ?? null;

  /** Every rule, in one place, so a field and its message cannot disagree. */
  const problems = useMemo(() => {
    const found: Partial<Record<FieldName, string>> = {};
    if (brand === "") found.brand = t(copy.form.errors.brand);
    if (department === "") found.department = t(copy.form.errors.department);

    if (yearRange) {
      const min = Math.round(yearRange.min);
      const max = Math.round(yearRange.max);
      const value = Number(year);
      if (year === "" || value < min || value > max) {
        found.year = fill(copy.form.errors.year, lang, { min, max });
      }
    }

    if (mileage === "") {
      found.mileage = t(copy.form.errors.mileageMissing);
    } else if (Number(mileage) > MAX_MILEAGE_KM) {
      found.mileage = fill(copy.form.errors.mileageRange, lang, {
        max: integer(MAX_MILEAGE_KM, lang),
      });
    }

    if (engineCc !== "" && engineRange) {
      const value = Number(engineCc);
      const min = Math.round(engineRange.min);
      const max = Math.round(engineRange.max);
      if (value < min || value > max) {
        found.engine = fill(copy.form.errors.engineRange, lang, { min, max });
      }
    }

    if (askingPrice !== "" && Number(askingPrice) < 1) {
      found.asking = t(copy.form.errors.price);
    }
    return found;
  }, [brand, department, year, mileage, engineCc, askingPrice, yearRange, engineRange, lang, t]);

  /** A rule only becomes a message once the person has left the field. */
  const shown = (field: FieldName) => (touched.has(field) ? problems[field] : undefined);
  const touch = (field: FieldName) => setTouched((current) => new Set(current).add(field));

  const complete = Object.keys(problems).length === 0;
  const busy = status === "submitting";
  const loading = status === "loading-catalog";

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!complete) {
      // Surface every rule at once rather than refusing silently.
      setTouched(new Set(["brand", "year", "mileage", "department", "engine", "asking"]));
      return;
    }

    const body: PredictRequest = {
      vehicle_type: vehicleType,
      brand,
      model: model === "" ? null : model,
      model_year: Number(year),
      mileage_km: Number(mileage),
      department,
      engine_cc: engineCc === "" ? null : Number(engineCc),
      asking_price_cop: askingPrice === "" ? null : Number(askingPrice),
    };

    setStatus("submitting");
    setError(null);
    // Both at once: they describe the same estimate, and two round trips in sequence would
    // double a cold start that already costs a minute.
    Promise.all([fetchPrediction(body), fetchExplanation(body)])
      .then(([predicted, explained]) => {
        setPrediction(predicted);
        setExplanation(explained);
        setPredictedFor(describe());
        setStatus("ready");
      })
      .catch((cause: unknown) => {
        setError(cause instanceof ApiError ? cause.message : String(cause));
        setStatus("failed");
      });
  }

  /** The spec line above the result: what was actually priced, as a classified reads. */
  function describe(): string {
    const brandLabel = brandOptions.find((option) => option.value === brand)?.label ?? brand;
    const modelLabel = modelOptions.find((option) => option.value === model)?.label;
    const departmentLabel =
      departmentOptions.find((option) => option.value === department)?.label ?? department;
    return [
      [brandLabel, modelLabel].filter(Boolean).join(" "),
      year,
      `${integer(Number(mileage), lang)} km`,
      departmentLabel,
    ]
      .filter(Boolean)
      .join(" · ");
  }

  function reset() {
    setBrand("");
    setModel("");
    setYear("");
    setMileage("");
    setDepartment("");
    setEngineCc("");
    setAskingPrice("");
    setPrediction(null);
    setExplanation(null);
    setPredictedFor(null);
    setTouched(new Set());
  }

  const failure = classify(error, catalogs.length === 0);
  const listingCount = (count: number) =>
    fill(copy.form.listingsCount, lang, { count: integer(count, lang) });
  const noMatch = (query: string) => fill(copy.form.searchNoMatch, lang, { query });

  return (
    <div className={`${WRAP} grid items-start gap-8 pb-20 min-[960px]:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]`}>
      <form
        onSubmit={submit}
        noValidate
        className="rounded-lg border border-line bg-surface p-5 sm:p-7"
      >
        {/* The first decision, and the largest control on the page: everything below it
            depends on which vertical answers. */}
        <div
          role="group"
          aria-label={t(copy.form.vehicleType)}
          className="mb-7 grid grid-cols-2 rounded-lg border border-line p-[3px]"
        >
          {(["car", "motorcycle"] as const).map((candidate) => (
            <button
              key={candidate}
              type="button"
              onClick={() => chooseVehicleType(candidate)}
              aria-pressed={vehicleType === candidate}
              className={`min-h-13 rounded-md font-display text-lg font-bold transition-colors duration-200 [font-stretch:112%] ${
                vehicleType === candidate ? "bg-ink text-ground" : "text-muted hover:text-ink"
              }`}
            >
              {t(candidate === "car" ? copy.form.car : copy.form.motorcycle)}
            </button>
          ))}
        </div>

        <Fieldset legend={t(copy.form.groupVehicle)} disabled={loading || busy}>
          <Combobox
            id="brand"
            required
            label={t(copy.form.brand)}
            placeholder={t(copy.form.brandPlaceholder)}
            options={brandOptions}
            value={brand}
            onChange={(next) => {
              setBrand(next);
              setModel("");
              touch("brand");
            }}
            emptyText={noMatch}
            countLabel={listingCount}
            error={shown("brand")}
          />

          <Combobox
            id="model"
            label={t(copy.form.model)}
            placeholder={t(copy.form.modelPlaceholder)}
            optionalLabel={t(copy.form.optional)}
            disabled={brand === ""}
            disabledHint={t(copy.form.modelAfterBrand)}
            options={modelOptions}
            value={model}
            onChange={setModel}
            emptyText={noMatch}
            countLabel={listingCount}
          />

          <NumberField
            id="year"
            lang={lang}
            label={t(copy.form.year)}
            value={year}
            onChange={setYear}
            onBlur={() => touch("year")}
            placeholder={
              yearRange
                ? `${Math.round(yearRange.min)}–${Math.round(yearRange.max)}`
                : undefined
            }
            error={shown("year")}
          />

          <NumberField
            id="engine"
            lang={lang}
            label={t(copy.form.engine)}
            optionalLabel={t(copy.form.optional)}
            unit={t(copy.form.engineUnit)}
            value={engineCc}
            onChange={setEngineCc}
            onBlur={() => touch("engine")}
            placeholder={
              engineRange
                ? `${integer(engineRange.min, lang)}–${integer(engineRange.max, lang)}`
                : undefined
            }
            hint={t(copy.form.engineHint)}
            error={shown("engine")}
          />
        </Fieldset>

        <Fieldset legend={t(copy.form.groupListing)} disabled={loading || busy}>
          <NumberField
            id="mileage"
            lang={lang}
            label={t(copy.form.mileage)}
            unit={t(copy.form.mileageUnit)}
            value={mileage}
            onChange={setMileage}
            onBlur={() => touch("mileage")}
            error={shown("mileage")}
          />

          <Combobox
            id="department"
            required
            label={t(copy.form.department)}
            options={departmentOptions}
            value={department}
            onChange={(next) => {
              setDepartment(next);
              touch("department");
            }}
            emptyText={noMatch}
            countLabel={listingCount}
            // The thin-department notice replaces the generic hint, so the warning lands
            // where someone is looking the moment they pick one.
            hint={
              departmentIsThin && chosenDepartment
                ? fill(copy.form.departmentLowDataHint, lang, {
                    count: integer(chosenDepartment.listings, lang),
                  })
                : undefined
            }
            error={shown("department")}
          />

          <div className="sm:col-span-2">
            <NumberField
              id="asking"
              lang={lang}
              label={t(copy.form.askingPrice)}
              optionalLabel={t(copy.form.optional)}
              prefix="$"
              value={askingPrice}
              onChange={setAskingPrice}
              onBlur={() => touch("asking")}
              hint={t(copy.form.askingPriceHint)}
              error={shown("asking")}
            />
          </div>
        </Fieldset>

        <div className="flex flex-wrap items-center gap-x-5 gap-y-3 border-t border-line pt-6">
          <button
            type="submit"
            disabled={busy || loading}
            className="inline-flex min-h-12 items-center justify-center rounded-md bg-accent px-5.5 font-semibold text-accent-ink transition-[filter,transform] duration-200 hover:brightness-105 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? t(copy.form.submitting) : t(copy.form.submit)}
          </button>

          {/* State next to the action, which is where someone looks when nothing happens.
              Silent when the request failed: the panel beside it is already saying so, and
              a green "model ready" under a visible error is the indicator lying. */}
          {status !== "failed" && (
            <span
              role="status"
              className="inline-flex items-center gap-2 font-mono text-xs text-muted"
            >
              <i aria-hidden className={`size-2 rounded-full ${loading ? "bg-faint" : "bg-good"}`} />
              {loading ? t(copy.status.connecting) : t(copy.status.ready)}
            </span>
          )}

          {prediction && (
            <button
              type="button"
              onClick={reset}
              className="ml-auto text-sm text-accent-text underline underline-offset-4 hover:opacity-80"
            >
              {t(copy.form.reset)}
            </button>
          )}
        </div>

        {loading && slowStart && (
          <div className="mt-5 border-l-2 border-accent pl-4 text-sm">
            <p className="font-semibold">{t(copy.status.wakingTitle)}</p>
            <p className="mt-1 text-muted">{t(copy.status.wakingBody)}</p>
          </div>
        )}
      </form>

      <div ref={resultRef} className="min-[960px]:sticky min-[960px]:top-21">
        {status === "failed" && error !== null ? (
          <div role="alert" className="rounded-lg border border-bad bg-bad-bg p-5 text-sm">
            <p className="font-semibold">{t(failure.title)}</p>
            <p className="mt-1 text-muted">{t(failure.body)}</p>
            <details className="mt-3 text-xs text-muted">
              <summary className="cursor-pointer">{t(copy.result.errors.detail)}</summary>
              <p className="mt-1 break-words font-mono">{error}</p>
            </details>
            <button
              type="button"
              onClick={() => {
                setError(null);
                if (catalogs.length === 0) {
                  // The lists never arrived, so retry means fetching them again.
                  setStatus("loading-catalog");
                  setSlowStart(false);
                  setReloads((count) => count + 1);
                } else {
                  setStatus("ready");
                }
              }}
              className="mt-4 inline-flex min-h-10 items-center rounded-md border border-line-strong px-4 text-sm font-medium"
            >
              {t(copy.result.errors.retry)}
            </button>
          </div>
        ) : (
          <PriceResult
            prediction={prediction}
            explanation={explanation}
            askingPrice={askingPrice === "" ? null : Number(askingPrice)}
            spec={predictedFor}
            busy={busy}
          />
        )}
      </div>
    </div>
  );
}
