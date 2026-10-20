# Desplegar la API en Render

**Esto lo haces tú.** El repositorio deja todo listo —`Dockerfile.api`, `render.yaml` y el
modelo dentro de la imagen— pero conectar la cuenta y apretar el botón requiere tus
credenciales, así que nadie más puede ni debe hacerlo por ti.

El plan gratuito de Render **no pide tarjeta**. Si en algún punto del flujo te la pide, algo
se salió del plan free: detente y revisa, porque el proyecto corre a costo cero por diseño
(ver la sección "Costo cero" de `CLAUDE.md`).

## Lo que vas a desplegar

Dos servicios, los dos gratis, declarados en el mismo `render.yaml`:

| Servicio | Qué es | Plan |
| --- | --- | --- |
| `autovalor-api` | La API FastAPI, como imagen Docker | Free |
| `autovalor-web` | El frontend Next.js, como **sitio estático** | Free (static) |

Sin base de datos, sin disco y sin worker. El modelo servido viaja **dentro de la imagen**
(`artifacts/models/`), así que el servicio no necesita descargar nada al arrancar ni
guardar nada entre despliegues; y el sitio estático es HTML, CSS y JS que Render sirve
desde su CDN, sin proceso que mantener despierto.

## Pasos

1. **Crea la cuenta.** <https://dashboard.render.com/register>, entra con GitHub. Autoriza
   el acceso al repositorio `AutoValorCo`.
2. **New → Blueprint.** Render busca `render.yaml` en la raíz y propone **los dos
   servicios**: `autovalor-api` y `autovalor-web`. Si solo ves uno, estás apuntando a un
   commit viejo; revisa que sea la rama `main`.
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

6. **Revisa `AUTOVALOR_CORS_ALLOW_ORIGINS`** (Environment → Edit). El blueprint trae
   `https://autovalor-web.onrender.com,http://localhost:3000`; si Render le asignó otro
   nombre al sitio estático, pon el origen real. Sin eso el navegador bloquea las llamadas
   desde el sitio.

   Se aceptan **las dos formas**: separados por coma (`https://a,https://b`) o un arreglo
   JSON (`["https://a","https://b"]`). Antes solo valía la segunda y la primera **impedía
   arrancar el servicio**, así que si lo tenías en JSON no hace falta cambiarlo.

   Un origen es esquema + host + puerto y nada más: `https://autovalor-web.onrender.com`
   sirve, `autovalor-web.onrender.com` y `https://autovalor-web.onrender.com/` no — el
   navegador compara literalmente y una barra al final nunca coincide.

7. **`PORT` tiene que quedar en 8000.** Es lo que le dice a Render dónde sondear: el `CMD`
   de la imagen le pasa `--port 8000` a uvicorn de forma literal y no lee el entorno. Si
   antes tenías `AUTOVALOR_API_PORT`, puedes borrarla: no la leía nadie.

8. **Abre el sitio estático** en `https://autovalor-web.onrender.com` y haz una consulta.
   Si el formulario se queda en «Cargando las listas del modelo…» y luego muestra un
   error, es una de dos: el navegador bloqueó la llamada por CORS —vuelve al paso 6— o la
   API todavía está arrancando, que la primera vez del día tarda cerca de un minuto.

   **Si Render le puso otro nombre al sitio** (porque `autovalor-web` ya estaba tomado),
   tienes que tocar dos cosas, no una: `AUTOVALOR_CORS_ALLOW_ORIGINS` en la API y
   `NEXT_PUBLIC_API_BASE_URL` en el sitio solo si también cambió el nombre de la API. Lo
   segundo es una variable **de construcción**: Next la hornea en el bundle, así que
   cambiarla exige un redespliegue del sitio, no basta con guardarla.

## Lo que te vas a encontrar en el plan gratuito

- **El servicio se duerme tras 15 minutos sin tráfico**, y la primera petición después de
  eso tarda ~50 s en responder mientras el contenedor arranca. No es un error. Si molesta
  para una demo, abre `/health` un minuto antes.
- **512 MB de RAM.** Medido: el proceso usa **240 MB** con los dos modelos cargados y
  estable bajo carga. La imagen pesa **779 MB en disco**, que es otra cosa —Render limita
  la memoria, no el tamaño de la imagen—; CI falla si el disco pasa de 900 MB para que no
  crezca sin que nadie lo note.
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

`export-model` reescribe también el `catalog.json` de cada vertical, que es lo que
`/catalog` sirve y de donde el formulario saca sus listas. Van juntos a propósito: un
catálogo de un lago y un modelo de otro ofrecerían marcas que el modelo no conoce.

`/model-info` reporta la versión del bundle, que lleva la fecha y el tamaño del lago
(`2026-10-07.11691`), así que siempre se puede saber qué modelo está contestando.

## Si algo falla

| Síntoma | Causa probable |
| --- | --- |
| `/health` dice `degraded` y `models_loaded` está vacío | La imagen se construyó sin `artifacts/models/`. Verifica que el directorio esté commiteado y que `.dockerignore` no lo excluya. |
| El build se queda sin memoria | El builder está instalando los grupos de desarrollo. `Dockerfile.api` usa `--no-default-groups`; si lo editaste, revisa eso primero. |
| El navegador bloquea las llamadas con un error de CORS | `AUTOVALOR_CORS_ALLOW_ORIGINS` no incluye el origen del frontend, o lo incluye con una barra al final. El navegador compara el origen literalmente. |
| La primera petición del día tarda casi un minuto | El servicio estaba dormido. Es el plan gratuito, no un fallo. |
| El build del sitio falla en `npm ci` | Falta `frontend/package-lock.json` en el commit, o no coincide con `package.json`. |
| El sitio carga pero el formulario no trae marcas | `/catalog` respondió 503: la imagen de la API es anterior a los catálogos. Reconstruye con `make export-model` y commitea `artifacts/`. |
| El sitio apunta a la API equivocada | `NEXT_PUBLIC_API_BASE_URL` se hornea en el build. Cámbiala y **redespliega el sitio**; guardarla no basta. |
