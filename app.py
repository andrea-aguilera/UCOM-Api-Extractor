# -*- coding: utf-8 -*-
from __future__ import annotations
import os, io, csv, json
from typing import Optional, List, Dict, Any

import pandas as pd
from fastapi import FastAPI, Header, HTTPException, Query, Depends, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from extractor import extraer_meds_con_dosis

# ==== Seguridad: API KEY OBLIGATORIA (si falta, no arranca) ====
API_KEY = os.getenv("API_KEY")
if not API_KEY:
    raise RuntimeError("API_KEY no configurada. En tu Space: Settings → Repository secrets → API_KEY")

def check_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")):
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

# ==== Modelos ====
class TextExtractionRequest(BaseModel):
    text: str
    include_span: bool = False

class Record(BaseModel):
    ID_paciente: str
    fecha_consulta: str
    relato_consulta: str
    riesgo: Optional[str] = None

class RecordsExtractionRequest(BaseModel):
    records: List[Record]
    include_span: bool = False

# ==== Utilidades ====
def first_per_med(extracciones: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set(); out: List[Dict[str, Any]] = []
    for x in sorted(extracciones, key=lambda d: (d.get("pos") if d.get("pos") is not None else 10**9)):
        med = x.get("med")
        if med and med not in seen:
            seen.add(med)
            esquema = x.get("esquema") or ""
            x["esquema"] = esquema.split(";")[0] if esquema else None
            out.append(x)
    return out

def _procesar_registros(records: List[Dict[str, Any]], include_span: bool, first_per_med_flag: bool) -> List[Dict[str, Any]]:
    resultados: List[Dict[str, Any]] = []
    for r in records:
        extr = extraer_meds_con_dosis(r["relato_consulta"], incluir_span=include_span)
        if first_per_med_flag:
            extr = first_per_med(extr)
        for h in extr:
            resultados.append({
                "ID_paciente": r["ID_paciente"],
                "fecha_consulta": r["fecha_consulta"],
                "riesgo": r.get("riesgo"),
                "relato_consulta": r["relato_consulta"],
                "med": h.get("med"),
                "alias": h.get("alias"),
                "alias_ocr": h.get("alias_ocr"),
                "dosis": h.get("dosis"),
                "esquema": h.get("esquema"),
                "pos": h.get("pos"),
                **({"span": h.get("span"), "contexto": h.get("contexto")} if include_span else {}),
            })
    return resultados

# ==== App con guardia global de API key ====
app = FastAPI(title="Extractor de relatos clínicos", version="1.1.0", dependencies=[Depends(check_api_key)])

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # si vas a llamarla desde un dominio fijo, cámbialo
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==== Endpoints base ====
@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/extract/text")
def extract_text(req: TextExtractionRequest):
    return extraer_meds_con_dosis(req.text, incluir_span=req.include_span)

@app.post("/extract/records")
def extract_records(
    req: RecordsExtractionRequest,
    first_per_med_flag: bool = Query(default=True, alias="first_per_med"),
    out_format: str = Query(default="json")
):
    if out_format not in {"json", "csv"}:
        raise HTTPException(status_code=400, detail="out_format debe ser 'json' o 'csv'")
    records = [r.model_dump() for r in req.records]
    resultados = _procesar_registros(records, req.include_span, first_per_med_flag)

    if out_format == "json":
        return resultados

    buf = io.StringIO()
    cols = ["ID_paciente","fecha_consulta","riesgo","relato_consulta","med","alias","alias_ocr","dosis","esquema","pos"]
    if req.include_span: cols += ["span","contexto"]
    writer = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for row in resultados: writer.writerow(row)
    buf.seek(0)
    return StreamingResponse(iter([buf.read()]), media_type="text/csv")

# ==== A) Subida directa (CSV/Excel) ====
@app.post("/extract/upload")
def extract_upload(
    file: UploadFile = File(...),
    include_span: bool = Query(False),
    first_per_med: bool = Query(True),
    out_format: str = Query("json")
):
    content = file.file.read()
    name = (file.filename or "").lower()
    try:
        if name.endswith(".xlsx") or name.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(content), dtype=str)
        else:
            df = pd.read_csv(io.StringIO(content.decode("utf-8")), dtype=str)
    except Exception as e:
        raise HTTPException(400, f"Error leyendo el archivo: {e}")

    df = df.fillna("")
    cols_req = {"ID_paciente","fecha_consulta","relato_consulta","riesgo"}
    if not cols_req.issubset(set(df.columns)):
        raise HTTPException(400, f"El archivo debe tener columnas {cols_req}")

    records = df[list(cols_req)].to_dict(orient="records")
    resultados = _procesar_registros(records, include_span, first_per_med)

    if out_format == "json":
        return resultados
    elif out_format == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=resultados[0].keys() if resultados else [])
        if resultados: writer.writeheader()
        for row in resultados: writer.writerow(row)
        buf.seek(0)
        return StreamingResponse(iter([buf.read()]), media_type="text/csv")
    else:
        raise HTTPException(400, "out_format debe ser 'json' o 'csv'")

# ==== B) Lectura desde Google Drive (privado) ====
def _drive_service():
    creds_json = os.getenv("GDRIVE_SA_JSON")
    if not creds_json:
        raise RuntimeError("Falta secreto GDRIVE_SA_JSON en el Space (Settings → Repository secrets).")
    creds = service_account.Credentials.from_service_account_info(
        json.loads(creds_json),
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=creds)

def _download_drive_file_as_bytes(file_id: str) -> bytes:
    svc = _drive_service()
    request = svc.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    return fh.getvalue()

@app.post("/extract/from_drive")
def extract_from_drive(
    file_id: str = Query(default=None, description="ID del archivo en Drive (compartido con el service account)"),
    sheet: str | int | None = Query(default=None, description="Nombre o índice de hoja (Excel); por defecto la primera"),
    include_span: bool = Query(False),
    first_per_med: bool = Query(True),
    out_format: str = Query("json")
):
    file_id = file_id or os.getenv("GDRIVE_FILE_ID_DEFAULT")
    if not file_id:
        raise HTTPException(400, "Debes pasar ?file_id=... o configurar GDRIVE_FILE_ID_DEFAULT en Secrets.")
    content = _download_drive_file_as_bytes(file_id)

    # Intentar Excel primero, si falla intentar CSV
    try:
        df = pd.read_excel(io.BytesIO(content), sheet_name=sheet if sheet is not None else 0, dtype=str)
    except Exception:
        try:
            df = pd.read_csv(io.StringIO(content.decode("utf-8")), dtype=str)
        except Exception as e:
            raise HTTPException(400, f"No se pudo leer como Excel ni como CSV: {e}")

    df = df.fillna("")
    cols_req = {"ID_paciente","fecha_consulta","relato_consulta","riesgo"}
    if not cols_req.issubset(set(df.columns)):
        raise HTTPException(400, f"El archivo de Drive debe tener columnas {cols_req}")

    records = df[list(cols_req)].to_dict(orient="records")
    resultados = _procesar_registros(records, include_span, first_per_med)

    if out_format == "json":
        return resultados
    elif out_format == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=resultados[0].keys() if resultados else [])
        if resultados: writer.writeheader()
        for row in resultados: writer.writerow(row)
        buf.seek(0)
        return StreamingResponse(iter([buf.read()]), media_type="text/csv")
    else:
        raise HTTPException(400, "out_format debe ser 'json' o 'csv'")

# Desarrollo local
if __name__ == "__main__":
    import uvicorn
    # Ejecutar con: API_KEY=tu_clave uvicorn app:app --reload
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
