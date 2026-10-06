# Estado del proyecto / Project status

Última actualización: **2026-10-06** · Fase actual: **F2 cerrada**, F3 en curso
(carros cumplen la meta de MAPE ≤ 15 % y publican etiqueta; motos publican precio y rango
sin etiqueta, por la regla de calidad de banda)

Este documento es el punto de retorno: dice qué funciona, qué falta, qué está decidido y
qué no. Se actualiza al cerrar cada bloque de trabajo.

---

## Resumen en una línea

El pipeline completo funciona de punta a punta —captura → bronze → silver → gold,
validado— con 7.639 carros y 4.052 motos, y las capturas ya no se pierden: viven en la
rama `data`. Tres modelos entrenados y medidos **fuera de muestra**: el mejor es LightGBM
con **11,3 % MAPE en carros** y **24,1 % en motos** (con 2.300 motos enriquecidas, 56,8 %
de la vertical). Carros cumple la meta de F2 (≤ 15 %); motos no. **F2 queda cerrada** con
una regla explícita que decide qué se publica en cada vertical: la etiqueta
ganga/justo/caro exige una banda con cobertura entre 78 % y 82 % y ancho medio ≤ 60 % del
estimado, y motos no la alcanza, así que sale con precio estimado, rango y aviso de
precisión. Lo que SHAP dejó claro es por qué motos falla —el modelo pesa identidad y casi
no pesa estado— y el hedónico de F3 lo confirmó por otra vía: una moto pierde entre 0,9 % y
6,5 % de valor al año, contra 4,8 %–9,6 % en carros.

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
- **`.github/workflows/enrich.yml`** — enriquecimiento manual (`workflow_dispatch`, con
  `enrich_budget`): trae el histórico, reconstruye gold, lee páginas de detalle y publica
  el resultado. Es un workflow aparte porque necesita dos cosas que una captura fresca no
  da: un gold sobre el lago acumulado —para que los candidatos sean los anuncios que de
  verdad faltan— y la capa de detalle ya publicada, para no pedir dos veces la misma
  página. Comparte el grupo de concurrencia `capture`, así que nunca hay dos raspadores
  sobre el sitio a la vez.
- **`ingest/history.py`** — mueve capturas entre el lago y la rama `data`. Una sola
  implementación para el workflow, `make pull-history` y el sembrado manual. Nunca
  sobrescribe, y solo viajan las capas crudas (bronze y detail).
- **`ingest/detail.py` + `ingest/detail_cli.py`** — `make enrich`: lee la tabla de
  atributos de la página de cada anuncio sin detalle, con presupuesto por corrida y
  muestreo aleatorio con semilla. Lista blanca de etiquetas, nunca HTML, nada personal.

### Estado de los datos

Tras traer el histórico completo de la rama `data` (8 capturas, 2026-09-30 y 2026-10-05):

| Capa | Filas | Antes | Nota |
| --- | --- | --- | --- |
| bronze | 18.859 | 13.696 | append-only, ocho capturas |
| detail | 2.300 | 1.500 | atributos de la página, una fila por anuncio; **solo motos** |
| silver | 11.925 | 10.982 | grano (anuncio, precio pedido): un cambio de precio es fila nueva |
| gold | 11.691 | 10.972 | solo filas plausibles, una fila por anuncio |

Por vertical en gold: **7.639 carros** y **4.052 motos**, de las cuales 2.300 (**56,8 %**)
tienen detalle.

> Las 800 filas de detalle que faltaban aparecieron solas: la corrida de `enrich.yml` que
> seguía en vuelo cuando se detuvo el enriquecimiento terminó y publicó su Parquet en la
> rama `data`. `pull-history` lo trajo. **No se reanudó el raspado** —la decisión de parar
> sigue en pie—; esto es dato que ya estaba capturado y no costó una sola petición nueva.

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
| `model` | **31,6 %** | 16,8 % |
| `vehicle_age_years` | **25,5 %** | 9,6 % |
| `brand` | 12,9 % | **28,5 %** |
| `mileage_km` | 9,2 % | 7,7 % |
| `engine_cc` | 8,9 % | **61,7 %** |
| `city` | 1,9 % | 7,3 % |
| `km_per_year` | 1,9 % | 2,0 % |
| `department` | 0,3 % | 0,4 % |
| `is_official_store` | 0,1 % | 0,4 % |
| `is_quad` | — | 0,0 % |

