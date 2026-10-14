"""Motor de conciliação: documento (com chaves em cascata), saldo por conta mapeada e contas sem mapeamento."""
import hashlib, json
import pandas as pd
from . import FONTES, NOMES_FONTES as NF
from .depara import resolver
from .diagnostico import diagnosticar, brl
from .regras import regra_para

PARES = [("SAP", "TAXONE"), ("SAP", "AA"), ("TAXONE", "AA")]
CAMPOS = ["empresa", "estabelecimento", "periodo", "num_doc", "chave_acesso", "doc_contabil", "item", "conta", "tributo", "base", "aliquota",
          "regra_calculo", "data_documento", "data_lancamento", "valor", "valor_original", "regra_valor", "dados_originais", "registro_id", "arquivo", "linha_origem"]
MAP_TXT = {"SEM_MAPEAMENTO": "Conta sem mapeamento", "NAO_APROVADO": "Conta sem mapeamento", "FORA_VIGENCIA": "Conta sem mapeamento", "AMBIGUO": "Mapeamento ambíguo"}


def _nn(v): return v is not None and not (isinstance(v, float) and pd.isna(v))


def _uf(parent, x):
    while parent.setdefault(x, x) != x:
        parent[x] = parent[parent[x]]; x = parent[x]
    return x


def _preparar(regs, depara):
    frames = []
    for f in FONTES:
        d = regs.get(f)
        if d is None or d.empty: continue
        d = d.copy()
        for c in CAMPOS:
            if c not in d: d[c] = None
        d["fonte"] = f
        frames.append(d[["fonte"] + CAMPOS])
    df = pd.concat(frames, ignore_index=True).astype(object).where(lambda x: x.notna(), None)
    cache = {}
    ms = []
    for r in df.itertuples():
        k = (r.fonte, r.conta, r.empresa, r.periodo)
        if k not in cache: cache[k] = resolver(depara, r.fonte, r.conta, r.empresa, r.periodo)
        ms.append(cache[k])
    df["mapa"] = ms
    # clusters por chaves compartilhadas (chave de acesso > nº doc+empresa > doc contábil+item+empresa)
    parent, tipo = {}, {}
    for i, r in df.iterrows():
        keys = []
        if r.chave_acesso: keys.append(("1-CHAVE", f"{r.chave_acesso}"))
        if r.num_doc: keys.append(("2-DOC", f"{r.empresa}|{r.num_doc}"))
        if r.doc_contabil: keys.append(("3-CONT", f"{r.empresa}|{r.doc_contabil}|{r.item or ''}"))
        for t, k in keys:
            parent_k = f"{t}:{k}"; _uf(parent, f"R{i}"); parent[_uf(parent, f"R{i}")] = _uf(parent, parent_k)
    df["cluster"] = [_uf(parent, f"R{i}") if (r.chave_acesso or r.num_doc or r.doc_contabil) else f"SEMCHAVE:{r.fonte}:{r.arquivo}:{r.linha_origem}" for i, r in df.iterrows()]
    lab = {}
    for i, r in df.iterrows():
        cands = []
        if r.chave_acesso: cands.append(("1-CHAVE", r.chave_acesso))
        if r.num_doc: cands.append(("2-DOC", r.num_doc))
        if r.doc_contabil: cands.append(("3-CONT", f"{r.doc_contabil}/{r.item or '1'}"))
        if cands:
            lab.setdefault(r.cluster, []).extend(cands)
    df["tipo_chave"] = df.cluster.map(lambda c: sorted(lab[c])[0][0][2:] if c in lab else "SEM_CHAVE")
    df["chave"] = df.cluster.map(lambda c: sorted(lab[c])[0][1] if c in lab else None)
    df["chave"] = [r.chave if r.chave else f"{NF[r.fonte]} linha {r.linha_origem}" for r in df.itertuples()]
    df["tributo_n"] = df.tributo.map(lambda t: t or "N/D")
    return df


def _soma(vals):
    v = [x for x in vals if _nn(x)]
    return round(sum(v), 2) if v else None


def _pares(vals, disp, tol):
    out = []
    for a, b in PARES:
        if a in disp and b in disp:
            va, vb = vals[a], vals[b]
            if va is None or vb is None:
                out.append(dict(par=f"{NF[a]} × {NF[b]}", a=a, b=b, dif=None, status="Não comparável", formula=f"{NF[a]} − {NF[b]}: dado ausente em {NF[a] if va is None else NF[b]} (ausência ≠ zero)"))
            else:
                dif = round(va - vb, 2)
                out.append(dict(par=f"{NF[a]} × {NF[b]}", a=a, b=b, dif=dif, status="Diferente" if abs(dif) > tol else "Igual",
                                formula=f"{NF[a]} − {NF[b]} = {brl(va)} − {brl(vb)} = {brl(dif)} (tolerância {brl(tol)})"))
    return out


