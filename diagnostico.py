"""Diagnóstico: categorias, hipóteses (sempre rotuladas como hipótese) e verificações. Nunca declara causa confirmada."""
from . import NOMES_FONTES as NF

PENDENTE = "Divergência identificada — causa pendente de investigação"


def brl(x):
    if x is None: return "ausente"
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def diagnosticar(d):
    """d: dict com 'categorias' e 'evid' (fatos coletados pelo motor). Retorna (hipoteses, verificacoes, causa_status, mensagem)."""
    ev, cats = d["evid"], d["categorias"]
    hip, ver = [], []
    for f in ev.get("ausentes", []):
        hip.append(dict(tipo="hipótese", texto=f"O documento pode não ter sido escriturado/importado em {NF[f]}.",
                        evidencia=f"Nenhum registro com a chave {ev['chave']} em {NF[f]} ({ev['total_regs'].get(f, 0)} registros importados dessa fonte)."))
        ver.append(f"Conferir em {NF[f]} se o documento existe e se o filtro de período/empresa do relatório o excluiu.")
    for f in ev.get("classificacao", []):
        hip.append(dict(tipo="hipótese", texto=f"Tributo/classificação diferente em {NF[f]}.", evidencia=f"Tributos por fonte: {ev['tributos']}"))
        ver.append("Validar com o Fiscal a classificação tributária do documento em cada sistema.")
    if "Convenção de sinal divergente" in cats:
        hip.append(dict(tipo="hipótese", texto="Possível convenção de sinal divergente entre fontes.", evidencia=ev["sinal"]))
        ver.append("Revisar o fator de sinal configurado para a fonte (Administração) e reprocessar.")
    if "Divergência de período" in cats:
        hip.append(dict(tipo="hipótese", texto="Documento lançado em período diferente.", evidencia=f"Períodos por fonte: {ev['periodos']}"))
        ver.append("Comparar data do documento e data de lançamento; verificar competência.")
    if "Possível duplicidade" in cats:
        hip.append(dict(tipo="hipótese", texto="Possível lançamento duplicado.", evidencia=ev["dup"]))
        ver.append("Verificar se os registros repetidos são lançamentos distintos legítimos (itens) ou duplicidade.")
    if "Diferença de base de cálculo" in cats:
        hip.append(dict(tipo="hipótese", texto="A diferença de valor pode decorrer da base de cálculo.", evidencia=ev["base"]))
        ver.append("Comparar composição da base (adições/exclusões) entre as fontes.")
    if "Regra de cálculo divergente" in cats:
        hip.append(dict(tipo="hipótese", texto="Regra/alíquota de cálculo diferente entre fontes.", evidencia=ev["regra"]))
        ver.append("Confirmar com o Fiscal a regra e a alíquota vigentes; o TRIAXIS não presume qual está correta.")
    for c in ("Conta sem mapeamento", "Mapeamento ambíguo"):
        if c in cats:
            hip.append(dict(tipo="hipótese", texto=f"{c}: a comparação por conta pode estar incompleta.", evidencia=ev["contas"]))
            ver.append("Cadastrar/aprovar a conta no De-para de contas e reprocessar.")
    if "Registro não comparável" in cats:
        ver.append("Incluir identificador comum (chave de acesso, nº do documento ou doc. contábil) no relatório de origem.")
    if "Dados insuficientes" in cats:
        ver.append("Solicitar relatório com valor preenchido para o registro.")
    if "Diferença de valor" in cats and not hip:
        faltam = [x for x in ("base", "aliquota") if x in ev.get("campos_ausentes", [])]
        ver += ["Obter base de cálculo e alíquota das fontes para decompor a diferença." if faltam else "Analisar os registros de origem linha a linha.",
                "Conferir ajustes, estornos e lançamentos manuais na conta."]
    if not hip:
        cats.append("Causa ainda não determinada") if "Causa ainda não determinada" not in cats else None
        return [], ver, "desconhecida", PENDENTE
    return hip, ver, "provável", "Hipóteses levantadas a partir dos dados; nenhuma causa foi confirmada. A confirmação depende do analista."
