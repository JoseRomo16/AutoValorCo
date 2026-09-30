# AutoValor CO

Sistema de valoración de carros y motos usados en Colombia. Estima el precio de mercado con intervalo P10–P90, clasifica anuncios como ganga / justo / caro, explica cada predicción (SHAP) y publica curvas de depreciación y un índice mensual de precios de usados.

Documento de requerimientos completo: https://claude.ai/code/artifact/cbe0b762-b8c4-4344-ade1-6df9230dadf8 (fuente de verdad para alcance, RF y RNF).

## Stack

- Backend y datos: Python 3.12, uv, Playwright/httpx + BeautifulSoup, Parquet + DuckDB, dbt-duckdb, Pandera, scikit-learn, statsmodels, LightGBM, CatBoost, Optuna, SHAP, MLflow, FastAPI + Pydantic.
- Frontend: Next.js (App Router) + TypeScript + Tailwind CSS, en `frontend/`.
- Infra: Docker + docker compose, GitHub Actions (CI y captura semanal), despliegue en Render.

## Estructura

```
src/autovalor/
  ingest/      # scrapers TuCarro (carros y motos), carga guía Fasecolda
  quality/     # esquemas Pandera
  features/    # features derivadas
  models/      # train.py, predict.py, explain.py
  api/         # FastAPI
dbt/           # modelos silver y gold
data/          # bronze/ silver/ gold/ (en .gitignore)
notebooks/     # solo exploración: 01_eda, 02_modelo_hedonico, 03_comparacion_modelos
frontend/      # Next.js + Tailwind
tests/
docs/          # ADRs y diccionario de datos
```

## Comandos

- `make setup` instala dependencias (uv sync + playwright install + npm install en frontend)
- `make scrape` captura anuncios a data/bronze
- `make transform` corre dbt (silver y gold) y validaciones Pandera
- `make train` entrena y registra modelos en MLflow
- `make serve` levanta la API en local
- `make test` corre pytest; `make lint` corre ruff + mypy

## Convenciones

- Código, nombres de variables, docstrings y commits en inglés. README bilingüe (ES/EN).
- Type hints en todo el código de `src/`. Ruff y mypy sin errores.
- Cobertura de pruebas ≥ 70 % en `src/`. Toda función nueva de limpieza o features lleva test.
- Commits pequeños con Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`).
- Nada de lógica de negocio en notebooks: los notebooks importan desde `src/autovalor`.
- Configuración por variables de entorno (`.env`, nunca commiteado); `.env.example` actualizado.

## Reglas de datos

- Scraping educado: respetar robots.txt, pausas aleatorias entre requests, user-agent identificable, sin paralelismo agresivo.
- Nunca guardar datos personales de vendedores (nombres, teléfonos, correos). Ley 1581 de 2012.
- La capa bronze es inmutable: se escribe una vez por captura, con `captured_at` y `source_url`.
- `valor_fasecolda` no se usa como feature del modelo base (fuga de información); solo como benchmark.
- Precio modelado como log(precio). Carros y motos son modelos separados.

## Fases y criterios de cierre

- F0 Requisitos: repo inicial, CI verde, estructura y Makefile. (actual)
- F1 Datos: piloto de 1.000 anuncios para medir σ del error; cierre con ≥ 6.000 carros y ≥ 2.600 motos limpios (captura bruta ~7.500 y ~3.500). Captura semanal activa desde aquí.
- F2 Modelación: hedónico OLS como línea base; los ensambles deben superarlo en MAPE. Meta MAPE ≤ 15 %.
- F3 Resultados: métricas por segmento, SHAP, curvas de depreciación, comparación con Fasecolda.
- F4 Producto: API (/predict, /explain, /health, /model-info), app Next.js, Docker, despliegue en Render.

## Forma de trabajo

Antes de implementar algo no trivial, propón un plan corto y espera confirmación. Trabaja una fase a la vez. Al terminar una tarea, corre `make lint` y `make test`.
