# Estado del proyecto / Project status

Última actualización: **2026-10-05** · Fase actual: **F2, los cinco pasos hechos**
(la meta de MAPE ≤ 15 % se cumple en carros, no en motos)

Este documento es el punto de retorno: dice qué funciona, qué falta, qué está decidido y
qué no. Se actualiza al cerrar cada bloque de trabajo.

---

## Resumen en una línea

El pipeline completo funciona de punta a punta —captura → bronze → silver → gold,
validado— con 7.207 carros y 3.765 motos, y las capturas ya no se pierden: viven en la
rama `data`. Tres modelos entrenados y medidos **fuera de muestra**: el mejor es LightGBM
con **11,5 % MAPE en carros** y **24,9 % en motos** tras enriquecer 1.500 anuncios con su
página de detalle (eran 26,7 %). Carros cumple la meta de F2 (≤ 15 %); motos no todavía.
La banda P10–P90 está calibrada y SHAP ya explica cada predicción, con lo que **los cinco
pasos de F2 están hechos**. Lo que SHAP dejó claro es por qué motos falla: el modelo pesa
identidad (marca, cilindrada, modelo) y casi no pesa estado (edad, kilometraje).

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
- **`ingest/history.py`** — mueve capturas entre el lago y la rama `data`. Una sola
  implementación para el workflow, `make pull-history` y el sembrado manual. Nunca
  sobrescribe, y solo viajan las capas crudas (bronze y detail).
- **`ingest/detail.py` + `ingest/detail_cli.py`** — `make enrich`: lee la tabla de
  atributos de la página de cada anuncio sin detalle, con presupuesto por corrida y
  muestreo aleatorio con semilla. Lista blanca de etiquetas, nunca HTML, nada personal.

### Estado de los datos

| Capa | Filas | Nota |
| --- | --- | --- |
| bronze | 13.696 | append-only, varias capturas |
| detail | 1.500 | atributos de la página, una fila por anuncio; **solo motos** |
| silver | 10.982 | tras colapsar repeticiones del mismo anuncio y precio |
| gold | 10.972 | solo filas plausibles (10 rechazadas) |

Cobertura de features sacadas del título, sin peticiones extra:

| Vertical | Marca | Cilindrada | Marcas | Modelos |
| --- | --- | --- | --- | --- |
| Carros | 99,2 % | 86,0 % | 47 | 498 |
| Motos | 81,0 % | 80,6 % | 31 | 764 |

### F2 — Modelación (cerrada)

Los cinco pasos están cerrados: partición honesta, línea base, ensambles afinados, banda
P10–P90 calibrada y SHAP. `make train` corre los tres modelos, la banda y la importancia.

| Entregable | Estado |
| --- | --- |
| `models/dataset.py` — partición train/test, estrategias `random` y `temporal` | hecho |
| `models/metrics.py` — error en pesos, más métricas de intervalo para P10–P90 | hecho |
| `models/hedonic.py` — pipeline OLS, dos conjuntos de features | hecho |
| `models/trees.py` — LightGBM y CatBoost con categóricas crudas | hecho |
| `models/tuning.py` — Optuna sobre CV agrupada, objetivo MAPE en pesos | hecho |
| `models/quantiles.py` — banda P10–P90 conformalizada, y la etiqueta ganga/justo/caro | hecho |
| `models/explain.py` — SHAP sobre LightGBM: factores `exp(φ)`, importancia global, top drivers | hecho |
| `models/train.py` — `make train`, `--model`, `--trials`, `--no-intervals`, `--no-explain`, MLflow | hecho |
| 214 tests en total; cobertura 95,9 %, ruff y mypy limpios | hecho |
| [ADR 0003](adr/0003-tree-model-validation.md) — encoding y protocolo de validación | hecho |

---

## Resultados fuera de muestra

Holdout del 20 %, `make train` del 2026-10-01. Estos **sí** se pueden citar.

