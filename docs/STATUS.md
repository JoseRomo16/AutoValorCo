# Estado del proyecto / Project status

Última actualización: **2026-10-01** · Fase actual: **F2 en curso (pasos 1 a 4 hechos)**

Este documento es el punto de retorno: dice qué funciona, qué falta, qué está decidido y
qué no. Se actualiza al cerrar cada bloque de trabajo.

---

## Resumen en una línea

El pipeline completo funciona de punta a punta —captura → bronze → silver → gold,
validado— con 7.207 carros y 3.765 motos. Tres modelos entrenados y medidos **fuera de
muestra**: el mejor es LightGBM con **11,5 % MAPE en carros** y **26,7 % en motos**.
Carros cumple la meta de F2 (≤ 15 %); motos no. La banda P10–P90 ya existe y está
calibrada. Falta SHAP.

---

## Lo que está hecho y verificado

### F0 — Esqueleto (cerrada)

| Entregable | Estado |
| --- | --- |
| `pyproject.toml` con uv, Python 3.12, deps de datos/modelado/API + grupo dev | hecho |
| Estructura `src/autovalor/{ingest,quality,features,models,api}` | hecho |
| `Makefile` + `make.ps1` (Windows no tiene GNU make) | hecho |
| `.gitignore`, `.env.example`, `.pre-commit-config.yaml`, `.gitattributes`, `LICENSE` | hecho |
| CI en GitHub Actions: ruff, ruff format, mypy, pytest | **verde en GitHub** |
| `Dockerfile` + `docker-compose.yml` (API + MLflow opcional) | escrito, **sin probar** |
| README bilingüe, ADR 0001, diccionario de datos | hecho |

### F1 — Datos (cerrada)

| Criterio de cierre | Meta | Real |
| --- | --- | --- |
| Piloto para medir σ del error | 1.000 anuncios | 2.704, luego 10.972 |
| Carros limpios | ≥ 6.000 | **7.207** |
| Motos limpias | ≥ 2.600 | **3.765** |
| Captura semanal activa | — | workflow activo en GitHub |

Componentes:

- **`ingest/polite.py`** — cliente HTTP que obedece `robots.txt`, pausa aleatoria entre
  peticiones, user-agent identificable, reintentos con backoff en 429/5xx. Si robots.txt
  responde 5xx o no responde, **se abstiene** (fail closed, RFC 9309).
- **`ingest/records.py`** — `RawListing`: bronze guarda cada valor como el string que se
  publicó. El nombre del vendedor está en el HTML y **no se lee** (Ley 1581); solo se
  guarda `official_store`. Hay un test que falla si se cuela.
- **`ingest/bronze.py`** — writer inmutable, particionado por fuente/vertical/fecha, se
  niega a sobrescribir.
- **`ingest/tucarro.py`** — scraper de carros y motos. Paginación por offset (`_Desde_N`,
  48 por página) porque los enlaces de paginación del sitio son client-side.
- **`ingest/cli.py`** — `make scrape`; `--location` repetible, `--pages`, `--dry-run`.
- **`quality/schemas.py`** — contratos Pandera de las tres capas. Los umbrales de
  plausibilidad viven aquí y se espejan como vars de dbt; un test falla si divergen.
- **`quality/cli.py`** — valida bronze / silver / gold; salta las capas sin datos.
- **dbt** — `stg_tucarro_listings` (parseo), `stg_title_features` (marca, modelo,
  cilindrada, flag de cuatrimoto), `silver_listings` (dedup + flags), `gold_listings`
  (filtrado + features). Seed `vehicle_brands`. **41/41 tests dbt en verde.**
- **`.github/workflows/capture.yml`** — captura semanal, lunes 07:00 UTC, barre seis
  departamentos, valida, **publica bronze en la rama `data`** y sube el resultado como
  artefacto.
- **`ingest/history.py`** — mueve capturas entre `data/bronze` y la rama `data`. Una sola
  implementación para el workflow, `make pull-history` y el sembrado manual. Nunca
  sobrescribe y solo mueve bronze.

### Estado de los datos

| Capa | Filas | Nota |
| --- | --- | --- |
| bronze | 13.696 | append-only, varias capturas |
| silver | 10.982 | tras colapsar repeticiones del mismo anuncio y precio |
| gold | 10.972 | solo filas plausibles (10 rechazadas) |

Cobertura de features sacadas del título, sin peticiones extra:

