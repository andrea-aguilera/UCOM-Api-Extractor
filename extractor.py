# -*- coding: utf-8 -*-
from __future__ import annotations
"""
Extractor de:
- Medicamentos + dosis + esquema (+ esquema_cambio)
- PLAN: psicoterapia/psicoeducación, reposición de medicación, próximo control, cambio de esquema

Notas:
- `extraer_meds_con_dosis(...)` devuelve una lista (1 dict por med detectada).
- `extraer_info_plan(...)` devuelve un dict con variables del PLAN (nivel consulta).
"""
import re
import unicodedata
from collections import defaultdict
from typing import Dict, List, Any, Optional
from rapidfuzz import fuzz, process


# ============================================================
# 1) Diccionario validado (canónico -> alias)
# ============================================================
meds: Dict[str, List[str]] = {
    # Benzodiacepinas
    "clonazepam": ["clonazepam", "cnz", "clonaz", "clonazep", "clonazepma"],
    "diazepam": ["diazepam", "dzp", "diazepan"],
    "clotiazepam": ["clotiazepam"],
    "alprazolam": ["alprazolam", "alp"],

    # Hipnóticos
    "eszopiclona": ["eszopiclona"],
    "zolpidem": ["zolpidem", "zlp", "zpd"],

    # Antipsicóticos
    "quetiapina": ["quetiapina", "qtp", "qtt", "qtppa", "qtp"],
    "risperidona": ["risperidona", "risp", "rsp"],
    "olanzapina": ["olanzapina", "olz", "oollzz"],
    "haloperidol": ["haloperidol"],

    # Antidepresivos
    "fluoxetina": ["fluoxetina", "flx", "fxt"],
    "sertralina": ["sertralina", "srt", "sertra", "srt"],
    "paroxetina": ["paroxetina", "pxt"],
    "escitalopram": ["escitalopram", "talopram"],
    "venlafaxina": ["venlafaxina", "vfx", "venla", "vlf"],
    "amitriptilina": ["amitriptilina", "amt"],
    "trazodona": ["trazodona", "trazo", "trz"],
    "bupropion": ["bupropion"],

    # Estabilizadores / antiepilépticos
    "carbamazepina": ["carbamazepina", "cbz", "arbamazepina"],
    "oxcarbazepina": ["oxcarbazepina"],
    "ácido valproico": ["ácido valproico", "acido valproico", "valproato", "valp"],
    "lamotrigina": ["lamotrigina"],
    "litio": ["litio"],
    "difenil hidantoinato": ["difenil hidantoinato", "difenil"],

    # Otros
    "calmina": ["calmina"],
    "metilfenidato": ["metilfenidato"],
    "pregabalina": ["pregabalina", "pregaba"],
    "biperideno": ["biperideno", "bpd", "bipe"],
    "donepecilo": ["donepecilo", "dnlp", "donepe"],
    "levodopa": ["levodopa"],
    "nimodipina": ["nimodipina"],
    "fenobarbital": ["fenobarbital"],
    "aripiprazol": ["aripiprazol"],
    "levomepromazina": ["levomepromacina", "levopromazina", "levomep", "levomeproma", "Levomepromazina"],
}


