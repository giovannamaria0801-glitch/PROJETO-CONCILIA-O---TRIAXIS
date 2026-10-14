"""Regras de conciliação versionadas. Regras críticas exigem aprovação; cada run guarda um snapshot das regras usadas."""
import json
from .db import agora

DIRETOS = {"IRPJ", "CSLL"}  # configurável pela equipe Fiscal
PADRAO = [
    dict(id="REG-DOC-001", nome="Comparação por documento", descricao="Compara o valor do imposto por documento entre as fontes.",
         tributo="*", tipo="documento", campos="chave_acesso|num_doc|doc_contabil, valor",
         formula="dif = valor_A − valor_B; diverge se |dif| > tolerância", tolerancia=0.01),
    dict(id="REG-SLD-001", nome="Conciliação de saldo por conta", descricao="Compara o saldo por empresa, período e conta mapeada no de-para.",
         tributo="*", tipo="saldo", campos="empresa, periodo, conta (de-para), valor",
         formula="dif = Σvalor_A − Σvalor_B; diverge se |dif| > tolerância", tolerancia=0.01),
]


def grupo_tributo(t):
    return "Direto" if (t or "").upper() in DIRETOS else "Indireto"


def garantir_padrao(db):
    for r in PADRAO:
        if not db.con.execute("SELECT 1 FROM regras WHERE id=?", (r["id"],)).fetchone():
            db.x("INSERT INTO regras VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (r["id"], 1, r["nome"], r["descricao"], r["tributo"], r["tipo"], r["campos"], r["formula"], r["tolerancia"],
                  "2026-01-01", None, "Aprovada", "sistema", "sistema", "Regra padrão do MVP", agora()))


def regras_ativas(db):
    """Última versão aprovada de cada regra (lista de dicts — snapshot gravado em cada processamento)."""
    df = db.q("SELECT * FROM regras WHERE status='Aprovada'")
    if df.empty: return []
    df = df.sort_values("versao").groupby("id").tail(1)
    return df.to_dict("records")


def salvar_regra(db, r, usuario):
    """Cria nova versão (nunca sobrescreve). Nasce 'Pendente de aprovação'."""
    if not r.get("justificativa"): raise ValueError("Informe a justificativa.")
    v = (db.con.execute("SELECT MAX(versao) FROM regras WHERE id=?", (r["id"],)).fetchone()[0] or 0) + 1
    db.x("INSERT INTO regras VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
         (r["id"], v, r["nome"], r.get("descricao"), r.get("tributo", "*"), r["tipo"], r.get("campos"), r.get("formula"),
          float(r["tolerancia"]), r.get("vig_ini"), r.get("vig_fim"), "Pendente", usuario, None, r["justificativa"], agora()))
    db.hist(usuario, "regra", f"{r['id']} v{v}", "criada", json.dumps(r, default=str))
    return v


def aprovar_regra(db, id_, versao, aprovador):
    cria = db.con.execute("SELECT resp_criacao FROM regras WHERE id=? AND versao=?", (id_, versao)).fetchone()
    if cria and cria[0] == aprovador:
        raise ValueError("O aprovador deve ser diferente de quem criou a regra (segregação de funções).")
    db.x("UPDATE regras SET status='Aprovada', resp_aprov=? WHERE id=? AND versao=?", (aprovador, id_, versao))
    db.hist(aprovador, "regra", f"{id_} v{versao}", "aprovada")


def regra_para(regras, tipo, tributo):
    cand = [r for r in regras if r["tipo"] == tipo and r["tributo"] in ("*", tributo)]
    if not cand:
        return dict(id="SEM-REGRA", versao=0, nome="Padrão técnico", tolerancia=0.01, formula="|dif| > 0,01", vig_ini=None, vig_fim=None)
    cand.sort(key=lambda r: (r["tributo"] != tributo, -r["versao"]))
    return cand[0]