(Medida sobre el lago completo del 2026-10-06. La versión anterior, sobre 10.972 filas y
1.500 motos enriquecidas, está en el historial de este documento; el orden no cambió.)

**El hallazgo: en motos el modelo pesa identidad y casi no pesa estado.** Marca, cilindrada
y modelo suman un tirón de 107 puntos; edad y kilometraje suman 17. En carros la relación
es la inversa —edad es el segundo factor (25,5 %) y el estado pesa 35 puntos—. Dicho de
otra forma, el modelo de motos funciona como un catálogo: sabe cuánto vale una Pulsar 180,
pero no cuánto descontarle por tener diez años y 60.000 km. Eso explica a la vez el MAPE y
los 94 % de ancho de banda: dentro de una celda (marca, cilindrada, modelo) le queda poca
información para separar un ejemplar barato de uno caro.

**El enriquecimiento reforzó el diagnóstico en vez de corregirlo.** Con la cilindrada
arreglada en 2.300 anuncios, `engine_cc` subió de 40,9 % a **61,7 %** de tirón típico: el
modelo ahora se apoya *más* en identidad, no menos. Es coherente —la cilindrada corregida
es una variable mejor, así que el modelo la usa más— y deja claro que la ruta para bajar de
24 % no es más identidad.

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

> **Qué pasó con esa extrapolación.** La cobertura subió a 56,8 % (2.300 de 4.052), no al
> 100 %, y la vertical completa quedó en **24,1 %** sobre el lago nuevo. No es comparable
> punto a punto —cambió el lago y con él el holdout— pero la dirección es la que la
> extrapolación anticipaba y la magnitud es más modesta. Las features nuevas **siguen
> apagadas por defecto**, así que esos 24,1 % son solo la cilindrada corregida; el −1,8 de
> las columnas nuevas sigue sin cobrarse en la vertical completa.

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

## Re-medición sobre el lago completo (final)

El 2026-10-06 se trajo el histórico entero de la rama `data` y se reconstruyó el lago:
gold pasó de 10.972 a **11.691** filas, y el detalle de motos de 1.500 a 2.300. Estas son
las cifras vigentes; las de la sección anterior quedan como registro de cómo se llegó aquí.

| Vertical | Modelo | CV MAPE | MAPE fuera | σ (log) | R² | Antes |
| --- | --- | --- | --- | --- | --- | --- |
| Carros | hedónico, edad + km + depto | — | 49,0 % | 0,567 | 0,309 | 48,8 % |
| Carros | hedónico, + marca/modelo/cc | — | 15,6 % | 0,215 | 0,901 | 15,3 % |
| Carros | **LightGBM** | 11,4 % | **11,3 %** | 0,171 | 0,937 | 11,5 % |
| Carros | CatBoost | 13,4 % | 13,1 % | 0,200 | 0,914 | 13,1 % |
| Motos | hedónico, edad + km + depto | — | 99,8 % | 0,978 | 0,093 | 101,0 % |
| Motos | hedónico, + marca/modelo/cc | — | **40,0 %** | 0,525 | 0,738 | 47,8 % |
| Motos | **LightGBM** | 24,0 % | 24,1 % | 0,377 | 0,865 | 26,7 % |
| Motos | CatBoost | 24,8 % | **23,6 %** | 0,364 | 0,875 | 26,8 % |

Holdouts de 1.528 y 810 filas, contra 1.441 y 753 antes.

Tres lecturas:

- **Carros mejoran levemente y siguen cumpliendo la meta** con 3,7 puntos de margen:
  11,5 % → 11,3 %, σ de 0,177 a 0,171. No se enriquecieron, así que la mejora viene solo
  de 432 filas más.
- **Motos bajan de 26,7 % a 24,1 %**, y la mayor parte no es el modelo: es la cilindrada
  corregida en 2.300 anuncios en vez de 1.500. El salto más grande está en la **línea base
  hedónica, que pasó de 47,8 % a 40,0 %** —casi ocho puntos— y eso solo puede venir de los
  datos, porque el modelo es el mismo. Sigue a 9 puntos de la meta.
