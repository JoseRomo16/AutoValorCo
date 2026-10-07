# Desplegar la API en Render

**Esto lo haces tú.** El repositorio deja todo listo —`Dockerfile.api`, `render.yaml` y el
modelo dentro de la imagen— pero conectar la cuenta y apretar el botón requiere tus
credenciales, así que nadie más puede ni debe hacerlo por ti.

El plan gratuito de Render **no pide tarjeta**. Si en algún punto del flujo te la pide, algo
se salió del plan free: detente y revisa, porque el proyecto corre a costo cero por diseño
(ver la sección "Costo cero" de `CLAUDE.md`).

## Lo que vas a desplegar

Un solo servicio web, sin base de datos, sin disco y sin worker. El modelo servido viaja
**dentro de la imagen** (`artifacts/models/`), así que el servicio no necesita descargar
nada al arrancar ni guardar nada entre despliegues.

## Pasos

1. **Crea la cuenta.** <https://dashboard.render.com/register>, entra con GitHub. Autoriza
   el acceso al repositorio `AutoValorCo`.
2. **New → Blueprint.** Render busca `render.yaml` en la raíz y propone el servicio
   `autovalor-api`. Si no lo encuentra, revisa que estés apuntando a la rama `main`.
3. **Revisa el plan antes de confirmar.** Tiene que decir **Free**. El blueprint ya lo
   fija, pero vale la pena verlo con los ojos.
4. **Apply.** El primer build tarda varios minutos: compila la imagen desde cero.
5. **Comprueba que responde:**

   ```bash
   curl https://autovalor-api.onrender.com/health
   curl https://autovalor-api.onrender.com/model-info
   ```

   `/health` debe decir `"status": "ok"` y listar `["car", "motorcycle"]` en
   `models_loaded`. Si dice `"degraded"`, la imagen se construyó sin `artifacts/` — mira la
   sección de problemas.

6. **Cuando exista el frontend**, cambia `AUTOVALOR_CORS_ALLOW_ORIGINS` por su origen real
   (Environment → Edit). Sin eso el navegador bloquea las llamadas desde el sitio estático.
   Acepta varios separados por coma.

## Lo que te vas a encontrar en el plan gratuito

- **El servicio se duerme tras 15 minutos sin tráfico**, y la primera petición después de
  eso tarda ~50 s en responder mientras el contenedor arranca. No es un error. Si molesta
  para una demo, abre `/health` un minuto antes.
- **512 MB de RAM.** La imagen está construida contra ese límite y CI falla si se pasa de
  900 MB en disco. El consumo medido está en `docs/STATUS.md`.
- **No hay disco persistente.** Correcto para este servicio: solo lee archivos que vienen
  en la imagen.

## Cuando el modelo cambie

El modelo servido se reconstruye y se commitea; Render redespliega solo al ver el commit.

```powershell
.\make.ps1 transform        # si el lago cambió
.\make.ps1 export-model     # reentrena y reescribe artifacts/models/
.\make.ps1 results          # si quieres que /market también se actualice
git add artifacts docs/results && git commit -m "chore(models): re-export the served model"
```

`/model-info` reporta la versión del bundle, que lleva la fecha y el tamaño del lago
(`2026-10-07.11691`), así que siempre se puede saber qué modelo está contestando.

## Si algo falla

| Síntoma | Causa probable |
| --- | --- |
| `/health` dice `degraded` y `models_loaded` está vacío | La imagen se construyó sin `artifacts/models/`. Verifica que el directorio esté commiteado y que `.dockerignore` no lo excluya. |
| El build se queda sin memoria | El builder está instalando los grupos de desarrollo. `Dockerfile.api` usa `--no-default-groups`; si lo editaste, revisa eso primero. |
| El navegador bloquea las llamadas con un error de CORS | `AUTOVALOR_CORS_ALLOW_ORIGINS` no incluye el origen del frontend. |
| La primera petición del día tarda casi un minuto | El servicio estaba dormido. Es el plan gratuito, no un fallo. |
