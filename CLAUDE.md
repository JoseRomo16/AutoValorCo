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
docs/          # ADRs, diccionario de datos, results/ (JSON y CSV versionados) y figures/
```

## Comandos

- `make setup` instala dependencias (uv sync + playwright install + npm install en frontend)
- `make scrape` captura anuncios a data/bronze
- `make transform` corre dbt (silver y gold) y validaciones Pandera
- `make train` entrena y registra modelos en MLflow (hedónico y LightGBM; CatBoost solo con `--model catboost`)
- `make serve` levanta la API en local
- `make test` corre pytest; `make lint` corre ruff + mypy

## Convenciones

- Código, nombres de variables, docstrings y commits en inglés. README bilingüe (ES/EN).
- Type hints en todo el código de `src/`. Ruff y mypy sin errores.
- Cobertura de pruebas ≥ 70 % en `src/`. Toda función nueva de limpieza o features lleva test.
- Commits pequeños con Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`).
- Nada de lógica de negocio en notebooks: los notebooks importan desde `src/autovalor`.
- Configuración por variables de entorno (`.env`, nunca commiteado); `.env.example` actualizado.

## Costo cero

Restricción de diseño, no una preferencia: **el proyecto opera sin ningún costo monetario**. Todo lo de abajo se deriva de ahí.

- **No propongas servicios que pidan tarjeta o suscripción** —Cloudflare R2, AWS, Apify, planes pagos de Render, APIs de pago— sin preguntar primero. Si una solución necesita uno, dilo y espera decisión en vez de asumirlo.
- **El repositorio se mantiene público**, que es lo que hace gratis a GitHub Actions. Cualquier propuesta que implique volverlo privado tiene que contar ese costo.
- **El histórico de capturas vive en la rama `data`** del propio repositorio ([ADR 0004](docs/adr/0004-capture-history-storage.md)). Almacenamiento de objetos solo se reconsidera con aprobación explícita.
- **F4 cabe en el plan gratuito de Render**: un solo servicio web para la API, con imagen mínima —sin CatBoost, MLflow, Playwright ni dbt— que quepa en 512 MB, y el modelo servido empaquetado dentro de la imagen en vez de descargado en arranque. El frontend Next.js se publica como sitio estático. Hoy el `Dockerfile` instala todas las dependencias, así que F4 tendrá que partir `pyproject.toml` en grupos (`api` contra `train`/`ingest`): ahí se van los 512 MB.
- **Fasecolda solo por fuentes públicas y gratuitas.** Sin suscripción a la guía.

## Reglas de datos

- Scraping educado: respetar robots.txt, pausas aleatorias entre requests, user-agent identificable, sin paralelismo agresivo.
- Nunca guardar datos personales de vendedores (nombres, teléfonos, correos). Ley 1581 de 2012.
- La capa bronze es inmutable: se escribe una vez por captura, con `captured_at` y `source_url`.
- `valor_fasecolda` no se usa como feature del modelo base (fuga de información); solo como benchmark.
- Precio modelado como log(precio). Carros y motos son modelos separados.

## Qué se publica de cada vertical

Regla de producto, implementada en `models/quantiles.py` y con tests: **la etiqueta
ganga/justo/caro solo se muestra si la banda P10–P90 medida en el holdout tiene cobertura
entre 78 % y 82 % y ancho medio ≤ 60 % del estimado**. La ventana de cobertura es de dos
lados a propósito: cubrir de menos dispara "ganga" en anuncios normales, cubrir de más mete
en "justo" anuncios mal preciados.

Si una vertical no cumple, se publica igual pero con **precio estimado, rango y aviso de
precisión, sin etiqueta** — hoy es el caso de motos (83,6 % y 84 %). No inventes una
excepción ni subas el umbral para que pase: el gate se evalúa sobre el holdout y arreglarlo
contra el holdout lo vuelve una cifra en muestra.

## Fases y criterios de cierre

- F0 Requisitos: repo inicial, CI verde, estructura y Makefile. (cerrada)
- F1 Datos: piloto de 1.000 anuncios para medir σ del error; cierre con ≥ 6.000 carros y ≥ 2.600 motos limpios (captura bruta ~7.500 y ~3.500). Captura semanal activa desde aquí. (cerrada)
- F2 Modelación: hedónico OLS como línea base; los ensambles deben superarlo en MAPE. Meta MAPE ≤ 15 %. (**cerrada**: carros 11,3 % y publican etiqueta; motos 24,1 % y publican precio + rango sin etiqueta, por la regla de abajo. El modelo servido es LightGBM.)
- F3 Resultados: métricas por segmento, SHAP, curvas de depreciación, comparación con Fasecolda. (actual)
- F4 Producto: API (/predict, /explain, /health, /model-info), app Next.js, Docker, despliegue en Render.

## Forma de trabajo

Antes de implementar algo no trivial, propón un plan corto y espera confirmación. Trabaja una fase a la vez. Al terminar una tarea, corre `make lint` y `make test`.
