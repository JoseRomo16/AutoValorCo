# El rediseño del sitio / The site redesign

Documento de trabajo del rediseño pedido el **2026-10-25**: limpiar los datos que alimentan
el sitio, reentrenar una vez y reescribir las tres páginas sobre el paquete de diseño de
[`docs/design/`](design/). Existe porque el trabajo son siete pasos con revisión entre cada
uno, y el diagnóstico del Paso 1 es la entrada de los Pasos 4 y 5: sin escribirlo, cada
sesión lo vuelve a derivar.

El prompt completo es la fuente de verdad del alcance. Esto registra **en qué estado está
cada paso, qué se midió y qué decisiones quedaron abiertas**.

## Estado de los pasos

| Paso | Qué es | Estado | Dónde |
| --- | --- | --- | --- |
| 0a | Limpieza del catálogo | **cerrado** | PR [#15](https://github.com/JoseRomo16/AutoValorCo/pull/15), en `main` |
| 0b | Capturas nuevas, reentrenamiento y `model.json` ampliado | **cerrado** | PR [#16](https://github.com/JoseRomo16/AutoValorCo/pull/16), en `main` |
| — | Los cuatro datos del lago que faltaba exportar | **cerrado** | rama `feat/lake-facts` |
| 1 | Diagnóstico de las tres páginas | **cerrado** | este documento, abajo |
| 2 | Copy completo de `i18n.ts`, ES y EN | **cerrado** | rama `feat/web-copy` |
| 3 | Pendientes de API y documentación | **sin empezar** | — |
| 4 | Fundaciones: tokens, fuentes, tema, header y footer | **sin empezar** | — |
| 5 | Las tres páginas | **sin empezar** | — |
| 6 | Verificación: capturas, Lighthouse, lint y pruebas | **sin empezar** | — |

Las ramas se apilan linealmente, así que `git merge --ff-only` integra en orden.

## Lo que midieron los pasos 0a y 0b

El detalle está en [`STATUS.md`](STATUS.md): la limpieza del catálogo (2026-10-21) y el
reentrenamiento (2026-10-25). En una línea: carros **11,3 % → 10,3 %** de error medio,
motos **22,4 % → 22,0 %**, y la cobertura de la banda de motos entra en la ventana del gate
por primera vez (79,4 %), así que la etiqueta pasa a fallar por un solo criterio en vez de
dos. Ningún umbral se tocó.

## Paso 1 — el diagnóstico

Verificado leyendo los 14 archivos de `frontend/` contra los datos ya reentrenados. De los
34 hallazgos del prompt, **27 se confirmaron, 4 se corrigieron y 3 ya estaban resueltos**
por los pasos de datos. El Paso 2 cerró varios; lo que sigue abierto es trabajo de los
Pasos 4 y 5.

### Lo que el Paso 2 ya resolvió

| Hallazgo | Cómo quedó |
| --- | --- |
| Cifras escritas a mano (9 de 14 ya falsas) | Cada cifra sale de `model.json`, `catalog.json` o `docs/results/` por plantilla con `{hueco}`; `fill` lanza si falta un valor |
| Versión críptica `2026-10-25.12948` | `modelDate()` la vuelve "Modelo del 25 de oct de 2026" |
| Porcentajes partidos entre líneas | Espacio de no separación en `percent`, `points`, `copMillions`, `kilometres` |
| Aviso de precisión en inglés en la versión ES | Se escribe desde `precision_codes`, con reserva sin cifras si la API desplegada es la vieja |
| "Lectura económica:" repetido siete veces | El texto empieza por el hallazgo; la etiqueta visual es del Paso 5 |
| `MAX_CURVES = 5` tomaba las cinco primeras del archivo | Ahora la que más conserva, la que menos y la de referencia |
| Aviso de arranque en frío abriendo la página | Solo aparece pasados ~5 s; el estado va junto al botón |
| "89 M" sin unidad legible | `copMillions` → "$ 89 millones" / "COP 89M" |
| `segment_error.json` sin lector | `results.ts` lo lee; Metodología nombra el peor segmento medido |
| Datos de `model.json` sin usar | `results.ts` expone doce campos más, incluida la partición temporal |

### Lo que sigue pendiente, con archivo

Todo esto es maquetación o interacción, es decir Pasos 4 y 5.

| # | Hallazgo | Archivo |
| --- | --- | --- |
| 1 | Aspecto de plantilla: paleta slate + emerald, fuente del sistema, `max-w-5xl` en todo | `app/globals.css`, `app/layout.tsx` |
| 2 | Sin interruptor de tema: el oscuro solo sigue al sistema | `app/globals.css`, `components/SiteChrome.tsx` |
| 3 | 61 pares `text-slate-… dark:text-slate-…` y cero tokens | nueve componentes |
| 4 | Header no sticky, y en móvil la navegación salta a una segunda línea | `components/SiteChrome.tsx` |
| 5 | Footer sin autoría, sin fecha de datos y sin enlace a metodología | `components/SiteChrome.tsx` |
| 6 | Título con raya, sin imagen Open Graph, `PageIntro` como componente cliente | `app/layout.tsx`, `components/PageIntro.tsx` |
| 7 | Formulario como pared de siete campos iguales, sin agrupar | `components/ValuationForm.tsx` |
| 8 | Marca y modelo son `<select>` nativos, sin búsqueda | `components/ValuationForm.tsx` |
| 9 | Kilometraje y precio pedido sin separador de miles mientras se escribe | `components/ValuationForm.tsx` |
| 10 | Sin validación en línea: el navegador bloquea el envío sin explicar | `components/ValuationForm.tsx` |
| 11 | Sin estado vacío diseñado antes de la primera valoración | `components/ValuationForm.tsx` |
| 12 | Sin enlace compartible de una valoración | `components/ValuationForm.tsx` |
| 13 | La barra del rango usa degradado verde→ámbar aunque no haya etiqueta | `components/PriceResult.tsx` |
| 14 | El rango no tiene el mismo peso visual que el estimado | `components/PriceResult.tsx` |
| 15 | Mercado sin tarjetas de hallazgos arriba | `components/MarketDashboard.tsx` |
| 16 | Carros y motos como bloques seguidos en vez de pestañas con la elección recordada | `components/MarketDashboard.tsx` |
| 17 | La depreciación se pinta en verde, que en el resto del sitio significa "ganga" | `components/charts/IntervalBars.tsx` |
| 18 | Eje de las curvas de 0 a 100 %, leyenda en vez de etiqueta al final | `components/charts/RetainedCurves.tsx` |
| 19 | Etiquetas de barra truncadas en móvil y columna de 10 rem desperdiciada | `components/charts/IntervalBars.tsx` |
| 20 | Metodología sin índice lateral sticky | `components/Methodology.tsx` |
| 21 | Términos técnicos sin definición a mano (el copy ya tiene `copy.terms`, nadie lo usa) | `components/Methodology.tsx` |
| 22 | Sin diagrama SVG del flujo (hoy es una lista numerada) | `components/Methodology.tsx` |
| 23 | Sin gráficas de calibración, de referencia OLS ni de error por marca | `components/Methodology.tsx` |
| 24 | Comillas de Markdown visibles: el copy ya no las trae, pero conviene revisarlo renderizado | — |

### Las cuatro correcciones al prompt

1. **La versión del modelo aparece en tres sitios, no en cuatro.** Mercado nunca la mostró:
   imprimía `generated_at` (`MarketDashboard.tsx`).
2. **La fecha del índice no salía de `manifest.skipped`.** Estaba teclada en `i18n.ts`; el
   manifiesto la tenía dentro de una frase en inglés. Ahora es `skipped_codes.ready_on`.
3. **El "botón con la sigla ADR" era el texto de la cadena**, no el componente.
4. **Los números de línea del prompt para `MAX_CURVES`** apuntaban al uso (108), no a la
   constante (41).

### Los departamentos de poca base, con número

El prompt pedía decidir entre agrupar o avisar. Los datos para decidirlo, de `catalog.json`:

| | Carros | Motos |
| --- | --- | --- |
| Departamentos ofrecidos | 10 | 9 |
| Con menos de 50 anuncios | Cauca 1, Meta 2, Quindío 12 | Cauca 3, Norte de Santander 31, Quindío 41 |

**Sigue pendiente de decidir** (Paso 5). Con tres de diez departamentos por debajo de 50
anuncios en carros, agruparlos al final con un encabezado y mostrar el aviso de menor
precisión al elegirlos es lo que menos miente; el copy ya tiene
`form.departmentLowData` y `form.departmentLowDataHint` para las dos mitades.

### La basura del catálogo se concentró, no desapareció

La limpieza del Paso 0a dejó **cero** palabras de anuncio bajo marcas reales de motos y
cero cilindradas bajo marcas de carros, medido contra los dos `catalog.json`. Lo que queda
está todo bajo **"Desconocida"**, que sigue ofreciéndose como marca: carros 1 anuncio, motos
309 con 185 tokens de modelo como `0`, `08`, `2027-09`, `110CC`. **Excluir esa única opción
del desplegable elimina los 185 de golpe**, y es la red de seguridad del Paso 5.

Residuos de cola larga que la limpieza no atrapa, por si alguna vez vale otra corrida de
seeds: AKT trae `dynanic` (1 anuncio, grafía no mapeada de `dynamic`) y `motocarro` y
`carguero` como modelos, que son las filas de `is_cargo`. Son 3 anuncios.

## Decisiones abiertas

1. **Los umbrales del gate en el copy.** `78 %`, `82 %` y `60 %` siguen escritos en
   `i18n.ts` (`method.rule.coverageTitle` y `method.rule.widthTitle`). No son una medición
   que se desactualice: son la regla, y el prompt prohíbe moverla. `model.json` publica el
   límite solo cuando una vertical falla (`limit: 0.60`), así que la ventana de cobertura no
   existe como dato cuando se cumple. Exportar los tres desde `models/quantiles.py` es
   posible y costaría re-exportar el modelo. **Pendiente de decisión del usuario.**
2. **La partición temporal.** Hoy toma el quinto de anuncios visto más recientemente, lo que
   reparte una misma captura entre entrenamiento y evaluación porque `last_seen_at` solo
   toma cuatro valores. Cortar por fecha dejaría holdouts de 575 y 425 filas. Ver
   [`STATUS.md`](STATUS.md#la-validación-temporal-por-primera-vez).
3. **Los departamentos de poca base**, arriba.

## Lo que no se vuelve a litigar

- **La regla de la etiqueta no se toca**, ni umbrales ni excepciones. Motos publica precio y
  rango sin calificar porque el ancho mide 84 % contra un techo de 60 %.
- **Un ancho de motos cerca de 65 % es sospechoso**, no una mejora: apareció una vez con los
  cuantiles cruzados en 33,2 % de las filas de calibración contra 8,2 % normales, es decir un
  ajuste inestable. El ancho honesto está entre 81 % y 84 %.
- **Mercado y Metodología leen archivos del repositorio en tiempo de construcción**, nunca
  por HTTP. Solo el formulario llama a la API.
- **Ninguna cifra se escribe en un componente ni en `i18n.ts`.** Si un número no existe en un
  archivo, se exporta desde Python.
- **Los cambios en las respuestas de la API son aditivos**, y el sitio funciona contra la API
  vieja y la nueva.

## Cómo verificar lo hecho

```powershell
.\make.ps1 web-lint     # ESLint + tsc
.\make.ps1 web-build    # export estático a frontend/out
.\make.ps1 lint         # ruff + mypy
.\make.ps1 test         # pytest con cobertura
```

Para comprobar que ninguna cifra quedó como plantilla sin rellenar, sobre el HTML ya
construido:

```powershell
Select-String -Path frontend/out/*/index.html -Pattern '\{[a-zA-Z]+\}'
```

## El despliegue sigue pendiente

El modelo reentrenado está en `main` y **no está desplegado**. El orden importa: **la API
primero, el sitio después.** El bundle vive dentro de la imagen, así que la API necesita un
despliegue para servirlo; el sitio lee `model.json` y `docs/results/` en tiempo de
construcción, así que su despliegue es el que publica las cifras. En ese orden no hay
ventana en la que la página cite una cifra que el servicio no está sirviendo. Pasos en
[`deploy-render.md`](deploy-render.md); lo hace el usuario.

Tras desplegar la API: que `/model-info` devuelva `version: "2026-10-25.12948"` y los campos
nuevos (`baseline_mape`, `interval_uncalibrated_coverage`, `metrics_temporal`,
`label_withheld_codes`), y que una moto siga devolviendo `label: null` con su aviso.