| Vertical | Marca | Cilindrada | Marcas | Modelos |
| --- | --- | --- | --- | --- |
| Carros | 99,2 % | 86,0 % | 47 | 498 |
| Motos | 81,0 % | 80,6 % | 31 | 764 |

### F2 — Modelación (en curso)

Pasos 1 a 4 cerrados: partición honesta, línea base, ensambles afinados y banda P10–P90
calibrada. `make train` corre los tres modelos y la banda.

| Entregable | Estado |
| --- | --- |
| `models/dataset.py` — partición train/test, estrategias `random` y `temporal` | hecho |
| `models/metrics.py` — error en pesos, más métricas de intervalo para P10–P90 | hecho |
| `models/hedonic.py` — pipeline OLS, dos conjuntos de features | hecho |
| `models/trees.py` — LightGBM y CatBoost con categóricas crudas | hecho |
| `models/tuning.py` — Optuna sobre CV agrupada, objetivo MAPE en pesos | hecho |
| `models/quantiles.py` — banda P10–P90 conformalizada, y la etiqueta ganga/justo/caro | hecho |
| `models/train.py` — `make train`, `--model`, `--trials`, `--no-intervals`, MLflow | hecho |
| 162 tests nuevos en total; cobertura 96 %, ruff y mypy limpios | hecho |
| [ADR 0003](adr/0003-tree-model-validation.md) — encoding y protocolo de validación | hecho |

---

## Resultados fuera de muestra

Holdout del 20 %, `make train` del 2026-10-01. Estos **sí** se pueden citar.

| Vertical | Modelo | CV MAPE | MAPE fuera | MAPE dentro | σ (log) | R² | vs base |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Carros | hedónico, edad + km + depto | — | 48,8 % | 46,8 % | 0,580 | 0,316 | +33,5 pt |
| Carros | hedónico, + marca/modelo/cc | — | 15,3 % | 14,0 % | 0,222 | 0,900 | base |
| Carros | **LightGBM** | 11,8 % | **11,5 %** | 5,9 % | 0,177 | 0,936 | −3,8 pt |
| Carros | CatBoost | 13,5 % | 13,1 % | 9,1 % | 0,204 | 0,915 | −2,2 pt |
| Motos | hedónico, edad + km + depto | — | 101,0 % | 97,9 % | 0,995 | 0,102 | +53,2 pt |
| Motos | hedónico, + marca/modelo/cc | — | 47,8 % | 41,5 % | 0,579 | 0,697 | base |
| Motos | **LightGBM** | 27,2 % | **26,7 %** | 14,5 % | 0,410 | 0,847 | −21,1 pt |
| Motos | CatBoost | 28,9 % | 26,8 % | 19,4 % | 0,411 | 0,847 | −21,0 pt |

**Carros cumple la meta de F2** (≤ 15 %) con 3,5 puntos de margen. Motos no, pero mejoró
21 puntos.

Cuatro cosas que salieron de aquí:

- **Los ensambles ganan y la ventaja es el tratamiento de categóricas.** El hedónico tiene
  que agrupar niveles raros antes del one-hot; los árboles parten sobre la categoría cruda.
  Esa diferencia vale 3,8 puntos en carros y 21 en motos.
- **Las motos no eran solo falta de señal.** La lectura de F1 —que el problema era la
  versión faltante y no la capacidad del modelo— era **demasiado pesimista**: el mismo
  feature set rinde 26,7 % con un ensamble. La versión sigue faltando, pero ya no es la
  explicación dominante.
- **La búsqueda no se sobreajustó a los folds.** La brecha entre CV y holdout es de 0,3 a
  2,1 puntos en los cuatro casos, con el holdout a veces *mejor*. Bajar a 3 folds para
  recortar el costo no distorsionó el ranking.
- **Había fuga por reposteos.** El mismo vehículo reaparece con otro `listing_id`: 521
  filas de carros (7,2 %) y 72 de motos. Con split por filas los gemelos caían a ambos
  lados y el hedónico marcaba 14,3 %. La partición agrupa por (título, año, km) y mueve
  grupos completos, y la CV de tuning hace lo mismo; el punto de diferencia era fuga.

### Costo de la corrida

~50 min en la máquina de desarrollo. LightGBM 40 trials por vertical, CatBoost 20, CV de
3 folds — presupuesto asimétrico porque un ajuste de CatBoost cuesta de 3 a 9 veces uno de
LightGBM. Detalle y razones en [ADR 0003](adr/0003-tree-model-validation.md).