- **CatBoost gana en motos por primera vez, y la evidencia se contradice a sí misma**:
  23,6 % contra 24,1 % en el holdout, pero 24,8 % contra 24,0 % en la CV. Cuando el orden
  se invierte según qué partición se mire, lo que hay es un empate, no un ganador. En
  carros no hay ambigüedad: LightGBM gana por 1,8 puntos en las dos. Ver la decisión abajo.

### La banda, y la regla que decide qué se publica

| Vertical | Cobertura | Ancho medio | Ensanche (log) | Cruzados | Etiqueta |
| --- | --- | --- | --- | --- | --- |
| Carros, antes (7.207) | 76,5 % | 38 % | +0,029 | 5,8 % | — |
| **Carros, ahora (7.639)** | **81,0 %** | **41 %** | +0,045 | 5,4 % | **se publica** |
| Motos, antes (3.012) | 76,8 % | 94 % | +0,061 | 8,4 % | — |
| **Motos, ahora (4.052)** | **83,6 %** | **84 %** | +0,104 | 12,0 % | **se retiene** |

**La regla es ahora código, no criterio.** `models.quantiles.label_policy` publica la
etiqueta ganga/justo/caro solo si la banda medida en el holdout cumple las dos cosas:

- **cobertura dentro de [78 %, 82 %]** — ventana de dos lados, no piso. Cubrir de menos
  dispara "ganga" en anuncios normales; cubrir de más mete en "justo" anuncios que de
  verdad están mal preciados, y la etiqueta deja de discriminar.
- **ancho medio ≤ 60 % del estimado.**

Carros pasan las dos. **Motos fallan las dos** —83,6 % de cobertura y 84 % de ancho—, así
que esa vertical se publica con **precio estimado, rango y un aviso de precisión**, sin
etiqueta. La vertical no se retira: un estimado con rango sigue siendo útil; lo que no se
puede sostener es la etiqueta.

**El déficit de cobertura no era lo que parecía.** Estaba documentado como deuda conocida
—76,5 % y 76,8 % contra un nominal de 80 %— con la hipótesis de que la conformalización
sufría por filas agrupadas por reposteo. Con más filas de calibración carros llegó a
81,0 % y motos a **83,6 %**, es decir **se pasó de largo**. Entonces ni "tamaño de muestra"
ni "agrupamiento" explican solos el comportamiento: con pocas filas la banda salía angosta
y con más sale ancha, que es lo que hace un ensanche conformal estimado sobre un residuo
de cola pesada. En motos, con un ensanche de +0,104 y 12 % de cuantiles cruzados, el
problema de fondo sigue siendo que los tres modelos cuantílicos no concuerdan sobre la
forma de la superficie de precios.

### CatBoost sale de `make train` por defecto, pero el caso ya no es limpio

**Ojo: la premisa con la que se pidió esta decisión —"si no gana en ninguna vertical"— ya
no se cumple exactamente.** CatBoost gana el holdout de motos por 0,5 puntos. Lo que pasa
es que pierde la CV de esa misma vertical por 0,8, y un orden que se invierte entre
particiones es ruido, no un ganador. En carros pierde por 1,8 puntos en las dos
particiones, que sí es consistente.

Se saca del camino por defecto igual, por tres razones y ninguna es "pierde siempre":

- **Cambiar de modelo servido en motos costaría la banda y la explicación.** `quantiles.py`
  y `explain.py` son solo-LightGBM. Servir CatBoost en motos exige escribir los tres
  modelos cuantílicos de CatBoost y su ruta de atribución —y motos es justamente la
  vertical cuyo rango sí se publica—, todo para una ventaja de 0,5 puntos que la CV
  contradice.
- **Cuesta más de la mitad de la corrida**: 46 minutos de los ~110 en carros y ~105 en
  motos. Un comando por defecto que se duplica en duración para reconfirmar un empate es un
  comando que se deja de correr.
- Sigue alcanzable con `--model catboost`, así que la comparación no se pierde; solo deja
  de pagarse en cada corrida.

Si en algún momento se quiere perseguir esos 0,5 puntos —por ejemplo si motos se acerca a
la meta y el margen empieza a importar—, lo correcto es **medirlo con el mismo presupuesto
de búsqueda** (40 trials para los dos) antes de mover nada. Detalle en
[ADR 0003](adr/0003-tree-model-validation.md).

---

## Resultados económicos (F3)