# ============================================================
# 2) Normalización / limpieza
# ============================================================
def quitar_tildes(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")


def limpiar_texto(texto: str) -> str:
    if not isinstance(texto, str):
        return ""
    t = quitar_tildes(texto.lower())

    # Normalizar coma decimal (2,5 -> 2.5)
    t = re.sub(r"(?<=\d),(?=\d)", ".", t)

    # Correcciones OCR 0/1/5 dentro de palabras
    t = re.sub(r"(?<=[a-z])0(?=[a-z])", "o", t)
    t = re.sub(r"(?<=[a-z])1(?=[a-z])", "l", t)
    t = re.sub(r"(?<=[a-z])5(?=[a-z])", "s", t)

    # Signos ¡!¿?
    t = t.translate(str.maketrans("", "", "¡!¿?"))

    # Colapsar repeticiones de 3+
    t = re.sub(r"(.)\1{2,}", r"\1", t)

    # Mantener letras/números/espacios y . - / :
    t = re.sub(r"[^a-z0-9\s\./:-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


# ============================================================
# 3) Índices y regex de fármacos
# ============================================================
alias_a_canonico: Dict[str, str] = {}
for canon, aliases in meds.items():
    alias_a_canonico[quitar_tildes(canon.lower())] = canon
    for a in aliases:
        alias_a_canonico[quitar_tildes(a.lower())] = canon

alias_ordenados = sorted(alias_a_canonico.keys(), key=len, reverse=True)
patron_alias = re.compile(r"\b(" + "|".join(re.escape(a) for a in alias_ordenados) + r")\b")

alias_lista = list(alias_a_canonico.keys())
aliases_by_first = defaultdict(list)
for a in alias_lista:
    if a:
        aliases_by_first[a[0]].append(a)

# Para “hard-stops” (detectar próximo fármaco)
MED_HINT_RX = re.compile(r"\b(?:" + "|".join(re.escape(a) for a in alias_ordenados if len(a) >= 3) + r")\b", re.IGNORECASE)

# Ítems numerados tipo "1. ... 2. ..."
PLAN_ITEM_RX = re.compile(r"(?:^|\s)(\d+)\.\s+(.*?)(?=(?:\s\d+\.\s)|\Z)", re.DOTALL)


def dividir_en_items_plan(t_norm: str):
    items = []
    for m in PLAN_ITEM_RX.finditer(t_norm):
        items.append({"n": m.group(1), "texto": m.group(2).strip(), "start": m.start(2), "end": m.end(2)})
    if not items:
        items = [{"n": None, "texto": t_norm, "start": 0, "end": len(t_norm)}]
    return items


# ============================================================
# 4) Helpers OCR
# ============================================================
def _squeeze_dupes_letters(s: str) -> str:
    # aa->a, qqq->q
    return re.sub(r"([a-z])\1+", r"\1", s)


def _denoise_scheme_text(s: str) -> str:
    # :: => : , .. => . , -- => - ; 00 => 0 , 22 => 2
    s = re.sub(r"([:./-])\1+", r"\1", s)
    s = re.sub(r"(\d)\1+", r"\1", s)
    return s


def _collapse_digit_pairpairs(num_str: str) -> str:
    # 2255 -> 25 ; 1122 -> 12 ; no toca 100, 250, etc.
    if not num_str:
        return num_str
    m = re.fullmatch(r"(\d)\1(\d)\2", num_str)
    return (m.group(1) + m.group(2)) if m else num_str


def _collapse_dup_digits(num_str: str) -> str:
    # 220 -> 20 ; 55 -> 5 ; 000 -> 0
    return re.sub(r"(\d)\1+", r"\1", num_str)


def _normalize_mg_unit(s: str) -> str:
    if not s:
        return ""
    mg_fuzzy = r"m+\s*g+"
    return re.sub(mg_fuzzy, "mg", s)


def _looks_like_ocr_dup(context: str, unit_raw: str) -> bool:
    if not context:
        context = ""
    if not unit_raw:
        unit_raw = ""
    dup_letters = re.search(r"([a-z])\1{1,}", context) is not None
    dup_seps = re.search(r"([:./-])\1{1,}", context) is not None
    dup_unit = re.search(r"m{2,}\s*g+|m+\s*g{2,}|m{2,}g{2,}", unit_raw) is not None  # mmgg
    return dup_letters or dup_seps or dup_unit


# ============================================================
# 5) Dosis
# ============================================================
MG_FUZZY = r"m+\s*g+"  # mg tolerante a OCR
UNIT_RX = r"(?:%s|g|mcg|µg|ug|ml|gota(?:s)?|comp(?:r?imidos?)?|cp|tab(?:s)?|caps?)" % MG_FUZZY
NUM = r"\d{1,4}(?:[.,]\d+)?"

DOSE_WITH_UNIT = re.compile(rf"\b(?P<num>{NUM})\s*(?P<unit>{UNIT_RX})\b", re.IGNORECASE)
DOSE_NEAR_UNIT_CAP = re.compile(rf"\b(?P<num>{NUM})(?:\s|[^\w]){{0,8}}(?P<unit>{UNIT_RX})\b", re.IGNORECASE)


def _normalize_dosis(num: str, unit: str, *, context: str = "", unit_raw: str = "") -> str:
    if _looks_like_ocr_dup(context, unit_raw or unit):
        num = _collapse_dup_digits(num)
    num_norm = _collapse_digit_pairpairs(num)
    unit_norm = _normalize_mg_unit(unit or unit_raw or "")
    return (num_norm + (unit_norm and f"{unit_norm}")).strip()


def _pick_dose(texto_item: str) -> str:
    m = DOSE_WITH_UNIT.search(texto_item)
    if m:
        return _normalize_dosis(m.group("num"), m.group("unit"), context=texto_item, unit_raw=m.group("unit"))
    m = DOSE_NEAR_UNIT_CAP.search(texto_item)
    if m:
        return _normalize_dosis(m.group("num"), m.group("unit"), context=texto_item, unit_raw=m.group("unit"))
    return ""


# ============================================================
# 6) Esquema + esquema_cambio
# ============================================================
# Esquemas soportados:
# - 0.0.1 ; 1-0-1 ; 0.0.1/2 ; 1/2 ; 10/20 ; "... o 1"
SCHEME_TOKEN = r"\b\d(?:[.\-]\d){1,5}(?:\s*/\s*\d{1,2})?\b"
SCHEME_FRAC_SIMPLE = r"\b\d{1,2}\s*/\s*\d{1,2}\b"
SCHEME_DIGIT = r"\b[0-3]\b"

SCHEME_ALT = rf"(?:\s*o+\s*(?:{SCHEME_TOKEN}|{SCHEME_FRAC_SIMPLE}|{SCHEME_DIGIT}))"
SCHEME_RX = re.compile(rf"(?:{SCHEME_TOKEN}|{SCHEME_FRAC_SIMPLE}|{SCHEME_DIGIT})(?:{SCHEME_ALT})?", re.IGNORECASE)

SCHEME_CHANGE_HINT_RX = re.compile(
    r"\b(?:luego|despues|después|posteriormente|por|pasar\s+a|cambiar|cambio|ajustar|modificar|"
    r"subir|bajar|aumentar|disminuir|reducir|incrementar|titular|suspender|suspension|suspensión|"
    r"o|y)\b|[+()]",
    re.IGNORECASE,
)

SCHEME_CHANGE_STOP_RX = re.compile(
    r"(?:;|\b\d+\.\s|\b(?:psicoterapia|psicoeducacion|psicoeducación|reposicion|reposición|"
    r"proximo\s+control|próximo\s+control|control|nota|observaciones|indicaciones|conducta|tratamiento)\b)",
    re.IGNORECASE,
)


def _normalize_scheme(s: str) -> str:
    s = re.sub(r"\s+", "", s)
    s = s.replace(",", ".")
    s = re.sub(r"([./-]){2,}", r"\1", s)
    s = s.replace("-", ".")  # normalizar 1-0-1 -> 1.0.1
    return s


def _sub_bloque_para_esquema(sub: str) -> str:
    p = sub.find(":")
    if p != -1:
        return sub[p + 1 :]
    m = DOSE_WITH_UNIT.search(sub) or DOSE_NEAR_UNIT_CAP.search(sub)
    return sub[m.end() :] if m else sub


def _pick_schemes(texto: str) -> List[str]:
    texto_clean = _denoise_scheme_text(texto or "")
    out: List[str] = []
    seen = set()
    for m in SCHEME_RX.finditer(texto_clean):
        # separar alternativas por "o"
        parts = re.split(r"\s*o+\s*", m.group(0), flags=re.IGNORECASE)
        for p in parts:
            p = _normalize_scheme(p)
            if p and p not in seen:
                seen.add(p)
                out.append(p)
    return out


def _pick_scheme_change(texto_esquema: str) -> Optional[str]:
    """
    Devuelve la frase literal de cambio/ajuste posterior al primer esquema.
    Ej:
      "0.0.1 por 7 dias luego 0.0.0"
      -> "por 7 dias luego 0.0.0"
    """
    if not texto_esquema:
        return None

    t = _denoise_scheme_text(texto_esquema)
    m0 = SCHEME_RX.search(t)
    if not m0:
        return None

    tail = t[m0.end() :]
    mh = SCHEME_CHANGE_HINT_RX.search(tail)
    if not mh:
        return None

    start = m0.end() + mh.start()

    # Stops dentro del mismo sub-bloque
    cand_ends = []

    ms = SCHEME_CHANGE_STOP_RX.search(t, start)
    if ms:
        cand_ends.append(ms.start())

    # No cruzar si aparece otro fármaco (por si el sub quedó largo)
    mm = MED_HINT_RX.search(t, start)
    if mm:
        cand_ends.append(mm.start())

    # No cruzar si empieza otro ítem numerado
    mn = re.search(r"\b\d+\.\s", t[start:])
    if mn:
        cand_ends.append(start + mn.start())

    end = min(cand_ends) if cand_ends else min(len(t), start + 180)
    frag = re.sub(r"\s+", " ", t[start:end]).strip()
    return frag or None


# ============================================================
# 7) Extracción principal (med + dosis + esquema + esquema_cambio)
# ============================================================
def extraer_meds_con_dosis(texto: str, incluir_span: bool = True) -> List[Dict[str, Any]]:
    if not isinstance(texto, str):
        return []

    t_norm = limpiar_texto(texto)
    resultados: List[Dict[str, Any]] = []
    items = dividir_en_items_plan(t_norm)

    for it in items:
        bloque = it["texto"]
        base = it["start"]
        hallados = []
        vistos_canon = set()

        # Regex exacto de alias
        for m in patron_alias.finditer(bloque):
            alias_norm = m.group(1)
            canon = alias_a_canonico.get(alias_norm)
            if not canon:
                continue
            pos_abs = base + m.start()
            hallados.append((canon, alias_norm, pos_abs, base + m.end(), "regex"))
            vistos_canon.add(canon)

        # Fallback fuzzy sobre tokens con letras duplicadas
        for tm in re.finditer(r"\b[a-z0-9]{5,40}\b", bloque):
            tok = tm.group(0)
            tok_s = _squeeze_dupes_letters(tok)
            if tok_s == tok or len(tok_s) < 5:
                continue
            cand_pool = aliases_by_first.get(tok_s[0], alias_lista)
            match = process.extractOne(tok_s, cand_pool, scorer=fuzz.ratio, score_cutoff=90)
            if not match:
                continue
            alias_hit, score, _ = match
            if len(tok_s) / max(1, len(alias_hit)) < 0.6:
                continue
            if tok_s[-1] != alias_hit[-1]:
                continue
            canon = alias_a_canonico[alias_hit]
            if canon in vistos_canon:
                continue
            pos_abs = base + tm.start()
            hallados.append((canon, alias_hit, pos_abs, base + tm.end(), "fuzzy_dupes", tok))
            vistos_canon.add(canon)

        # Enriquecer con dosis/esquema/esquema_cambio
        for item in sorted(hallados, key=lambda x: x[2]):
            if len(item) == 6:
                canon, alias_match, pos_abs_i, pos_abs_f, metodo, alias_ocr = item
            else:
                canon, alias_match, pos_abs_i, pos_abs_f, metodo = item
                alias_ocr = None

            start_local = pos_abs_i - base
            # un poco más largo para capturar "por X ... luego ..."
            sub = bloque[start_local : start_local + 350]

            dosis = _pick_dose(sub)
            sub_esq = _sub_bloque_para_esquema(sub)

            esquemas = _pick_schemes(sub_esq)
            esquema_cambio = _pick_scheme_change(sub_esq)

            salida: Dict[str, Any] = {
                "med": canon,
                "alias": alias_match,
                "dosis": dosis or None,
                "esquema": ";".join(esquemas) if esquemas else None,
                "esquema_cambio": esquema_cambio or None,
                "pos": pos_abs_i,
                "alias_ocr": alias_ocr,
            }
            if incluir_span:
                salida["span"] = [pos_abs_i, pos_abs_f]
                salida["contexto"] = sub[:180]
            resultados.append(salida)

    return resultados


# ============================================================
# 8) EXTRACCIÓN DE PLAN (psicoterapia, reposición, próximo control, cambio de esquema)
# ============================================================
_PLAN_HEAD_RX = re.compile(r"\bplan\s*[:\-]\s*", re.IGNORECASE)
_HEADERS_RX = re.compile(
    r"\b(?:diagnostico|impresion|evolucion|examen|indicaciones|conducta|tratamiento|observaciones|nota|anamnesis|motivo)\s*[:\-]",
    re.IGNORECASE,
)

def _extraer_bloque_plan(relato: str) -> Optional[str]:
    if not isinstance(relato, str) or not relato.strip():
        return None
    t = limpiar_texto(relato)
    mh = _PLAN_HEAD_RX.search(t)
    if not mh:
        return None
    start = mh.end()
    mn = _HEADERS_RX.search(t, pos=start)
    end = mn.start() if mn else len(t)
    plan = t[start:end].strip()
    return plan or None


def _build_fuzzy_word_rx(word: str) -> re.Pattern:
    # tolera duplicación de letras + espacios/guiones
    parts = []
    for ch in word:
        if ch == " ":
            parts.append(r"(?:\s|-)*")
        else:
            parts.append(re.escape(ch) + r"+")
    return re.compile(r"\b" + "".join(parts) + r"\b", re.IGNORECASE)


PSICOEDU_RX = _build_fuzzy_word_rx("psico educacion")
PSICOTER_RX = _build_fuzzy_word_rx("psico terapia")
NEG_RX = re.compile(r"\b(?:no(?:\s+se)?\s+(?:indica|realiza|hace|requiere|recomienda)|sin)\b", re.IGNORECASE)

def _negado(texto: str, idx: int, window: int = 25) -> bool:
    ctx = texto[max(0, idx - window) : idx]
    return bool(NEG_RX.search(ctx))


REPO_KEY_RX = re.compile(
    r"\b(reposic|reponer|repone|reposicion|reposición|retirar|dispensa|dispensar|farmacia|receta)\w*\b",
    re.IGNORECASE,
)

# Próximo control: "control en 15 dias" | "control el 10/11/2025" | "proximo control ..."
REL_CONTROL_RX = re.compile(
    r"\b(?:proximo\s+control|próximo\s+control|control|proxima\s+consulta|próxima\s+consulta|volver)\b"
    r".{0,30}?\b(?:en|a\s+los?)\s+"
    r"(?P<num>\d+|uno|una|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|quince|veinte|treinta)"
    r"\s*(?P<u>d+i+a+s?|s+e+m+a+n+a+s?|m+e+s+e?s?|h(?:o?r+a+s?)?|hs)\b",
    re.IGNORECASE,
)
FECHA_CONTROL_RX = re.compile(
    r"\b(?:proximo\s+control|próximo\s+control|control|proxima\s+consulta|próxima\s+consulta|volver)\b"
    r".{0,25}?\b(?:el|para\s+el)?\s*(\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)",
    re.IGNORECASE,
)
_MESES_RX = re.compile(
    r"\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)\b",
    re.IGNORECASE,
)
CONTROL_MES_RX = re.compile(
    r"\b(?:proximo\s+control|próximo\s+control|control|proxima\s+consulta|próxima\s+consulta|volver)\b"
    r".{0,25}?\b(?:en|para)\s+(?P<mes>" + _MESES_RX.pattern[2:-2] + r")\b",
    re.IGNORECASE,
)

_NUM_WORDS = {
    "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
    "quince": 15, "veinte": 20, "treinta": 30
}

# Cambio de esquema (flag dentro de PLAN)
DE_A_RX = re.compile(
    r"\bde\s+(?:\d(?:[.\-]\d){1,5}(?:/\d{1,2})?|\d{1,2}\s*/\s*\d{1,2})\s+a\s+"
    r"(?:\d(?:[.\-]\d){1,5}(?:/\d{1,2})?|\d{1,2}\s*/\s*\d{1,2})\b",
    re.IGNORECASE,
)
CAMBIO_VERB_RX = re.compile(
    r"\b(cambio|cambiar|modificar|ajustar|pasar\s+a|subir|bajar|aumentar|disminuir|reducir|incrementar|titular|suspender)\b",
    re.IGNORECASE,
)
LUEGO_RX = re.compile(r"\b(luego|despues|después|posteriormente)\b", re.IGNORECASE)

def _prox_control_texto(plan_txt: Optional[str]) -> str:
    if not plan_txt:
        return "No se encuentra dato"

    m = REL_CONTROL_RX.search(plan_txt)
    if m:
        num_raw = m.group("num").lower()
        num = str(_NUM_WORDS.get(num_raw, num_raw))
        u = m.group("u").lower()
        if u.startswith("d"):
            u_txt = "dias"
        elif u.startswith("sem"):
            u_txt = "semanas"
        elif u.startswith("mes"):
            u_txt = "mes" if num in ("1", "1.0") else "meses"
        else:
            u_txt = "horas"
        return f"en {num} {u_txt}"

    m2 = FECHA_CONTROL_RX.search(plan_txt)
    if m2:
        return f"el {m2.group(1)}"

    m3 = CONTROL_MES_RX.search(plan_txt)
    if m3:
        return f"en {m3.group('mes').lower()}"

    return "No se encuentra dato"


def _hay_cambio_esquema_plan(plan_txt: Optional[str]) -> str:
    if not plan_txt:
        return "No se encuentra dato"

    if DE_A_RX.search(plan_txt):
        return "Sí"

    if CAMBIO_VERB_RX.search(plan_txt) and (SCHEME_RX.search(plan_txt) is not None):
        return "Sí"

    # dos regímenes separados por "luego"
    toks = list(SCHEME_RX.finditer(plan_txt))
    toks = sorted(toks, key=lambda m: m.start())
    for a, b in zip(toks, toks[1:]):
        if LUEGO_RX.search(plan_txt[a.end():b.start()]):
            return "Sí"

    return "No se encuentra dato"


def extraer_info_plan(relato: str, fecha_consulta: Optional[str] = None) -> Dict[str, Any]:
    """
    Devuelve info a nivel PLAN (consulta):
      - PLAN_texto_limpio
      - PLAN_psicoeducacion, PLAN_psicoterapia, PLAN_psico_unificado
      - PLAN_reposicion_medicacion (dentro del PLAN)
      - REPO_medicacion (en todo el relato)
      - PLAN_prox_control_texto
      - PLAN_cambio_esquema
    """
    plan = _extraer_bloque_plan(relato)

    # Psicoeducación / Psicoterapia
    pe = "No se encuentra dato"
    pt = "No se encuentra dato"
    if plan:
        m = PSICOEDU_RX.search(plan)
        if m:
            pe = "No" if _negado(plan, m.start()) else "Sí"
        m = PSICOTER_RX.search(plan)
        if m:
            pt = "No" if _negado(plan, m.start()) else "Sí"

    psico_uni = "Sí" if (pe == "Sí" or pt == "Sí") else "No se encuentra dato"

    # Reposición
    repo_plan = "Sí" if (plan and REPO_KEY_RX.search(plan)) else "No se encuentra dato"
    repo_global = "Sí" if (isinstance(relato, str) and REPO_KEY_RX.search(limpiar_texto(relato))) else "No se encuentra dato"

    # Próximo control
    prox_txt = _prox_control_texto(plan)

    # Cambio de esquema (flag)
    cambio_plan = _hay_cambio_esquema_plan(plan)

    return {
        "PLAN_texto_limpio": plan or "",
        "PLAN_psicoeducacion": pe,
        "PLAN_psicoterapia": pt,
        "PLAN_psico_unificado": psico_uni,
        "PLAN_prox_control_texto": prox_txt,
        "PLAN_reposicion_medicacion": repo_plan,
        "REPO_medicacion": repo_global,
        "PLAN_cambio_esquema": cambio_plan,
    }


__all__ = ["extraer_meds_con_dosis", "extraer_info_plan"]
