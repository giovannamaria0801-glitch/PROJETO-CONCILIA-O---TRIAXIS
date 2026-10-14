"""Normalização: toda transformação preserva o valor original e é registrável em log."""
import math, re
from datetime import date, datetime
import pandas as pd


def _vazio(v):
    return v is None or v is pd.NaT or (isinstance(v, float) and math.isnan(v))


def texto(v):
    if _vazio(v):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s or None


def ident(v):
    """Identificadores em maiúsculas; zeros à esquerda são preservados (nunca converte para número)."""
    s = texto(v)
    return s.upper() if s else None


def chave_acesso(v):
    s = texto(v)
    return re.sub(r"\s", "", s) if s else None


def parse_valor(v, decimal="auto"):
    """Retorna float, ou None se vazio (ausência != zero). Levanta ValueError se inválido."""
    if _vazio(v):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = str(v).strip()
    if s == "" or s.lower() in ("nan", "none", "null"):
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1]
    s = re.sub(r"(R\$|US\$|\$|€|\s)", "", s)
    if s.endswith("-"):
        neg, s = True, s[:-1]
    if s.startswith("-"):
        neg, s = True, s[1:]
    s = s.lstrip("+")
    if not re.fullmatch(r"[\d.,]+", s):
        raise ValueError(f"valor monetário inválido: {v!r}")
    if decimal == ",":
        s = s.replace(".", "").replace(",", ".")
    elif decimal == ".":
        s = s.replace(",", "")
    elif "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".") if s.count(",") == 1 else s.replace(",", "")
    elif "." in s and (s.count(".") > 1 or (re.fullmatch(r"\d{1,3}\.\d{3}", s) and not s.startswith("0."))):
        s = s.replace(".", "")  # "1.234" => milhar (padrão BR). Use decimal="." para forçar o contrário.
    try:
        x = float(s)
    except ValueError:
        raise ValueError(f"valor monetário inválido: {v!r}")
    return round(-x if neg else x, 2)


def parse_data(v):
    if _vazio(v):
        return None
    if isinstance(v, (datetime, pd.Timestamp)):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip().split(" ")[0].split("T")[0]
    if not s:
        return None
    for f in ("%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y", "%d-%m-%Y", "%Y%m%d", "%d/%m/%y"):
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            pass
    raise ValueError(f"data inválida: {v!r}")


def parse_periodo(v):
    """Retorna 'AAAA-MM'."""
    if _vazio(v):
        return None
    if isinstance(v, (datetime, date, pd.Timestamp)):
        return f"{v.year:04d}-{v.month:02d}"
    s = str(v).strip()
    m = re.fullmatch(r"(\d{4})[-/.]?(\d{1,2})", s)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{m.group(1)}-{int(m.group(2)):02d}"
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{4})", s)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{m.group(2)}-{int(m.group(1)):02d}"
    d = parse_data(s)
    return f"{d.year:04d}-{d.month:02d}"