Estimados con el hedónico y errores robustos **HC3**, no con los ensambles. Un ensamble
predice bien y no dice cuánto vale un año; estas son preguntas de coeficiente con intervalo,
así que son de OLS. Tablas completas en [`docs/results/`](results/README.md), figuras en
`docs/figures/`, y todo se regenera con `make results`.

### Las motos casi no se deprecian con la edad

| Vertical | Marca | Depreciación anual | IC 95 % | Solo edad | ¿Distinguible de cero? |
| --- | --- | --- | --- | --- | --- |
| Carros | Volkswagen | 4,8 % | 1,3 – 8,2 | 4,3 % | sí |
| Carros | Kia | 5,2 % | 4,6 – 5,8 | 4,5 % | sí |
| Carros | Chevrolet | 5,2 % | 3,7 – 6,7 | 4,7 % | sí |
| Carros | Mazda | 5,3 % | 4,7 – 5,9 | 4,7 % | sí |
| Carros | Toyota (ref.) | 5,9 % | 5,2 – 6,5 | 5,2 % | sí |
| Carros | Renault | 6,1 % | 5,2 – 7,1 | 5,6 % | sí |
| Carros | Nissan | 7,2 % | 6,6 – 7,8 | 6,8 % | sí |
| Carros | BMW | 9,2 % | 8,0 – 10,4 | 8,8 % | sí |
| Carros | Mercedes-Benz | 9,2 % | 8,0 – 10,5 | 8,8 % | sí |
| Carros | Ford | **9,6 %** | 8,1 – 11,1 | 9,2 % | sí |
| Motos | Yamaha (ref.) | **0,9 %** | −0,7 – 2,4 | 0,2 % | **no** |
| Motos | Honda | 1,9 % | 0,9 – 2,9 | 1,4 % | sí |
| Motos | Suzuki | 2,1 % | 0,3 – 3,8 | 1,4 % | sí |
| Motos | BMW | 3,5 % | −0,1 – 7,0 | 3,0 % | **no** |
| Motos | KTM | 3,7 % | 2,3 – 5,0 | 2,9 % | sí |
| Motos | Bajaj | 6,5 % | 5,0 – 7,9 | 5,7 % | sí |

Se reportan **dos tasas** porque "depreciación anual" es ambiguo y la diferencia es real.
La regresión controla por kilometraje, así que el coeficiente de edad solo es el precio de
un año *con el uso congelado*. Un año también trae kilómetros y esos también se pagan: la
columna principal suma el efecto del kilometraje de un año típico de esa marca. Las dos
salen del mismo ajuste y el total es una combinación lineal con pesos fijos, así que su
intervalo es exacto y no una aproximación.

**El hallazgo:** una Yamaha pierde 0,9 % al año y el intervalo incluye el cero —estos datos
no la distinguen de no perder nada—, mientras una Bajaj pierde 6,5 %. En carros el rango va
de 4,8 % a 9,6 % y **la folk theory se sostiene**: japonesas y coreanas aguantan, las
premium alemanas y Ford caen al doble de velocidad.

Esto es **la misma conclusión que SHAP**, por una vía independiente. SHAP decía que el
modelo de motos pesa identidad y casi no pesa estado, y eso tenía dos lecturas que SHAP
sola no separa: que el estado de verdad importe poco, o que marca y modelo ya lo hubieran
absorbido. El hedónico pone la edad explícitamente, con la marca fija, y encuentra el mismo
efecto diminuto. **Sobrevive la primera lectura**: en motos la edad de verdad no mueve el
precio. Eso es un hecho del mercado, no una limitación del modelo, y explica por qué más
columnas de identidad no iban a ayudar.

La marca de referencia excluye el bucket de **marca desconocida** —en motos es el 19 % de
los títulos y sería la "marca" más grande de la vertical—. Sus filas siguen en la regresión
como control; lo que no se publica es una tasa para "desconocida".

### El kilometraje se cobra en proporción al valor, y abajo no se cobra

| Vertical | Segmento | Mediana de precio | Costo de 10.000 km | ¿Distinguible de cero? |
| --- | --- | --- | --- | --- |
| Carros | toda la vertical | 89,0 M | −216.000 | sí |
| Carros | Q1 | 51,9 M | −119.000 | sí |
| Carros | Q2 | 75,9 M | +1.000 | **no** |
| Carros | Q3 | 110,0 M | −126.000 | sí |
| Carros | Q4 | 198,9 M | −323.000 | sí |
| Motos | toda la vertical | 14,9 M | −81.000 | sí |
| Motos | Q1 | 6,9 M | +9.000 | **no** |
| Motos | Q2 | 11,1 M | −12.000 | **no** |
| Motos | Q3 | 18,4 M | −281.000 | sí |
| Motos | Q4 | 58,9 M | −322.000 | **no** |

