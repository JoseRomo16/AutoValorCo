# Data dictionary / Diccionario de datos

Status: bronze, detail, silver and gold documented. Fasecolda benchmark tables follow.

Contracts live in `src/autovalor/quality/schemas.py` (Pandera) and are checked by
`make transform`, which validates bronze, runs dbt, and then validates silver and gold.
The detail layer is validated with `--stage detail`, which the enrichment command runs
for itself.

## Layers / Capas

| Layer  | Location       | Content                                                  |
| ------ | -------------- | -------------------------------------------------------- |
| bronze | `data/bronze/` | Raw captures, immutable, one file per scraping run       |
| detail | `data/detail/` | Listing-page attribute tables, one row per listing       |
| silver | `data/silver/` | Cleaned, typed and deduplicated listings                 |
| gold   | `data/gold/`   | Analysis-ready tables for models, metrics and the API    |

## Bronze

Written by `src/autovalor/ingest`, partitioned as
`data/bronze/source=<site>/vehicle_type=<car|motorcycle>/capture_date=<YYYY-MM-DD>/listings_<UTC timestamp>.parquet`.
Every advertised value is kept as the **string it was published as**; parsing, unit
normalisation and deduplication belong to silver.

| Column                  | Type      | Notes                                                        |
| ----------------------- | --------- | ------------------------------------------------------------ |
| `listing_id`            | string    | Publisher id, e.g. `MCO-1686772601`. Natural key              |
| `source`                | string    | Site the listing came from (`tucarro`)                        |
| `source_url`            | string    | Canonical listing URL, tracking fragment stripped             |
| `captured_at`           | timestamp | Capture instant, timezone-aware UTC                           |
| `vehicle_type`          | string    | `car` or `motorcycle`; each has its own model                 |
| `title`                 | string    | Advertised title                                              |
| `price_raw`             | string    | Price as shown, e.g. `78.990.000`                             |
| `currency`              | string    | Currency symbol as shown, e.g. `$`                            |
| `model_year_raw`        | string    | Model year as shown, e.g. `2019`                              |
| `mileage_raw`           | string    | Mileage as shown, e.g. `86.000 Km`                            |
| `location_raw`          | string    | City / department as shown, e.g. `Medellín - Antioquia`       |
| `attributes_json`       | string    | JSON of any other label/value pair found on the card          |
| `bronze_schema_version` | int       | Bumped when these columns change                              |

Keys currently seen inside `attributes_json`:

| Key                | Notes                                                                   |
| ------------------ | ----------------------------------------------------------------------- |
| `price_aria_label` | Unpunctuated amount, e.g. `78990000 pesos colombianos`                   |
| `official_store`   | `true` / `false`; whether the seller is an official store                |
| `attribute_<n>`    | Any extra card attribute, e.g. `Mecánica`                                |

No personal data of sellers is ever stored (names, phone numbers, e-mail addresses),
per Ley 1581 de 2012. The seller name **is** present in the page markup and is
deliberately not read; only the official-store flag is kept, since that is a market
signal rather than information about a person.

### Known bias

The first search page is geolocated by IP, so a capture run from a single machine
over-represents that region. Later pages (`_Desde_N`) are national. Captures should
sweep explicit location slugs (`--location bogota-dc --location medellin ...`) so the
sample is not tied to where the scraper happens to run.

## Detail

Written by `src/autovalor/ingest/detail.py`, partitioned as
`data/detail/source=<site>/vehicle_type=<car|motorcycle>/details_<UTC timestamp>.parquet`.

A **sibling root of bronze, not a directory inside it.** dbt reads bronze as a single
`read_parquet` union over `bronze/**/*.parquet`; a second schema under that glob would be
unioned into the capture source and fill silver with null columns.

One row per `listing_id`, not per capture: the attributes describe the vehicle, which does
not change while the advert is up, so a listing is enriched once and never re-fetched.
Values are kept as published; parsing happens in `stg_listing_details`.

| Column                  | Type      | Notes                                                 |
| ----------------------- | --------- | ----------------------------------------------------- |
| `listing_id`            | string    | Publisher id. Unique in this layer                     |
| `source`                | string    | Site the listing came from (`tucarro`)                 |
| `source_url`            | string    | Page the attributes were read from                     |
| `fetched_at`            | timestamp | Fetch instant, timezone-aware UTC                      |
| `vehicle_type`          | string    | `car` or `motorcycle`                                  |
| `attributes_json`       | string    | JSON of the allow-listed label/value pairs             |
| `detail_schema_version` | int       | Bumped when these columns change                       |

Keys inside `attributes_json`, mapped from the Spanish labels in
`DETAIL_LABELS`. Coverage is from a 12-page survey plus the first production run:

| Key             | Spanish label                | Coverage  | Notes                                     |
| --------------- | ---------------------------- | --------- | ----------------------------------------- |
| `body_type`     | Tipo de moto                 | ~100 %    | Naked, Scooter, Enduro, Calle, Doble propósito. **The reason to run this** |
| `brand`         | Marca                        | ~100 %    | As the seller filled the form in           |
| `model`         | Modelo                       | ~100 %    | Model name; some adverts put a year here   |
| `model_year`    | Año                          | ~100 %    |                                            |
| `engine_type`   | Motor                        | ~100 %    | Nearly always `4 tiempos`; little variance |
| `mileage`       | Kilómetros                   | ~100 %    |                                            |
| `engine_cc`     | Cilindrada                   | ~100 %    | Fills the 19 % the title leaves missing    |
| `color`         | Color                        | ~100 %    |                                            |
| `brakes`        | Frenos                       | ~100 %    | Nearly always `Disco`; little variance     |
| `transmission`  | Transmisión                  | rare      |                                            |
| `gear_count`    | Numero de velocidades        | ~25 %     | Closest thing to a transmission type       |
| `single_owner`  | Único dueño                  | ~17 %     | One of the few condition signals           |
| `power`         | Potencia                     | ~25 %     | Unit inconsistent (`24 W`, `11 hp`)        |
| `abs`           | Frenos ABS                   | rare      |                                            |
| `alarm`, `gps`  | Alarma, GPS                  | rare      | Equipment                                  |
| `charger_type`  | Tipo de cargador             | rare      | Identifies electric motorcycles            |
| `vehicle_class` | Clasificación del vehículo   | rare      |                                            |
| `negotiable`    | Con precio negociable        | rare      | About the advert, not the vehicle          |

