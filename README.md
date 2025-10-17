# UCOM-Api-Extractor
API (FastAPI + Docker) para acceder al Extractor de Medicación y Posología (dosis y esquema) de relatos de consultas médicas en español de pacientes anonimizados diagnosticados con depresión, de un Hospital Psiquiátrica en Asunción, Paraguay.

Incluye:
* Endpoints: `/health`, `/extract/text`, `/extract/records`, `/extract/upload`, `/extract/from_drive`
* **API Key obligatoria** (header `X-API-Key`)
* Lectura de base de datos en Excel/CSV desde **Google Drive** (archivo privado con Service Account)
* Imagen **Docker** lista para correr localmente o en **Hugging Face Spaces (SDK: Docker)**

---

## Tabla de contenidos

1. [Estructura](#estructura)
2. [Requisitos](#requisitos)
3. [Variables de entorno](#variables-de-entorno)
4. [Instalación local con Docker](#instalación-local-con-docker)
5. [Uso local (cURL / Postman)](#uso-local-curl--postman)
6. [Endpoints](#endpoints)
7. [Google Drive (archivo privado)](#google-drive-archivo-privado)

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

  * Windows: Docker Desktop + WSL2.
    
---

## Variables de entorno

| Variable                 | Obligatoria | Descripción                                                                         |
| ------------------------ | ----------- | ----------------------------------------------------------------------------------- |
| `API_KEY`                | **Sí**      | Clave de la API. La API **no arranca** si falta. Se envía en el header `X-API-Key`. |
| `GDRIVE_SA_JSON`         | No*         | **Contenido JSON** de la Service Account (para `/extract/from_drive`).              |
| `GDRIVE_FILE_ID_DEFAULT` | No          | `file_id` por defecto del archivo de Drive (opcional).                              |

* Requerida solo al usar el endpoint **`/extract/from_drive`**.

---

## Instalación local con Docker

1. Construir la imagen:

```bash
docker build -t extractor-api .
```

2. Ejecutar el contenedor (la API exige API key):

```bash
docker run -p 7860:7860 \
  -e PORT=7860 \
  -e API_KEY=mi_clave_supersecreta \
  extractor-api
```

3. Abrir documentos interactivos:
   `http://localhost:7860/docs`

> Nota: Swagger UI **no** agrega el header `X-API-Key` automáticamente. Para probar desde `/docs`, usar Postman o curl (ver abajo).

---

## Uso local (cURL / Postman)

### Salud

```bash
curl "http://localhost:7860/health" \
  -H "X-API-Key: API_KEY"
```

### Texto único

```bash
curl -X POST "http://localhost:7860/extract/text" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: API_KEY" \
  -d '{"text":"Plan: clonazepam 0.5 mg 0.0.1 por 1 semana. sertra 50mg 1/2.","include_span":true}'
```

### Lote (JSON → JSON)

```bash
curl -X POST "http://localhost:7860/extract/records?first_per_med=true&out_format=json" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: API_KEY" \
  -d '{
    "records": [
      {"ID_paciente":"P001","fecha_consulta":"2025-01-10","relato_consulta":"quetiapina 25 mg 0.0.1","riesgo":"bajo"},
      {"ID_paciente":"P002","fecha_consulta":"2025-01-12","relato_consulta":"sertralina 50mg 1/2 por 7 días","riesgo":null}
    ],
    "include_span": false
  }'
```

### Subida de archivo (CSV/Excel → CSV)

```bash
curl -X POST "http://localhost:7860/extract/upload?out_format=csv&include_span=false&first_per_med=true" \
  -H "X-API-Key: API_KEY" \
  -F "file=@./datos.xlsx"
```

**Columnas esperadas (en Excel/CSV):**
`ID_paciente, fecha_consulta, relato_consulta, riesgo` (en minúsculas).

---

## Endpoints

* `GET /health` → `{"status": "ok"}`
* `POST /extract/text`

  * Body (JSON): `{ "text": "...", "include_span": false }`
* `POST /extract/records`

  * Body (JSON): `{ "records": [...], "include_span": false }`
  * Query:

    * `first_per_med=true|false` (default: true) → deja 1ª mención por fármaco.
    * `out_format=json|csv` (default: json)
* `POST /extract/upload`

  * Form-Data: `file=@archivo.xlsx` o `file=@archivo.csv`
  * Query: `include_span`, `first_per_med`, `out_format`
* `POST /extract/from_drive`

  * Query: `file_id=<ID>`, `sheet=<hoja>` (opcional), `include_span`, `first_per_med`, `out_format`
  * Requiere secrets de Drive (ver abajo).

**Header de seguridad (obligatorio en todos):**

```
X-API-Key: API_KEY
```

---

## Google Drive (archivo privado)

  * URL del archivo: https://docs.google.com/spreadsheets/d/1LmMKbRg-Pfpho930t5E0R1M5s5E27Xwl/edit?usp=drive_link&ouid=103567077341073819710&rtpof=true&sd=true

### 1) Configurar variables

* En **Hugging Face Spaces**:

  * `API_KEY` (obligatoria)
  * `GDRIVE_SA_JSON` (pegar **contenido** del JSON)
  * `GDRIVE_FILE_ID_DEFAULT` (opcional)

### 2) Llamada de ejemplo

```bash
curl -X POST "http://localhost:7860/extract/from_drive?file_id=<FILE_ID>&out_format=csv" \
  -H "X-API-Key: API_KEY"
```

> El endpoint intentará leer como Excel; si falla, intenta CSV.
