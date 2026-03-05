```md
# UCOM-Api-Extractor

API (FastAPI + Docker) para extraer información de relatos clínicos en español.

Incluye:
- **Medicaciones**: medicamento + dosis + esquema + **esquema_cambio**
- **PLAN (a nivel consulta)**: psicoterapia/psicoeducación, reposición de medicación, próximo control, cambio de esquema

---

## Estructura

```

UCOM-Api-Extractor/
├─ app.py
├─ extractor.py
├─ requirements.txt
└─ Dockerfile

````

---

## Requisitos

- **Docker** instalado (Windows/macOS/Linux).

---

## Ejecutar localmente (Docker)

Construir imagen:

```bash
docker build -t extractor-api .
````

Correr contenedor:

```bash
docker run -p 7860:7860 \
  -e PORT=7860 \
  -e APIKEY=<TU_API_KEY> \
  extractor-api
```

Swagger UI (docs):
`http://localhost:7860/docs`

> Todas las solicitudes deben incluir el header:
> `X-API-Key: <TU_API_KEY>`

---

## Endpoints (resumen)

### `GET /health`

Ping.

### `POST /extract/text`

Devuelve **solo** la lista de medicamentos (compatibilidad).

Body (JSON):

```json
{ "text": "clonazepam 0.5 mg 0.0.1 por 7 dias luego 0.0.0", "include_span": false }
```

Salida: lista de dicts con (según exista): `med, dosis, esquema, esquema_cambio, ...`

### `POST /extract/full`

Devuelve **medicaciones + plan**:

Body (JSON):

```json
{ "text": "PLAN: psicoterapia... clonazepam 0.5 mg 0.0.1 ... control en 15 dias", "include_span": false, "first_per_med": true }
```

Salida:

```json
{
  "meds": [ ... ],
  "plan": {
    "PLAN_psico_unificado": "Sí|No se encuentra dato",
    "PLAN_prox_control_texto": "en 15 dias|el 10/11/2025|No se encuentra dato",
    "PLAN_reposicion_medicacion": "Sí|No se encuentra dato",
    "REPO_medicacion": "Sí|No se encuentra dato",
    "PLAN_cambio_esquema": "Sí|No se encuentra dato",
    "PLAN_texto_limpio": "..."
  }
}
```

### `POST /extract/records`

Procesa múltiples registros. Salida **una fila por medicamento** y además agrega columnas del PLAN (repetidas en cada fila de esa consulta).

Query:

* `first_per_med=true|false`
* `out_format=json|csv`

Body (JSON):

```json
{
  "records": [
    {
      "ID_paciente":"P001",
      "fecha_consulta":"2025-01-10",
      "relato_consulta":"PLAN: psicoterapia... quetiapina 25 mg 0.0.1 ... control en 15 dias",
      "riesgo":"bajo"
    }
  ],
  "include_span": false
}
```

### `POST /extract/upload` (CSV/Excel)

form-data: `file=@archivo.xlsx`

Query: `include_span`, `first_per_med`, `out_format=json|csv`

### `POST /extract/from_hub` (Hugging Face Hub dataset privado)

Query:

* `repo_id` (default: `ama388/ucom-dataset`)
* `path` (ruta del archivo dentro del repo)
* `revision` (default: `main`)
* `include_span`, `first_per_med`, `out_format=json|csv`

---

## Columnas esperadas en CSV/Excel

`ID_paciente, fecha_consulta, relato_consulta, riesgo`

---

## Variables de entorno

* `APIKEY` *(obligatoria)*
  (También se acepta `API_KEY` si la definís así.)
* `HFTOKEN` *(obligatoria solo si usas `/extract/from_hub`)*

---

## Despliegue en Hugging Face Spaces (Docker)

1. Crear Space con **SDK: Docker**.
2. Subir a la raíz: `Dockerfile`, `app.py`, `extractor.py`, `requirements.txt`.
3. En **Settings → Repository secrets**:

   * `APIKEY` (o `API_KEY`)
   * `HFTOKEN` (si vas a usar `/extract/from_hub`)
4. Probar:

   * `https://<tu-space>.hf.space/health` (con header `X-API-Key`)

---

## Seguridad y privacidad

* No subir **datos sensibles** al repositorio.
* Mantener claves y credenciales como **Secrets**.
* La API es **stateless** (no persiste datos entre llamadas).