> **Las motos de esta tabla ya están superadas.** El enriquecimiento corrigió la
> cilindrada de 573 anuncios, y con eso LightGBM en motos pasó de 26,7 % a **24,9 %** sobre
> el mismo holdout. Ver [El enriquecimiento de motos](#el-enriquecimiento-de-motos). Las
> filas de carros siguen vigentes: no se enriquecieron.

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

## Qué mueve el estimado (SHAP)

Sobre LightGBM, medido **en el holdout** del `make train` del 2026-10-05 —no en train, que
sobreestimaría lo que los árboles memorizaron. El modelo predice `log(precio)`, así que las
contribuciones son aditivas en logaritmo y **multiplicativas en pesos**: `exp(φ)` es un
factor exacto sobre el precio. La columna "tirón típico" es `exp(media |φ|) − 1`, es decir
cuánto mueve esa variable el precio en una fila cualquiera, sin su signo.

| Variable | Carros | Motos |
| --- | --- | --- |
| `model` | **31,0 %** | 22,2 % |
| `vehicle_age_years` | **25,3 %** | 8,5 % |
| `brand` | 14,5 % | **42,6 %** |
| `mileage_km` | 9,6 % | 6,5 % |
| `engine_cc` | 8,5 % | **40,9 %** |
| `city` | 1,9 % | 9,0 % |
| `km_per_year` | 1,6 % | 2,1 % |
| `department` | 0,2 % | 0,8 % |
| `is_official_store` | 0,1 % | 0,5 % |
| `is_quad` | — | 0,6 % |

**El hallazgo: en motos el modelo pesa identidad y casi no pesa estado.** Marca, cilindrada
y modelo suman un tirón de 105 puntos; edad y kilometraje suman 15. En carros la relación
es la inversa —edad es el segundo factor (25,3 %) y el estado pesa 35 puntos—. Dicho de
otra forma, el modelo de motos funciona como un catálogo: sabe cuánto vale una Pulsar 180,
pero no cuánto descontarle por tener diez años y 60.000 km. Eso explica a la vez el MAPE y
los 94 % de ancho de banda: dentro de una celda (marca, cilindrada, modelo) le queda poca
información para separar un ejemplar barato de uno caro.

(Esta tabla se midió **antes** del enriquecimiento, cuando motos iba en 26,7 %. El orden de
las variables es lo que importa aquí, y es lo que motivó la sección siguiente.)

Dos matices antes de usar esto para decidir:

- La media de |φ| mide **cuánta varianza de precio explica** la variable, no si la relación
  es correcta. Que la edad pese poco en motos puede ser que de verdad importe menos, o que
  marca y modelo ya la estén absorbiendo. No se distingue con esta tabla.
- `engine_cc` pesa 40,9 % en motos y 8,5 % en carros porque el rango real es distinto: de
  50 cc a 1.200 cc son dos órdenes de magnitud de precio; de 1,0 L a 3,0 L no.

Esto reordena la discusión sobre páginas de detalle: versión y transmisión agregan **más
identidad**, que es justo lo que a motos no le falta. Lo que falta es señal de estado, y
eso no está en la tabla de atributos.

---

## El enriquecimiento de motos

Se leyó la tabla de atributos de la página de **1.500 de las 3.765 motos** (39,8 %), una
petición por anuncio con las pausas educadas: **1.500/1.500 sin un solo fallo**, ~100 min,
94 KB de Parquet. La muestra es aleatoria con semilla fija, no los primeros N, porque los
identificadores correlacionan con la fecha de publicación.

### Lo primero: la tabla de motos no es la de carros

Verificado contra páginas reales, no supuesto. **No existen versión, combustible ni
carrocería** —esos son el esquema de carros—. Lo que sí trae, y es el hallazgo que
justifica la corrida:

| Campo pedido | Qué hay en motos |
| --- | --- |
| Cilindrada | **sí**, 94,9 % de cobertura contra 80,6 % del título |
| Carrocería | **no**, pero `Tipo de moto` es su equivalente: Naked, Touring, Scooter, Enduro… |
| Transmisión | **sí**, pero solo en 22,8 % de los anuncios |
| Versión | **no existe** en la tabla |
| Combustible | **no existe**; `Motor` trae el ciclo (4 tiempos), no el combustible |

Cobertura real de lo que se guardó, sobre las 1.500 filas: `body_type` 100 %, `color`
99,7 %, `engine_cc` 94,9 %, `brakes` 86,3 %, `single_owner` 53,4 %, `transmission` 22,8 %,
`gear_count` 16,3 %.

**`Tipo de moto` es señal nueva de verdad**, con 12 segmentos y buen reparto: Naked 321,
Touring 274, Scooters 177, Calle 155, Enduro 99, Deportivas 93, Cuatrimotos 58, Doble
propósito 49, Custom 28, Cross 15, Chopper 12. Una Touring y una Scooter de la misma
cilindrada son clases de precio distintas y el título nunca lo dice.

### La muestra es representativa

Pregunta obligada antes de medir sobre un subconjunto:

| | Enriquecidas (1.500) | Resto (2.265) |
| --- | --- | --- |
| Precio medio | 30,91 M | 30,47 M |
| σ de log(precio) | 1,009 | 1,032 |
| Edad media | 4,14 | 4,12 |
| Km medios | 23.729 | 23.501 |

La mezcla de marcas se desvía como máximo ~1 punto porcentual (Suzuki 7,27 % contra
6,32 %; Yamaha 11,67 % contra 11,00 %). El subconjunto se parece a la vertical.

### El resultado: motos pasan de 26,7 % a 24,9 %

LightGBM afinado, 40 trials, misma semilla y misma partición agrupada en las cuatro
corridas. El enriquecimiento tiene **dos efectos separables** y se midieron por separado,
porque mezclarlos daría un número que no se puede atribuir a nada:

| Qué se midió | Filas | Holdout | CV MAPE | **MAPE fuera** | σ (log) | R² |
| --- | --- | --- | --- | --- | --- | --- |
| Publicado, antes del enriquecimiento | 3.765 | 753 | 27,2 % | 26,7 % | 0,410 | 0,847 |
| Vertical completa, solo con la cilindrada corregida | 3.765 | 753 | 25,9 % | **24,9 %** | 0,378 | 0,870 |
| Subconjunto enriquecido, sin las columnas nuevas | 1.500 | 300 | 24,2 % | 22,4 % | 0,363 | 0,879 |
| Subconjunto enriquecido, con las columnas nuevas | 1.500 | 300 | 22,7 % | **20,6 %** | 0,331 | 0,900 |

Dos lecturas, las dos limpias:

- **La cilindrada corregida sola vale −1,8 puntos en la vertical completa**: 26,7 % →
  **24,9 %**, mismas 3.012 filas de entrenamiento y mismo holdout de 753 que el número
  publicado. `engine_cc` mejoró en **573 de las 1.500 filas enriquecidas** —251 huecos
  llenados y **322 valores corregidos**, donde el token del título contradecía al campo
  del formulario—, y eso solo alcanzó a bajar casi dos puntos de toda la vertical.
- **Las columnas nuevas valen otros −1,8 puntos** donde existen: 22,4 % → 20,6 % sobre
  exactamente las mismas 1.500 filas, con la cilindrada corregida ya presente en las dos
  ramas. Es la única diferencia entre esas dos corridas, así que es atribuible a las
  features y no a la población.

El par de filas del subconjunto **no se compara contra el 26,7 %**: usa 1.200 filas de
entrenamiento en vez de 3.012. Ese es justamente el motivo de haber corrido las cuatro.

**Estimación, no medición:** si las 2.265 motos restantes se enriquecen, la vertical
completa debería caer de 24,9 % a algo cercano a **23 %**, suponiendo que el −1,8 de las
columnas nuevas se sostenga al triplicar la cobertura. Es una extrapolación de dos puntos
medidos, no un resultado.

### Lo que la página trae y el modelo todavía no usa

El reporte de etiquetas desconocidas —que existe justamente para esto— encontró campos
que no estaban en la lista blanca: peso (105 anuncios), dimensiones y distancia entre ejes,
entrada USB (230), y el bloque de batería de las motos eléctricas (voltaje, capacidad,
autonomía, tiempo de carga). Ya están en la lista blanca, pero **las 1.500 filas ya
escritas no los traen**: se capturan desde la próxima pasada.

### Dos cosas que el contrato de calidad atrapó

El campo de cilindrada de la página es texto libre y devolvió **0, 1, 11, 12, 13 y 40 cc**
—en parte errores de digitación, en parte motos eléctricas que no tienen cilindrada—. El
de velocidades devolvió **0 y 82**. Los dos se acotan ahora en `stg_listing_details` con
los mismos umbrales de siempre, y la cilindrada cae de vuelta al valor del título cuando
la página miente. Lo detectó el esquema Pandera de gold, no una revisión a ojo.

---

## Lo que falta

### F2 — los cinco pasos hechos

Queda abierto el criterio de cierre en sí: **motos no llega a la meta de 15 %**. Lo que las
corridas dejaron pendiente:

- **Elegir el modelo servido.** LightGBM gana en ambas verticales y es ~5 veces más rápido
  de ajustar que CatBoost. En motos la diferencia con CatBoost es de 0,1 puntos, que es
  ruido; en carros son 1,6 puntos reales. Falta decidir si CatBoost se mantiene como
  comparación o se retira.
- **Motos a 26,7 % todavía no sirve para el producto**, y la banda lo confirma: 94 % de
  ancho. SHAP acota el diagnóstico: falta señal de estado, no de identidad.
- **La cobertura de la banda queda ~3 puntos corta** del nominal. Ver deuda conocida; no
  bloquea, pero hay que decidir si se arregla antes de exponer la etiqueta en la API.

### F3 — Resultados

Métricas por segmento, curvas de depreciación, índice mensual, comparación con Fasecolda
(bloqueada, ver abajo). La importancia global ya está; lo que falta de SHAP en F3 es
desagregarla por segmento.

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

### 1. Páginas de detalle — decidido para motos, abierto para carros

**Motos: aprobado y hecho en 1.500 anuncios**, de forma incremental. Resultados arriba.

**Lo que falta de motos**: 2.265 anuncios sin detalle, ~2,5 h en cinco corridas de 500.
Vale la pena, y no por el MAPE: el bloqueador real de la vertical era **el ancho de banda
del 94 %**, y con 3,8 veces más filas enriquecidas se puede volver a medir la banda con
las features nuevas, que es la medición que decide si la etiqueta ganga/justo/caro sirve.

**Carros: la recomendación es no extenderlo, al menos no por precisión.** El argumento,
con el número en la mano:

- Carros van en **11,5 %**, 3,5 puntos bajo la meta, sin una sola petición extra.
- El efecto limpio de las features nuevas fue de **−1,8 puntos**, y se consiguió en la
  vertical que estaba hambrienta de señal: SHAP mostró que motos pesa identidad (105
  puntos de tirón entre marca, cilindrada y modelo) y casi no pesa estado (15 puntos).
  Carros no tienen ese desbalance —la edad es su segundo factor, con 25,3 %—, así que
  ahí hay menos hueco que llenar.
- El costo no es comparable: **~8 h** de raspado educado para 7.207 carros, contra los
  100 min que costaron 1.500 motos, y duplica el peso de la rama `data`.
- Matiz honesto a favor de carros: su tabla **sí** trae versión, transmisión, combustible,
  carrocería y puertas —el esquema que motos no tiene—, así que la ganancia por anuncio
  podría ser mayor que −1,8. Lo que es menor es la necesidad.

Dónde sí lo reconsideraría: si F4 quiere mostrar versión o transmisión en la ficha, o si
F3 necesita carrocería para segmentar. Eso es una razón de producto, no de modelo, y
cambia la respuesta.

### 2. Fasecolda — bloqueada

`fasecolda.com/guia-de-valores/` es un shell de JS sin datos;
`guiadevalores.fasecolda.com` responde **403**. Su `robots.txt` no prohíbe nada, pero la
guía no se obtiene por HTTP simple. No bloquea F2 porque `valor_fasecolda` nunca fue
feature del modelo; se vuelve necesaria en F3.

**La suscripción queda descartada por la regla de costo cero.** Lo que queda: un export
manual que tú consigas, o alguna fuente pública gratuita que republique la guía. Si no
aparece ninguna, el benchmark se cae y hay que decirlo en los resultados en vez de
sustituirlo por algo que no es Fasecolda.

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
- **La rama `data` crece para siempre.** ~1 MB hoy con las 8 capturas más el detalle,
  ~25 MB al año. Quitar algo publicado por error exige reescribir la rama. Cuando empiece
  a apretar hay que **avisar, no migrar**: el proyecto corre a costo cero y pasar a
  almacenamiento de objetos exige aprobación explícita
  ([ADR 0004](adr/0004-capture-history-storage.md), y la sección "Costo cero" de
  `CLAUDE.md`). Podar el histórico o acotar lo que se captura son respuestas igual de
  válidas.
- **El detalle solo cubre 39,8 % de motos y 0 % de carros.** Por eso las features de
  detalle están **apagadas por defecto** en el modelo: encenderlas sobre la vertical
  completa le daría al modelo columnas nulas en seis de cada diez filas. Tienen sentido
  con `--only-enriched`, o cuando la cobertura sea alta.
- **Las 1.500 filas de detalle ya escritas no traen peso, dimensiones ni batería.** Esas
  etiquetas se agregaron a la lista blanca *después* de esa pasada, con el reporte de
  drift en la mano; se capturan desde la siguiente.
- **`model` y `brand` de la página de detalle se guardan pero no se usan.** El `Modelo`
  del formulario es más limpio que el token minado del título, pero en algunos anuncios
  trae el año. Reconciliarlo con `stg_title_features` está sin hacer.
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
- **El gráfico de barras de SHAP no está.** Dibujarlo exige importar matplotlib directo, y
  hoy llega solo como dependencia transitiva de `shap`; declararlo pide regenerar
  `uv.lock`, que esta máquina no pudo hacer (pypi.org no resolvía) y CI corre con
  `UV_FROZEN=1`, así que un `pyproject` en desacuerdo con el lock rompe el build. El CSV y
  las métricas por variable en MLflow llevan la misma información. F3 declara matplotlib
  de todos modos para las curvas de depreciación.
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
.\make.ps1 test          # 276 tests, cobertura 96,4 %
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
.\make.ps1 pull-history   # trae los Parquet publicados al lago, sin sobrescribir
.\make.ps1 transform      # reconstruye silver y gold desde ahí
```

Para seguir enriqueciendo motos (quedan 2.265, ~35 min por corrida de 500):

```powershell
$env:AUTOVALOR_USE_SYSTEM_CERTS = 'true'
.\make.ps1 enrich -Budget 500   # solo anuncios sin detalle, muestreo con semilla
.\make.ps1 transform
.\make.ps1 push-history         # publica el detalle nuevo
```

Y para repetir la medición pareada tal cual se hizo:

```powershell
uv run python -m autovalor.models.train --model lightgbm --vehicle-type motorcycle `
    --only-enriched --no-intervals --no-mlflow                     # sin las features
uv run python -m autovalor.models.train --model lightgbm --vehicle-type motorcycle `
    --only-enriched --detail-features --no-intervals --no-mlflow    # con ellas
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
