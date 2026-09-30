# Estado del proyecto / Project status

Última actualización: **2026-09-30** · Fase actual: **F1 cerrada, F2 sin empezar**

Este documento es el punto de retorno: dice qué funciona, qué falta, qué está decidido y
qué no. Se actualiza al cerrar cada bloque de trabajo.

---

## Resumen en una línea

El pipeline completo funciona de punta a punta —captura → bronze → silver → gold,
validado— con 7.207 carros y 3.765 motos listos para modelar. **No hay ningún modelo
entrenado todavía.**

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
  departamentos, valida y sube el resultado como artefacto.

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

---

## Lo que falta

### F2 — Modelación (siguiente)

Nada empezado. `src/autovalor/models/` solo tiene el `__init__.py`.

1. **Partición y métricas honestas.** Split train/test con validación temporal
   (`captured_at` existe, y el índice mensual exige que el modelo no vea el futuro).
   Define el número contra el que se compara todo lo demás.
2. **Hedónico OLS como línea base**, en `models/train.py`, registrado en MLflow.
3. **LightGBM y CatBoost con Optuna**, modelos separados por vertical, target
   `log(precio)`. Criterio: deben superar al hedónico en MAPE. Meta **MAPE ≤ 15 %**.
4. **Intervalos P10–P90.** Requisito de producto, no un extra: la clasificación
   ganga/justo/caro depende de dónde cae el precio pedido. Sale de regresión cuantílica,
   no de la desviación del error.
5. **SHAP**, para `/explain`.

### F3 — Resultados

Métricas por segmento, curvas de depreciación, índice mensual, comparación con Fasecolda
(bloqueada, ver abajo).

### F4 — Producto

`/predict` y `/explain` (hoy solo existen `/health` y un `/model-info` stub), app Next.js
—**nada del frontend está creado**—, Docker probado, despliegue en Render.

---

## Dónde quedó el modelo base (y por qué no es un resultado)

**Todos los σ y MAPE medidos hasta ahora son en muestra**: un OLS ajustado y evaluado
sobre las mismas filas. Fuera de muestra serán peores. No citar como rendimiento logrado.

| Vertical | Features | σ (log) | R² | MAPE en muestra |
| --- | --- | --- | --- | --- |
| Carros | edad + km + depto | 0,580 | 0,331 | 55,9 % |
| Carros | + marca + modelo + cc | **0,244** | 0,885 | 17,5 % |
| Motos | edad + km + depto | 0,970 | 0,104 | 113,8 % |
| Motos | + marca + modelo + cc | **0,541** | 0,730 | 43,7 % |

Detalle completo en [`f1-pilot.md`](f1-pilot.md).

### Las dos lecciones que orientan F2

**El volumen por sí solo no compró nada.** Pasar de 1.468 a 7.207 carros dejó σ
prácticamente igual (0,578 → 0,580) con el feature set débil. Lo que compró el volumen
fue que los dummies de modelo se volvieran estimables: marca+modelo da σ 0,252 con 7.200
filas contra 0,352 con 1.468. Volumen y features se necesitan mutuamente.

**Las motos son el problema abierto**, por tres razones en orden de tamaño: falta la
versión y pesa más que en carros; el 19 % de títulos no resuelve marca (contra 0,8 % en
carros); y el token `model` es más ruidoso (764 valores distintos para 3.765 anuncios).

---

## Decisiones abiertas (del usuario, no mías)

### 1. Páginas de detalle

Lo que falta para acercarse a la meta —versión, transmisión, combustible, carrocería,
puertas— está en la página de cada anuncio como tabla estructurada, a **una petición
extra por anuncio**. Con las pausas educadas son ~4 h para los 11.000 actuales. Convierte
el workflow semanal de minutos en horas.

Recomendación: pasada incremental con presupuesto por corrida, enriqueciendo solo
anuncios sin detalle, en vez de un barrido monolítico. Y decidirlo **después** del paso 1
de F2, con números fuera de muestra en la mano: los carros podrían cumplir sin esto.

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
- **Las capturas expiran.** Los artefactos de Actions se retienen 90 días; el paso a
  almacenamiento de objetos está en [ADR 0002](adr/0002-weekly-capture-storage.md) y ese
  plazo es una fecha límite real.
- **Cuatrimotos, buggies y side-by-sides** viven en la vertical de motos (121 anuncios).
  Marcados con `is_quad` para que F2 los segmente, no eliminados.
- **Las tarjetas patrocinadas se filtran entre regiones**, así que `department` no es un
  marco de muestreo limpio.
- **GitHub desactiva los workflows programados** tras 60 días sin actividad en el repo.

---

## Cómo retomar

```powershell
# El entorno local tiene tres particularidades, ver docs/ y .env.example:
#  1. uv no está en el PATH: %APPDATA%\Python\Python312\Scripts\uv.exe
#  2. la red intercepta TLS: uv necesita --system-certs, y el scraping
#     necesita AUTOVALOR_USE_SYSTEM_CERTS=true
#  3. no hay make ni docker en Windows: usar .\make.ps1
.\make.ps1 test          # 83 tests, cobertura 96 %
.\make.ps1 lint          # ruff + mypy
.\make.ps1 transform     # valida bronze, corre dbt, valida silver y gold
```

Los datos de `data/` no están en git. Si el lago está vacío, se reconstruye con:

```powershell
$env:AUTOVALOR_USE_SYSTEM_CERTS = 'true'
.\make.ps1 scrape -Pages 25   # ~35 min, seis departamentos, ambas verticales
.\make.ps1 transform
```
