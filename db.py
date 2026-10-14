"""Persistência SQLite (protótipo local). Para multiusuário, trocar por banco corporativo mantendo esta interface."""
import json, sqlite3
from datetime import datetime
import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS depara(id INTEGER PRIMARY KEY AUTOINCREMENT, conta_sap TEXT, conta_taxone TEXT, conta_aa TEXT,
 descricao TEXT, tributo TEXT, empresa TEXT, estabelecimento TEXT, categoria TEXT, natureza TEXT, regra_sinal TEXT,
 criterio TEXT, vig_ini TEXT, vig_fim TEXT, status TEXT DEFAULT 'Pendente', resp_cadastro TEXT, resp_aprov TEXT,
 justificativa TEXT, atualizado_em TEXT);
CREATE TABLE IF NOT EXISTS regras(id TEXT, versao INTEGER, nome TEXT, descricao TEXT, tributo TEXT, tipo TEXT, campos TEXT,
 formula TEXT, tolerancia REAL, vig_ini TEXT, vig_fim TEXT, status TEXT, resp_criacao TEXT, resp_aprov TEXT,
 justificativa TEXT, criado_em TEXT, PRIMARY KEY(id, versao));
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, usuario TEXT, arquivos TEXT, depara_snapshot TEXT,
 regras_snapshot TEXT, params TEXT, resumo TEXT, hash_resultado TEXT);
