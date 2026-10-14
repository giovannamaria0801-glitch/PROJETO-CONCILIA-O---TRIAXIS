"""Exportação em Excel/CSV com parâmetros, arquivos, regras, tolerâncias e versão do de-para em cada relatório."""
import io, json
import pandas as pd
from . import NOMES_FONTES as NF


def _planilha(w, nome, df, cab):
    df = df if df is not None and len(df) else pd.DataFrame({"Informação": ["Sem registros para este relatório."]})
    pd.DataFrame({"Parâmetro": list(cab), "Valor": [str(v) for v in cab.values()]}).to_excel(w, sheet_name=nome[:31], index=False, startrow=0)
    df.to_excel(w, sheet_name=nome[:31], index=False, startrow=len(cab) + 2)


def excel(db, resultado, run_id):
    run = db.con.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    regras = json.loads(run["regras_snapshot"])
    cab = {"Processamento": f"#{run_id}", "Data do processamento": run["ts"], "Arquivos utilizados": "; ".join(f"{k}: {v}" for k, v in json.loads(run["arquivos"]).items()),
           "Regras aplicadas": "; ".join(f"{r['id']} v{r['versao']}" for r in regras),
           "Tolerâncias": "; ".join(f"{r['id']}: {r['tolerancia']}" for r in regras),
           "Critério": "Diferença = A − B; valores ausentes não são tratados como zero", "Versão do de-para": f"snapshot do processamento #{run_id}"}
    dv = db.q("SELECT * FROM divergencias")
    dv_run = dv[dv.ultimo_run == run_id].copy() if len(dv) else dv
    if len(dv_run): dv_run["categorias"] = dv_run.categorias.map(lambda s: "; ".join(json.loads(s)))
    cols = ["id", "nivel", "tributo", "periodo", "empresa", "chave", "categorias", "valor_dif", "causa_status", "causa", "status", "responsavel", "prioridade", "prazo", "justificativa"]
    d = dv_run[cols] if len(dv_run) else dv_run
    doc = resultado["doc"]; sem = resultado["sem_mapeamento"]
    ausentes = doc[doc.categorias.str.contains("Documento ausente")] if len(doc) else doc
    dups = doc[doc.categorias.str.contains("duplicidade")] if len(doc) else doc
    por_causa = d.assign(categoria=d.categorias.str.split("; ")).explode("categoria").groupby("categoria").agg(qtd=("id", "count"), soma_abs=("valor_dif", lambda s: s.abs().sum())).reset_index() if len(d) else d
    por_trib = d.groupby("tributo").agg(qtd=("id", "count"), soma_abs_diferencas=("valor_dif", lambda s: s.abs().sum()), maior_diferenca=("valor_dif", lambda s: s.abs().max())).reset_index() if len(d) else d
    por_per = d.groupby("periodo").agg(qtd=("id", "count"), soma_abs_diferencas=("valor_dif", lambda s: s.abs().sum())).reset_index() if len(d) else d
    pend = d.groupby(["responsavel", "status"], dropna=False).size().reset_index(name="qtd") if len(d) else d
    hist = db.q("SELECT * FROM historico WHERE entidade='divergencia' ORDER BY ts")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        _planilha(w, "Conciliação completa", doc, cab); _planilha(w, "Saldo por conta", resultado["saldo"], cab)
        _planilha(w, "Somente divergências", d, cab); _planilha(w, "Resumo por tributo", por_trib, cab)
        _planilha(w, "Resumo por período", por_per, cab); _planilha(w, "Contas sem mapeamento", sem, cab)
        _planilha(w, "Documentos ausentes", ausentes, cab); _planilha(w, "Possíveis duplicidades", dups, cab)
        _planilha(w, "Divergências por causa", por_causa, cab); _planilha(w, "Pendências por responsável", pend, cab)
        _planilha(w, "Histórico de resoluções", hist, cab)
    return buf.getvalue()


def csv(df):
    return df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
