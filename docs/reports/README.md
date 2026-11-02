# Mediciones de diagnóstico / Diagnostic measurements

Mediciones puntuales que respaldan una decisión (un ADR, un bloque del plan) y no se
publican en el sitio. No van en `docs/results/` porque `/market` sirve cada JSON de ese
directorio como tabla.

| Archivo | Qué contiene | Cómo se regenera |
| --- | --- | --- |
| `block4_baseline.json` | La banda y el error del bundle `2026-10-25.12948` (con ciudad), con los valores reales y con los que manda la API | `python -m autovalor.models.band_diagnostics --output docs/reports/block4_baseline.json` sobre ese bundle |

El significado de cada campo está en el docstring de `autovalor.models.band_diagnostics`.