CREATE TABLE IF NOT EXISTS run_dados(run_id INTEGER, fonte TEXT, arquivo TEXT, sha256 TEXT, registros TEXT, log TEXT);
CREATE TABLE IF NOT EXISTS divergencias(id TEXT PRIMARY KEY, fingerprint TEXT UNIQUE, nivel TEXT, tributo TEXT, periodo TEXT,
 empresa TEXT, estabelecimento TEXT, chave TEXT, categorias TEXT, causa_status TEXT, causa TEXT, justificativa TEXT,
 status TEXT, responsavel TEXT, prioridade TEXT, prazo TEXT, providencia TEXT, data_ident TEXT, data_resolucao TEXT,
 encerrado_por TEXT, ultimo_run INTEGER, primeiro_run INTEGER, detalhe TEXT, valor_dif REAL, reincidencias INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS comentarios(div_id TEXT, ts TEXT, usuario TEXT, texto TEXT);
CREATE TABLE IF NOT EXISTS historico(ts TEXT, usuario TEXT, entidade TEXT, ref TEXT, acao TEXT, detalhe TEXT);
CREATE TABLE IF NOT EXISTS modelos_mapa(fonte TEXT, nome TEXT, mapa TEXT, PRIMARY KEY(fonte, nome));
CREATE TABLE IF NOT EXISTS config(chave TEXT PRIMARY KEY, valor TEXT);
"""
DEPARA_COLS = ["conta_sap", "conta_taxone", "conta_aa", "descricao", "tributo", "empresa", "estabelecimento", "categoria",
               "natureza", "regra_sinal", "criterio", "vig_ini", "vig_fim", "status", "resp_cadastro", "resp_aprov", "justificativa"]


def agora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class Banco:
    def __init__(self, caminho="dados/triaxis.db"):
        self.con = sqlite3.connect(caminho, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        self.con.commit()

    def x(self, sql, p=()):
        cur = self.con.execute(sql, p); self.con.commit(); return cur

    def q(self, sql, p=()):
        return pd.read_sql_query(sql, self.con, params=p)

    def hist(self, usuario, entidade, ref, acao, detalhe=""):
        self.x("INSERT INTO historico VALUES(?,?,?,?,?,?)", (agora(), usuario, entidade, str(ref), acao, detalhe))

    # ---- configuração
    def cfg_get(self, chave, padrao=None):
        r = self.con.execute("SELECT valor FROM config WHERE chave=?", (chave,)).fetchone()
        return json.loads(r[0]) if r else padrao

    def cfg_set(self, chave, valor, usuario="sistema"):
        self.x("INSERT OR REPLACE INTO config VALUES(?,?)", (chave, json.dumps(valor)))
        self.hist(usuario, "config", chave, "alterada", json.dumps(valor)[:500])

    # ---- modelos de mapeamento
    def salvar_modelo(self, fonte, nome, mapa, usuario="sistema"):
        self.x("INSERT OR REPLACE INTO modelos_mapa VALUES(?,?,?)", (fonte, nome, json.dumps(mapa)))
        self.hist(usuario, "modelo_mapa", f"{fonte}/{nome}", "salvo")

    def modelos(self, fonte):
        return {r["nome"]: json.loads(r["mapa"]) for r in self.con.execute("SELECT * FROM modelos_mapa WHERE fonte=?", (fonte,))}

    # ---- de-para
    def depara(self):
        return self.q("SELECT * FROM depara ORDER BY id")

    def depara_salvar(self, reg: dict, usuario, justificativa=""):
        reg = {k: (None if (v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "") else str(v).strip()) for k, v in reg.items() if k in DEPARA_COLS}
        for k in ("conta_sap", "conta_taxone", "conta_aa"):
            if reg.get(k): reg[k] = reg[k].upper()
        reg.setdefault("status", "Pendente")
        if reg["status"] == "Aprovado" and not reg.get("resp_aprov"):
            raise ValueError("Mapeamento aprovado exige responsável pela aprovação.")
        reg["resp_cadastro"] = reg.get("resp_cadastro") or usuario
        reg["justificativa"] = reg.get("justificativa") or justificativa
        cols = list(reg)
        cur = self.x(f"INSERT INTO depara({','.join(cols)},atualizado_em) VALUES({','.join('?'*len(cols))},?)", [reg[c] for c in cols] + [agora()])
        self.hist(usuario, "depara", cur.lastrowid, "criado", json.dumps(reg, ensure_ascii=False))
        return cur.lastrowid

    def depara_atualizar(self, id_, campos: dict, usuario, justificativa):
        if not justificativa:
            raise ValueError("Informe a justificativa da alteração.")
        antigo = self.con.execute("SELECT * FROM depara WHERE id=?", (id_,)).fetchone()
        novo = {k: v for k, v in campos.items() if k in DEPARA_COLS}
        if novo.get("status") == "Aprovado":
            novo["resp_aprov"] = novo.get("resp_aprov") or usuario
        dif = {k: (antigo[k], v) for k, v in novo.items() if antigo[k] != v}
        if not dif:
            return
        sets = ",".join(f"{k}=?" for k in novo)
        self.x(f"UPDATE depara SET {sets}, justificativa=?, atualizado_em=? WHERE id=?", list(novo.values()) + [justificativa, agora(), id_])
        self.hist(usuario, "depara", id_, "alterado", json.dumps({"mudancas": dif, "justificativa": justificativa}, ensure_ascii=False, default=str))

    # ---- runs
    def salvar_run(self, usuario, arquivos, depara_df, regras, params, resumo, hash_res, dados):
        cur = self.x("INSERT INTO runs(ts,usuario,arquivos,depara_snapshot,regras_snapshot,params,resumo,hash_resultado) VALUES(?,?,?,?,?,?,?,?)",
                     (agora(), usuario, json.dumps(arquivos), depara_df.to_json(orient="records"), json.dumps(regras, default=str),
                      json.dumps(params), json.dumps(resumo, default=str), hash_res))
        rid = cur.lastrowid
        for fonte, (arq, sha, reg, log) in dados.items():
            self.x("INSERT INTO run_dados VALUES(?,?,?,?,?,?)", (rid, fonte, arq, sha, reg.to_json(orient="records", date_format="iso"), log.to_json(orient="records")))
        self.hist(usuario, "processamento", rid, "executado", json.dumps(resumo, default=str)[:800])
        return rid

    def carregar_run(self, rid):
        r = self.con.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
        dados = {d["fonte"]: pd.read_json(__import__("io").StringIO(d["registros"]), orient="records", dtype=False)
                 for d in self.con.execute("SELECT * FROM run_dados WHERE run_id=?", (rid,))}
        return dict(run=dict(r), registros=dados, depara=pd.read_json(__import__("io").StringIO(r["depara_snapshot"]), orient="records", dtype=False),
                    regras=json.loads(r["regras_snapshot"]), params=json.loads(r["params"]))

    # ---- divergências
    def upsert_divergencias(self, run_id, divs, usuario="sistema"):
        ano = datetime.now().year
        for d in divs:
            ex = self.con.execute("SELECT id,status FROM divergencias WHERE fingerprint=?", (d["fingerprint"],)).fetchone()
            det, cats = json.dumps(d["detalhe"], ensure_ascii=False, default=str), json.dumps(d["categorias"], ensure_ascii=False)
            if ex:
                self.x("UPDATE divergencias SET categorias=?,detalhe=?,valor_dif=?,ultimo_run=?,periodo=?,causa_status=CASE WHEN causa_status='confirmada' THEN causa_status ELSE ? END WHERE id=?",
                       (cats, det, d["valor_dif"], run_id, d["periodo"], d["causa_status"], ex["id"]))
                if ex["status"] in ("Resolvida", "Encerrada"):
                    self.x("UPDATE divergencias SET status='Nova',data_resolucao=NULL,reincidencias=reincidencias+1 WHERE id=?", (ex["id"],))
                    self.hist(usuario, "divergencia", ex["id"], "reaberta", "Divergência reapareceu em novo processamento (recorrente).")
            else:
                n = self.con.execute("SELECT COUNT(*) FROM divergencias WHERE id LIKE ?", (f"DIV-{ano}-%",)).fetchone()[0] + 1
                did = f"DIV-{ano}-{n:06d}"
                self.x("INSERT INTO divergencias(id,fingerprint,nivel,tributo,periodo,empresa,estabelecimento,chave,categorias,causa_status,status,prioridade,data_ident,ultimo_run,primeiro_run,detalhe,valor_dif,prazo) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (did, d["fingerprint"], d["nivel"], d["tributo"], d["periodo"], d["empresa"], d["estabelecimento"], d["chave"], cats,
                        d["causa_status"], "Nova", "Média", agora(), run_id, run_id, det, d["valor_dif"], None))
                self.hist(usuario, "divergencia", did, "identificada", cats)
                d["id"] = did
            if ex: d["id"] = ex["id"]
        return divs
