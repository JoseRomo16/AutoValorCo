# Data dictionary / Diccionario de datos

Status: skeleton created in F0. Filled in during F1 once the bronze schema is stable.

## Layers / Capas

| Layer  | Location       | Content                                                  |
| ------ | -------------- | -------------------------------------------------------- |
| bronze | `data/bronze/` | Raw captures, immutable, one file per scraping run       |
| silver | `data/silver/` | Cleaned, typed and deduplicated listings                 |
| gold   | `data/gold/`   | Analysis-ready tables for models, metrics and the API    |

## Bronze (planned)

| Column        | Type      | Notes                                           |
| ------------- | --------- | ----------------------------------------------- |
| `source_url`  | string    | Listing URL, natural key                        |
| `captured_at` | timestamp | Capture instant, UTC                            |
| `raw_payload` | string    | Extracted fields, before cleaning               |

No personal data of sellers is ever stored (names, phone numbers, e-mail addresses),
per Ley 1581 de 2012.

## Features (planned)

| Feature       | Source                          | Notes                                    |
| ------------- | ------------------------------- | ---------------------------------------- |
| `vehicle_age` | `features/age.vehicle_age`      | `captured_at.year - model_year`, min 0   |

`valor_fasecolda` is a benchmark only and is never used as a model feature
(information leakage).