El modelo lleva el kilometraje como `log1p(km)`, que es lo correcto —el efecto del uso es
proporcional— y es la unidad equivocada para una respuesta. La cifra en pesos se evalúa en
**la mediana del segmento**, y la tabla reporta esa mediana al lado: el número solo es
cierto cerca de ahí.

**Los segmentos se cortan por la clase de precio del vehículo** —la mediana de su marca y
modelo—, no por el precio del anuncio. Cortar por el precio pedido sería condicionar sobre
la variable dependiente: dentro de una franja estrecha, un anuncio con muchos kilómetros
tiene que estar compensado por otra cosa, y el coeficiente se aplasta contra cero por
construcción. Medido así, tres de los cuatro cuartiles de carros daban "el kilometraje no
se paga", que es un artefacto del corte y no un hecho del mercado. **Esta distinción se
descubrió comparando los dos cortes, no de entrada.**

Lo que queda después de arreglarlo: **en las motos baratas el kilometraje de verdad no se
paga** (Q1 y Q2 no se distinguen de cero), que es otra vez la historia del catálogo.

### Dónde está más caro el mismo vehículo

Contra Bogotá D.C., que es el departamento con más anuncios en las dos verticales, para un
vehículo comparable: mismo modelo, misma edad, mismo kilometraje, misma cilindrada.

| Vertical | Departamento | Diferencia | IC 95 % |
| --- | --- | --- | --- |
| Carros | Santander | **+8,6 %** | 5,6 – 11,7 |
| Carros | Antioquia | +7,1 % | 4,3 – 10,0 |
| Carros | Norte de Santander | +4,7 % | 1,9 – 7,7 |
| Carros | Valle del Cauca | +1,9 % | −0,3 – 4,1 |
| Carros | Cundinamarca | +0,8 % | −1,5 – 3,1 |
| Carros | Atlántico | +0,1 % | −2,2 – 2,5 |
| Motos | Antioquia | **+28,3 %** | 21,4 – 35,5 |
| Motos | Valle del Cauca | −6,0 % | −13,2 – 1,7 |
| Motos | Santander | −13,6 % | −22,8 – −3,3 |
| Motos | Cundinamarca | −17,5 % | −23,7 – −10,7 |
| Motos | Atlántico | −25,5 % | −38,7 – −9,5 |
| Motos | Quindío | **−31,3 %** | −44,7 – −14,7 |

En carros el rango completo es de 8,6 puntos; en motos es de **60**. Antioquia es el caso
llamativo: la misma moto se pide 28 % más cara allá que en Bogotá, con un intervalo que no
se acerca al cero.

Dos advertencias que viajan con estos números:

- **`department` no es un marco de muestreo limpio.** Las tarjetas patrocinadas se filtran
  entre regiones, así que esto describe dónde se *publica* el anuncio, que se parece a pero
  no es dónde está el mercado. Ya estaba en la deuda conocida; aquí es donde muerde.
- El bucket de departamento desconocido y el de departamentos con menos de 30 anuncios
  **siguen en la regresión como control pero no se reportan**. "Los anuncios cuyo
  departamento no parseó son 22 % más baratos" es una afirmación sobre el parser, no sobre
  un lugar de Colombia. Con esos buckets dentro, el rango de carros se veía de 30 puntos en
  vez de 8,6.

### Dónde se equivoca el modelo, y la sorpresa que eso destapó

MAPE del modelo servido sobre el holdout, abierto por marca. Lo que sigue es el resultado
más accionable de F3:

| Vertical | Segmento | n | MAPE | σ (log) |
| --- | --- | --- | --- | --- |
| Motos | **Desconocida** | 163 | **50,2 %** | 0,638 |
| Motos | Yamaha | 86 | 19,0 % | 0,342 |
| Motos | Suzuki | 69 | 18,6 % | 0,283 |
| Motos | Honda | 52 | 16,6 % | 0,251 |
| Motos | BMW | 80 | 15,7 % | 0,249 |
| Motos | **Bajaj** | 51 | **9,7 %** | 0,121 |
| Carros | Mercedes-Benz | 107 | 19,9 % | 0,294 |
| Carros | Toyota | 240 | 9,8 % | 0,133 |
| Carros | Mazda | 134 | 6,8 % | 0,105 |

