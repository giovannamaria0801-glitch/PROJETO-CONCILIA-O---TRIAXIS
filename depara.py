"""Resolução de contas via de-para: nunca trata mapeamento ambíguo, pendente ou fora de vigência como aprovado."""
import pandas as pd
COL = {"SAP": "conta_sap", "TAXONE": "conta_taxone", "AA": "conta_aa"}


def _ok(v): return v is not None and not (isinstance(v, float) and pd.isna(v)) and str(v).strip() != ""


def resolver(depara, fonte, conta, empresa, periodo):
    base = dict(status="SEM_MAPEAMENTO", ref=None, descricao=None, regra=None, vigencia=None, aprovacao=None, ids=[])
    if not _ok(conta) or depara is None or depara.empty:
        return base
    c = depara[depara[COL[fonte]].fillna("").astype(str).str.upper() == str(conta).upper()]
    if _ok(empresa):
        c = c[c.empresa.isna() | (c.empresa == "") | (c.empresa == empresa)]
    if c.empty:
        return base
    base["ids"] = c.id.tolist()
    ap = c[c.status == "Aprovado"]
    if ap.empty:
        base.update(status="NAO_APROVADO", aprovacao=", ".join(sorted(set(c.status))), ref=int(c.id.iloc[0]))
        return base
    if _ok(periodo):
        ini = ap.vig_ini.fillna("").astype(str).str[:7]; fim = ap.vig_fim.fillna("").astype(str).str[:7]
        ap = ap[((ini == "") | (ini <= periodo)) & ((fim == "") | (fim >= periodo))]
        if ap.empty:
            base["status"] = "FORA_VIGENCIA"; return base
    if ap.id.nunique() > 1:
        base["status"] = "AMBIGUO"; base["ids"] = ap.id.tolist(); return base
    r = ap.iloc[0]
    base.update(status="OK", ref=int(r.id), descricao=r.descricao, regra=f"De-para #{int(r.id)} ({r.conta_sap or '—'} / {r.conta_taxone or '—'} / {r.conta_aa or '—'})",
                vigencia=f"{r.vig_ini or 'sem início'} a {r.vig_fim or 'sem fim'}", aprovacao=f"Aprovado por {r.resp_aprov}")
    return base


def validar_cadastro(depara):
    """Alertas: duplicidades, ambiguidades, sem correspondência e vigência encerrada."""
    al = []
    for f, col in COL.items():
        d = depara[depara[col].notna() & (depara[col] != "")]
        for conta, g in d.groupby(col):
            ativos = g[g.status != "Inativo"]
            if len(ativos) > 1:
                al.append(dict(tipo="Código duplicado/ambíguo", fonte=f, conta=conta, ids=ativos.id.tolist()))
    for _, r in depara[depara.status != "Inativo"].iterrows():
        faltam = [f for f, c in COL.items() if not _ok(r[c])]
        if faltam:
            al.append(dict(tipo="Sem correspondência", fonte=",".join(faltam), conta=f"#{r.id}", ids=[int(r.id)]))
    return al