---

## La banda P10–P90

Solo LightGBM la lleva, por ser el ganador en ambas verticales. Mismo holdout, mismos
parámetros afinados que el modelo puntual.

| Vertical | Cobertura | Ancho medio | Ganga | Caro | Ensanche (log) | Cruzados |
| --- | --- | --- | --- | --- | --- | --- |
| Carros | 76,5 % | **38 %** | 13,0 % | 10,5 % | +0,029 | 5,8 % |
| Motos | 76,8 % | **94 %** | 12,1 % | 11,2 % | +0,061 | 8,4 % |

**Sin conformalizar la banda no servía.** Los tres modelos cuantílicos ajustados y usados
directamente cubrían **67,2 % en carros y 63,2 % en motos** contra un nominal de 80 %: los
árboles pegan los cuantiles al train y la banda sale angosta en filas nuevas. Una banda
anunciada al 80 % que sostiene 63 % es peor que no tener banda, porque la etiqueta "ganga"
se dispararía en anuncios normales. `models/quantiles.py` aparta el 25 % del train, mide
ahí el error de la propia banda y ensancha por el cuantil que restituye la cobertura
(Romano, Patterson & Candès, 2019). El split interno reutiliza el splitter agrupado, porque
un reposteo en las dos mitades sesgaría el ensanche hacia abajo.

**El ancho es el problema de motos, no la cobertura.** 94 % del estimado significa que la
banda va de aproximadamente la mitad al doble del precio: la etiqueta ganga/justo/caro no
dice nada ahí. Carros a 38 % sí es utilizable. Afinar los hiperparámetros apretó carros de
44 % a 38 %; motos no se movió.

---

## Lo que falta

### F2 — lo que queda

5. **SHAP**, para `/explain`. Sobre LightGBM. Es lo único que queda de F2.

Además, tres cosas que las corridas dejaron pendientes:

- **Elegir el modelo servido.** LightGBM gana en ambas verticales y es ~5 veces más rápido
  de ajustar que CatBoost. En motos la diferencia con CatBoost es de 0,1 puntos, que es
  ruido; en carros son 1,6 puntos reales. Falta decidir si CatBoost se mantiene como
  comparación o se retira.
- **Motos a 26,7 % todavía no sirve para el producto**, y la banda lo confirma: 94 % de
  ancho. Decidir entre enriquecer con páginas de detalle (ver decisiones abiertas) o
  limitar el alcance de la vertical.
- **La cobertura de la banda queda ~3 puntos corta** del nominal. Ver deuda conocida; no
  bloquea, pero hay que decidir si se arregla antes de exponer la etiqueta en la API.

### F3 — Resultados

Métricas por segmento, curvas de depreciación, índice mensual, comparación con Fasecolda
(bloqueada, ver abajo).

### F4 — Producto

`/predict` y `/explain` (hoy solo existen `/health` y un `/model-info` stub), app Next.js
—**nada del frontend está creado**—, Docker probado, despliegue en Render.

---

## Las cifras del piloto de F1 (ya superadas)

Los números de [`f1-pilot.md`](f1-pilot.md) son **en muestra**: un OLS ajustado y evaluado
sobre las mismas filas. Quedan como registro del piloto, no como rendimiento. La tabla de
arriba los reemplaza.

| Vertical | Features | σ (log) | R² | MAPE en muestra |
| --- | --- | --- | --- | --- |
| Carros | edad + km + depto | 0,580 | 0,331 | 55,9 % |
| Carros | + marca + modelo + cc | 0,244 | 0,885 | 17,5 % |
| Motos | edad + km + depto | 0,970 | 0,104 | 113,8 % |
| Motos | + marca + modelo + cc | 0,541 | 0,730 | 43,7 % |

### Las dos lecciones que orientan F2

**El volumen por sí solo no compró nada.** Pasar de 1.468 a 7.207 carros dejó σ
prácticamente igual (0,578 → 0,580) con el feature set débil. Lo que compró el volumen
fue que los dummies de modelo se volvieran estimables: marca+modelo da σ 0,252 con 7.200
filas contra 0,352 con 1.468. Volumen y features se necesitan mutuamente.

**Las motos son el problema abierto**, por tres razones en orden de tamaño: falta la
versión y pesa más que en carros; el 19 % de títulos no resuelve marca (contra 0,8 % en
carros); y el token `model` es más ruidoso (764 valores distintos para 3.765 anuncios).

