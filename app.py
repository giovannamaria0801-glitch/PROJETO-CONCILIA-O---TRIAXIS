"""TRIAXIS — Tax Reconciliation & Control. Interface Streamlit (protótipo local, somente leitura sobre os dados de origem)."""
import io, json, os
from datetime import date
import pandas as pd
import streamlit as st
from triaxis import FONTES, NOMES_FONTES as NF, demo_data, exportacao, gestao, regras as rg, servico
from triaxis.db import Banco
from triaxis.depara import validar_cadastro
from triaxis.diagnostico import brl
from triaxis.importacao import CAMPOS, automap, ler_arquivo

st.set_page_config(page_title="TRIAXIS — Tax Reconciliation & Control", layout="wide")
st.markdown("""<style>
[data-testid=stSidebar]{background:#171717} [data-testid=stSidebar] *{color:#fff!important}
[data-testid=stSidebar] input{color:#171717!important}
h1,h2,h3{color:#171717} [data-testid=stMetric]{background:#F5F5F5;padding:10px 14px;border-left:4px solid #D71920}
.cab{background:#171717;color:#fff;padding:10px 18px;margin:-1rem -1rem 1rem -1rem;display:flex;align-items:center;gap:12px}
.cab b{font-size:1.3rem;letter-spacing:.12em}.cab span{color:#bbb;font-size:.85rem}
</style>""", unsafe_allow_html=True)
LOGO = '<svg width="34" height="34" viewBox="0 0 40 40"><g stroke="#fff" stroke-width="2.5" stroke-linecap="round"><path d="M3 6L22 20"/><path d="M3 34L22 20"/><path d="M3 20H22"/></g><circle cx="29" cy="20" r="8" fill="#D71920"/></svg>'
PAGINAS = ["Dashboard", "Importação de arquivos", "Conciliação fiscal", "Divergências", "Diagnóstico detalhado", "De-para de contas", "Regras fiscais",
           "Tributos diretos", "Tributos indiretos", "Reforma Tributária", "Relatórios", "Histórico de processamentos", "Administração e configurações"]


@st.cache_resource
def banco():
    os.makedirs("dados", exist_ok=True); b = Banco("dados/triaxis.db"); rg.garantir_padrao(b); return b


db = banco()
ss = st.session_state
for k, v in dict(arquivos={}, preparados={}, resultado=None, run_id=None, div_sel=None, pagina="Dashboard").items():
    ss.setdefault(k, v)
rg.DIRETOS = set(db.cfg_get("tributos_diretos", ["IRPJ", "CSLL"]))
st.sidebar.markdown(f"{LOGO} **TRIAXIS**<br><small>Tax Reconciliation & Control</small>", unsafe_allow_html=True)
usuario = st.sidebar.text_input("Usuário (identificação)", value="analista.fiscal")
st.sidebar.radio("Navegação", PAGINAS, key="pagina")
pagina = ss.pagina
st.markdown(f'<div class="cab">{LOGO}<b>TRIAXIS</b><span>Tax Reconciliation & Control · {pagina}</span></div>', unsafe_allow_html=True)


def ir(div_id):
    ss.div_sel = div_id; ss.pagina = "Diagnóstico detalhado"


def divs(filtro=""):
    d = db.q("SELECT * FROM divergencias" + filtro)
    if len(d):
        d["cats"] = d.categorias.map(lambda s: "; ".join(json.loads(s)))
        d["grupo"] = d.tributo.map(rg.grupo_tributo)
    return d


def dif_liquida(det):
    for p in json.loads(det)["comparacao"]["pares"]:
        if p["dif"] is not None: return p["dif"]
    return 0.0


