# Data dictionary / Diccionario de datos

Status: bronze, silver and gold documented (F1). Fasecolda benchmark tables follow.

Contracts live in `src/autovalor/quality/schemas.py` (Pandera) and are checked by
`make transform`, which validates bronze, runs dbt, and then validates silver and gold.

## Layers / Capas

| Layer  | Location       | Content                                                  |
| ------ | -------------- | -------------------------------------------------------- |
| bronze | `data/bronze/` | Raw captures, immutable, one file per scraping run       |
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

`valor_fasecolda` is a benchmark only and is never joined into gold or used as a model
feature (information leakage).
