# Estado del proyecto / Project status

Última actualización: **2026-10-25** · Fase actual: **F4**, con la API y el sitio
desplegados en Render, y el rediseño del frontend en curso sobre el modelo reentrenado. F2 y F3 cerradas salvo el índice de precios, que espera histórico;
la comparación con Fasecolda quedó **fuera de alcance**. (Carros cumplen la meta de
MAPE ≤ 15 % y publican etiqueta; motos publican precio y rango sin etiqueta, por la regla
de calidad de banda.)

Este documento es el punto de retorno: dice qué funciona, qué falta, qué está decidido y
qué no. Se actualiza al cerrar cada bloque de trabajo.

---

## Resumen en una línea

El pipeline completo funciona de punta a punta —captura → bronze → silver → gold,
validado— con **8.443 carros y 4.505 motos**, y las capturas ya no se pierden: viven en la
rama `data`. Tres modelos entrenados y medidos **fuera de muestra**: el mejor es LightGBM
con **10,3 % MAPE en carros** y **22,0 % en motos** (con 2.812 motos enriquecidas, 62,4 %
de la vertical, y la marca resuelta en 91,9 % de los títulos tras el arreglo de parseo y la
limpieza del catálogo: eran 24,1 % con 80,4 %). Sobre una partición temporal, que se mide
al lado y nunca reemplaza a la publicada, son 11,6 % y 23,5 %. Carros cumple la meta de
F2 (≤ 15 %); motos no. **F2 queda cerrada** con
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

> **Hay dos capturas nuevas en la rama `data` que todavía no están medidas.** La captura
> semanal corrió sola el **2026-10-12** (2.880 carros y 2.228 motos crudos, 264 KB) y el
> **2026-10-19** (576 carros y 426 motos, 71 KB), y las publicó en la rama. **No se han
> traído al lago local a propósito**: el modelo que está en `artifacts/models/` se entrenó
> sobre las 11.691 filas de gold de abajo, y todas las cifras de este documento son de ese
> lago. Traerlas cambia el lago, el holdout y por tanto todos los números — es el trabajo
> de volver a medir, no un paso de higiene. Con ellas la rama va en **10 capturas**.
>
> Dos cosas que conviene mirar cuando se haga: la corrida del 2026-10-19 trajo una quinta
> parte de lo que trajo la del 2026-10-12, que puede ser el sitio o puede ser la corrida, y
> no se ha averiguado; y el lago ya abarcaría ~20 días de `last_seen_at`, por encima de los
> 14 que exige `--split temporal`, así que esa partición pasa a ser posible por primera vez.

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
| Carros | 99,2 % | 86,0 % | 47 | 507 |
| Motos | **87,6 %** | 80,6 % | 33 | 821 |