Matiz del paso 3 de F2: el tercer punto resultó ser menos grave de lo que parecía. Los
árboles parten sobre el token crudo sin necesidad de agrupar niveles raros, y eso solo
valió 21 puntos de MAPE en motos.

---

## Decisiones abiertas (del usuario, no mías)

### 1. Páginas de detalle

Lo que falta para acercarse a la meta —versión, transmisión, combustible, carrocería,
puertas— está en la página de cada anuncio como tabla estructurada, a **una petición
extra por anuncio**. Con las pausas educadas son ~4 h para los 11.000 actuales. Convierte
el workflow semanal de minutos en horas.

Recomendación: pasada incremental con presupuesto por corrida, enriqueciendo solo
anuncios sin detalle, en vez de un barrido monolítico.

Con los ensambles medidos, la decisión es **solo sobre motos** y ya no es obvia:

- **Carros quedaron fuera del debate.** 11,5 % con LightGBM, 3,5 puntos bajo la meta, sin
  una sola petición extra. Enriquecerlos no se justifica por rendimiento.
- **Motos mejoraron 21 puntos sin datos nuevos**, de 47,8 % a 26,7 %. Eso debilita el
  argumento de que la versión era el cuello de botella: parte de lo que parecía falta de
  señal era falta de capacidad del modelo. Cuánto queda por ganar con la versión ya no se
  puede estimar desde el hedónico.
- Pero **26,7 % sigue sin servir para el producto.** Un intervalo honesto a ese nivel de
  error será demasiado ancho para que la etiqueta ganga/justo/caro diga algo.

Enriquecer solo motos cuesta ~1,3 h (3.765 anuncios) en vez de ~4 h. La alternativa es
acotar el alcance: publicar motos con una advertencia de precisión, o dejarlas fuera del
clasificador y solo estimar carros.

### 2. Fasecolda — bloqueada

`fasecolda.com/guia-de-valores/` es un shell de JS sin datos;
`guiadevalores.fasecolda.com` responde **403**. Su `robots.txt` no prohíbe nada, pero la
guía no se obtiene por HTTP simple. Hace falta decidir la fuente: export manual,
suscripción, o se cae el benchmark. No bloquea F2 porque `valor_fasecolda` nunca fue
feature del modelo; se vuelve necesaria en F3.

---

## Deuda conocida

- **`vehicle_age` está implementado dos veces**: `features/age.py` en Python y como SQL en
  `gold_listings`. Decidir la fuente de verdad antes de que divergan.
- **Docker nunca se ha construido ni corrido.** No hay docker en la máquina de desarrollo.
- **La captura semanal sigue construyendo silver y gold solo con su propia corrida**, no
  con el histórico acumulado. Eso basta para validar que la captura salió bien, pero el
  `gold_listings` del workflow no es el lago completo; el acumulado se arma en local con
  `pull-history` + `transform`. Si el índice mensual de F3 va a correr en CI, el workflow
  tendrá que traer el histórico antes de dbt.
- **La rama `data` crece para siempre.** 944 KB hoy, ~25 MB al año. Quitar una captura
  publicada por error exige reescribir la rama. Los disparadores para pasar a R2 están en
  [ADR 0004](adr/0004-capture-history-storage.md).
- **Cuatrimotos, buggies y side-by-sides** viven en la vertical de motos (121 anuncios).
  Marcados con `is_quad` para que F2 los segmente, no eliminados.
- **Las tarjetas patrocinadas se filtran entre regiones**, así que `department` no es un
  marco de muestreo limpio.
- **GitHub desactiva los workflows programados** tras 60 días sin actividad en el repo.
- **La validación temporal todavía no se puede hacer.** Todo el gold viene de una sola
  ventana de captura (2026-09-29 21:48 → 2026-09-30 01:01), así que `--split temporal`
  falla a propósito hasta que haya 14 días de histórico. Con la captura semanal activa eso
  llega solo; conviene repetir la medición con `temporal` cuando llegue, porque es la
  partición que exige el índice mensual.
- **La cobertura de la banda queda corta: 76,5 % y 76,8 % contra el nominal de 80 %.** Son
  ~3 puntos, demasiado para ser ruido de muestreo con n=1441 (±1 punto). La causa probable
  es que la conformalización supone filas **intercambiables** y estos datos están agrupados
  por vehículo reposteado, así que el cuantil empírico subestima. El arreglo es conformal
  consciente de grupos o una calibración anidada. **No** subir el nivel hasta que el
  holdout cuadre: eso sería ajustar contra el holdout y devolvería la cobertura a ser una
  cifra en muestra.
