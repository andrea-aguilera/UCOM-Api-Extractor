# -*- coding: utf-8 -*-
from __future__ import annotations
"""
Extractor de medicamentos, dosis y esquema (tolerante a OCR y alias).
Exporta: extraer_meds_con_dosis(texto: str, incluir_span: bool = True) -> List[Dict]
"""
import re
import unicodedata
from collections import defaultdict
from typing import Dict, List, Any
from rapidfuzz import fuzz, process

# 1) Diccionario validado (canónico -> alias)
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
    "levomepromazina": ["levomepromacina","levopromazina","levomep","levomeproma", "Levomepromazina"],
}

# 2) Normalización / limpieza
def quitar_tildes(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn")

def limpiar_texto(texto: str) -> str:
    if not isinstance(texto, str):
        return ""
    t = quitar_tildes(texto.lower())
    # Correcciones OCR 0/1/5 dentro de palabras
    t = re.sub(r'(?<=[a-z])0(?=[a-z])', 'o', t)
    t = re.sub(r'(?<=[a-z])1(?=[a-z])', 'l', t)
    t = re.sub(r'(?<=[a-z])5(?=[a-z])', 's', t)
    # Signos ¡!¿?
    t = t.translate(str.maketrans('', '', '¡!¿?'))
    # Colapsar repeticiones de 3+
    t = re.sub(r'(.)\1{2,}', r'\1', t)
    # Mantener letras/números/espacios y . - / :
    t = re.sub(r"[^a-z0-9\s\./:-]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

# 3) Índices y regex
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

PLAN_ITEM_RX = re.compile(r"(?:^|\s)(\d+)\.\s+(.*?)(?=(?:\s\d+\.\s)|\Z)", re.DOTALL)
def dividir_en_items_plan(t_norm: str):
    items = []
    for m in PLAN_ITEM_RX.finditer(t_norm):
        items.append({"n": m.group(1), "texto": m.group(2).strip(), "start": m.start(2), "end": m.end(2)})
    if not items:
        items = [{"n": None, "texto": t_norm, "start": 0, "end": len(t_norm)}]
    return items

# 4) Helpers OCR
def _squeeze_dupes_letters(s: str) -> str:
    return re.sub(r'([a-z])\1+', r'\1', s)
def _denoise_scheme_text(s: str) -> str:
    s = re.sub(r'([:./-])\1+', r'\1', s); s = re.sub(r'(\d)\1+', r'\1', s); return s
def _collapse_digit_pairpairs(num_str: str) -> str:
    if not num_str: return num_str
    m = re.fullmatch(r"(\d)\1(\d)\2", num_str)
    return (m.group(1) + m.group(2)) if m else num_str
def _collapse_dup_digits(num_str: str) -> str:
    return re.sub(r'(\d)\1+', r'\1', num_str)
def _normalize_mg_unit(s: str) -> str:
    if not s: return ""
    MG_FUZZY = r"m+\s*g+"
    return re.sub(MG_FUZZY, "mg", s)
def _looks_like_ocr_dup(context: str, unit_raw: str) -> bool:
    if not context: context = ""
    if not unit_raw: unit_raw = ""
    dup_letters = re.search(r'([a-z])\1{1,}', context) is not None
    dup_seps    = re.search(r'([:./-])\1{1,}', context) is not None
    dup_unit    = re.search(r'm{2,}\s*g+|m+\s*g{2,}|m{2,}g{2,}', unit_raw) is not None
    return dup_letters or dup_seps or dup_unit

# 5) Dosis y esquema
MG_FUZZY = r"m+\s*g+"  # mg tolerante a OCR
UNIT_RX = r"(?:%s|g|mcg|µg|ug|ml|gota(?:s)?|comp(?:r?imidos?)?|cp|tab(?:s)?|caps?)" % MG_FUZZY
NUM = r"\d{1,4}(?:[.,]\d+)?"
DOSE_WITH_UNIT = re.compile(rf"\b(?P<num>{NUM})\s*(?P<unit>{UNIT_RX})\b")
DOSE_NEAR_UNIT_CAP = re.compile(rf"\b(?P<num>{NUM})(?:\s|[^\w]){{0,8}}(?P<unit>{UNIT_RX})\b")

def _normalize_dosis(num: str, unit: str, *, context: str = "", unit_raw: str = "") -> str:
    if _looks_like_ocr_dup(context, unit_raw or unit):
        num = _collapse_dup_digits(num)
    num_norm  = _collapse_digit_pairpairs(num)
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

# Esquemas: 0.0.1 ; 1/2 ; 0.0.1/2 ; "... o 1"
SCHEME_DOTTED = r"\b\d(?:[.]\d){1,5}\b"
SCHEME_FRAC_SIMPLE = r"\b\d\s*/\s*\d\b"
SCHEME_DOTTED_FRAC = r"\b\d(?:[.]\d){1,5}\s*/\s*\d\b"
SCHEME_ALT = r"(?:\s*o\s*(?:\d(?:[.]\d){1,5}|\d\s*/\s*\d))"
SCHEME_RX = re.compile(rf"(?:{SCHEME_DOTTED_FRAC}|{SCHEME_DOTTED}|{SCHEME_FRAC_SIMPLE})(?:{SCHEME_ALT})?", re.IGNORECASE)

def _normalize_scheme(s: str) -> str:
    s = re.sub(r"\s+", "", s); s = s.replace(",", "."); s = re.sub(r"([./]){2,}", r"\1", s); return s
def _sub_bloque_para_esquema(sub: str) -> str:
    p = sub.find(":")
    if p != -1: return sub[p+1:]
    m = DOSE_WITH_UNIT.search(sub) or DOSE_NEAR_UNIT_CAP.search(sub)
    return sub[m.end():] if m else sub
def _pick_schemes(texto: str):
    texto_clean = _denoise_scheme_text(texto)
    out, seen = [], set()
    for m in SCHEME_RX.finditer(texto_clean):
        for p in re.split(r"\s*o\s*", m.group(0), flags=re.IGNORECASE):
            p = _normalize_scheme(p)
            if p and p not in seen:
                seen.add(p); out.append(p)
    return out

# 6) Extracción principal
def extraer_meds_con_dosis(texto: str, incluir_span: bool = True) -> List[Dict[str, Any]]:
    if not isinstance(texto, str):
        return []
    t_norm = limpiar_texto(texto)
    resultados: List[Dict[str, Any]] = []
    items = dividir_en_items_plan(t_norm)

    for it in items:
        bloque = it["texto"]; base = it["start"]
        hallados = []; vistos_canon = set()

        # Regex exacto de alias
        for m in patron_alias.finditer(bloque):
            alias_norm = m.group(1); canon = alias_a_canonico.get(alias_norm)
            if not canon: continue
            pos_abs = base + m.start()
            hallados.append((canon, alias_norm, pos_abs, base + m.end(), "regex"))
            vistos_canon.add(canon)

        # Fallback fuzzy sobre tokens con letras duplicadas
        for tm in re.finditer(r"\b[a-z0-9]{5,40}\b", bloque):
            tok = tm.group(0); tok_s = _squeeze_dupes_letters(tok)
            if tok_s == tok or len(tok_s) < 5: continue
            cand_pool = aliases_by_first.get(tok_s[0], alias_lista)
            match = process.extractOne(tok_s, cand_pool, scorer=fuzz.ratio, score_cutoff=90)
            if not match: continue
            alias_hit, score, _ = match
            if len(tok_s) / len(alias_hit) < 0.6: continue
            if tok_s[-1] != alias_hit[-1]: continue
            canon = alias_a_canonico[alias_hit]
            if canon in vistos_canon: continue
            pos_abs = base + tm.start()
            hallados.append((canon, alias_hit, pos_abs, base + tm.end(), "fuzzy_dupes", tok))
            vistos_canon.add(canon)

        # Enriquecer con dosis/esquema
        for item in sorted(hallados, key=lambda x: x[2]):
            if len(item) == 6:
                canon, alias_match, pos_abs_i, pos_abs_f, metodo, alias_ocr = item
            else:
                canon, alias_match, pos_abs_i, pos_abs_f, metodo = item; alias_ocr = None

            start_local = pos_abs_i - base
            sub = bloque[start_local: start_local + 220]
            dosis   = _pick_dose(sub)
            sub_esq = _sub_bloque_para_esquema(sub)
            esquemas = _pick_schemes(sub_esq)

            salida: Dict[str, Any] = {
                "med": canon, "alias": alias_match,
                "dosis": dosis or None,
                "esquema": ";".join(esquemas) if esquemas else None,
                "pos": pos_abs_i, "alias_ocr": alias_ocr
            }
            if incluir_span:
                salida["span"] = [pos_abs_i, pos_abs_f]
                salida["contexto"] = sub[:180]
            resultados.append(salida)
    return resultados

__all__ = ["extraer_meds_con_dosis"]