def tabela(df, key, cols, busca=True, tam=25):
    if df.empty:
        st.info("Nenhum registro para os filtros atuais."); return df
    if busca:
        t = st.text_input("Pesquisar", key=f"b_{key}")
        if t: df = df[df.astype(str).apply(lambda c: c.str.contains(t, case=False, na=False)).any(axis=1)]
    pg = st.number_input("Página", 1, max(1, -(-len(df) // tam)), 1, key=f"p_{key}")
    st.caption(f"{len(df)} registro(s)")
    st.dataframe(df[cols].iloc[(pg - 1) * tam: pg * tam], hide_index=True, use_container_width=True)
    return df


def vazio(msg):
    st.info(msg)


# ───────────────────────────── Dashboard
def dashboard(grupo=None, titulo=None, tributos=None):
    d = divs()
    run = db.q("SELECT * FROM runs ORDER BY id DESC LIMIT 1")
    if run.empty:
        vazio("Nenhum dado importado ainda. Vá em **Importação de arquivos**, envie os relatórios SAP, TaxOne e (se houver) da apuração assistida, mapeie as colunas e processe. "
              "Para conhecer o fluxo, use **Carregar dados de demonstração** (fictícios)."); return
    resumo = json.loads(run.resumo.iloc[0])
    c = st.columns(4)
    f1 = c[0].selectbox("Visão", ["Consolidada", "Tributos diretos", "Tributos indiretos"]) if grupo is None else grupo
    if len(d):
        if f1 == "Tributos diretos" or f1 == "Direto": d = d[d.grupo == "Direto"]
        if f1 == "Tributos indiretos" or f1 == "Indireto": d = d[d.grupo == "Indireto"]
        if tributos: d = d[d.tributo.isin(tributos)]
        for i, (lab, col) in enumerate([("Tributo", "tributo"), ("Empresa", "empresa"), ("Período", "periodo")]):
            o = c[i + 1].multiselect(lab, sorted(d[col].dropna().unique())); d = d[d[col].isin(o)] if o else d
        c = st.columns(4)
        for i, (lab, col) in enumerate([("Status", "status"), ("Responsável", "responsavel"), ("Nível", "nivel")]):
            o = c[i].multiselect(lab, sorted(d[col].dropna().unique())); d = d[d[col].isin(o)] if o else d
        cat = c[3].multiselect("Tipo de divergência", sorted({x for s in d.cats for x in s.split("; ")}))
        if cat: d = d[d.cats.map(lambda s: any(x in s for x in cat))]
    st.caption(f"Último processamento: #{run.id.iloc[0]} em {run.ts.iloc[0]} · Período(s): {', '.join(resumo.get('periodos', [])) or '—'} · Fontes: {', '.join(resumo['fontes'])}")
    docs = resumo["docs_comparados"]; conc = resumo["conciliados"]
    k = st.columns(5)
    k[0].metric("Registros processados", resumo["registros"]); k[1].metric("Documentos conciliados", conc)
    k[2].metric("Divergências", len(d)); k[3].metric("% de conciliação (documentos)", f"{(100 * conc / docs):.1f}%" if docs else "—")
    k[4].metric("Contas sem mapeamento", int((d.nivel == "conta").sum()) if len(d) else 0)
    if len(d):
        ab = d.valor_dif.abs().sum(); liq = sum(dif_liquida(x) for x in d.detalhe)
        k = st.columns(5)
        k[0].metric("Soma dos valores absolutos das diferenças", brl(ab)); k[1].metric("Saldo líquido das diferenças", brl(liq))
        k[2].metric("Docs. ausentes / duplicados", f"{int(d.cats.str.contains('Documento ausente').sum())} / {int(d.cats.str.contains('duplicidade').sum())}")
        k[3].metric("Pendentes de análise", int((d.status == "Nova").sum())); k[4].metric("Resolvidas", int(d.status.isin(["Resolvida", "Encerrada"]).sum()))
        st.caption("Critério: por divergência usa-se a maior diferença entre pares de fontes (absoluta) e a diferença assinada do primeiro par comparável (líquida). Valores ausentes não entram como zero.")
        g1, g2, g3 = st.columns(3)
        g1.write("**Divergências por status**"); g1.bar_chart(d.status.value_counts())
        g2.write("**Pendências por responsável**"); g2.bar_chart(d.responsavel.fillna("Sem responsável").value_counts())
        g3.write("**Divergências por tipo**"); g3.bar_chart(d.cats.str.split("; ").explode().value_counts())
        st.subheader("Registros que compõem os indicadores")
        ind = st.radio("Detalhar", ["Todas as divergências", "Aguardando ajuste", "Pendentes de análise", "Resolvidas", "Contas sem mapeamento", "Documentos ausentes", "Possíveis duplicidades"], horizontal=True)
        m = {"Todas as divergências": d, "Aguardando ajuste": d[d.status == "Aguardando ajuste"], "Pendentes de análise": d[d.status == "Nova"], "Resolvidas": d[d.status.isin(["Resolvida", "Encerrada"])],
             "Contas sem mapeamento": d[d.nivel == "conta"], "Documentos ausentes": d[d.cats.str.contains("Documento ausente")], "Possíveis duplicidades": d[d.cats.str.contains("duplicidade")]}[ind]
        tabela(m, "dash", ["id", "nivel", "tributo", "periodo", "chave", "cats", "valor_dif", "status", "responsavel"], busca=False)
    elif docs:
        st.success("Todos os documentos comparados foram conciliados.")


# ───────────────────────────── Importação
def importacao():
    st.write("Envie os relatórios (XLSX, XLS ou CSV). Os arquivos originais não são alterados; as transformações ficam registradas em log.")
    if st.button("Carregar dados de demonstração (fictícios)"):
        dfs, dp = demo_data.gerar()
        for f, df in dfs.items():
            ss.arquivos[f] = dict(nome=f"{f.lower()}_demo.xlsx", conteudo=demo_data.para_xlsx(df.astype(str).replace("nan", "")))
        if db.depara().empty:
            for r in dp.to_dict("records"): db.depara_salvar(r, usuario, "Carga demonstrativa")
        ss.preparados = {}; st.success("Dados fictícios carregados. Valide cada fonte e depois processe.")
    abas = st.tabs([f"Importar {NF[f]}" for f in FONTES])
    for f, aba in zip(FONTES, abas):
        with aba:
            up = st.file_uploader(f"Arquivo {NF[f]}", type=["xlsx", "xls", "csv"], key=f"up_{f}")
            if up: ss.arquivos[f] = dict(nome=up.name, conteudo=up.getvalue()); ss.preparados.pop(f, None)
            a = ss.arquivos.get(f)
            if not a:
                vazio(f"Nenhum arquivo de {NF[f]} carregado." + (" Opcional: a conciliação funciona entre as fontes disponíveis." if f == "AA" else "")); continue
            try: df = ler_arquivo(a["conteudo"], a["nome"])
            except Exception as e: st.error(f"Não foi possível ler o arquivo: {e}"); continue
            st.write(f"**{a['nome']}** — {len(df)} linhas · pré-visualização"); st.dataframe(df.head(15), use_container_width=True)
            modelos = db.modelos(f); esc = st.selectbox("Modelo de mapeamento", ["(reconhecimento automático)"] + list(modelos), key=f"mod_{f}")
            base = modelos.get(esc) if esc in modelos else automap(list(df.columns))
            mapa = {}
            with st.expander("Mapeamento de colunas", expanded=True):
                cols = st.columns(3)
                for i, campo in enumerate(CAMPOS):
                    padrao = base.get(campo); op = ["(não mapear)"] + list(df.columns)
                    v = cols[i % 3].selectbox(campo, op, index=op.index(padrao) if padrao in op else 0, key=f"m_{f}_{campo}")
                    if v != "(não mapear)": mapa[campo] = v
            c = st.columns(4)
            fator = c[0].selectbox("Convenção de sinal da fonte", [1, -1], format_func=lambda x: "Débito positivo (como no arquivo)" if x == 1 else "Inverter sinal (×−1)", key=f"s_{f}",
                                   index=0 if db.cfg_get(f"sinal_{f}", 1) == 1 else 1)
            dec = c[1].selectbox("Separador decimal", ["auto", ",", "."], key=f"d_{f}")
            exc = c[2].checkbox("Excluir linhas inválidas", key=f"x_{f}")
            nome_m = c[3].text_input("Salvar mapeamento como", key=f"nm_{f}")
            if nome_m and st.button("Salvar modelo", key=f"sm_{f}"): db.salvar_modelo(f, nome_m, mapa, usuario); st.success("Modelo salvo.")
            if st.button("Validar e normalizar", key=f"v_{f}", type="primary"):
                ss.preparados[f] = servico.preparar(f, a["nome"], a["conteudo"], df, mapa, fator, dec, exc)
            p = ss.preparados.get(f)
            if p:
                if p["bloqueado"]: st.error("Há erros que impedem o processamento. Corrija o mapeamento, o formato decimal ou exclua as linhas inválidas.")
                else: st.success(f"{len(p['reg'])} registros normalizados e prontos.")
                if p["problemas"]: st.dataframe(pd.DataFrame(p["problemas"]).drop(columns="linhas"), use_container_width=True, hide_index=True)
                if len(p["log"]): 
                    with st.expander(f"Log de transformações ({len(p['log'])})"): st.dataframe(p["log"], use_container_width=True, hide_index=True)
    st.divider()
    ok = {f: p for f, p in ss.preparados.items() if not p["bloqueado"]}
    st.write("Fontes prontas:", ", ".join(NF[f] for f in ok) or "nenhuma")
    if st.button("Processar conciliação", type="primary", disabled=not ok or len(ok) != len(ss.preparados)):
        try:
            ss.resultado, ss.run_id = servico.executar(db, usuario, ok)
            st.success(f"Processamento #{ss.run_id} concluído: {ss.resultado['resumo']['divergencias']} divergência(s). Veja Dashboard e Divergências.")
        except ValueError as e: st.error(str(e))


# ───────────────────────────── Conciliação
def conciliacao():
    if ss.resultado is None:
        vazio("Execute um processamento em **Importação de arquivos** para ver a conciliação lado a lado."); return
    r = ss.resultado
    st.caption(f"Processamento #{ss.run_id} · Fórmula: diferença = A − B por par de fontes; 'Não comparável' quando uma fonte não tem dado (ausência ≠ zero).")
    a, b, c = st.tabs(["Por documento", "Por saldo/conta", "Contas sem mapeamento"])
    with a:
        d = r["doc"]; s = st.multiselect("Situação", sorted(d.status_conc.unique()) if len(d) else [], key="fs")
        d = d[d.status_conc.isin(s)] if s else d
        tabela(d, "cd", [x for x in ["chave", "tributo", "periodo", "valor_SAP", "valor_TAXONE", "valor_AA", "dif_SAP_TAXONE", "dif_SAP_AA", "dif_TAXONE_AA", "status_conc", "categorias"] if x in d]); st.download_button("CSV", exportacao.csv(d), "conciliacao_documentos.csv")
    with b:
        if r["saldo"].empty: vazio("Sem contas mapeadas e aprovadas para conciliar saldo. Cadastre e aprove o De-para.")
        else: tabela(r["saldo"], "cs", list(r["saldo"].columns))
    with c:
        if r["sem_mapeamento"].empty: st.success("Todas as contas têm mapeamento aprovado e vigente.")
        else: st.dataframe(r["sem_mapeamento"], hide_index=True, use_container_width=True)


# ───────────────────────────── Divergências / Diagnóstico
def divergencias(grupo=None, tributos=None):
    d = divs()
    if d.empty: vazio("Nenhuma divergência registrada. Processe uma conciliação em **Importação de arquivos**."); return
    if grupo: d = d[d.grupo == grupo]
    if tributos: d = d[d.tributo.isin(tributos)]
    c = st.columns(5)
    for i, (lab, col) in enumerate([("Status", "status"), ("Responsável", "responsavel"), ("Prioridade", "prioridade"), ("Tributo", "tributo"), ("Causa", "causa_status")]):
        o = c[i].multiselect(lab, sorted(d[col].dropna().unique()), key=f"f{col}{grupo}"); d = d[d[col].isin(o)] if o else d
    esp = st.radio("Visão", ["Todas", "Novas", "Pendentes", "Vencidas", "Recorrentes", "Resolvidas"], horizontal=True, key=f"v{grupo}")
    ab = ~d.status.isin(["Resolvida", "Encerrada"])
    d = {"Todas": d, "Novas": d[d.status == "Nova"], "Pendentes": d[ab], "Vencidas": d[ab & d.prazo.notna() & (d.prazo < str(date.today()))],
         "Recorrentes": d[d.reincidencias > 0], "Resolvidas": d[~ab]}[esp]
    d = tabela(d, f"dv{grupo}", ["id", "nivel", "tributo", "periodo", "chave", "cats", "valor_dif", "causa_status", "status", "responsavel", "prioridade", "prazo"])
    if len(d):
        sel = st.selectbox("Abrir diagnóstico", d.id.tolist(), key=f"sel{grupo}"); st.button("Abrir diagnóstico detalhado", on_click=ir, args=(sel,), key=f"ab{grupo}")


def origem(run_id, reg_id):
    c = db.carregar_run(run_id)
    for df in c["registros"].values():
        m = df[df.registro_id == reg_id]
        if len(m): return json.loads(m.dados_originais.iloc[0])
    return {}


def diagnostico():
    d = divs()
    if d.empty: vazio("Sem divergências para diagnosticar."); return
    ids = d.id.tolist(); cur = ss.div_sel if ss.div_sel in ids else ids[0]
    did = st.selectbox("Divergência", ids, index=ids.index(cur)); ss.div_sel = did
    r = gestao.obter(db, did); det = json.loads(r["detalhe"]); ident = det["identificacao"]
    st.subheader(f"{did} — {r['tributo']} — {r['chave']}")
    st.caption(f"Status: **{r['status']}** · Causa: **{r['causa_status']}** · Identificada em {r['data_ident']} · Processamento #{r['ultimo_run']}" + (f" · reincidente ({r['reincidencias']}x)" if r["reincidencias"] else ""))
    t = st.tabs(["A. Identificação", "B. Valores", "C. Conta", "D. Documento/lançamento", "E. Regra", "F. Diagnóstico", "G. Evidências e tratamento"])
    with t[0]:
        st.json({"Tributo": ident["tributo"], "Períodos": ident["periodos"], "Empresa": ident["empresa"], "Estabelecimento": ident["estabelecimento"], "Contas": ident["contas"], "Chave/Documento": f"{ident['chave']} ({ident['tipo_chave']})", "Nível": r["nivel"]})
    with t[1]:
        cp = det["comparacao"]
        st.dataframe(pd.DataFrame([dict(Fonte=k, Valor="— (sem registro/valor)" if v is None else brl(v), Registro="Presente" if cp["presenca"][k] else "Ausente") for k, v in cp["valores"].items()]), hide_index=True)
        st.write("**Diferenças e fórmulas**"); st.dataframe(pd.DataFrame(cp["pares"])[["par", "formula", "status"]] if cp["pares"] else pd.DataFrame({"Info": ["Sem par de fontes comparável."]}), hide_index=True, use_container_width=True)
        st.caption(f"Fontes disponíveis neste processamento: {', '.join(cp['fontes_disponiveis'])}. Fonte ausente nunca é tratada como zero.")
    with t[2]:
        cs = det["contas"]; linhas = [dict(Fonte=NF.get(f, f), **x) for f, l in cs.items() for x in l] if isinstance(cs, dict) else cs
        if linhas: st.dataframe(pd.DataFrame(linhas).drop(columns=["ids", "ref"], errors="ignore").rename(columns={"conta": "Conta", "status": "Situação do mapeamento", "descricao": "Descrição", "regra": "Regra de mapeamento", "vigencia": "Vigência", "aprovacao": "Aprovação"}), hide_index=True, use_container_width=True)
        st.caption("Situações: OK · SEM_MAPEAMENTO · NAO_APROVADO · FORA_VIGENCIA · AMBIGUO. Só 'OK' (aprovado e vigente) entra na conciliação por conta.")
    with t[3]:
        regs = det["registros"]; regs = regs if isinstance(regs, dict) else {}
        for f, l in regs.items():
            if not l: st.write(f"**{NF.get(f, f)}**: sem registros correspondentes."); continue
            st.write(f"**{NF.get(f, f)}**"); st.dataframe(pd.DataFrame(l), hide_index=True, use_container_width=True)
            rid = st.selectbox("Ver dados originais do arquivo", [x["registro_id"] for x in l], key=f"o_{f}_{did}")
            with st.expander(f"Linha de origem {rid}"): st.json(origem(r["ultimo_run"], rid))
    with t[4]:
        g = det["regra"]; st.json({"Regra": f"{g['id']} v{g['versao']} — {g.get('nome')}", "Vigência": g["vigencia"], "Fórmula": g["formula"], "Tolerância": g["tolerancia"], "Esperado": g["esperado"], "Observado": g["observado"], "Diferença": g["diferenca"]})
    with t[5]:
        st.write("**Categorias:** " + "; ".join(det["categorias"])); st.info(det["mensagem"])
        for h in det["hipoteses"]: st.write(f"• **[{h['tipo']}]** {h['texto']}  \n  _Evidência:_ {h['evidencia']}")
        st.write("**Verificações recomendadas**"); [st.write(f"- {v}") for v in det["verificacoes"]]
    with t[6]:
        c1, c2 = st.columns(2)
        with c1, st.form(f"trat{did}"):
            st.write("**Tratamento**"); resp = st.text_input("Responsável", r["responsavel"] or ""); pr = st.selectbox("Prioridade", gestao.PRIORIDADES, index=gestao.PRIORIDADES.index(r["prioridade"] or "Média"))
            pz = st.date_input("Prazo", value=date.fromisoformat(r["prazo"]) if r["prazo"] else None); stt = st.selectbox("Status", gestao.STATUS, index=gestao.STATUS.index(r["status"])); pv = st.text_input("Providência recomendada", r["providencia"] or "")
            if st.form_submit_button("Salvar tratamento", type="primary"):
                try: gestao.atualizar(db, did, usuario, responsavel=resp or None, prioridade=pr, prazo=str(pz) if pz else None, status=stt, providencia=pv or None); st.success("Atualizado."); st.rerun()
                except ValueError as e: st.error(str(e))
        with c2, st.form(f"causa{did}"):
            st.write("**Confirmar causa** (exige evidência e justificativa)"); ca = st.text_area("Causa confirmada", r["causa"] or ""); ju = st.text_area("Justificativa", r["justificativa"] or "")
            if st.form_submit_button("Confirmar causa"):
                try: gestao.confirmar_causa(db, did, usuario, ca, ju); st.success("Causa confirmada e registrada."); st.rerun()
                except ValueError as e: st.error(str(e))
        cm = st.text_input("Novo comentário", key=f"cm{did}")
        if st.button("Comentar", key=f"bc{did}"):
            try: gestao.comentar(db, did, usuario, cm); st.rerun()
            except ValueError as e: st.error(str(e))
        st.write("**Comentários**"); st.dataframe(db.q("SELECT ts,usuario,texto FROM comentarios WHERE div_id=? ORDER BY ts", (did,)), hide_index=True, use_container_width=True)
        st.write("**Histórico completo**"); st.dataframe(db.q("SELECT ts,usuario,acao,detalhe FROM historico WHERE ref=? ORDER BY ts", (did,)), hide_index=True, use_container_width=True)


# ───────────────────────────── De-para, Regras
def depara():
    dp = db.depara()
    for a in validar_cadastro(dp) if len(dp) else []: st.warning(f"{a['tipo']} — {a['fonte']} {a['conta']} (ids {a['ids']})")
    if dp.empty: vazio("Cadastro vazio. Adicione contas abaixo ou importe um Excel.")
    else: st.dataframe(dp, hide_index=True, use_container_width=True); st.download_button("Exportar de-para (Excel)", demo_data.para_xlsx(dp), "depara.xlsx")
    up = st.file_uploader("Importar de-para (Excel)", type=["xlsx"])
    if up and st.button("Importar linhas como 'Pendente'"):
        n = 0
        for r in pd.read_excel(up, dtype=str).to_dict("records"): r["status"] = "Pendente"; r.pop("id", None); db.depara_salvar(r, usuario, "Importação Excel"); n += 1
        st.success(f"{n} linha(s) importada(s) como Pendente — aprovação é etapa separada."); st.rerun()
    with st.form("novo"):
        st.write("**Novo mapeamento**"); c = st.columns(4); v = {}
        for i, k in enumerate(["conta_sap", "conta_taxone", "conta_aa", "descricao", "tributo", "empresa", "estabelecimento", "categoria", "natureza", "regra_sinal", "criterio", "vig_ini", "vig_fim", "justificativa"]): v[k] = c[i % 4].text_input(k)
        if st.form_submit_button("Cadastrar (status Pendente)", type="primary"):
            try: db.depara_salvar(dict(v, status="Pendente"), usuario); st.success("Cadastrado."); st.rerun()
            except ValueError as e: st.error(str(e))
    if len(dp):
        with st.form("alt"):
            st.write("**Alterar status / aprovar** (exige justificativa; quem aprova fica registrado)")
            i = st.selectbox("Mapeamento #", dp.id.tolist()); s = st.selectbox("Novo status", ["Pendente", "Em análise", "Aprovado", "Inativo"]); j = st.text_input("Justificativa")
            if st.form_submit_button("Salvar alteração"):
                try: db.depara_atualizar(int(i), dict(status=s), usuario, j); st.success("Alterado."); st.rerun()
                except ValueError as e: st.error(str(e))
        st.write("**Histórico de alterações**"); st.dataframe(db.q("SELECT ts,usuario,ref,acao,detalhe FROM historico WHERE entidade='depara' ORDER BY ts DESC"), hide_index=True, use_container_width=True)


def regras_pg():
    st.dataframe(db.q("SELECT id,versao,nome,tributo,tipo,formula,tolerancia,vig_ini,vig_fim,status,resp_criacao,resp_aprov,justificativa,criado_em FROM regras ORDER BY id,versao"), hide_index=True, use_container_width=True)
    st.caption("Cada processamento grava um snapshot das regras usadas; alterações criam nova versão e exigem aprovação por outra pessoa.")
    with st.form("rg"):
        c = st.columns(4); i = c[0].text_input("Identificador (nova versão se já existir)", "REG-DOC-001"); n = c[1].text_input("Nome"); tp = c[2].selectbox("Tipo", ["documento", "saldo"]); tr = c[3].text_input("Tributo ('*' = todos)", "*")
        tol = st.number_input("Tolerância (R$)", 0.0, 1e9, 0.01, 0.01); fo = st.text_input("Fórmula/critério", "dif = valor_A − valor_B; diverge se |dif| > tolerância"); ju = st.text_input("Justificativa")
        if st.form_submit_button("Criar nova versão (pendente de aprovação)"):
            try: st.success(f"Versão {rg.salvar_regra(db, dict(id=i, nome=n or i, tipo=tp, tributo=tr, tolerancia=tol, formula=fo, justificativa=ju), usuario)} criada."); st.rerun()
            except ValueError as e: st.error(str(e))
    pend = db.q("SELECT id,versao FROM regras WHERE status='Pendente'")
    if len(pend):
        s = st.selectbox("Aprovar", [f"{r.id} v{r.versao}" for r in pend.itertuples()])
        if st.button("Aprovar versão"):
            try: i, v = s.split(" v"); rg.aprovar_regra(db, i, int(v), usuario); st.success("Aprovada."); st.rerun()
            except ValueError as e: st.error(str(e))


def tributos(grupo):
    nome = "diretos" if grupo == "Direto" else "indiretos"
    lista = ["IRPJ", "CSLL"] if grupo == "Direto" else ["ICMS", "IPI", "PIS", "COFINS", "ISS", "CBS", "IBS"]
    st.write(f"Tributos {nome} de referência: {', '.join(lista)} (a lista é configurável em Administração).")
    divergencias(grupo=grupo)
    st.info("Regras específicas por tributo/regime/período são adicionadas em **Regras fiscais** (tipo, tributo e tolerância). O MVP não presume critérios de apuração; "
            + ("memórias de cálculo, adições/exclusões e provisões dependem de relatórios de exemplo anonimizados." if grupo == "Direto" else "a elegibilidade de crédito depende de critérios validados pelo Fiscal."))


def reforma():
    cfg = db.cfg_get("reforma", dict(cbs_inicio="", ibs_inicio="", observacao=""))
    with st.form("ref"):
        c = st.columns(3); a = c[0].text_input("Início de vigência CBS (AAAA-MM)", cfg["cbs_inicio"]); b = c[1].text_input("Início de vigência IBS (AAAA-MM)", cfg["ibs_inicio"]); o = c[2].text_input("Observação / fonte oficial", cfg["observacao"])
        if st.form_submit_button("Salvar configuração"): db.cfg_set("reforma", dict(cbs_inicio=a, ibs_inicio=b, observacao=o), usuario); st.success("Salvo.")
    st.info("A apuração assistida é importada por arquivo. Não há integração com APIs governamentais; qualquer integração futura exige documentação oficial, credenciais autorizadas e validação de TI.")
    divergencias(tributos=["CBS", "IBS"])


def relatorios():
    runs = db.q("SELECT id,ts FROM runs ORDER BY id DESC")
    if runs.empty: vazio("Sem processamentos. Execute uma conciliação para gerar relatórios."); return
    rid = st.selectbox("Processamento", runs.id.tolist(), format_func=lambda i: f"#{i} — {runs[runs.id == i].ts.iloc[0]}")
    res, igual = servico.reexecutar(db, rid)
    st.caption("Resultado reproduzido com dados, de-para e regras do processamento: " + ("**idêntico ao original**." if igual else "**DIFERENTE do original — investigar**."))
    st.download_button("Baixar relatório Excel completo", exportacao.excel(db, res, rid), f"triaxis_processamento_{rid}.xlsx", type="primary")
    d = divs(); st.download_button("Divergências (CSV)", exportacao.csv(d.drop(columns=["detalhe"])) if len(d) else b"", "divergencias.csv")


def historico():
    r = db.q("SELECT id,ts,usuario,arquivos,hash_resultado,resumo FROM runs ORDER BY id DESC")
    if r.empty: vazio("Nenhum processamento realizado."); return
    st.dataframe(r, hide_index=True, use_container_width=True)
    st.write("**Trilha de auditoria**"); tabela(db.q("SELECT * FROM historico ORDER BY ts DESC"), "hist", ["ts", "usuario", "entidade", "ref", "acao", "detalhe"])


def admin():
    st.write("**Convenção de sinal por fonte** (usada como padrão na importação)")
    c = st.columns(3)
    for i, f in enumerate(FONTES):
        v = c[i].selectbox(NF[f], [1, -1], index=0 if db.cfg_get(f"sinal_{f}", 1) == 1 else 1, format_func=lambda x: "Como no arquivo" if x == 1 else "Inverter (×−1)", key=f"ad_{f}")
        if v != db.cfg_get(f"sinal_{f}", 1): db.cfg_set(f"sinal_{f}", v, usuario)
    t = st.text_input("Tributos diretos (separados por vírgula)", ", ".join(sorted(rg.DIRETOS)))
    if st.button("Salvar lista de tributos diretos"): db.cfg_set("tributos_diretos", [x.strip().upper() for x in t.split(",") if x.strip()], usuario); st.success("Salvo."); st.rerun()
    st.warning("Autenticação corporativa, perfis e segregação por empresa **não estão implementados** neste protótipo local: o campo 'Usuário' apenas identifica quem registra cada ação. "
               "Para implantação multiusuário, integrar autenticação autorizada e banco corporativo (ver README).")


{"Dashboard": dashboard, "Importação de arquivos": importacao, "Conciliação fiscal": conciliacao, "Divergências": divergencias, "Diagnóstico detalhado": diagnostico,
 "De-para de contas": depara, "Regras fiscais": regras_pg, "Tributos diretos": lambda: tributos("Direto"), "Tributos indiretos": lambda: tributos("Indireto"),
 "Reforma Tributária": reforma, "Relatórios": relatorios, "Histórico de processamentos": historico, "Administração e configurações": admin}[pagina]()