La marca de motos era 80,4 % hasta el 2026-10-06, cuando el mapa modelo → marca del seed
subió 290 anuncios. Ver [Resolver la marca de las motos](#resolver-la-marca-de-las-motos).

### La limpieza del catálogo (2026-10-21)

Hecha **sin una sola petición nueva**: todo sale de títulos ya capturados. El motivo es de
producto —los desplegables del formulario mostraban la basura del token `model`— pero el
efecto llega al modelo, porque `brand` y `model` son sus dos features de más peso.

Las reglas son **por tipo de vehículo**, y eso no es un detalle de implementación: `1.6` es
cilindrada en un carro y nada en una moto, mientras que un número pelado **sí** es un modelo
de moto (KTM 390, BMW 1200) y nunca uno de carro. Una regla única borraría el catálogo de
KTM o dejaría las cilindradas de Mazda como modelos.

| | Carros | Motos |
| --- | --- | --- |
| Anuncios en gold | 7.639 | 4.052 → **4.041** |
| Sin marca resolver | 62 (0,8 %) | 504 (12,4 %) |
| Sin marca resolver, después | **1** | **329 (8,1 %)** |
| Marca resuelta | 99,2 % → **99,99 %** | 87,6 % → **91,9 %** |
| Marcas en el catálogo | 47 → **70** | 33 → **43** |
| Tokens de modelo | 507 → **534** | 821 → **767** |

Los tokens de carros **suben** a propósito: `clase` era un solo nivel con 405 de los 481
Mercedes-Benz dentro, y ahora son `clase c`, `clase gle`, `clase glc`, `clase gla`… Es el
cambio más probable detrás del peor segmento de carros (Mercedes-Benz, 19,9 % de MAPE, el
único por encima de la meta), y se mide en el Paso 0b.

Cuatro piezas, todas en dbt y con sus mapas versionados como seeds:

- **`vehicle_brands` gana una columna `brand_rank`.** 0 es fabricante, 1 es distribuidor
  que además vende otras marcas con su nombre (AKT, Victory, y Auteco, que ahora apunta a
  Victory en vez de ser una marca propia). Un fabricante le gana a un distribuidor, así que
  "Akt Voge Ds300" es una Voge y "Auteco Kymco Twist" una Kymco; el distribuidor sigue
  ganando todos los títulos donde no se nombra otra marca, así que no pierde su catálogo.
  **Es la única excepción deliberada a la aditividad** y tiene test propio.
- **`model_tokens`** (331 filas) lista los tokens que nunca son un modelo, con qué hacer al
  encontrarlos. `drop` salta el token y sigue —el verbo del vendedor, el estado, los
  papeles, el color, el tipo de moto, la dirección del concesionario—; sin esto el modelo de
  un título que nombraba su marca era la primera palabra que apareciera, que en "Vendo
  Suzuki Agility 125" era "vendo". `join` se queda con el token y le pega el siguiente,
  porque la palabra sola nombra una familia: "Clase", "Serie", "Land", "Model".
- **`model_aliases`** (96 filas) deja una sola escritura por modelo. `v-strom` llegaba en
  cinco grafías, `nmax` en seis, `himalayan` en tres.
- **`colombian_departments`** normaliza el nombre contra un slug sin tildes ni mayúsculas,
  así que "Valle Del Cauca" pasa a "Valle del Cauca" y una grafía que nadie ha capturado
  todavía también resuelve. Los 32 departamentos están en el seed, no solo los capturados.
  La API acepta las dos formas y normaliza (`api.features.resolve_department`), porque el
  sitio y el servicio no se despliegan a la vez.

Dos arreglos que solo aparecieron al medir, y los dos valían cientos de filas:

- **La marca se quita del texto como alias completo y de mayor a menor longitud.** Quitar
  primero el alias corto se come el delimitador que el largo necesitaba: dejaba "benz" como
  modelo de los 481 Mercedes-Benz y "am" en 40 Can-Am. Con el orden invertido, desaparecen.
- **Quitar solo el nombre canónico no bastaba.** Los 77 Citroën tenían "citroën" como
  modelo, porque el título lo escribe con diéresis y la marca canónica no.

Lo que sale y lo que se marca:

| | Filas | Qué se hizo |
| --- | --- | --- |
| Bicicletas, bicimotos, patinetas | 11 | fuera de gold, `invalid_reason = 'not_a_motor_vehicle'` |
| Cuatrimotos, buggies, side-by-sides | 123 | `is_quad`, como antes (+ `cuatriciclo` al patrón) |
| Motocarros, cargueros, tricargos | 15 | `is_cargo`, columna y feature nuevos |

`is_cargo` es feature solo de motos, igual que `is_quad`. Son 15 filas: está para que la
población sea separable, no porque se espere que mueva el MAPE.

El nombre de presentación no se guarda dos veces. `features/naming.py` lo deriva con una
regla —sigla arriba, palabra con mayúscula inicial, nombre con guion por segmentos— y
`catalog.json` lo publica resuelto por marca, modelo y departamento, así que el desplegable
y la tarjeta de `/explain` escriben "CX-30" igual. La regla no alcanza para "bZ4X" ni para
distinguir "Rio" de "RZR", y esas dos listas están en el módulo, medidas contra el lago.

**Lo que sigue sucio y no se tocó**: en BMW y Yamaha el token de modelo es solo la primera
palabra, así que "BMW R 1250 GS" sale como `r` (91 anuncios), y hay `f` (53), `g` (40) y
`mt` (40). Es la limitación de siempre —`split_part(..., ' ', 1)`—, no algo que la limpieza
haya introducido, y arreglarla cambia los niveles dominantes de dos marcas grandes, así que
es una decisión aparte y no un paso de higiene.

### El reentrenamiento del 2026-10-25

Entran tres cosas a la vez: las capturas del 12 y el 19 de octubre, el enriquecimiento de
las motos que esas capturas trajeron, y la limpieza del catálogo de arriba. **Estas son las
cifras vigentes**; las de [Re-medición sobre el lago completo](#re-medición-sobre-el-lago-completo-final)
quedan como registro.

| | Carros | Motos |
| --- | --- | --- |
| Anuncios en gold | 7.639 → **8.443** | 4.041 → **4.505** |
| Con detalle | — | 2.300 → **2.812 (62,4 %)** |
| Marca sin resolver | 1 (0,01 %) | 389 (8,63 %) |
| Marcas / modelos | 70 / 546 | 44 / 830 |

El enriquecimiento se corrió con `enrich.yml` sobre la rama del paso, con
`first_seen_after=2026-10-12`, que es lo que evita gastar el presupuesto en las motos viejas
cuyo enriquecimiento está detenido por decisión. Candidatos 517, en dos corridas de 500 y
17: **las 570 motos que gold ve por primera vez el 12 o el 19 tienen fila de detalle**. Lo
que sigue sin detalle son las viejas.

#### Lo que aporta la limpieza y lo que aportan los datos

Se midió aparte, entrenando primero el lago viejo con la limpieza puesta. La ventana para
hacerlo era única: después de `pull-history` ya no se puede separar.

| | Publicado | Solo limpieza | Lago completo |
| --- | --- | --- | --- |
| Carros, MAPE | 11,3 % | 10,8 % | **10,3 %** |
| Carros, referencia OLS | — | 14,1 % | **12,9 %** |
| Motos, MAPE | 22,4 % | 22,7 % | **22,0 %** |
| Motos, referencia OLS | — | 38,4 % | **34,6 %** |

**En carros el punto de mejora se reparte mitad y mitad**: medio punto la limpieza, medio
los 804 anuncios nuevos. **En motos la limpieza sola empeora** (22,7 % contra 22,4 %) y toda
la mejora viene de los datos; lo que la limpieza aporta en esa vertical es la marca resuelta
—87,6 % → 91,9 %—, que es producto y no MAPE.

Donde la limpieza se ve con claridad es en el peor segmento de carros: **Mercedes-Benz pasa
de 19,9 % a 15,3 %** de MAPE, que es la hipótesis que la sección anterior dejó anotada
—partir `clase` en `clase c`, `clase gle`, `clase glc`— confirmada contra el holdout.

#### La banda y la etiqueta

| | Cobertura | Ancho medio | Ensanche | Cruzados | Etiqueta |
| --- | --- | --- | --- | --- | --- |
| Carros, antes (7.639) | 81,0 % | 41 % | +0,045 | 5,4 % | se publica |
| **Carros, ahora (8.443)** | **80,0 %** | **40 %** | +0,037 | 6,9 % | **se publica** |
| Motos, antes (4.052) | 81,6 % | 81 % | +0,090 | 9,3 % | se retiene |
| **Motos, ahora (4.505)** | **79,4 %** | **84 %** | +0,052 | 8,2 % | **se retiene** |

**La cobertura de motos entra en la ventana por primera vez** (79,4 %, dentro de
[78 %, 82 %]), así que la etiqueta pasa a fallar por **un solo** criterio, el ancho, en vez
de los dos. Ningún umbral se tocó.

**El ancho de motos empeora 2,6 puntos y eso tiene una explicación medida.** La corrida
intermedia —lago viejo, limpieza puesta— marcó 65 % de ancho, que parecía justo la mejora
que la etiqueta necesita, pero venía con los cuantiles **cruzados en 33,2 % de las filas de
calibración** contra un histórico de 9,3 %: bandas crudas estrechas, un ensanche que
sobrecorregía en calibración (+0,114) y que aun así se quedaba corto en test (cobertura
77,6 %). Sobre el lago completo el cruce vuelve a 8,2 %, el ensanche baja a +0,052 y la
cobertura cae dentro de la ventana. **Aquel 65 % no era una mejora, era el síntoma de un
ajuste cuantílico inestable**, y exportarlo habría publicado un ancho que no se sostiene. El
ancho honesto de motos está entre 81 % y 84 %, lejos del 60 % que pide la regla.

#### La validación temporal, por primera vez

El lago abarca **19,5 días** de `last_seen_at`, por encima de los 14 que exige
`--split temporal`, así que `export.py` la mide al lado de la aleatoria. **No reemplaza
nada**: el modelo servido se sigue ajustando sobre la partición aleatoria agrupada, que es
la de todas las cifras publicadas.

| | Aleatoria agrupada | Temporal | Diferencia |
| --- | --- | --- | --- |
| Carros, MAPE | 10,3 % | **11,6 %** | +1,3 pt |
| Carros, APE mediano | 7,0 % | 7,6 % | +0,6 pt |
| Motos, MAPE | 22,0 % | **23,5 %** | +1,5 pt |
| Motos, APE mediano | 10,5 % | 13,0 % | +2,5 pt |

Las dos verticales empeoran entre 1,3 y 1,5 puntos, que es la dirección esperada: la
partición aleatoria le deja al modelo vehículos contemporáneos de los que tiene que
predecir, y la temporal no. La brecha es la respuesta honesta a "cuánto se degrada esto en
una semana" y es pequeña, lo que dice que el modelo no vive de memorizar el momento de
mercado.

**Dos salvedades sobre esta partición, y la segunda importa.** La primera es que el corte
que el log imprime (`temporal split of car at 2026-09-30…`) es el mínimo de `last_seen_at`
de las **filas** de test, no el del grupo: un vehículo reposteado arrastra sus filas viejas
al lado de test, así que el valor impreso no es el corte real. La segunda es que
`last_seen_at` solo toma **cinco valores**, uno por captura:

| Última vez visto | Carros | Motos |
| --- | --- | --- |
| 2026-09-29 | 20 | 65 |
| 2026-09-30 | 4.634 | 1.674 |
| 2026-10-05 | 744 | 477 |
| 2026-10-12 | 2.470 | 1.864 |
| 2026-10-19 | 575 | 425 |

Un holdout del 20 % no cae en una frontera de fecha: en carros son 1.690 filas, así que
toma las 575 vistas por última vez el 19 y **1.115 de las 2.470 del 12**, dejando las otras
1.355 de esa misma fecha en entrenamiento. El empate se rompe por orden de ordenamiento, que
es determinista pero arbitrario. Así que esto mide "el quinto visto más recientemente", no
"entrena en el pasado y prueba en el futuro". Con más capturas la frontera se vuelve
nítida; un corte limpio hoy —test = todo lo visto por última vez el 19— dejaría holdouts de
575 y 425 filas, y es **decisión abierta** porque cambia el tamaño del test, no algo que se
deba cambiar de paso.

#### Lo que `model.json` publica ahora

Cuatro grupos de campos nuevos, todos aditivos (formato 2; `load_bundle` sigue leyendo
formato 1, así que el servicio desplegado sirve su bundle sin cambios):

- **`metrics.baseline_mape`**: la referencia OLS ajustada en la misma partición. "LightGBM
  reduce el error N puntos" pasa a ser una resta de dos cifras publicadas: **2,6 puntos en
  carros** (12,9 → 10,3) y **12,5 en motos** (34,6 → 22,0).
- **`interval.uncalibrated_coverage`**: lo que cubren los tres modelos cuantílicos antes del
  ensanche conformal, **66,3 % en carros y 66,1 % en motos** contra un nominal de 80 %. La
  cifra que circulaba como "67 % y 63 %" en prosa ahora sale del artefacto.
- **`metrics_temporal`**: la tabla de arriba. `null` cuando el lago es demasiado joven para
  la partición, que no debe impedir un export.
- **`label.failure_codes`**: los fallos de la regla como `{code, value, limit, message}` —hoy
  `width_above_max` con 0,838 contra 0,60 en motos—, para que la página los escriba en
  español. `label.failures` conserva su texto exacto por compatibilidad.

Versión del bundle: **2026-10-25.12948**.

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
gold pasó de 10.972 a **11.691** filas, y el detalle de motos de 1.500 a 2.300.

> **Superada por [el reentrenamiento del 2026-10-25](#el-reentrenamiento-del-2026-10-25)**,
> que suma las capturas del 12 y el 19 de octubre y la limpieza del catálogo: carros
> 11,3 % → 10,3 % y motos 22,4 % → 22,0 %. Esta sección queda como registro de cómo se
> llegó aquí, y es la referencia contra la que se mide el efecto de la limpieza.

| Vertical | Modelo | CV MAPE | MAPE fuera | σ (log) | R² | Antes |
| --- | --- | --- | --- | --- | --- | --- |
| Carros | hedónico, edad + km + depto | — | 49,0 % | 0,567 | 0,309 | 48,8 % |
| Carros | hedónico, + marca/modelo/cc | — | 15,6 % | 0,215 | 0,901 | 15,3 % |
| Carros | **LightGBM** | 11,4 % | **11,3 %** | 0,171 | 0,937 | 11,5 % |
| Carros | CatBoost | 13,4 % | 13,1 % | 0,200 | 0,914 | 13,1 % |
| Motos | hedónico, edad + km + depto | — | 99,8 % | 0,978 | 0,093 | 101,0 % |
| Motos | hedónico, + marca/modelo/cc | — | **40,0 %** | 0,525 | 0,738 | 47,8 % |
| Motos | **LightGBM** | 23,2 % | **22,4 %** | 0,355 | 0,880 | 24,1 % |
| Motos | CatBoost | 24,8 % | 23,6 % | 0,364 | 0,875 | 26,8 % |

> La fila de motos es del 2026-10-06 **después** de resolver la marca; la de CatBoost es de
> antes, sobre 80,4 % de marcas resueltas en vez de 87,6 %, así que ya no son comparables
> entre sí. Con los datos viejos CatBoost ganaba el holdout por 0,5 puntos; con los nuevos
> LightGBM va 1,2 puntos adelante de ese número sin que CatBoost se haya vuelto a medir.

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
etiqueta. (Con el lago del 2026-10-25 motos ya cumple la cobertura y falla solo el ancho;
la decisión no cambia.) La vertical no se retira: un estimado con rango sigue siendo útil; lo que no se
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

**El 24,1 % de motos no se repartía parejo: estaba concentrado en los anuncios cuya marca
no se pudo extraer del título.** Ese bucket eran 163 de las 810 filas del holdout (20,1 %,
y 19,6 % de la vertical) y iba en 50,2 % de MAPE. Las marcas que sí resuelven van entre
9,7 % y 19,0 %, y **Bajaj ya cumple la meta de F2** con 9,7 %.

(Esta tabla es la medición que *motivó* el arreglo de parseo y se deja como estaba. Con la
marca resuelta en 87,6 % de los títulos, la vertical bajó a 22,4 % — ver más abajo.)

Haciendo la cuenta al revés: si el bucket desconocido se comportara como el resto, la
vertical estaría en **17,5 %**. Dicho de otro modo, **el problema de parseo del título vale
6,6 puntos de MAPE**, más que cualquier cosa que haya salido del modelado en toda F2.

Esto no contradice el diagnóstico de SHAP —dentro de las marcas conocidas sigue faltando
señal de estado para bajar de 17,5 % a 15 %— pero **cambió cuál era el siguiente trabajo**.
Era "conseguir señal de estado, que no está en la página de detalle"; pasó a ser **resolver
la marca en el 19,6 % de títulos que no la resuelven**, sobre datos ya capturados y sin una
sola petición nueva. Eso es lo que hace la sección siguiente.

### Resolver la marca de las motos

Hecho el 2026-10-06, **sin una sola petición nueva**: todo sale de títulos ya capturados.

El análisis de los 794 títulos sin marca encontró tres patrones:

- **El nombre del modelo sin la marca** — "Xtz 150", "Hunk 150", "Agility Go". Es el grueso.
- **Una marca que faltaba en el seed**: `PLR`, importador de cuatrimotos, con 53 anuncios.
- **Ruido que no es vehículo**: la dirección del concesionario ("Potenza Cali Norte Avenida
  6 #24-37"), el estado ("Excelente Estado", "Papeles Al Día"), o el prefijo "Moto" /
  "Cuatrimoto" / "Motocicleta" con el que abre uno de cada seis títulos.

El arreglo tiene tres piezas y la primera es la que lo vuelve seguro:

1. **`vehicle_brands` gana una columna `alias_kind`** (`brand` o `model`) y
   `stg_title_features` ordena los candidatos poniendo las marcas por encima de los
   modelos. Sin esto, "Vendo **Suzuki** **Agility** 125" se habría vuelto una Kymco, porque
   el alias de modelo es más largo que el de marca. Con esto, **un alias de modelo solo
   puede dispararse en un título donde no se encontró ninguna marca**, así que agregarlos es
   estrictamente aditivo: ningún anuncio que ya resolvía puede cambiar.
2. **48 aliases de modelo → marca**, elegidos por medición y no por intuición. Un candidato
   entró solo si, entre los títulos que *ya* resolvían, el token aparece con una marca y
   prácticamente ninguna otra: `gs` es BMW en 261 de 265, así que entra; `mt` es Yamaha en
   solo 58 % y `xr` en 78 %, así que quedan fuera. `raptor` también queda fuera, porque es
   a la vez una Yamaha y una cuatrimoto PLR. La regla vieja de "nada de aliases de dos
   letras" se reemplazó por esta prueba de concentración, que es evidencia en vez de miedo.
3. **El nombre del vertical sale del token de modelo** antes de extraerlo, y cuando la marca
   se resolvió *a través* de un nombre de modelo, ese nombre **es** el modelo —no hay que
   adivinarlo—.

Resultado, mismo lago, misma semilla, misma partición:

| | Antes | Después |
| --- | --- | --- |
| Títulos de moto con marca | 80,4 % | **87,6 %** (+290 anuncios) |
| Anuncios cuya marca *cambió* | — | **0** |
| Modelo de moto que era la palabra "moto" | 250 | **1** |
| Hedónico completo | 40,0 % | **38,4 %** |
| LightGBM CV | 24,0 % | **23,2 %** |
| **LightGBM fuera de muestra** | **24,1 %** | **22,4 %** |
| σ (log) | 0,377 | 0,355 |
| R² | 0,865 | 0,880 |
| Cuantiles cruzados | 12,0 % | 9,3 % |

**−1,7 puntos de MAPE por parseo.** Los carros no se movieron: 0 de 7.639 anuncios
cambiaron de marca o de modelo, que es lo que el diseño prometía.

Que la línea base hedónica haya bajado 1,6 puntos con el mismo modelo es la confirmación de
que esto fueron datos y no modelado: el estimador es idéntico, lo único que cambió es lo
que se le da de comer.

**La etiqueta sigue apagada, pero por una condición en vez de dos.** La banda pasó de
83,6 % de cobertura a **81,6 %, que ya está dentro de la ventana [78 %, 82 %]**. Lo que
falta es el ancho: 81 % del estimado contra el máximo de 60 %. El gate lo dice solo y con
precisión —"mean width 81 % of the estimate, above 60 %"—, así que cuando el ancho ceda, la
etiqueta se enciende sin que nadie toque un umbral.

**Lo que queda del bucket desconocido es más difícil, no menos**, y eso es la confirmación
de que el parseo ya dio lo que tenía que dar:

| Marca (holdout) | Antes | Después |
| --- | --- | --- |
| Desconocida | 163 filas, 50,2 % | **109 filas, 55,5 %** |
| Yamaha | 86, 19,0 % | 96, 19,6 % |
| Honda | 52, 16,6 % | 55, 18,0 % |
| BMW | 80, 15,7 % | 81, 15,4 % |
| Suzuki | 69, 18,6 % | 76, **15,2 %** |
| Bajaj | 51, 9,7 % | 53, **9,5 %** |

El bucket encogió un tercio y su MAPE *subió* cinco puntos: los anuncios que se podían
resolver leyendo el título eran justamente los fáciles —los que al menos nombraban un
modelo—, y los que quedan son los que de verdad no dicen qué vehículo son ("Excelente
Estado Papeles Al Día", la dirección de un concesionario). **Esos ya no se arreglan
parseando**; necesitarían la página de detalle, que es justo lo que está detenido por
decisión. La ruta para los 7,4 puntos que faltan hasta la meta vuelve a ser la que SHAP
señaló: señal de estado.

Dos cosas más del corte por segmento:

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
- **Motos no llegan** (22,4 %) y su banda falla **una** de las dos condiciones —el ancho,
  81 % contra 60 %; la cobertura ya entró en la ventana—, así que salen con estimado, rango
  y aviso de precisión, **sin etiqueta**. La regla está en el código y hay tests sobre los
  cuatro modos de fallo, así que no es una nota en un documento: cuando el ancho ceda, la
  etiqueta se enciende sola.
- **El modelo servido es LightGBM** en ambas verticales. CatBoost sale del camino por
  defecto.

Lo que **no** cierra F2 y pasa a F3 o F4: que motos llegue a 15 %. F3 encontró por dónde
empezar y no era el modelo —el bucket de marca sin resolver iba en 50,2 % de MAPE—, y
arreglarlo valió **1,7 puntos** (24,1 % → 22,4 %). Quedan 7,4 para la meta, y el siguiente
obstáculo vuelve a ser el que SHAP señaló: falta señal de estado. Ver
[Resolver la marca de las motos](#resolver-la-marca-de-las-motos).

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

Falta publicar el **índice mensual de precios** —implementado, probado y deliberadamente
sin correr, ver abajo— y la **comparación con Fasecolda**, que queda fuera de alcance (ver
decisiones abiertas).

#### El índice de precios está hecho y no se publica hasta ~2027-03-29

`autovalor.analysis.price_index` implementa el índice hedónico con **efectos fijos de
periodo**: una regresión de `log(precio)` sobre los atributos del vehículo más una dummy por
mes, de forma que lo que se mide es el precio de un vehículo de **calidad constante** y no
el de la mezcla. Esa distinción es el punto entero: una mediana de precios sube cuando el
mes trae más camionetas y menos hatchbacks, y eso no es inflación de usados.

Se deflacta con el IPC del DANE, y **las dos cifras se reportan**. Un índice de usados que
sube 6 % en un año donde todo subió 7 % describe un mercado que se abarató en términos
reales; publicar solo el "+6 %" invertiría el hallazgo.

**Está probado sobre datos sintéticos con una tendencia plantada**, que es la única forma de
validar un índice cuando todavía no hay histórico: los tests le plantan un 2 % mensual y
verifican que lo recupera, que un mercado plano da un índice plano, que deflactar por la
misma tendencia deja el índice real en 100, y que un periodo sin IPC queda en nulo en vez de
asumir uno.

**No corre sobre datos reales, a propósito.** `check_publishable` exige
`MIN_INDEX_SPAN_DAYS = 180` y el lago abarca 5,5 días. Son 180 y no los 14 de la partición
temporal porque son preguntas distintas: una partición solo tiene que separar pasado de
futuro, mientras que un índice describe una **trayectoria**, y dos o tres puntos no
distinguen una tendencia del ruido de dos semanas concretas. La primera captura es del
**2026-09-30**, así que con la captura semanal corriendo sola el índice tiene sentido desde
**~2027-03-29**. El error lo dice con esa fecha calculada, no con un "faltan datos", y
`make results` lo anota en el campo `skipped` del manifiesto en vez de fallar.

Lo que hay que conseguir a mano para entonces: **la serie del IPC del DANE**, en
`data/reference/ipc_dane.csv` con columnas `period,cpi`. Es pública y gratuita —no viola la
regla de costo cero— pero no está en una URL estable que una máquina pueda leer. **No se
inventaron valores** para dejar el archivo completo: cualquier cifra real que dependiera de
ellos heredaría números que nadie puede verificar. Sin el archivo el índice nominal igual
funciona y el real queda indefinido, que es lo correcto.

### F4 — Producto: la API está desplegada, el frontend está en curso

| Entregable | Estado |
| --- | --- |
| `POST /predict` — precio, banda P10–P90, etiqueta o aviso, versión del modelo | hecho |
| `POST /explain` — los 5 factores principales, con nombres legibles ES/EN | hecho |
| `GET /catalog` — marcas, modelos por marca, departamentos y rangos del modelo servido | hecho |
| `GET /market` — sirve los JSON de `docs/results` para el dashboard | hecho |
| `GET /health` y `GET /model-info` reales | hecho |
| `models/bundle.py` + `make export-model` — el modelo servido, sin MLflow | hecho |
| `Dockerfile.api` multi-stage con solo el runtime | hecho, **construido y arrancado en CI** |
| `render.yaml` + [pasos de despliegue](deploy-render.md) | hecho; **desplegado y probado por el usuario el 2026-10-07** |
| Tests de contrato de los endpoints | hecho |
| App Next.js: export estático, ES/EN, tres vistas | hecho; **falta que el usuario la despliegue** |
| `autovalor-web` en `render.yaml` + CI de frontend | hecho |

#### El frontend

Next.js (App Router) + TypeScript + Tailwind v4 en `frontend/`, **export estático**
(`output: "export"`), que es lo único que cabe gratis en Render. Español por defecto con
cambio a inglés —un diccionario de pares `{es, en}`, de modo que una cadena sin traducir no
compila—, y el idioma se lee de `localStorage` con `useSyncExternalStore` en vez de un
efecto, así que el HTML prerenderizado sale en español por construcción y no parpadea al
hidratar.

Tres decisiones que vale la pena no deshacer:

- **Mercado y Metodología no llaman a la API.** Leen `docs/results/` y los `model.json` de
  los bundles **en tiempo de construcción**. Son archivos commiteados: pedirlos por HTTP
  costaría un minuto de arranque en frío para números que ya están en el repositorio, y
  además así la página no puede citar una cifra distinta a la del commit del que salió. El
  costo es que el sitio es tan fresco como su último despliegue, que es correcto porque
  `make results` y `make export-model` son commits y un commit redespliega.
- **El formulario se construye desde `/catalog`.** Es el motivo por el que ese endpoint
  existe; ver arriba.
- **Los gráficos son HTML/CSS y SVG escritos a mano**, sin librería de charts. El intervalo
  de confianza no es decoración —un efecto que cruza el cero significa otra cosa— y los
  números van impresos como texto al lado de cada barra, así que la figura se lee con un
  lector de pantalla sin tabla alternativa.

Verificado con Playwright contra la API local: las tres vistas, el camino de carros (con
etiqueta) y el de motos (con aviso y sin etiqueta), el cambio de idioma, cero errores de
consola y cero desbordamiento horizontal a 390 px. Las capturas de `docs/screenshots/`
salieron de esa misma corrida. Dos cosas que encontró y que no se habrían visto leyendo el
código: un `step` en los campos numéricos hacía que el navegador rechazara en silencio
precios como 78.000.000 —la validación nativa bloquea el submit antes de que corra el
`onSubmit`—, y el `min-width` de un gráfico estiraba su columna del grid y hacía scrollear
la página entera en móvil.

#### Los tres arreglos que salieron de probar el servicio desplegado

**1. `AUTOVALOR_CORS_ALLOW_ORIGINS` no aceptaba la forma en que se escribe.** Es una lista,
y pydantic-settings decodifica los tipos compuestos como JSON y nada más, así que
`https://a,https://b` —la forma que invita la caja de variables de un dashboard— no
arrancaba el servicio: fallaba en el import. Ahora el campo lleva `NoDecode` y un
`field_validator` que acepta las dos formas, y lo que lo mantiene arreglado no es el
validador sino dos tests: uno carga `Settings` **con exactamente las envVars de
render.yaml**, leídas del blueprint por `autovalor.deploy`, y otro recorre
`Settings.model_fields` y falla si aparece otro campo de tipo colección sin validador. El
problema de fondo era que **nada en el repositorio leía `render.yaml`**, así que un valor
que rompía la configuración solo se descubría en la plataforma.

**2. `/predict` y `/explain` publicaban dos precios distintos para el mismo vehículo.**
`/predict` centraba su banda en el modelo cuantílico P50 y `/explain` reportaba el modelo
puntual. Gana el puntual, y no por sorteo: es el modelo cuyo MAPE es el publicado (11,3 % y
22,4 %) y el que SHAP atribuye, así que `base × factores = estimado` se cumple exacto. La
exactitud del P50 nunca se midió. Los límites siguen siendo la banda conformalizada, y si
el estimado puntual cae fuera de ella la banda se ensancha hasta contenerlo —publicar un
rango que excluya el número que va al lado sería incoherente en su propia cara—.
`ServedModel.predict_published_band` es ahora el único sitio donde se decide "el precio", y
un test exige igualdad **exacta** entre los dos endpoints: una tolerancia dejaría que los
dos modelos se separaran otra vez.

**3. `PORT` en vez de `AUTOVALOR_API_PORT`.** El `CMD` de la imagen le pasa `--port 8000` a
uvicorn de forma literal y no lee el entorno; `AUTOVALOR_API_PORT` solo alimentaba
`make serve`, así que la variable que estaba en el blueprint no hacía nada y su comentario
decía lo contrario. `PORT=8000` es lo que le dice a Render dónde sondear, y hay un test que
lo ata al `--port` del Dockerfile.

Y el paso de CI que las tres cosas necesitaban: el job de Docker ya no solo construye y
arranca la imagen, la **arranca con el `--env-file` sacado de `render.yaml`** y verifica que
`/health` responda `ok` con los dos modelos cargados y que `/catalog` traiga las dos
verticales con marcas. "200 y algo de JSON" no era la afirmación que valía la pena medir:
un contenedor sin artefactos responde 200 `degraded` por diseño, que es justo el despliegue
roto que este paso existe para atrapar.

#### `/catalog`, y por qué los listados viven dentro del bundle

El formulario no puede ser texto libre: los árboles se ajustaron con **niveles categóricos
congelados**, así que una marca que el modelo nunca vio cae fuera de sus categorías, baja
por la rama de faltante y produce un estimado que se ve igual de confiado que uno real. Así
que las listas se derivan **de las filas con las que se entrenó el modelo servido**, en el
mismo `make export-model`, y viajan en `artifacts/models/<vertical>/catalog.json` (42 KB
carros, 69 KB motos). Esa es la propiedad que vale: el catálogo no puede describir una
población distinta a la del modelo, porque sale del mismo frame en la misma corrida.

Hoy publica 47 marcas / 487 tokens de modelo / 10 departamentos en carros, y 33 / 855 / 9
en motos, cada entrada con su conteo de anuncios —el frontend decide si ordena por
popularidad o esconde los tokens raros; esa decisión no es de la API—. Nada se filtra: un
nivel raro sigue siendo un nivel que el modelo conoce, y quitarlo volvería un vehículo
legítimo imposible de consultar. El `catalog.json` de los dos bundles ya commiteados se
generó sin reentrenar, reconstruyendo la misma partición (mismo lago, misma semilla) y
**rechazando escribir si el `n_train` reconstruido no coincidía con el que registra el
manifiesto**, que es lo que prueba que son las filas del modelo y no de un split nuevo.

**El modelo servido viaja dentro de la imagen**, en `artifacts/models/`, no se descarga al
arrancar. Son los cuatro boosters de LightGBM por vertical —el puntual y los tres
cuantílicos— en el volcado de texto de la propia librería, más un JSON con el `FeatureSpec`,
los niveles de categoría congelados, el ensanche conformal, la decisión de etiqueta y la
huella del lago. **Nada de pickle**: un pickle ata el artefacto a la versión exacta de la
librería que lo escribió y ejecuta código arbitrario al cargarse.

Gzipeados porque un volcado de LightGBM es texto repetitivo y comprime ~3:1: **47 MB → 16 MB**,
que es lo que se commitea y lo que entra en la imagen. Un test compara la predicción del
modelo cargado contra la del modelo en memoria y exige igualdad a 1e-12: si el round-trip
no es exacto, el modelo servido no es el que mide el MAPE publicado.

**De dónde salen los 512 MB.** `pyproject.toml` quedó partido: `dependencies` es lo que la
API necesita (pandas, numpy, lightgbm, fastapi, uvicorn, pydantic) y el resto se fue a
grupos `ingest` / `transform` / `train` / `analysis` / `dev`, que `uv sync` **sigue
instalando por defecto** vía `[tool.uv] default-groups`, así que ni el desarrollo ni CI
cambian. Solo `Dockerfile.api` pide `--no-default-groups`.

La pieza que más pesaba era inesperada: **`/explain` ya no importa `shap`**. Los valores
SHAP salen de `pred_contrib` de LightGBM, que *es* el mismo algoritmo TreeSHAP implementado
dentro de la librería, y eso saca shap, numba y llvmlite de la imagen. Un test los compara
numéricamente y exige igualdad a 1e-9, así que es una decisión de empaquetado y no de
matemática.

**Memoria medida**, con los dos modelos cargados y 250 peticiones encima:

| | RSS |
| --- | --- |
| Intérprete vacío | 15 MB |
| Tras importar la app (pandas + lightgbm + fastapi) | 185 MB |
| Tras cargar los dos bundles | 237 MB |
| Tras 200 `/predict` y 50 `/explain` | **240 MB** |

Estable —2,8 MB en 250 peticiones, sin fuga— y con holgura sobre los 512 MB del plan
gratuito. **Es RSS del proceso, no del contenedor**: esta máquina no tiene Docker, así que
el tamaño de la imagen se mide en CI, donde el job `api image builds` lo publica como
anotación —legible desde la API de checks sin token, a diferencia del resumen del job—,
falla por encima de 900 MB y además arranca el contenedor para comprobar que `/health` y
`/model-info` responden de verdad.

**Imagen: 779 MB en disco.** Los dos números miden cosas distintas y los dos importan: los
779 MB son capas en disco —el sistema base, el intérprete, las ruedas de pandas/LightGBM y
los 16 MB de modelo— y lo que Render limita a 512 MB es la **memoria**, que son los 240 MB
medidos. El techo de 900 MB en CI es para que el disco no crezca sin que nadie lo note, no
porque 900 sea un límite de la plataforma.

**La imagen no arrancaba, y el motivo es la lección del bloque.** Construía bien y el
contenedor se moría en el `import`: partir las dependencias dejó fuera `duckdb` y
`scikit-learn`, que la ruta de servicio importaba *a nivel de módulo* sin usarlos —
`dataset.py` importaba DuckDB para una sola función, y `FeatureSpec`, que es un dataclass de
strings, vivía en `hedonic.py`, que importa scikit-learn—. Nada de eso se ve en el
desarrollo, donde todo está instalado. El arreglo fue hacer el `import duckdb` perezoso y
mover `FeatureSpec` a `models/spec.py`; `tests/api/test_runtime_dependencies.py` ahora
importa la ruta de servicio con esos paquetes **bloqueados**, y además verifica que la lista
de bloqueados coincida con los grupos de `pyproject.toml` —lo que inmediatamente encontró
dos que se me habían pasado—.

Antes de eso creí que el problema era `libgomp1`, que el `python:3.12-slim` no trae y
LightGBM necesita. Resultó ser un segundo fallo real, latente desde F0 en el `Dockerfile`
original: CI **construía** la imagen y nunca la arrancaba, así que un contenedor que no
podía importar nada se veía idéntico a uno que nadie había pedido arrancar. Las dos cosas
están arregladas y el paso de CI que levanta el contenedor y pega a `/health` es lo que las
destapó.

Dos cosas que conviene saber antes de tocar esto:

- **`api/features.py` deriva `vehicle_age_years` y `km_per_year` igual que `gold_listings`**,
  con el mismo piso en cero y el mismo divisor en uno. Es la tercera copia de esa lógica
  (ya estaba duplicada entre `features/age.py` y el SQL) y está así para no meter dbt y
  DuckDB en una imagen con presupuesto; el test es lo que mantiene honestas a las tres.
- **La decisión de etiqueta viaja dentro del bundle.** `/predict` no la vuelve a calcular:
  si lo hiciera, tendría que re-derivar el gate en tiempo de petición a partir de números
  que la API no tiene.

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

- **`vehicle_age` está implementado tres veces**: `features/age.py`, el SQL de
  `gold_listings` y ahora `api/features.py`, que tiene que derivarlo sin dbt dentro de la
  imagen. Hay test que las ata, pero sigue siendo una fuente de verdad pendiente.
- **Docker sigue sin existir en la máquina de desarrollo**, pero ya no es un punto ciego:
  CI construye `Dockerfile.api`, imprime el tamaño, falla por encima de 900 MB y
  **arranca el contenedor** para comprobar que `/health` y `/model-info` responden. Eso
  es lo que destapó dos fallos que llevaban desde F0 sin verse.
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
- **La validación temporal ya es posible, pero sobre un lago que todavía no se ha
  reconstruido.** El lago medido abarca **5,54 días** (2026-09-29 21:48 → 2026-10-05 10:49)
  contra los **14** que exige `MIN_TEMPORAL_SPAN_DAYS`, así que `--split temporal` falla hoy
  a propósito. Las dos capturas semanales que faltaban **ya llegaron solas** —2026-10-12 y
  2026-10-19, en la rama `data`—, de modo que un `pull-history` llevaría el span a ~20 días.
  Conviene repetir la medición con `temporal` cuando se haga, porque es la partición que
  exige el índice mensual de F3.
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

### Dónde quedó esto el 2026-10-25

La API y el sitio están desplegados en Render y verificados. El trabajo en curso es el
**rediseño del frontend**, que arrancó con dos pasos de datos ya hechos: la limpieza del
catálogo y el reentrenamiento de arriba. El bundle publicado es **2026-10-25.12948**, con
las capturas del 12 y el 19 de octubre dentro.

**Lo que sigue:**

1. **Desplegar el modelo nuevo: la API primero, el sitio después.** El bundle vive dentro
   de la imagen, así que la API necesita un deploy para servirlo; el sitio lee
   `model.json` y `docs/results/` en tiempo de construcción, así que su deploy es el que
   publica las cifras nuevas. En ese orden no hay ventana en la que la página cite una
   cifra que el servicio no está sirviendo. Pasos en [`deploy-render.md`](deploy-render.md);
   el despliegue no se automatiza desde aquí.
2. **El rediseño del sitio**, página por página, sobre las cifras ya exportadas.
3. **Opcional, de producto**: el índice mensual cuando haya histórico (~2027-03-29), y que
   motos bajen de 22,0 %, que sigue siendo señal de estado y no más identidad.

Lo que **no** está hecho y no es un olvido: el índice mensual de precios (espera a
~2027-03-29 por histórico), la comparación con Fasecolda (fuera de alcance por decisión) y
que motos lleguen a 15 % (faltan 7 puntos y la ruta es señal de estado, no más identidad).

**Decisión abierta que dejó el reentrenamiento**: si la partición temporal debe cortar por
fecha en vez de tomar el quinto más reciente, lo que hoy repartiría el mismo día de captura
entre entrenamiento y test. Ver la salvedad en
[la validación temporal](#la-validación-temporal-por-primera-vez).

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

Estado de la rama hoy: **10 capturas, ~1,3 MB** —las ocho medidas más 2026-10-12 y
2026-10-19, que el lago local **no** tiene—, dos commits de backfill. Solo viaja bronze;
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