**`version`, `fuel`, `body_style` and `doors` are on the allow-list but have never
appeared on a motorcycle page.** They are the car schema. The motorcycle equivalent of a
body style is `body_type`; there is no version field, and fuel is not stated because
`engine_type` carries the stroke count instead. They stay listed so that the day one
appears it is captured rather than dropped.

Only labels on the allow-list can reach this layer, and the Pandera contract is
`strict=True`, so the column set is closed. That is two independent barriers against a
seller's name, phone number or e-mail ever landing here (Ley 1581 de 2012); the page
carries all three, and the raw HTML is never stored either. A test asserts it.

Labels seen but not on the allow-list are counted and reported at the end of a run, which
is how schema drift surfaces — that report is what added `Transmisión`, `GPS`, `Alarma`
and `Tipo de cargador` after the first trial run.

## Silver — `main_silver.silver_listings`

Built by `dbt/models/silver/`. One row per **listing and asking price**: a listing
re-captured unchanged collapses into one row, while a price change becomes a new row,
which is what the monthly price index needs.

Implausible rows are **kept and flagged**, not dropped, so data quality stays
measurable over time.

| Column              | Type      | Notes                                                    |
| ------------------- | --------- | -------------------------------------------------------- |
| `listing_id`        | varchar   | Publisher id                                             |
| `source`            | varchar   | Site the listing came from                               |
| `source_url`        | varchar   | Canonical listing URL                                    |
| `vehicle_type`      | varchar   | `car` or `motorcycle`                                    |
| `title`             | varchar   | Trimmed title, `NULL` when empty                         |
| `price_cop`         | bigint    | Parsed from the card's aria-label, price text as fallback |
| `model_year`        | bigint    | Parsed model year                                        |
| `mileage_km`        | bigint    | `86.000 Km` → `86000`                                    |
| `city`              | varchar   | First half of `location_raw`                             |
| `department`        | varchar   | Second half of `location_raw`                            |
| `is_official_store` | boolean   | Seller is an official store                              |
| `first_seen_at`     | timestamp | Earliest capture at this price                           |
| `last_seen_at`      | timestamp | Latest capture at this price                             |
| `capture_count`     | bigint    | Captures seen at this price                              |
| `is_valid`          | boolean   | True exactly when `invalid_reason` is `NULL`              |
| `invalid_reason`    | varchar   | See below                                                |

`invalid_reason` values: `price_missing`, `price_too_low`, `price_too_high`,
`currency_not_cop`, `model_year_missing`, `model_year_too_old`, `model_year_in_future`,
`mileage_missing`, `mileage_too_high`.

Thresholds (defined once in `schemas.py`, mirrored as dbt vars): price between
1.000.000 and 2.000.000.000 COP, model year from 1950 to next calendar year, mileage up
to 1.000.000 km.

## Gold — `main_gold.gold_listings`

Built by `dbt/models/gold/`. Plausible rows only, **one row per listing** (its latest
asking price), with everything the models consume.

| Column              | Type      | Notes                                                  |
| ------------------- | --------- | ------------------------------------------------------ |
| `listing_id`        | varchar   | Unique in this table                                   |
| `source_url`        | varchar   |                                                        |
| `vehicle_type`      | varchar   | Cars and motorcycles are modeled separately            |
| `title`             | varchar   |                                                        |
| `price_cop`         | bigint    | Asking price                                           |
| `log_price`         | double    | **Modeling target**                                    |
| `model_year`        | bigint    |                                                        |
| `vehicle_age_years` | bigint    | `year(last_seen_at) - model_year`, floored at 0         |
| `mileage_km`        | bigint    |                                                        |
| `km_per_year`       | double    | Divides by at least one year, so new vehicles read as  |
|                     |           | "kilometres so far" instead of exploding               |
| `city`              | varchar   |                                                        |
| `department`        | varchar   |                                                        |
| `is_official_store` | boolean   |                                                        |
| `first_seen_at`     | timestamp |                                                        |
| `last_seen_at`      | timestamp |                                                        |
| `has_detail`        | boolean   | Whether the listing page has been read                 |
| `body_type`         | varchar   | From the detail page; null when not enriched           |
| `transmission`      | varchar   | idem                                                   |
| `brakes`            | varchar   | idem                                                   |
| `color`             | varchar   | idem                                                   |
| `gear_count`        | bigint    | idem                                                   |
| `is_single_owner`   | boolean   | idem; null means "not stated", not "no"                |

`engine_cc` takes the detail page's value when there is one and falls back to the token
mined from the title, so a listing with no detail row keeps exactly the value it had
before the enrichment existed.

The detail columns are **null for every listing that has not been enriched**, which both
tree libraries route down their own missing branch — "not enriched" stays a state instead
of becoming an imputed average. They are off by default in the model specification; see
`tree_spec(detail_features=...)` and `--only-enriched`.

`valor_fasecolda` is a benchmark only and is never joined into gold or used as a model
feature (information leakage).