**El 24,1 % de motos no se reparte parejo: está concentrado en los anuncios cuya marca no
se pudo extraer del título.** Ese bucket son 163 de las 810 filas del holdout (20,1 %, y
19,6 % de la vertical) y va en 50,2 % de MAPE. Las marcas que sí resuelven van entre 9,7 %
y 19,0 %, y **Bajaj ya cumple la meta de F2** con 9,7 %.

Haciendo la cuenta al revés: si el bucket desconocido se comportara como el resto, la
vertical estaría en **17,5 %**. Dicho de otro modo, **el problema de parseo del título vale
6,6 puntos de MAPE**, más que cualquier cosa que haya salido del modelado en toda F2.

Esto no contradice el diagnóstico de SHAP —dentro de las marcas conocidas sigue faltando
señal de estado para bajar de 17,5 % a 15 %— pero **cambia cuál es el siguiente trabajo**.
Era "conseguir señal de estado, que no está en la página de detalle"; ahora el primer
renglón es **resolver la marca en el 19,6 % de títulos que no la resuelven**, que es
trabajo de parseo sobre datos que ya están capturados, sin una sola petición nueva. El
semillero `vehicle_brands` y `stg_title_features` son donde se haría.

Dos cosas más del mismo corte:

- **En motos la dispersión por departamento es enorme**: Santander 35,2 % y Valle del Cauca
  34,5 % contra Bogotá 19,0 %. En carros el rango va de 7,8 % a 12,5 %.
- **En carros el peor segmento es Mercedes-Benz con 19,9 %**, el único por encima de la
  meta. Es coherente con que sea la marca con más dispersión de versión dentro del mismo
  modelo, que es justo lo que el título no trae.

### El contraste del catálogo, con número

| Vertical | SHAP: identidad | SHAP: estado | Razón | Hedónico: depreciación anual |
| --- | --- | --- | --- | --- |
| Carros | 57,4 % | 39,8 % | **1,4** | 8,3 % a los 5 años |
| Motos | 77,0 % | 16,1 % | **4,8** | 3,3 % a los 3 años |

Las dos columnas no miden lo mismo y el export lo dice: la de SHAP es importancia relativa
dentro de un modelo, la del hedónico es un coeficiente. Lo comparable es **el orden entre
verticales**, y ahí las dos coinciden: el modelo de motos se apoya 4,8 veces más en
identidad que en estado, y el hedónico encuentra que la edad de verdad mueve poco el precio
de una moto. La hipótesis alternativa —que marca y modelo ya hubieran absorbido la edad— no
sobrevive, porque el hedónico pone la edad explícitamente con la marca fija y sigue
encontrando 3,3 %.

---

## Lo que falta

### F2 — cerrada

Los cinco pasos estaban hechos desde el 2026-10-05; lo que faltaba era el criterio de
cierre, y se cerró decidiendo **qué se publica en cada vertical** en vez de esperar a que
motos llegue a 15 %:

- **Carros cumplen la meta** (11,3 % contra 15 %) y su banda pasa la regla, así que salen
  con estimado, rango y etiqueta.
- **Motos no llegan** (24,1 %) y su banda falla las dos condiciones, así que salen con
  estimado, rango y aviso de precisión, **sin etiqueta**. La regla está en el código y hay
  tests sobre los cuatro modos de fallo, así que no es una nota en un documento: si una
  corrida futura mejora la banda de motos, la etiqueta se enciende sola.
- **El modelo servido es LightGBM** en ambas verticales. CatBoost sale del camino por
  defecto.

Lo que **no** cierra F2 y pasa a F3 o F4: que motos llegue a 15 %. F3 encontró por dónde
empezar y no es el modelo — **el 19,6 % de títulos de moto cuya marca no se resuelve va en
50,2 % de MAPE y se lleva 6,6 puntos de la vertical**. Ver "Dónde se equivoca el modelo".

### F3 — Resultados

