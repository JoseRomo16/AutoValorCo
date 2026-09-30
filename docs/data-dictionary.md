# Data dictionary / Diccionario de datos

Status: bronze documented (F1). Silver, gold and the feature table follow as dbt lands.

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

## Features (planned)

| Feature       | Source                          | Notes                                    |
| ------------- | ------------------------------- | ---------------------------------------- |
| `vehicle_age` | `features/age.vehicle_age`      | `captured_at.year - model_year`, min 0   |

`valor_fasecolda` is a benchmark only and is never used as a model feature
(information leakage).
