import io, json, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pandas as pd
from triaxis import normalizacao as nz, demo_data, servico, gestao, regras, exportacao
from triaxis.db import Banco
from triaxis.importacao import automap, normalizar
from triaxis.conciliacao import conciliar
from triaxis.depara import resolver


def prep(db=None, depara=True):
    db = db or Banco(":memory:"); regras.garantir_padrao(db)
    dfs, dp = demo_data.gerar()
    if depara:
        for r in dp.to_dict("records"): db.depara_salvar(r, "teste")
    pp = {}
    for f, df in dfs.items():
        raw = demo_data.para_xlsx(df)
        pp[f] = servico.preparar(f, f"{f}.xlsx", raw, df, automap(list(df.columns)))
    return db, pp


def por_chave(res, chave, nivel="documento"):
    return [d for d in res["divergencias"] if d["chave"] == chave and d["nivel"] == nivel]


class Normalizacao(unittest.TestCase):
    def test_valores(self):
        self.assertEqual(nz.parse_valor("1.234,56"), 1234.56); self.assertEqual(nz.parse_valor("1,234.56"), 1234.56)
        self.assertEqual(nz.parse_valor("(100,00)"), -100.0); self.assertEqual(nz.parse_valor("R$ 10.000,00"), 10000.0)
        self.assertEqual(nz.parse_valor("100,00-"), -100.0); self.assertIsNone(nz.parse_valor("")); self.assertEqual(nz.parse_valor("0,00"), 0.0)
        with self.assertRaises(ValueError): nz.parse_valor("abc")

    def test_datas_periodos_ident(self):
        self.assertEqual(str(nz.parse_data("15/03/2026")), "2026-03-15"); self.assertEqual(str(nz.parse_data("20260315")), "2026-03-15")
        self.assertEqual(nz.parse_periodo("03/2026"), "2026-03"); self.assertEqual(nz.parse_periodo("202603"), "2026-03")
        with self.assertRaises(ValueError): nz.parse_data("31/02/2026")
        self.assertEqual(nz.ident(" 00123 abc "), "00123 ABC")  # zeros preservados

    def test_original_preservado_e_log(self):
        df = pd.DataFrame({"Conta": ["  0012x "], "Valor": ["1.000,50"], "Período": ["03/2026"]})
        reg, log, prob = normalizar(df, automap(list(df.columns)), "SAP", "a.csv")
        self.assertEqual(reg.conta[0], "0012X"); self.assertEqual(reg.valor[0], 1000.5)
        self.assertEqual(json.loads(reg.dados_originais[0])["Conta"], "  0012x ")  # valor original intacto
        self.assertTrue((log.campo == "conta").any() and (log.valor_original == "  0012x ").any())

    def test_sinal_configuravel(self):
        df = pd.DataFrame({"Conta": ["A"], "Valor": ["100,00"]})
        reg, _, _ = normalizar(df, automap(list(df.columns)), "SAP", "a", fator_sinal=-1)
        self.assertEqual(reg.valor[0], -100.0); self.assertEqual(reg.valor_original[0], 100.0)

    def test_validacoes(self):
        df = pd.DataFrame({"Conta": ["A", "B"], "Valor": ["xx", "1,00"]})
        _, _, prob = normalizar(df, automap(list(df.columns)), "SAP", "a")
        self.assertTrue(any(p["nivel"] == "erro" for p in prob))
        _, _, prob = normalizar(df, {"conta": "Conta"}, "SAP", "a")
        self.assertTrue(any(p["tipo"] == "Colunas obrigatórias" for p in prob))