Hecho: **curvas de depreciación por marca** con intervalos, **efecto del kilometraje** por
vertical y segmento, **diferencias regionales**, **error por segmento** del modelo servido
y el **contraste del catálogo** (SHAP contra el hedónico). Todo en
`src/autovalor/analysis/`, exportado a [`docs/results/`](results/README.md) y graficado en
`docs/figures/`. El cuaderno `04_resultados_economicos` solo importa de `src`.

La separación con `models/` es deliberada: `models/` predice y se juzga por MAPE fuera de
muestra; `analysis/` explica y se juzga por si un efecto se distingue de cero. Por eso
`analysis/` usa OLS con errores robustos **HC3** —la dispersión de precios crece con el
precio, y los errores clásicos saldrían demasiado angostos— y no los ensambles, que
predicen bien y no dicen cuánto vale un año.

Falta: el **índice mensual de precios** y la **comparación con Fasecolda**, que queda fuera
de alcance (ver decisiones abiertas).

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

### 2. Fasecolda — fuera de alcance por ahora

`fasecolda.com/guia-de-valores/` es un shell de JS sin datos;
`guiadevalores.fasecolda.com` responde **403**. Su `robots.txt` no prohíbe nada, pero la
guía no se obtiene por HTTP simple. Nunca bloqueó F2 porque `valor_fasecolda` no es feature
del modelo —sería fuga—; solo era benchmark.

**Decisión: el benchmark queda documentado como fuera de alcance y no se busca una fuente
de pago.** La suscripción está descartada por la regla de costo cero, y sustituir Fasecolda
por otra tabla de referencia sería peor que no tener benchmark: el valor de comparar contra
Fasecolda es precisamente que es *la* referencia del mercado colombiano, y comparar contra
otra cosa respondería una pregunta que nadie hizo.

Queda abierto solo si aparece **un export manual** que consigas por tu cuenta. Mientras
tanto los resultados de F3 se publican diciendo que no hay comparación externa, en vez de
inventar una.

---

## Deuda conocida

- **`vehicle_age` está implementado dos veces**: `features/age.py` en Python y como SQL en
  `gold_listings`. Decidir la fuente de verdad antes de que divergan.
- **Docker nunca se ha construido ni corrido.** No hay docker en la máquina de desarrollo.
- **La captura semanal sigue construyendo silver y gold solo con su propia corrida**, no
  con el histórico acumulado. Eso basta para validar que la captura salió bien, pero el
  `gold_listings` del workflow no es el lago completo. `enrich.yml` ya hace lo correcto
  —`pull-history` antes de dbt— y ese es el patrón que el índice mensual de F3 tendrá que
  copiar si va a correr en CI. La captura semanal se dejó como está a propósito: volverla
  acumulativa cambia qué valida y qué sube como artefacto.
- **La rama `data` crece para siempre.** ~1 MB hoy con las 8 capturas más el detalle,
  ~25 MB al año. Quitar algo publicado por error exige reescribir la rama. Cuando empiece
  a apretar hay que **avisar, no migrar**: el proyecto corre a costo cero y pasar a
  almacenamiento de objetos exige aprobación explícita
  ([ADR 0004](adr/0004-capture-history-storage.md), y la sección "Costo cero" de
  `CLAUDE.md`). Podar el histórico o acotar lo que se captura son respuestas igual de
  válidas.
- **El detalle cubre 56,8 % de motos y 0 % de carros.** Por eso las features de
  detalle están **apagadas por defecto** en el modelo: encenderlas sobre la vertical
  completa le daría al modelo columnas nulas en cuatro de cada diez filas. Tienen sentido
  con `--only-enriched`, o cuando la cobertura sea alta. A 56,8 % ya está cerca del punto
  en que encenderlas vale la pena; medirlo es una tarea abierta, no una conclusión.
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
- **La validación temporal sigue sin poderse hacer, y ahora se sabe por cuánto.** Con el
  histórico completo el lago abarca **5,54 días** (2026-09-29 21:48 → 2026-10-05 10:49, en
  tres días distintos) contra los **14** que exige `MIN_TEMPORAL_SPAN_DAYS`, así que
  `--split temporal` sigue fallando a propósito. Faltan ~8 días, es decir **una o dos
  capturas semanales más**; llega solo. Conviene repetir la medición con `temporal` en ese
  momento, porque es la partición que exige el índice mensual de F3.
