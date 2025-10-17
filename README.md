# UCOM-Api-Extractor
API (FastAPI + Docker) para acceder al Extractor de Medicación y Posología (dosis y esquema) de relatos de consultas médicas en español de pacientes anonimizados diagnosticados con depresión, de un Hospital Psiquiátrica en Asunción, Paraguay.

---

## Estructura

```
UCOM-Api-Extractor/
├─ app.py
├─ extractor.py
├─ requirements.txt
└─ Dockerfile
```

---

## Requisitos

* **Docker** instalado (Windows/macOS/Linux).
  
---

## Ejecutar localmente (Docker)

Construir imagen:

```bash
docker build -t extractor-api .
```

Correr contenedor:

```bash
docker run -p 7860:7860 \
  -e PORT=7860 \
  -e API_KEY=<API_KEY> \
  extractor-api
```

Swagger UI (docs):
`http://localhost:7860/docs`

> Todas las solicitudes deben incluir el header:
> `X-API-Key: <API_KEY>`

## Endpoints (resumen)

* `GET /health` → ping
* `POST /extract/text`

  * Body (JSON):

    ```json
    { "text": "clonazepam 0.5 mg 0.0.1", "include_span": false }
    ```
* `POST /extract/records`

  * Query: `first_per_med=true|false`, `out_format=json|csv`
  * Body (JSON):

    ```json
    {
      "records": [
        {"ID_paciente":"P001","fecha_consulta":"2025-01-10","relato_consulta":"quetiapina 25 mg 0.0.1","riesgo":"bajo"}
      ],
      "include_span": false
    }
    ```
* `POST /extract/upload` (CSV/Excel)

  * form-data: `file=@archivo.xlsx`
  * Query: `include_span`, `first_per_med`, `out_format=json|csv`
* `POST /extract/from_drive`

  * Query: `file_id=<FILE_ID>`, `sheet=<opcional>`, `include_span`, `first_per_med`, `out_format=json|csv`

**Columnas esperadas** en CSV/Excel:
`ID_paciente, fecha_consulta, relato_consulta, riesgo`

## Variables de entorno

* `API_KEY`  *(obligatoria; la API no arranca si falta)*
* `GDRIVE_SA_JSON` *(contenido JSON del Service Account para Google Drive; requerido si se usa `/extract/from_drive`)*
* `GDRIVE_FILE_ID_DEFAULT` *(opcional)*

## Despliegue en Hugging Face Spaces (Docker)

1. Crear Space con **SDK: Docker**.
2. Subir a la raíz: `Dockerfile`, `app.py`, `extractor.py`, `requirements.txt`.
3. En **Settings → Repository secrets**:

   * `API_KEY`
   * (opcional) `GDRIVE_SA_JSON` y `GDRIVE_FILE_ID_DEFAULT`
4. Esperar build y probar: `https://<tu-space>.hf.space/health` (con `X-API-Key`).

## Seguridad y privacidad

* No subir **datos sensibles** al repositorio.
* Mantener claves y credenciales como **Secrets**.
* La API es **stateless** (no persiste datos entre llamadas).

