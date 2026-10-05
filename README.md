# AutoValor CO

**Valoración de carros y motos usados en Colombia** ·
_Used car and motorcycle valuation for the Colombian market_

[![CI](https://github.com/JoseRomo16/AutoValorCo/actions/workflows/ci.yml/badge.svg)](https://github.com/JoseRomo16/AutoValorCo/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Status](https://img.shields.io/badge/fase-F2%20modelaci%C3%B3n-blue)

---

## Español

### ¿Qué hace?

AutoValor CO estima el precio de mercado de un carro o una moto usada en Colombia y
entrega, además del valor puntual, un intervalo de predicción **P10–P90**. Con eso:

- **Clasifica anuncios** como _ganga_, _justo_ o _caro_ según dónde cae el precio pedido
  dentro del intervalo.
- **Explica cada predicción** con SHAP: cuánto aporta el año, el kilometraje, la versión,
  la ciudad o la transmisión al precio estimado.
- **Publica curvas de depreciación** por marca y segmento, y un **índice mensual** de
  precios de usados.
- **Compara** su estimación contra la guía Fasecolda, que se usa solo como referencia
  externa y nunca como variable del modelo.

### Arquitectura

```
TuCarro / Fasecolda
        │  scraping educado (robots.txt, pausas aleatorias, UA identificable)
        ▼
┌──────────────┐   dbt + Pandera   ┌──────────────┐   dbt    ┌────────────┐
│    BRONZE    │ ────────────────► │    SILVER    │ ───────► │    GOLD    │
│ Parquet CRUDO│   validación      │ limpio, sin  │ features │ listo para │
│  inmutable   │   de esquema      │  duplicados  │          │  modelar   │
└──────────────┘                   └──────────────┘          └─────┬──────┘
                                                                   │
                      ┌────────────────────────────────────────────┘
                      ▼
        ┌─────────────────────────────┐        ┌──────────────────────────┐
        │  MODELOS (log del precio)   │  MLflow│  API FastAPI             │
        │  hedónico OLS  (línea base) │ ─────► │  /predict  /explain      │
        │  LightGBM / CatBoost        │        │  /health   /model-info   │
        │  + SHAP, intervalos P10–P90 │        └───────────┬──────────────┘
        └─────────────────────────────┘                    │
                                                           ▼
                                              App Next.js + Tailwind
```

Carros y motos se modelan por separado y el objetivo siempre es `log(precio)`.

```
src/autovalor/
  ingest/      # scrapers TuCarro (carros y motos), carga guía Fasecolda
  quality/     # esquemas Pandera
  features/    # features derivadas
  models/      # train.py, predict.py, explain.py
  api/         # FastAPI
dbt/           # modelos silver y gold
data/          # bronze/ silver/ gold/ (en .gitignore)
notebooks/     # solo exploración
frontend/      # Next.js + Tailwind (F4)
tests/
docs/          # ADRs y diccionario de datos
```

### Stack

| Capa        | Herramientas                                                                 |
| ----------- | ---------------------------------------------------------------------------- |
| Captura     | Playwright, httpx, BeautifulSoup, tenacity                                   |
| Almacén     | Parquet, DuckDB, dbt-duckdb                                                  |
| Calidad     | Pandera                                                                      |
| Modelación  | scikit-learn, statsmodels, LightGBM, CatBoost, Optuna, SHAP, MLflow          |
| Servicio    | FastAPI, Pydantic, Uvicorn                                                   |
| Frontend    | Next.js (App Router), TypeScript, Tailwind CSS                               |
| Infra       | uv, Docker, docker compose, GitHub Actions, Render                           |

### Arranque

Requisitos: Python 3.12 y [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/JoseRomo16/AutoValorCo.git
cd AutoValorCo
cp .env.example .env     # ajusta lo que necesites
make setup               # uv sync + playwright + pre-commit (+ npm en F4)
make test
```

En **Windows** no hay GNU make; usa el script equivalente:

```powershell
Copy-Item .env.example .env
.\make.ps1 setup
.\make.ps1 test
```

### Comandos

| Comando          | Qué hace                                             | Disponible |
| ---------------- | ---------------------------------------------------- | ---------- |
| `make setup`     | Instala dependencias de Python, navegador y frontend | F0         |
| `make scrape`    | Captura anuncios de TuCarro en `data/bronze`         | F1         |
| `make transform` | Corre dbt (silver y gold) + validaciones Pandera     | F1         |
| `make train`     | Entrena y registra modelos en MLflow                 | F2         |
| `make serve`     | Levanta la API en local (`:8000`)                    | F0         |
| `make test`      | pytest con cobertura (mínimo 70 %)                   | F0         |
| `make lint`      | ruff + mypy                                          | F0         |

La captura también se puede afinar desde el CLI:

```bash
# Barrido nacional, 10 páginas por vertical
uv run python -m autovalor.ingest.cli --vehicle-type all --pages 10

# Por ciudad (la primera página del sitio está geolocalizada por IP)
uv run python -m autovalor.ingest.cli --vehicle-type car \
  --location bogota-dc --location medellin --pages 20

# Ver cuántos anuncios saldrían, sin escribir en bronze
uv run python -m autovalor.ingest.cli --vehicle-type car --pages 1 --dry-run
```

En redes que inspeccionan TLS (proxy corporativo, algunos antivirus) hay que poner
`AUTOVALOR_USE_SYSTEM_CERTS=true` en el `.env` para validar contra el almacén de
certificados del sistema.

**Captura semanal.** El workflow `.github/workflows/capture.yml` corre los lunes a las
07:00 UTC (02:00 en Colombia), barre seis departamentos, transforma y valida, y sube el
resultado como artefacto del run. La retención de artefactos es de 90 días; el paso a
almacenamiento de objetos está documentado en
[ADR 0002](docs/adr/0002-weekly-capture-storage.md).

Con Docker:

```bash
docker compose up -d api                    # API en http://localhost:8000
docker compose --profile ml up -d mlflow    # UI de MLflow en http://localhost:5000
```

### Roadmap

Estado detallado, decisiones abiertas y cómo retomar: **[`docs/STATUS.md`](docs/STATUS.md)**.

| Fase   | Objetivo    | Criterio de cierre                                                                                    | Estado      |
| ------ | ----------- | ----------------------------------------------------------------------------------------------------- | ----------- |
| **F0** | Requisitos  | Repo inicial, estructura, Makefile y CI en verde                                                      | cerrada     |
| **F1** | Datos       | Piloto para medir σ del error; ≥ 6.000 carros y ≥ 2.600 motos limpios; captura semanal activa          | cerrada (7.207 / 3.765) |
| **F2** | Modelación  | Hedónico OLS como línea base; los ensambles deben superarlo. Meta **MAPE ≤ 15 %**                      | en curso    |
| **F3** | Resultados  | Métricas por segmento, SHAP, curvas de depreciación, comparación con Fasecolda                        | pendiente   |
| **F4** | Producto    | API (`/predict`, `/explain`, `/health`, `/model-info`), app Next.js, Docker y despliegue en Render     | pendiente   |

### Datos y ética

- Scraping educado: se respeta `robots.txt`, hay pausas aleatorias entre peticiones, el
  user-agent es identificable y no se usa paralelismo agresivo.
- **Nunca** se almacenan datos personales de vendedores (nombres, teléfonos, correos),
  conforme a la **Ley 1581 de 2012**.
- La capa bronze es inmutable: se escribe una vez por captura, con `captured_at` y
  `source_url`.
- Las estimaciones son informativas y no constituyen un avalúo comercial.

---

## English

### What it does

AutoValor CO estimates the market price of a used car or motorcycle in Colombia and
returns, besides the point estimate, a **P10–P90** prediction interval. On top of that it:

- **Classifies listings** as _bargain_, _fair_ or _overpriced_, depending on where the
  asking price falls inside the interval.
- **Explains every prediction** with SHAP: how much the model year, mileage, trim, city
  or transmission contribute to the estimate.
- **Publishes depreciation curves** by brand and segment, plus a **monthly used-price
  index**.
- **Benchmarks** its estimate against the Fasecolda guide, which is used as an external
  reference only and never as a model feature.

### Architecture

Medallion data lake (bronze → silver → gold) built with Parquet, DuckDB and dbt, with
Pandera validating each layer. Cars and motorcycles get separate models and the target is
always `log(price)`: a hedonic OLS regression is the baseline any gradient-boosting
ensemble must beat. Models are tracked in MLflow and served by a FastAPI app, consumed by
a Next.js + Tailwind frontend. See the Spanish diagram above.

### Getting started

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/JoseRomo16/AutoValorCo.git
cd AutoValorCo
cp .env.example .env
make setup      # on Windows: .\make.ps1 setup
make test
```

`make lint` runs ruff and mypy; `make serve` starts the API on `:8000`. Targets that
belong to a later phase (`scrape`, `transform`, `train`) print a notice until that phase
is implemented.

### Roadmap

Detailed status, open decisions and how to resume: **[`docs/STATUS.md`](docs/STATUS.md)**.

| Phase  | Goal        | Exit criteria                                                                                              | Status      |
| ------ | ----------- | ---------------------------------------------------------------------------------------------------------- | ----------- |
| **F0** | Requirements| Initial repo, structure, Makefile and green CI                                                             | closed      |
| **F1** | Data        | Pilot to measure error σ; ≥ 6,000 clean cars and ≥ 2,600 clean motorcycles; weekly capture on               | closed (7,207 / 3,765) |
| **F2** | Modeling    | Hedonic OLS baseline; ensembles must beat it. Target **MAPE ≤ 15 %**                                        | in progress |
| **F3** | Results     | Per-segment metrics, SHAP, depreciation curves, Fasecolda comparison                                        | pending     |
| **F4** | Product     | API (`/predict`, `/explain`, `/health`, `/model-info`), Next.js app, Docker, Render deployment              | pending     |

### Data and ethics

Scraping is deliberately polite (robots.txt, randomized delays, identifiable user-agent,
no aggressive parallelism). No personal seller data is ever stored — names, phone numbers
or e-mail addresses — in line with Colombian data protection law (Ley 1581 de 2012). The
bronze layer is immutable: written once per capture, with `captured_at` and `source_url`.
Estimates are informational and are not a commercial appraisal.

---

## Licencia / License

MIT. See [`LICENSE`](LICENSE).
