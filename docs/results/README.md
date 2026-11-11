# Resultados económicos exportados

Estos archivos son la salida de `make results` (`autovalor.analysis.cli`). Están
versionados a propósito: la app de F4 los lee como datos y no vuelve a estimar nada —un
sitio estático de Next.js no corre statsmodels, y el plan gratuito de Render no está para
ajustar regresiones por petición—.

Cada tabla se escribe en dos formatos desde el mismo DataFrame, así que no pueden
divergir: **JSON** para la app y **CSV** para un cuaderno o una hoja de cálculo.

| Archivo | Qué contiene |
| --- | --- |
| `depreciation_by_brand` | Tasa anual de depreciación por marca, con intervalo de confianza, vida media y la tasa que congela el kilometraje |
| `retained_value_by_age` | Porcentaje del valor que conserva cada marca a 1, 3, 5 y 10 años |
| `mileage_effect` | Lo que cuestan 10.000 km, por vertical y por segmento de precio, en pesos y en porcentaje |
| `regional_effect` | Diferencia de precio por departamento para un vehículo comparable |
| `segment_error` | MAPE del modelo servido por marca, segmento de precio y departamento, sobre el holdout |
| `catalogue_contrast` | El contraste identidad/estado de SHAP frente a la depreciación del hedónico |
| `price_index` | Índice hedónico mensual de calidad constante — **no se publica: fuera de alcance**, ver abajo |
| `manifest.json` | Sobre qué lago se midió todo: filas, cobertura de detalle, span de capturas, umbrales vigentes y lo que la corrida **no** pudo producir |

**Lee `manifest.json` antes de citar una cifra.** Un número sin saber sobre cuántas filas
se midió no se puede comparar con el siguiente. Su campo `skipped` dice qué análisis no se
pudo producir y por qué: un resultado ausente y un resultado que nadie pidió se ven igual
en un directorio, y no son lo mismo.

## Convenciones

- Los porcentajes son multiplicativos, no aditivos: salen de `exp(β) − 1`. Una
  depreciación de 5,9 % anual significa que el precio queda en 94,1 % del año anterior.
- `significant` es si el intervalo del 95 % excluye el cero. Una fila con `significant`
  en falso **no** es un efecto pequeño: es un efecto que estos datos no distinguen de cero.
- Los valores faltantes son `null` en JSON, nunca `NaN` —que no es JSON válido—.
- Los flotantes vienen redondeados a cuatro decimales para que los diffs del repositorio
  sean legibles.

## El IPC del DANE no está aquí, y el índice tampoco

El índice de precios (`autovalor.analysis.price_index`) deflacta con el IPC del DANE, que es
público y gratuito pero no se publica en una URL estable que una máquina pueda leer.
Inventar valores para dejar el archivo completo sería peor que no tenerlo: toda cifra real
que dependiera de ellos heredaría números que nadie puede verificar.

Cuando haga falta —no hoy— se descarga a mano y se guarda como `data/reference/ipc_dane.csv`
con dos columnas:

```csv
period,cpi
2026-09,142.37
2026-10,142.91
```

El nivel puede venir en cualquier base; solo se usan razones entre periodos.

**El índice no corre, y no por falta del IPC:** un índice mensual necesita 180 días de
histórico y el corte fijo del proyecto abarca ~19,5. `check_publishable` se niega y esa
negativa es la que aparece en `skipped`. La fecha que ese texto todavía nombra
(2027-03-29) suponía una captura semanal que ya no existe: la captura está cerrada y el
índice queda **fuera de alcance**
([ADR 0005](../adr/0005-capture-source-after-verification-wall.md#final-decision-2026-11-11)).
El código se conserva probado y no publicado.

## Cómo se regeneran

```powershell
.\make.ps1 results          # con el presupuesto de búsqueda afinado, ~25 min
.\make.ps1 results -Trials 0   # vistazo rápido, sin búsqueda
```

El ajuste de LightGBM que hay detrás de `segment_error` y `catalogue_contrast` usa la misma
semilla y la misma partición que `make train`, así que el error por segmento reconcilia con
el MAPE publicado en vez de ser otro número parecido.
