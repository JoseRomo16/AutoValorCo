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
| `manifest.json` | Sobre qué lago se midió todo: filas, cobertura de detalle, span de capturas y los umbrales vigentes |

**Lee `manifest.json` antes de citar una cifra.** Un número sin saber sobre cuántas filas
se midió no se puede comparar con el siguiente.

## Convenciones

- Los porcentajes son multiplicativos, no aditivos: salen de `exp(β) − 1`. Una
  depreciación de 5,9 % anual significa que el precio queda en 94,1 % del año anterior.
- `significant` es si el intervalo del 95 % excluye el cero. Una fila con `significant`
  en falso **no** es un efecto pequeño: es un efecto que estos datos no distinguen de cero.
- Los valores faltantes son `null` en JSON, nunca `NaN` —que no es JSON válido—.
- Los flotantes vienen redondeados a cuatro decimales para que los diffs del repositorio
  sean legibles.

## Cómo se regeneran

```powershell
.\make.ps1 results          # con el presupuesto de búsqueda afinado, ~25 min
.\make.ps1 results -Trials 0   # vistazo rápido, sin búsqueda
```

El ajuste de LightGBM que hay detrás de `segment_error` y `catalogue_contrast` usa la misma
semilla y la misma partición que `make train`, así que el error por segmento reconcilia con
el MAPE publicado en vez de ser otro número parecido.