def _regs_ref(g):
    return [{k: (None if not _nn(r[k]) else (str(r[k]) if k in ("data_documento", "data_lancamento") else r[k])) for k in
             ("registro_id", "linha_origem", "arquivo", "valor", "valor_original", "regra_valor", "conta", "num_doc", "chave_acesso", "doc_contabil", "item", "periodo", "data_documento", "data_lancamento", "base", "aliquota")}
            for _, r in g.iterrows()]


def conciliar(regs, depara, regras):
    df = _preparar(regs, depara)
    disp = [f for f in FONTES if f in set(df.fonte)]
    linhas, divs = [], []
    for (cl, trib), g in df.groupby(["cluster", "tributo_n"], sort=False):
        regra = regra_para(regras, "documento", trib); tol = float(regra["tolerancia"])
        vals, pres, per, bases, contas, regs_ref, mapi = {}, {}, {}, {}, {}, {}, {}
        for f in FONTES:
            gf = g[g.fonte == f]; pres[f] = len(gf) > 0
            vals[f] = _soma(gf.valor) if len(gf) else None
            per[f] = sorted({p for p in gf.periodo if p}); bases[f] = _soma(gf.base) if len(gf) else None
            contas[f] = sorted({c for c in gf.conta if c}); regs_ref[f] = _regs_ref(gf)
            mapi[f] = [dict(conta=r.conta, **r.mapa) for r in gf.itertuples()]
        cats, ev = [], dict(chave=g.chave.iloc[0], total_regs={f: int((df.fonte == f).sum()) for f in disp}, tributos={}, campos_ausentes=[])
        sem_chave = g.tipo_chave.iloc[0] == "SEM_CHAVE"
        if sem_chave: cats += ["Registro não comparável"]
        ausentes, classif = [], []
        for f in disp:
            if not pres[f] and not sem_chave:
                outro = df[(df.cluster == cl) & (df.fonte == f)]
                (classif if len(outro) else ausentes).append(f)
        if ausentes: cats.append("Documento ausente"); ev["ausentes"] = ausentes
        if classif:
            cats.append("Divergência de classificação fiscal"); ev["classificacao"] = classif
            ev["tributos"] = {NF[f]: sorted(set(df[(df.cluster == cl) & (df.fonte == f)].tributo_n)) for f in disp}
        if any(pres[f] and vals[f] is None for f in FONTES): cats.append("Dados insuficientes")
        pares = _pares(vals, [f for f in disp if pres[f] or sem_chave is False], tol)
        pares = [p for p in pares]
        if any(p["status"] == "Diferente" for p in pares): cats.append("Diferença de valor")
        for p in pares:
            va, vb = vals[p["a"]], vals[p["b"]]
            if va is not None and vb is not None and abs(va) > tol and abs(va + vb) <= tol:
                cats.append("Convenção de sinal divergente"); ev["sinal"] = f"{NF[p['a']]} = {brl(va)} e {NF[p['b']]} = {brl(vb)} (mesmo módulo, sinais opostos)"
        presentes = [f for f in FONTES if pres[f]]
        if len({tuple(per[f]) for f in presentes if per[f]}) > 1:
            cats.append("Divergência de período"); ev["periodos"] = {NF[f]: per[f] for f in presentes}
        dups = [f for f in presentes if g[g.fonte == f].duplicated(subset=["valor", "conta", "item"], keep=False).any() and len(g[g.fonte == f]) > 1]
        if dups: cats.append("Possível duplicidade"); ev["dup"] = "; ".join(f"{NF[f]}: {len(g[g.fonte == f])} registros com mesmo valor/conta/item (linhas {[int(x) for x in g[g.fonte == f].linha_origem]})" for f in dups)
        bs = {f: bases[f] for f in presentes if bases[f] is not None}
        if len(bs) >= 2 and max(bs.values()) - min(bs.values()) > tol:
            cats.append("Diferença de base de cálculo"); ev["base"] = "Bases: " + ", ".join(f"{NF[f]} = {brl(v)}" for f, v in bs.items())
        elif len(presentes) >= 2 and len(bs) < 2: ev["campos_ausentes"].append("base")
        rg = {f: sorted({x for x in g[g.fonte == f].regra_calculo if x} | {str(a) for a in g[g.fonte == f].aliquota if _nn(a)}) for f in presentes}
        if len({tuple(v) for v in rg.values() if v}) > 1:
            cats.append("Regra de cálculo divergente"); ev["regra"] = "Regra/alíquota por fonte: " + str({NF[f]: v for f, v in rg.items()})
        flags = {MAP_TXT[m["status"]] for f in presentes for m in mapi[f] if m["status"] != "OK" and m["conta"]}
        if flags:
            cats += sorted(flags); ev["contas"] = str({NF[f]: [(m["conta"], m["status"]) for m in mapi[f]] for f in presentes})
        cats = list(dict.fromkeys(cats))
        difs = [abs(p["dif"]) for p in pares if p["dif"] is not None]
        conc = (not cats) and len(presentes) >= 2 and all(p["status"] == "Igual" for p in pares) and len(disp) >= 2
        row = dict(nivel="documento", chave=ev["chave"], tipo_chave=g.tipo_chave.iloc[0], tributo=trib, empresa=g.empresa.iloc[0], estabelecimento=g.estabelecimento.iloc[0],
                   periodo=next((p for f in FONTES for p in per[f]), None), status_conc="Conciliado" if conc else "Divergente" if cats else "Pendente",
                   **{f"valor_{f}": vals[f] for f in FONTES}, **{f"presente_{f}": pres[f] for f in FONTES},
                   **{f"dif_{p['a']}_{p['b']}": p["dif"] for p in pares}, categorias="; ".join(cats))
        linhas.append(row)
        if conc or len(disp) < 2: continue
        if not cats: cats = ["Dados insuficientes"]
        det = dict(identificacao=dict(tributo=trib, periodos={NF[f]: per[f] for f in FONTES}, empresa=row["empresa"], estabelecimento=row["estabelecimento"], contas={NF[f]: contas[f] for f in FONTES}, chave=ev["chave"], tipo_chave=row["tipo_chave"]),
                   comparacao=dict(valores={NF[f]: vals[f] for f in FONTES}, presenca={NF[f]: pres[f] for f in FONTES}, fontes_disponiveis=[NF[f] for f in disp], pares=pares),
                   contas=mapi, registros=regs_ref,
                   regra=dict(id=regra["id"], versao=regra["versao"], nome=regra.get("nome"), vigencia=f"{regra.get('vig_ini') or '—'} a {regra.get('vig_fim') or '—'}", formula=regra.get("formula"), tolerancia=tol,
                              esperado=f"|diferença| ≤ {brl(tol)}", observado=f"maior |diferença| = {brl(max(difs))}" if difs else "sem par comparável", diferenca=max(difs) if difs else None))
        d = dict(categorias=cats, evid=ev)
        hip, ver, cs, msg = diagnosticar(d)
        det.update(categorias=d["categorias"], hipoteses=hip, verificacoes=ver, mensagem=msg)
        divs.append(dict(fingerprint=f"doc|{row['empresa']}|{trib}|{ev['chave']}" if not sem_chave else f"semchave|{cl}", nivel="documento", tributo=trib, periodo=row["periodo"],
                         empresa=row["empresa"], estabelecimento=row["estabelecimento"], chave=ev["chave"], categorias=d["categorias"],
                         causa_status=cs, valor_dif=max(difs) if difs else None, detalhe=det))
    # saldo por conta mapeada + contas sem mapeamento
    saldos, sem_map = [], []
    ok = df[df.mapa.map(lambda m: m["status"] == "OK")]
    for (emp, per_, ref), g in ok.groupby(["empresa", "periodo", ok.mapa.map(lambda m: m["ref"])], dropna=False):
        trib = g.tributo_n.iloc[0]; regra = regra_para(regras, "saldo", trib); tol = float(regra["tolerancia"])
        vals = {f: (_soma(g[g.fonte == f].valor) if (g.fonte == f).any() else None) for f in FONTES}
        pares = _pares(vals, disp, tol)
        cats = (["Diferença de valor"] if any(p["status"] == "Diferente" for p in pares) else []) + (["Documento ausente"] if any(vals[f] is None for f in disp) else [])
        row = dict(nivel="saldo", chave=f"Conta #{ref}", tributo=trib, empresa=emp, periodo=per_, descricao=g.iloc[0]["mapa"]["descricao"], status_conc="Divergente" if cats else "Conciliado",
                   **{f"valor_{f}": vals[f] for f in FONTES}, **{f"dif_{p['a']}_{p['b']}": p["dif"] for p in pares}, categorias="; ".join(cats))
        saldos.append(row)
        if cats:
            difs = [abs(p["dif"]) for p in pares if p["dif"] is not None]
            ev = dict(chave=f"Conta #{ref}", ausentes=[f for f in disp if vals[f] is None], total_regs={f: int((df.fonte == f).sum()) for f in disp}, campos_ausentes=[])
            d = dict(categorias=list(cats), evid=ev); hip, ver, cs, msg = diagnosticar(d)
            det = dict(identificacao=dict(tributo=trib, periodos={"": [per_]}, empresa=emp, estabelecimento=None, contas={NF[f]: sorted({c for c in g[g.fonte == f].conta if c}) for f in FONTES}, chave=f"Conta #{ref}", tipo_chave="SALDO"),
                       comparacao=dict(valores={NF[f]: vals[f] for f in FONTES}, presenca={NF[f]: vals[f] is not None for f in FONTES}, fontes_disponiveis=[NF[f] for f in disp], pares=pares),
                       contas=[dict(conta=r.conta, **r.mapa) for r in g.itertuples()], registros={f: _regs_ref(g[g.fonte == f]) for f in FONTES},
                       regra=dict(id=regra["id"], versao=regra["versao"], nome=regra.get("nome"), vigencia="—", formula=regra.get("formula"), tolerancia=tol, esperado=f"|diferença| ≤ {brl(tol)}", observado=f"maior |diferença| = {brl(max(difs))}" if difs else "sem par comparável", diferenca=max(difs) if difs else None),
                       categorias=d["categorias"], hipoteses=hip, verificacoes=ver, mensagem=msg)
            divs.append(dict(fingerprint=f"saldo|{emp}|{per_}|{ref}", nivel="saldo", tributo=trib, periodo=per_, empresa=emp, estabelecimento=None, chave=f"Conta #{ref}",
                             categorias=d["categorias"], causa_status=cs, valor_dif=max(difs) if difs else None, detalhe=det))
    bad = df[df.mapa.map(lambda m: m["status"] != "OK") & df.conta.notna()]
    for (f, conta, emp), g in bad.groupby(["fonte", "conta", "empresa"], dropna=False):
        m = g.iloc[0]["mapa"]; cat = MAP_TXT[m["status"]]
        sem_map.append(dict(fonte=NF[f], conta=conta, empresa=emp, situacao=m["status"], registros=len(g), valor_total=_soma(g.valor)))
        ev = dict(chave=f"{conta}", contas=f"{NF[f]} conta {conta}: {m['status']}", total_regs={}, campos_ausentes=[])
        d = dict(categorias=[cat], evid=ev); hip, ver, cs, msg = diagnosticar(d)
        det = dict(identificacao=dict(tributo=g.tributo_n.iloc[0], periodos={NF[f]: sorted({p for p in g.periodo if p})}, empresa=emp, estabelecimento=None, contas={NF[f]: [conta]}, chave=conta, tipo_chave="CONTA"),
                   comparacao=dict(valores={NF[f]: _soma(g.valor)}, presenca={NF[f]: True}, fontes_disponiveis=[NF[f]], pares=[]), contas=[dict(conta=conta, **m)], registros={f: _regs_ref(g)},
                   regra=dict(id="DE-PARA", versao=0, nome="Resolução de conta via de-para", vigencia="—", formula="conta da fonte → de-para aprovado e vigente", tolerancia=0, esperado="1 mapeamento aprovado e vigente", observado=m["status"], diferenca=None),
                   categorias=d["categorias"], hipoteses=hip, verificacoes=ver, mensagem=msg)
        divs.append(dict(fingerprint=f"conta|{f}|{conta}|{emp}|{m['status']}", nivel="conta", tributo=g.tributo_n.iloc[0], periodo=sorted({p for p in g.periodo if p})[0] if g.periodo.notna().any() else None,
                         empresa=emp, estabelecimento=None, chave=conta, categorias=d["categorias"], causa_status=cs, valor_dif=_soma(g.valor), detalhe=det))
    doc_df, saldo_df = pd.DataFrame(linhas), pd.DataFrame(saldos)
    resumo = dict(fontes=[NF[f] for f in disp], registros=int(len(df)), docs_comparados=len(doc_df), conciliados=int((doc_df.status_conc == "Conciliado").sum()) if len(doc_df) else 0,
                  divergencias=len(divs), contas_sem_mapeamento=len(sem_map))
    h = hashlib.sha256(json.dumps(sorted((d["fingerprint"], d["valor_dif"], d["categorias"]) for d in divs), default=str).encode()).hexdigest()
    return dict(resumo=resumo, doc=doc_df, saldo=saldo_df, sem_mapeamento=pd.DataFrame(sem_map), divergencias=divs, hash=h)
