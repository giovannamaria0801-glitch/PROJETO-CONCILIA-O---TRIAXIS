"""Orquestração do processamento (usada pela interface e pelos testes)."""
import hashlib
from . import FONTES
from .conciliacao import conciliar
from .importacao import normalizar
from .regras import regras_ativas, garantir_padrao
import pandas as pd


def preparar(fonte, nome, conteudo, df, mapa, fator_sinal=1, decimal="auto", excluir_invalidas=False):
    reg, log, prob = normalizar(df, mapa, fonte, nome, fator_sinal, decimal, excluir_invalidas)
    return dict(nome=nome, sha=hashlib.sha256(conteudo).hexdigest(), reg=reg, log=log, problemas=prob,
                bloqueado=any(p["nivel"] == "erro" for p in prob))


def executar(db, usuario, preparados):
    """preparados: {fonte: preparar(...)}. Bloqueia se houver erros de validação."""
    if not preparados: raise ValueError("Nenhum arquivo importado.")
    if any(p["bloqueado"] for p in preparados.values()):
        raise ValueError("Há erros de validação pendentes; corrija antes de processar.")
    garantir_padrao(db)
    regras, depara = regras_ativas(db), db.depara()
    regs = {f: p["reg"] for f, p in preparados.items()}
    res = conciliar(regs, depara, regras)
    dados = {f: (p["nome"], p["sha"], p["reg"], p["log"]) for f, p in preparados.items()}
    periodos = sorted({x for r in regs.values() if "periodo" in r for x in r["periodo"].dropna().unique()})
    res["resumo"]["periodos"] = periodos
    rid = db.salvar_run(usuario, {f: p["nome"] for f, p in preparados.items()}, depara, regras, {"fontes": list(preparados)}, res["resumo"], res["hash"], dados)
    res["divergencias"] = db.upsert_divergencias(rid, res["divergencias"], usuario)
    return res, rid


def reexecutar(db, run_id):
    """Reprocessa com os mesmos dados, o mesmo de-para e as mesmas regras do processamento original."""
    c = db.carregar_run(run_id)
    res = conciliar(c["registros"], c["depara"], c["regras"])
    return res, res["hash"] == c["run"]["hash_resultado"]