class Conciliacao(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db, cls.pp = prep(); cls.res, cls.rid = servico.executar(cls.db, "analista", cls.pp)

    def test_exemplo_nf12345(self):
        d = por_chave(self.res, demo_data.ch(12345))[0]
        pares = {p["par"]: p for p in d["detalhe"]["comparacao"]["pares"]}
        self.assertEqual(pares["SAP × TaxOne"]["dif"], 500.0); self.assertEqual(pares["SAP × Apuração assistida"]["dif"], 500.0)
        self.assertEqual(pares["TaxOne × Apuração assistida"]["dif"], 0.0)
        self.assertIn("10.000,00 − 9.500,00 = 500,00", pares["SAP × TaxOne"]["formula"])
        self.assertIn("Diferença de valor", d["categorias"])
        self.assertNotEqual(d["causa_status"], "confirmada")
        self.assertTrue(all(h["tipo"] == "hipótese" for h in d["detalhe"]["hipoteses"]))
        regs = d["detalhe"]["registros"]["SAP"][0]; self.assertEqual(regs["linha_origem"], 2)

    def test_conciliado(self):
        doc = self.res["doc"]; self.assertEqual(doc[doc.chave == demo_data.ch(20001)].status_conc.iloc[0], "Conciliado")
        self.assertEqual(por_chave(self.res, demo_data.ch(20001)), [])

    def test_ausente_nao_conciliado(self):
        d = por_chave(self.res, demo_data.ch(20002))[0]
        self.assertIn("Documento ausente", d["categorias"]); self.assertEqual(self.res["doc"].query("chave==@demo_data.ch(20002)").status_conc.iloc[0], "Divergente")

    def test_ausente_difere_de_zero(self):
        d = por_chave(self.res, demo_data.ch(20007))[0]  # SAP=0 e AA=0 reais; TaxOne presente mas sem valor
        c = d["detalhe"]["comparacao"]
        self.assertEqual(c["valores"]["SAP"], 0.0); self.assertIsNone(c["valores"]["TaxOne"])
        self.assertIn("Dados insuficientes", d["categorias"])
        pares = {p["par"]: p for p in c["pares"]}; self.assertEqual(pares["SAP × Apuração assistida"]["status"], "Igual")
        self.assertEqual(pares["SAP × TaxOne"]["status"], "Não comparável")

    def test_sinal_duplicidade_periodo(self):
        self.assertIn("Convenção de sinal divergente", por_chave(self.res, demo_data.ch(20003))[0]["categorias"])
        self.assertIn("Possível duplicidade", por_chave(self.res, demo_data.ch(20004))[0]["categorias"])
        self.assertIn("Divergência de período", por_chave(self.res, demo_data.ch(20005))[0]["categorias"])

    def test_conta_sem_mapeamento(self):
        self.assertIn("ICMS_NOVA", set(self.res["sem_mapeamento"].conta))  # pendente != aprovado
        self.assertTrue(por_chave(self.res, "ICMS_NOVA", "conta"))

    def test_sem_chave_nao_conciliado(self):
        sc = [d for d in self.res["divergencias"] if "Registro não comparável" in d["categorias"]]
        self.assertEqual(len(sc), 1)

    def test_base_valor_total_e_hash(self):
        self.assertEqual(self.res["resumo"]["fontes"], ["SAP", "TaxOne", "Apuração assistida"])

    def test_ids_unicos_e_estaveis(self):
        ids = [d["id"] for d in self.res["divergencias"]]; self.assertEqual(len(ids), len(set(ids))); self.assertTrue(ids[0].startswith("DIV-"))
        res2, _ = servico.executar(self.db, "analista", self.pp)
        self.assertEqual(sorted(ids), sorted(d["id"] for d in res2["divergencias"]))  # mesma divergência, mesmo ID


class DuasFontesETolerancia(unittest.TestCase):
    def test_duas_fontes_sem_apuracao(self):
        db, pp = prep(); pp.pop("AA")
        res, _ = servico.executar(db, "u", pp)
        d = por_chave(res, demo_data.ch(12345))[0]
        self.assertEqual(len(d["detalhe"]["comparacao"]["pares"]), 1)  # só SAP × TaxOne; AA não vira zero
        self.assertNotIn("Documento ausente", d["categorias"])

    def test_tolerancia(self):
        mk = lambda v: {"SAP": pd.DataFrame(dict(registro_id=["a"], linha_origem=[2], arquivo=["x"], num_doc=["N1"], empresa=["1"], valor=[v], conta=[None], tributo=["ICMS"], periodo=["2026-03"])),
                        "TAXONE": pd.DataFrame(dict(registro_id=["b"], linha_origem=[2], arquivo=["y"], num_doc=["N1"], empresa=["1"], valor=[100.0], conta=[None], tributo=["ICMS"], periodo=["2026-03"]))}
        dp = pd.DataFrame(columns=["id", "conta_sap", "conta_taxone", "conta_aa", "status", "empresa", "vig_ini", "vig_fim"])
        r = [dict(id="R", versao=1, tipo="documento", tributo="*", tolerancia=0.01, nome="t")]
        self.assertEqual(conciliar(mk(100.005), dp, r)["doc"].status_conc.iloc[0], "Conciliado")
        self.assertEqual(conciliar(mk(100.50), dp, r)["doc"].status_conc.iloc[0], "Divergente")
        r[0]["tolerancia"] = 1.0
        self.assertEqual(conciliar(mk(100.50), dp, r)["doc"].status_conc.iloc[0], "Conciliado")


class DeParaTests(unittest.TestCase):
    def test_ambiguo_e_vigencia(self):
        dp = pd.DataFrame([dict(id=1, conta_sap="X", conta_taxone="A", conta_aa=None, empresa=None, status="Aprovado", vig_ini="2026-01-01", vig_fim=None, descricao="", resp_aprov="m"),
                           dict(id=2, conta_sap="X", conta_taxone="B", conta_aa=None, empresa=None, status="Aprovado", vig_ini="2026-01-01", vig_fim=None, descricao="", resp_aprov="m"),
                           dict(id=3, conta_sap="Y", conta_taxone="C", conta_aa=None, empresa=None, status="Aprovado", vig_ini="2026-01-01", vig_fim="2026-02-28", descricao="", resp_aprov="m")])
        self.assertEqual(resolver(dp, "SAP", "X", "1", "2026-03")["status"], "AMBIGUO")
        self.assertEqual(resolver(dp, "SAP", "Y", "1", "2026-03")["status"], "FORA_VIGENCIA")
        self.assertEqual(resolver(dp, "SAP", "Z", "1", "2026-03")["status"], "SEM_MAPEAMENTO")

    def test_aprovacao_exige_responsavel(self):
        with self.assertRaises(ValueError): Banco(":memory:").depara_salvar(dict(conta_sap="A", status="Aprovado"), "u")


class GestaoERastreabilidade(unittest.TestCase):
    def setUp(self):
        self.db, pp = prep(); self.res, self.rid = servico.executar(self.db, "ana", pp)
        self.div = por_chave(self.res, demo_data.ch(12345))[0]["id"]

    def test_causa_exige_justificativa_e_evidencia(self):
        with self.assertRaises(ValueError): gestao.confirmar_causa(self.db, self.div, "ana", "Base diferente", "")
        with self.assertRaises(ValueError): gestao.atualizar(self.db, self.div, "ana", status="Resolvida")  # sem causa confirmada
        gestao.confirmar_causa(self.db, self.div, "ana", "Base de cálculo divergente no SAP", "Conferido nos registros de origem")
        gestao.atualizar(self.db, self.div, "ana", status="Resolvida")
        with self.assertRaises(ValueError): gestao.atualizar(self.db, self.div, "ana", valor_dif=1)  # valores não editáveis
        gestao.atualizar(self.db, self.div, "chefe", status="Encerrada")
        h = self.db.q("SELECT * FROM historico WHERE ref=?", (self.div,)); self.assertGreaterEqual(len(h), 4)

    def test_reaparece_reabre(self):
        gestao.confirmar_causa(self.db, self.div, "a", "c", "j"); gestao.atualizar(self.db, self.div, "a", status="Resolvida")
        pp = prep(self.db)[1]; servico.executar(self.db, "a", pp)
        self.assertEqual(gestao.obter(self.db, self.div)["status"], "Nova")

    def test_reproducibilidade_com_regra_alterada(self):
        v = regras.salvar_regra(self.db, dict(id="REG-DOC-001", nome="x", tipo="documento", tributo="*", tolerancia=1000, justificativa="teste"), "ana")
        with self.assertRaises(ValueError): regras.aprovar_regra(self.db, "REG-DOC-001", v, "ana")  # mesmo usuário
        regras.aprovar_regra(self.db, "REG-DOC-001", v, "chefe")
        self.assertEqual(regras.regra_para(regras.regras_ativas(self.db), "documento", "CBS")["tolerancia"], 1000)
        res, igual = servico.reexecutar(self.db, self.rid)  # usa a versão original da regra
        self.assertTrue(igual)

    def test_exportacao(self):
        data = exportacao.excel(self.db, self.res, self.rid)
        x = pd.ExcelFile(io.BytesIO(data)); self.assertIn("Somente divergências", x.sheet_names)
        s = pd.read_excel(x, "Somente divergências", header=None).astype(str)
        self.assertTrue(s.apply(lambda c: c.str.contains("DIV-")).any().any()); self.assertTrue(s.apply(lambda c: c.str.contains("Regras aplicadas")).any().any())


if __name__ == "__main__":
    unittest.main()