- **La cobertura de la banda ya no queda corta — ahora se pasa, y en motos lo bastante
  para costarle la etiqueta.** Era 76,5 % y 76,8 % contra el nominal de 80 %; con el lago
  completo es 81,0 % en carros y **83,6 % en motos**. La hipótesis vieja (filas no
  intercambiables por reposteo) no explica un cambio de signo. Lo que sí: el ensanche
  conformal se estima sobre el cuantil empírico de un residuo de cola pesada, y ese
  estimador es inestable en los dos sentidos según cuántas filas de calibración haya. El
  arreglo sigue siendo conformal consciente de grupos o calibración anidada, ahora con el
  objetivo de **estabilizar**, no de subir. **No** bajar el nivel hasta que el holdout
  cuadre: eso sería ajustar contra el holdout.
- **Los cuantiles se cruzan en 5,4 % de carros y 12,0 % de motos.** Se ordenan por fila, que
  es correcto, pero un cruce alto significa que los tres niveles no concuerdan sobre la
  forma de la superficie de precios. En motos subió de 8,4 % a 12,0 % y es la pista más
  concreta de por qué esa banda sigue midiendo 84 % de ancho. Ajustar los tres con un
  objetivo multicuantil, o con monotonicidad impuesta, es el siguiente intento.
- **La banda entrena con 25 % menos filas** que el modelo puntual, porque esa parte se
  aparta para calibrar. El modelo puntual no paga ese costo; la banda sí.
- **CatBoost se exploró con la mitad del presupuesto que LightGBM** (20 trials contra 40),
  porque cuesta de 3 a 9 veces más por ajuste. Que pierda es evidencia más débil que si
  hubiera perdido con el mismo presupuesto; tenerlo en cuenta antes de retirarlo.
- **El gráfico de barras de SHAP sigue sin estar**, pero ya no por la razón que decía esta
  nota. `matplotlib` quedó **declarado en `pyproject.toml`** para las figuras de F3: el
  bloqueo era regenerar `uv.lock` sin red, y **`uv lock --offline` lo resuelve** porque la
  versión ya estaba en el lock como dependencia transitiva de `shap`. El diff del lock son
  dos líneas. Dibujar la barra de SHAP es ahora trabajo pendiente, no un impedimento; el
  CSV y las métricas por variable en MLflow llevan la misma información mientras tanto.
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
.\make.ps1 test          # la suite completa con cobertura
.\make.ps1 lint          # ruff + mypy
.\make.ps1 transform     # valida bronze, corre dbt, valida silver y gold
.\make.ps1 train         # LightGBM y el hedónico, con banda; ~25 min
.\make.ps1 results       # los resultados económicos a docs/results y docs/figures
```

`train` ya **no corre CatBoost por defecto** (perdía en las dos verticales y costaba más
de la mitad del tiempo). Para la comparación: `--model catboost`.

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

**La re-medición está completa** y F2 cerrada; no hay nada a medias esperando. Lo que
sigue es F3: queda el índice mensual (implementado, no publicable hasta ~2027-03) y la
comparación con Fasecolda (bloqueada).

Para seguir enriqueciendo motos —**detenido por decisión, no reanudar sin que lo pidan**—
el camino preferido es GitHub Actions: es gratis, no
depende de una máquina encendida y ya trae el histórico por sí solo. Lanza
`Enrich motorcycle details` desde la pestaña Actions con el presupuesto que quieras
(~15 páginas/min, así que 800 son ~55 min). El workflow pide el histórico, reconstruye
gold, enriquece y publica.

En local, si hace falta:

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

**Ojo con los números al reconstruir.** El lago local ya está sincronizado con la rama: 8
capturas de bronze y los dos Parquet de detalle, 11.691 filas de gold, que es donde se
midió todo lo de arriba. La próxima captura semanal lo hará crecer otra vez, y entonces
**las métricas hay que volver a medirlas** —no son constantes del proyecto, son medidas
sobre un lago con fecha—. El `manifest.json` de `docs/results/` existe justamente para que
una cifra publicada diga sobre cuántas filas se tomó.

Si de verdad hace falta raspar de nuevo:

```powershell
$env:AUTOVALOR_USE_SYSTEM_CERTS = 'true'
.\make.ps1 scrape -Pages 25   # ~35 min, seis departamentos, ambas verticales
.\make.ps1 transform
```