- **Los cuantiles se cruzan en 5,8 % de carros y 8,4 % de motos.** Se ordenan por fila, que
  es correcto, pero un cruce alto significa que los tres niveles no concuerdan sobre la
  forma de la superficie de precios. Ajustar los tres con un objetivo multicuantil, o con
  monotonicidad impuesta, lo reduciría.
- **La banda entrena con 25 % menos filas** que el modelo puntual, porque esa parte se
  aparta para calibrar. El modelo puntual no paga ese costo; la banda sí.
- **CatBoost se exploró con la mitad del presupuesto que LightGBM** (20 trials contra 40),
  porque cuesta de 3 a 9 veces más por ajuste. Que pierda es evidencia más débil que si
  hubiera perdido con el mismo presupuesto; tenerlo en cuenta antes de retirarlo.
- **Quedan corridas `hedonic_ols-*` en MLflow** del nombre anterior al refactor del paso 3.
  No molestan, pero al filtrar por nombre de modelo hay que contar con ellas.
- **MLflow 3 rechaza el backend de archivos.** `file:./mlruns` quedó en modo
  mantenimiento y lanza excepción; el tracking pasó a `sqlite:///mlflow.db` en
  `config.py`, `.env.example` y `docker-compose.yml`. Si existía un `mlruns/` viejo, se
  migra con `mlflow migrate-filestore`.

---

## Cómo retomar

```powershell
# El entorno local tiene tres particularidades, ver docs/ y .env.example:
#  1. uv no está en el PATH: %APPDATA%\Python\Python312\Scripts\uv.exe
#  2. la red intercepta TLS: uv necesita --system-certs, y el scraping
#     necesita AUTOVALOR_USE_SYSTEM_CERTS=true
#  3. no hay make ni docker en Windows: usar .\make.ps1
.\make.ps1 test          # 205 tests, cobertura 95,8 %
.\make.ps1 lint          # ruff + mypy
.\make.ps1 transform     # valida bronze, corre dbt, valida silver y gold
.\make.ps1 train         # los tres modelos y la banda, ~50 min, todo a MLflow
```

Para ver solo los números rápido, sin búsqueda y sin escribir en MLflow:

```powershell
uv run python -m autovalor.models.train --trials 0 --no-mlflow
# o un modelo y una vertical, sin banda:
uv run python -m autovalor.models.train --model lightgbm --vehicle-type car `
    --trials 5 --no-intervals --no-mlflow
```

### El lago se reconstruye desde la rama `data`

`data/` no está en git, pero **las capturas sí**, en la rama huérfana `data`
([ADR 0004](adr/0004-capture-history-storage.md)). Ya no hace falta volver a raspar para
tener el lago:

```powershell
.\make.ps1 pull-history   # trae los Parquet publicados a data/bronze, sin sobrescribir
.\make.ps1 transform      # reconstruye silver y gold desde ahí
```

Estado de la rama hoy: **8 capturas, 944 KB**, dos commits de backfill. Solo viaja bronze;
silver y gold se derivan. `pull-history` nunca sobrescribe un archivo local —bronze es
inmutable y el nombre lleva el instante UTC, así que una colisión es la misma captura— y
correrlo dos veces no hace nada la segunda vez.

A partir de ahora la captura semanal publica sola: `capture.yml` corre
`autovalor.ingest.history push` con `contents: write`, y lo hace con `if: !cancelled()`
por la misma razón que la subida del artefacto —la captura es la parte irremplazable—. El
artefacto sigue subiéndose como red de seguridad; los dos caminos son independientes a
propósito.

**Ojo con los números al reconstruir.** El lago local tiene solo las **6 capturas del
2026-09-30** (10.972 filas de gold), que es donde se midieron el 11,5 % y el 26,7 %. La
rama tiene 8: incluye la captura programada del 2026-10-05, que deliberadamente no se
incorporó al lago local para no invalidar las cifras de F2 a mitad de camino. Si corres
`pull-history` + `transform`, gold crece y **las métricas de F2 hay que volver a medirlas**
sobre ese gold más grande.

Si de verdad hace falta raspar de nuevo:

```powershell
$env:AUTOVALOR_USE_SYSTEM_CERTS = 'true'
.\make.ps1 scrape -Pages 25   # ~35 min, seis departamentos, ambas verticales
.\make.ps1 transform
```
