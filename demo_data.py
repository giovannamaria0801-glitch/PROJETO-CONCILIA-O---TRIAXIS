"""Dados 100% FICTÍCIOS para demonstração. Não representam resultados reais da LANXESS."""
import io
import pandas as pd


def ch(n): return f"3526{n:040d}"


def gerar():
    A = lambda *a: a
    sap = [  # Empresa, Estab, Período, Chave, NF, Doc contábil, Item, Conta, Tributo, Base, Alíq, Valor, Data lançamento
        A("1000", "0001", "2026-03", ch(12345), "NF-12345", "5000001", "1", "CBS_RECUPERAR", "CBS", "100000,00", "10", "10.000,00", "15/03/2026"),
        A("1000", "0001", "2026-03", ch(20001), "NF-20001", "5000002", "1", "ICMS_RECUPERAR", "ICMS", "50000,00", "12", "6.000,00", "16/03/2026"),
        A("1000", "0001", "2026-03", ch(20002), "NF-20002", "5000003", "1", "ICMS_RECUPERAR", "ICMS", "20000,00", "12", "2.400,00", "17/03/2026"),
        A("1000", "0001", "2026-03", ch(20003), "NF-20003", "5000004", "1", "ICMS_RECUPERAR", "ICMS", "", "", "800,00", "18/03/2026"),
        A("1000", "0001", "2026-03", ch(20004), "NF-20004", "5000005", "1", "ICMS_RECUPERAR", "ICMS", "", "", "300,00", "19/03/2026"),
        A("1000", "0001", "2026-03", ch(20004), "NF-20004", "5000005", "1", "ICMS_RECUPERAR", "ICMS", "", "", "300,00", "19/03/2026"),
        A("1000", "0001", "2026-03", ch(20005), "NF-20005", "5000006", "1", "ICMS_RECUPERAR", "ICMS", "", "", "1.500,00", "30/03/2026"),
        A("1000", "0001", "2026-03", ch(20006), "NF-20006", "5000007", "1", "ICMS_NOVA", "ICMS", "", "", "700,00", "20/03/2026"),
        A("1000", "0001", "2026-03", ch(20007), "NF-20007", "5000008", "1", "ICMS_RECUPERAR", "ICMS", "", "", "0,00", "21/03/2026"),
        A("1000", "0001", "2026-03", "", "", "", "", "ICMS_RECUPERAR", "ICMS", "", "", "123,45", "22/03/2026"),
    ]
    tax = [  # Empresa, Filial, Competência, Chave NFe, NF, Conta TaxOne, Imposto, Base, Alíq, Valor Imposto, Data emissão
        A("1000", "0001", "03/2026", ch(12345), "NF-12345", "TX_CBS_REC", "CBS", "95000,00", "10", "9.500,00", "2026-03-14"),
        A("1000", "0001", "03/2026", ch(20001), "NF-20001", "TX_ICMS_REC", "ICMS", "50000,00", "12", "6.000,00", "2026-03-15"),
        A("1000", "0001", "03/2026", ch(20003), "NF-20003", "TX_ICMS_REC", "ICMS", "", "", "-800,00", "2026-03-17"),
        A("1000", "0001", "03/2026", ch(20004), "NF-20004", "TX_ICMS_REC", "ICMS", "", "", "300,00", "2026-03-18"),
        A("1000", "0001", "04/2026", ch(20005), "NF-20005", "TX_ICMS_REC", "ICMS", "", "", "1.500,00", "2026-04-01"),
        A("1000", "0001", "03/2026", ch(20006), "NF-20006", "TX_ICMS_REC", "ICMS", "", "", "700,00", "2026-03-19"),
        A("1000", "0001", "03/2026", ch(20007), "NF-20007", "TX_ICMS_REC", "ICMS", "", "", "", "2026-03-20"),
    ]
    aa = [  # Empresa, Período, Chave, NF, Conta AA, Tributo, Base, Alíq, Valor
        A("1000", "2026-03", ch(12345), "NF-12345", "AA_CBS_REC", "CBS", "95000,00", "10", "9.500,00"),
        A("1000", "2026-03", ch(20001), "NF-20001", "AA_ICMS_REC", "ICMS", "50000,00", "12", "6.000,00"),
        A("1000", "2026-03", ch(20002), "NF-20002", "AA_ICMS_REC", "ICMS", "20000,00", "12", "2.400,00"),
        A("1000", "2026-03", ch(20007), "NF-20007", "AA_ICMS_REC", "ICMS", "", "", "0,00"),
    ]
    dfs = dict(
        SAP=pd.DataFrame(sap, columns=["Empresa", "Estabelecimento", "Período", "Chave de Acesso", "Número NF", "Documento Contábil", "Item", "Conta Contábil", "Tributo", "Base de Cálculo", "Alíquota", "Valor", "Data Lançamento"]),
        TAXONE=pd.DataFrame(tax, columns=["Empresa", "Filial", "Competência", "Chave NFe", "NF", "Conta TaxOne", "Imposto", "Base de Cálculo", "Alíquota", "Valor Imposto", "Data Emissão"]),
        AA=pd.DataFrame(aa, columns=["Empresa", "Período", "Chave de Acesso", "Número NF", "Conta", "Tributo", "Base", "Alíquota", "Valor"]))
    depara = pd.DataFrame([
        dict(conta_sap="CBS_RECUPERAR", conta_taxone="TX_CBS_REC", conta_aa="AA_CBS_REC", descricao="CBS a recuperar", tributo="CBS", empresa="1000", categoria="Ativo", natureza="Devedora", vig_ini="2026-01-01", status="Aprovado", resp_cadastro="Ana Lima", resp_aprov="Carlos Dias", justificativa="Carga demonstrativa"),
        dict(conta_sap="ICMS_RECUPERAR", conta_taxone="TX_ICMS_REC", conta_aa="AA_ICMS_REC", descricao="ICMS a recuperar", tributo="ICMS", empresa="1000", categoria="Ativo", natureza="Devedora", vig_ini="2026-01-01", status="Aprovado", resp_cadastro="Ana Lima", resp_aprov="Carlos Dias", justificativa="Carga demonstrativa"),
        dict(conta_sap="ICMS_NOVA", conta_taxone="TX_ICMS_REC", conta_aa="", descricao="ICMS nova conta (pendente)", tributo="ICMS", empresa="1000", categoria="Ativo", natureza="Devedora", vig_ini="2026-01-01", status="Pendente", resp_cadastro="Ana Lima", justificativa="Aguardando validação"),
    ])
    return dfs, depara


def para_xlsx(df):
    b = io.BytesIO(); df.to_excel(b, index=False); return b.getvalue()


def gravar(pasta="demo"):
    dfs, dp = gerar()
    nomes = dict(SAP="sap_demo.xlsx", TAXONE="taxone_demo.xlsx", AA="apuracao_assistida_demo.xlsx")
    for f, df in dfs.items(): open(f"{pasta}/{nomes[f]}", "wb").write(para_xlsx(df.astype(str).replace("nan", "")))
    open(f"{pasta}/depara_demo.xlsx", "wb").write(para_xlsx(dp))


if __name__ == "__main__":
    gravar()
